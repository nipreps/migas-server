# /// script
# dependencies = [
#   "asyncpg",
#   "pyarrow",
#   "python-dotenv",
# ]
# ///
"""Restore migas crumbs from a parquet archive back into PostgreSQL.

Standalone recovery tool (run via ``uv run --script``), the inverse of
``archive_crumbs.py``. Given an archive directory it reads every
``*.parquet`` beneath it and inserts the rows into ``migas.crumbs``,
preserving each row's original ``idx`` and then advancing the id sequence past
the restored maximum so future inserts do not collide.

The insert is **schema-driven**: each file's own columns are used, so archives
written under an older or newer crumbs schema both restore correctly (columns
absent from an archive take their database default; the archive never has to
match today's table exactly). Text-encoded columns are cast back to their real
types via ``COLUMN_CASTS`` — extend that map when a new typed column is added.

Parent ``projects`` are upserted from the archive; ``users`` are assumed to
still be present (they are never archived). Connection settings are read from
``DATABASE_*`` env vars (see ``async_creator``).

Example::

    uv run --script scripts/rebuild_crumbs.py exports/archive
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path

import asyncpg
import pyarrow.parquet as pq
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('rebuild_crumbs')

load_dotenv(os.getenv('MIGAS_ENV_FILE', '.env'))

# Archive columns stored as text that must be cast back to their real type on
# insert. Add an entry here when a new typed column joins the crumbs schema
# (e.g. a JSONB `params` column would map to 'jsonb').
COLUMN_CASTS = {'session_id': 'uuid', 'user_id': 'uuid', 'status': 'migas.status'}


def _insert_sql(columns: list[str]) -> str:
    """Build an INSERT for exactly the columns present in an archive file."""
    placeholders = []
    for i, col in enumerate(columns, start=1):
        cast = COLUMN_CASTS.get(col)
        placeholders.append(f'${i}::{cast}' if cast else f'${i}')
    return f'INSERT INTO migas.crumbs ({", ".join(columns)}) VALUES ({", ".join(placeholders)})'


async def async_creator():
    """Proven connection pattern for Cloud SQL Proxy."""
    return await asyncpg.connect(
        user=os.getenv('DATABASE_USER', 'postgres'),
        password=os.getenv('DATABASE_PASSWORD', 'crumbs'),
        host=os.getenv('DATABASE_HOST', 'localhost'),
        port=int(os.getenv('DATABASE_PORT', 5433)),
        database=os.getenv('DATABASE_NAME', 'migas'),
    )


async def rebuild_crumbs(archive_dir: Path):
    files = sorted(Path(archive_dir).rglob('*.parquet'))
    if not files:
        logger.info(f'No parquet files under {archive_dir}. Nothing to rebuild.')
        return

    conn = await async_creator()
    try:
        total = 0
        for path in files:
            # read the file directly so the `project=` partition dir isn't inferred
            table = pq.ParquetFile(str(path)).read()
            columns = list(table.schema.names)
            rows = table.to_pylist()
            if not rows:
                continue
            for project in {r['project'] for r in rows}:
                await conn.execute(
                    'INSERT INTO migas.projects (project) VALUES ($1) ON CONFLICT DO NOTHING',
                    project,
                )
            await conn.executemany(
                _insert_sql(columns), [tuple(r[col] for col in columns) for r in rows]
            )
            total += len(rows)
            logger.info(f'  Restored {len(rows)} crumbs from {path.name}')

        await conn.execute(
            "SELECT setval(pg_get_serial_sequence('migas.crumbs', 'idx'), "
            '(SELECT max(idx) FROM migas.crumbs))'
        )
        logger.info(f'Rebuilt {total} crumbs; idx sequence reset.')
    finally:
        await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Rebuild crumbs from a parquet archive.')
    parser.add_argument('archive_dir', help='Directory holding the parquet archive to restore')
    args = parser.parse_args()

    asyncio.run(rebuild_crumbs(Path(args.archive_dir)))
