# /// script
# dependencies = [
#   "asyncpg",
#   "pandas",
#   "pyarrow",
#   "python-dotenv",
# ]
# ///
"""Archive crumbs from PostgreSQL to cold parquet storage.

This is a standalone maintenance job (run via ``uv run --script``), not part of
the server package. It has two steps:

- **Archive** (default): export every project's crumbs older than a cutoff to
  ``$MIGAS_ARCHIVE_DIR/project=<name>/archive_<date>.parquet``. The cutoff comes
  from ``--before``; when omitted it defaults to the frozen cutoff (the latest
  crumb day minus ``FROZEN_LAG``), so recent-but-still-finalizing sessions are
  never archived early. Dry-run unless ``--no-dry-run`` is given.
- **Prune** (optional, requires ``--delete``): after a successful export, delete the archived rows
  from ``migas.crumbs``. Only ``crumbs`` is deleted from; the legacy ``projects`` and
  ``users`` tables are never archived or pruned.

The parquet layout keeps every column (uuids/enum as text, ``idx`` retained) so
the export can be restored bit-exactly. Restoring is the inverse job,
``rebuild_crumbs.py``. Connection settings are read from ``DATABASE_*`` env
vars (see ``async_creator``).

Example::

    uv run --script scripts/archive_crumbs.py --no-dry-run --delete
"""

import asyncio
import argparse
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import asyncpg
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('archive_crumbs')

# Configuration
EXPORT_DIR = Path(os.getenv('MIGAS_ARCHIVE_DIR', 'exports/archive'))
BATCH_SIZE = 5000

# Superset of the 6-day session window, so recent-but-final sessions aren't archived early.
FROZEN_LAG = timedelta(days=7)

# Portable archive layout: uuids/enum as text, timestamp UTC, idx retained so a
# rebuild is bit-exact.
PARQUET_SCHEMA = pa.schema(
    [
        ('idx', pa.int64()),
        ('project', pa.string()),
        ('version', pa.string()),
        ('language', pa.string()),
        ('language_version', pa.string()),
        ('timestamp', pa.timestamp('us', tz='UTC')),
        ('session_id', pa.string()),
        ('user_id', pa.string()),
        ('status', pa.string()),
        ('status_desc', pa.string()),
        ('error_type', pa.string()),
        ('error_desc', pa.string()),
        ('is_ci', pa.bool_()),
    ]
)

# Columns cast to text on export so the archive is portable; rebuild_crumbs.py
# casts them back. Add an entry when a new typed column joins the schema.
COLUMN_CASTS = {'session_id': 'text', 'user_id': 'text', 'status': 'text'}


def _select_columns() -> str:
    """SELECT list derived from PARQUET_SCHEMA, so the schema is the only place
    to edit when the crumbs table gains a column."""
    return ', '.join(
        f'{name}::{COLUMN_CASTS[name]}' if name in COLUMN_CASTS else name
        for name in PARQUET_SCHEMA.names
    )


async def assert_schema_covers_table(conn):
    """Fail loudly if migas.crumbs has columns the archive schema would drop."""
    rows = await conn.fetch(
        'SELECT column_name FROM information_schema.columns '
        "WHERE table_schema = 'migas' AND table_name = 'crumbs'"
    )
    missing = {r['column_name'] for r in rows} - set(PARQUET_SCHEMA.names)
    if missing:
        raise SystemExit(
            f'migas.crumbs has columns not in the archive schema: {sorted(missing)}. '
            'Add them to PARQUET_SCHEMA (and COLUMN_CASTS if text-encoded) before '
            'archiving, or those columns would be silently lost.'
        )


# Load environment
env_file = os.getenv('MIGAS_ENV_FILE', '.env')
load_dotenv(env_file)


async def async_creator():
    """Proven connection pattern for Cloud SQL Proxy"""
    return await asyncpg.connect(
        user=os.getenv('DATABASE_USER', 'postgres'),
        password=os.getenv('DATABASE_PASSWORD', 'crumbs'),
        host=os.getenv('DATABASE_HOST', 'localhost'),
        port=int(os.getenv('DATABASE_PORT', 5433)),
        database=os.getenv('DATABASE_NAME', 'migas'),
    )


async def get_frozen_cutoff(conn) -> datetime | None:
    """Latest crumb day minus FROZEN_LAG; the newest day safe to archive."""
    ref = await conn.fetchval("SELECT max((timezone('UTC', timestamp))::date) FROM migas.crumbs")
    if ref is None:
        return None
    day = ref - FROZEN_LAG
    return datetime(day.year, day.month, day.day)


async def archive_crumbs(before_date: datetime | None, dry_run: bool, delete: bool):
    conn = await async_creator()
    await assert_schema_covers_table(conn)
    if before_date is None:
        before_date = await get_frozen_cutoff(conn)
        if before_date is None:
            logger.info('No crumbs present. Nothing to archive.')
            await conn.close()
            return
        logger.info(
            f'No --before given; using frozen cutoff {before_date:%Y-%m-%d} '
            f'(latest day - {FROZEN_LAG.days}d)'
        )
    logger.info(f'Connection established. Archive threshold: {before_date}')
    if dry_run:
        logger.info('DRY RUN MODE: No changes will be made to the database.')

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Identify projects with records before the threshold
        projects = await conn.fetch(
            """
            SELECT DISTINCT project FROM migas.crumbs WHERE timestamp < $1
        """,
            before_date,
        )

        if not projects:
            logger.info('No records found before the threshold. Nothing to archive.')
            return

        logger.info(f'Identified {len(projects)} projects for archiving.')
        summary = []

        for p_row in projects:
            project = p_row['project']
            logger.info(f'Processing project: {project}')

            total_to_archive = await conn.fetchval(
                """
                SELECT COUNT(*) FROM migas.crumbs WHERE project = $1 AND timestamp < $2
            """,
                project,
                before_date,
            )

            project_summary = {'project': project, 'archived': 0, 'pruned': 0}

            if total_to_archive > 0:
                logger.info(f'  Found {total_to_archive} records to archive.')

                if not dry_run:
                    parquet_schema = PARQUET_SCHEMA

                    # Create project directory
                    project_dir = EXPORT_DIR / f'project={project.replace("/", "_")}'
                    project_dir.mkdir(parents=True, exist_ok=True)

                    # We'll save as a single file per project/run for now
                    # A more advanced version could partition by month
                    filename = f'archive_{before_date.strftime("%Y%m%d")}.parquet'
                    archive_path = project_dir / filename

                    writer = pq.ParquetWriter(
                        str(archive_path), parquet_schema, compression='snappy'
                    )
                    processed = 0

                    async with conn.transaction():
                        cur = await conn.cursor(
                            f"""
                            SELECT {_select_columns()}
                            FROM migas.crumbs
                            WHERE project = $1 AND timestamp < $2
                            ORDER BY timestamp ASC
                        """,
                            project,
                            before_date,
                        )

                        while True:
                            rows = await cur.fetch(BATCH_SIZE)
                            if not rows:
                                break

                            df = pd.DataFrame([dict(r) for r in rows])
                            # Ensure all schema columns exist
                            for col in parquet_schema.names:
                                if col not in df.columns:
                                    df[col] = None

                            table = pa.Table.from_pandas(df, schema=parquet_schema)
                            writer.write_table(table)
                            processed += len(rows)
                            logger.info(f'    Export progress: {processed}/{total_to_archive}')

                    writer.close()
                    project_summary['archived'] = processed

                    # Pruning logic
                    if delete:
                        logger.info(f'  Pruning {processed} records from database...')
                        # Verify count before delete?
                        # We use the same criteria and transaction-like safety is preferred
                        deleted = await conn.execute(
                            """
                            DELETE FROM migas.crumbs WHERE project = $1 AND timestamp < $2
                        """,
                            project,
                            before_date,
                        )
                        # Extract count from response like 'DELETE 123'
                        deleted_count = int(deleted.split()[-1])
                        project_summary['pruned'] = deleted_count
                        logger.info(f'    Pruned {deleted_count} records.')
                else:
                    project_summary['archived'] = total_to_archive

            summary.append(project_summary)

        # 4. Summary Report
        logger.info('\n--- ARCHIVE SUMMARY ---')
        header = f'{"Project":<30} | {"Archived":<10} | {"Pruned":<10}'
        logger.info(header)
        logger.info('-' * len(header))
        for s in summary:
            logger.info(f'{s["project"]:<30} | {s["archived"]:<10} | {s["pruned"]:<10}')

    except Exception as e:
        logger.error(f'FATAL ERROR during archiving: {e}')
        raise
    finally:
        await conn.close()


def valid_date(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d')
    except ValueError:
        msg = f"Not a valid date: '{s}'. Expected format: YYYY-MM-DD"
        raise argparse.ArgumentTypeError(msg)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Archive old crumbs from PostgreSQL to Parquet.')
    parser.add_argument(
        '--before',
        type=valid_date,
        default=None,
        metavar='YYYY-MM-DD',
        help=f'Archive records before this UTC date (default: frozen cutoff = latest crumb day minus {FROZEN_LAG.days} days)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview changes without executing (enabled by default)',
    )
    parser.add_argument(
        '--no-dry-run', dest='dry_run', action='store_false', help='Execute changes'
    )
    parser.add_argument(
        '--delete', action='store_true', help='Delete records from DB after successful export'
    )

    args = parser.parse_args()

    asyncio.run(archive_crumbs(args.before, args.dry_run, args.delete))
