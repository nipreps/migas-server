import asyncio
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from migas.server.models import Base

# Load from a specific file if provided, otherwise default to .env
env_file = os.getenv('MIGAS_ENV_FILE', '.env')
load_dotenv(env_file)


class MissingEnvironmentVariable(Exception):
    pass


def _any_defined(names: list) -> bool:
    env = os.environ
    for name in names:
        if name in env:
            return True
    return False


def get_db_url() -> str:
    """Generate the database connection url"""
    from sqlalchemy.engine import make_url, URL

    if not _any_defined(['DATABASE_URL', 'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_NAME']):
        raise MissingEnvironmentVariable('No database variables are set')

    if db_url := os.getenv('DATABASE_URL'):
        db_url = make_url(db_url).set(drivername='postgresql+asyncpg')
    else:
        db_url = URL.create(
            drivername='postgresql+asyncpg',
            username=os.getenv('DATABASE_USER'),
            password=os.getenv('DATABASE_PASSWORD'),
            host=os.getenv('DATABASE_HOST', 'localhost'),
            port=int(os.getenv('DATABASE_PORT', 5432)),
            database=os.getenv('DATABASE_NAME'),
        )

    if gcp_conn := os.getenv('GCP_SQL_CONNECTION'):
        db_url = db_url.set(query={'host': f'/cloudsql/{gcp_conn}/.s.PGSQL.5432'})
    return str(db_url)


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
URL = get_db_url()
config.set_main_option('sqlalchemy.url', URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy.ext.asyncio import create_async_engine
    import asyncpg

    # NOTE: Future migrations through Cloud SQL Proxy
    # SQLAlchemy's URL-string generation can mangle passwords,
    # and asyncpg is particularly sensitive to this when using SCRAM-SHA-256.
    # We use an async_creator to pass raw environment variables directly to the
    # asyncpg driver, bypassing all URL-string parsing and escaping issues.
    async def async_creator(*args, **kwargs):
        return await asyncpg.connect(
            user=os.getenv('DATABASE_USER'),
            password=os.getenv('DATABASE_PASSWORD'),
            host=os.getenv('DATABASE_HOST', 'localhost'),
            port=int(os.getenv('DATABASE_PORT', 5432)),
            database=os.getenv('DATABASE_NAME'),
        )

    connectable = create_async_engine(
        'postgresql+asyncpg://',  # Refined dummy URL
        async_creator=async_creator,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        global target_metadata
        target_metadata = Base.metadata
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
