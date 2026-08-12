# /// script
# dependencies = [
#   "asyncpg",
#   "pyarrow",
# ]
# ///
"""Self-test that the crumb archive lifecycle preserves data exactly.

Seeds test crumbs into a throwaway source database, drives the real
``archive_crumbs.py`` job to export and prune them to parquet, rebuilds them
into a second throwaway database, and checks that the rebuilt crumbs match what
was seeded (row count, idx set, and a hash of every column) and that the source
was pruned. Both throwaway databases are created from deploy/docker/init.sql and
dropped on exit, so the test needs only a Postgres server and no existing data.

Run against any Postgres (local socket by default; DATABASE_* env overrides):

    uv run --script scripts/test_archive_rebuild.py

Exits non-zero if the rebuilt data does not match, so it can gate CI.
"""

import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = REPO_ROOT / 'deploy' / 'docker' / 'init.sql'
ARCHIVE_CRUMBS = REPO_ROOT / 'scripts' / 'archive_crumbs.py'
REBUILD_CRUMBS = REPO_ROOT / 'scripts' / 'rebuild_crumbs.py'

SRC_DB = 'migas_archive_selftest_src'
DST_DB = 'migas_archive_selftest_dst'
PROJECT = 'nipreps/selftest'
N_USERS = 5
N_CRUMBS = 250

SELECT_CRUMBS = """
    SELECT idx, project, version, language, language_version, timestamp,
           session_id::text, user_id::text, status::text,
           status_desc, error_type, error_desc, is_ci
    FROM migas.crumbs {where} ORDER BY idx
"""


def _conn_env() -> dict:
    return {
        'host': os.getenv('DATABASE_HOST', '/tmp'),
        'port': int(os.getenv('DATABASE_PORT', 5432)),
        'user': os.getenv('DATABASE_USER') or os.getenv('USER', 'postgres'),
        'password': os.getenv('DATABASE_PASSWORD'),
    }


async def _connect(database):
    kw = {k: v for k, v in _conn_env().items() if v is not None}
    return await asyncpg.connect(database=database, **kw)


def _subprocess_env(database: str, archive_dir: str | None = None) -> dict:
    env = dict(os.environ)
    cfg = _conn_env()
    env['DATABASE_NAME'] = database
    env['DATABASE_HOST'] = str(cfg['host'])
    env['DATABASE_PORT'] = str(cfg['port'])
    env['DATABASE_USER'] = str(cfg['user'])
    if cfg['password'] is not None:
        env['DATABASE_PASSWORD'] = cfg['password']
    if archive_dir is not None:
        env['MIGAS_ARCHIVE_DIR'] = archive_dir
    return env


def _run_script(script: Path, args: list[str], env: dict):
    result = subprocess.run(
        ['uv', 'run', '--script', str(script), *args], env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f'{script.name} {args} failed ({result.returncode})')
    return result


def _test_rows():
    users = [uuid.uuid5(uuid.NAMESPACE_DNS, f'selftest-user-{i}') for i in range(N_USERS)]
    statuses = ['R', 'C', 'F', 'S']
    base = datetime(2125, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(N_CRUMBS):
        status = statuses[i % len(statuses)]
        rows.append(
            {
                'user_id': users[i % N_USERS],
                'session_id': uuid.uuid5(uuid.NAMESPACE_DNS, f'selftest-session-{i // 3}'),
                'timestamp': base.replace(minute=i % 60, second=i % 60),
                'status': status,
                # exercise nullable columns and the failure path
                'status_desc': None if status != 'C' else 'completed',
                'error_type': 'RuntimeError' if status == 'F' else None,
                'error_desc': 'boom' if status == 'F' else None,
                'is_ci': i % 2 == 0,
            }
        )
    return users, rows


async def _reset_db(database: str):
    admin = await _connect('postgres')
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS {database} WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE {database}')
    finally:
        await admin.close()
    conn = await _connect(database)
    try:
        await conn.execute(INIT_SQL.read_text())
    finally:
        await conn.close()


async def _seed_parents(database: str, users):
    conn = await _connect(database)
    try:
        await conn.execute(
            'INSERT INTO migas.projects (project) VALUES ($1) ON CONFLICT DO NOTHING', PROJECT
        )
        await conn.executemany(
            'INSERT INTO migas.users (user_id, user_type, platform, container) '
            "VALUES ($1, 'hash', 'Linux-x86_64', 'unknown') ON CONFLICT DO NOTHING",
            [(u,) for u in users],
        )
    finally:
        await conn.close()


async def main():
    users, rows = _test_rows()

    # 1. seed test crumbs into a fresh source DB (idx assigned by SERIAL)
    await _reset_db(SRC_DB)
    await _seed_parents(SRC_DB, users)
    src = await _connect(SRC_DB)
    try:
        await src.executemany(
            'INSERT INTO migas.crumbs (project, version, language, language_version, '
            'timestamp, session_id, user_id, status, status_desc, error_type, error_desc, '
            'is_ci) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::migas.status, $9, $10, $11, $12)',
            [
                (
                    PROJECT,
                    '1.0.0',
                    'python',
                    '3.12',
                    r['timestamp'],
                    r['session_id'],
                    r['user_id'],
                    r['status'],
                    r['status_desc'],
                    r['error_type'],
                    r['error_desc'],
                    r['is_ci'],
                )
                for r in rows
            ],
        )
        seeded = await src.fetch(SELECT_CRUMBS.format(where='WHERE project = $1'), PROJECT)
    finally:
        await src.close()
    print(f'Seeded {len(seeded)} test crumbs into {SRC_DB}')

    with tempfile.TemporaryDirectory(prefix='archive-selftest-') as tmp:
        # 2. real archiver: export + prune from the source DB
        _run_script(
            ARCHIVE_CRUMBS,
            ['--no-dry-run', '--delete', '--before', '2999-01-01'],
            _subprocess_env(SRC_DB, archive_dir=tmp),
        )

        src = await _connect(SRC_DB)
        try:
            remaining = await src.fetchval(
                'SELECT count(*) FROM migas.crumbs WHERE project = $1', PROJECT
            )
        finally:
            await src.close()

        # 3. real rebuild job: restore into a fresh destination DB whose schema
        # has moved on (a nullable column the archive predates), proving the
        # rebuild is schema-driven rather than pinned to the archive's columns.
        await _reset_db(DST_DB)
        await _seed_parents(DST_DB, users)
        dst = await _connect(DST_DB)
        try:
            await dst.execute('ALTER TABLE migas.crumbs ADD COLUMN params jsonb')
        finally:
            await dst.close()
        _run_script(REBUILD_CRUMBS, [tmp], _subprocess_env(DST_DB))

    dst = await _connect(DST_DB)
    try:
        rebuilt = await dst.fetch(SELECT_CRUMBS.format(where=''))
        params_set = await dst.fetchval(
            'SELECT count(*) FROM migas.crumbs WHERE params IS NOT NULL'
        )
    finally:
        await dst.close()

    for database in (SRC_DB, DST_DB):
        admin = await _connect('postgres')
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS {database} WITH (FORCE)')
        finally:
            await admin.close()

    def _hash(records):
        h = hashlib.sha256()
        for r in records:
            h.update(repr(tuple(r)).encode())
        return h.hexdigest()

    src_hash, dst_hash = _hash(seeded), _hash(rebuilt)
    src_idx = {r['idx'] for r in seeded}
    dst_idx = {r['idx'] for r in rebuilt}

    print('\n--- VERIFICATION ---')
    print(
        f'pruned      : source now has {remaining} crumbs  '
        f'{"OK" if remaining == 0 else "MISMATCH"}'
    )
    print(
        f'row count   : seeded={len(seeded)}  rebuilt={len(rebuilt)}  '
        f'{"OK" if len(seeded) == len(rebuilt) else "MISMATCH"}'
    )
    print(f'idx set     : {"identical" if src_idx == dst_idx else "MISMATCH"}')
    print(f'content hash: {"identical" if src_hash == dst_hash else "MISMATCH"}')
    print(
        f'schema drift: newer column defaulted for {params_set} of {len(rebuilt)} '
        f'rows  {"OK" if params_set == 0 else "MISMATCH"}'
    )

    ok = (
        remaining == 0
        and len(seeded) == len(rebuilt)
        and src_idx == dst_idx
        and src_hash == dst_hash
        and params_set == 0
    )
    print(f'\nRESULT: {"ARCHIVE ROUND-TRIP OK" if ok else "ARCHIVE ROUND-TRIP FAILED"}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
