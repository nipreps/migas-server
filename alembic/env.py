import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context


def get_db_url() -> str:
    """Generate the database connection url"""
    from sqlalchemy.engine import make_url, URL

    if db_url := os.getenv("DATABASE_URL"):
        db_url = make_url(db_url).set(drivername="postgresql+asyncpg")
    else:
        db_url = URL.create(
            drivername="postgresql+asyncpg",
            username=os.getenv("DATABASE_USER"),
            password=os.getenv("DATABASE_PASSWORD"),
            database=os.getenv("DATABASE_NAME")
        )

    if gcp_conn := os.getenv("GCP_SQL_CONNECTION"):
        db_url = db_url.set(query={"host": f"/cloudsql/{gcp_conn}/.s.PGSQL.5432"})
    return db_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
URL = get_db_url()
config.set_main_option("sqlalchemy.url", URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from migas_server.models import Base, populate_base

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
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # populate dynamically created tables
    connectable = AsyncEngine(
        engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        )
    )

    async with connectable.connect() as connection:
        await populate_base(connection)
        global target_metadata
        target_metadata = Base.metadata
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
