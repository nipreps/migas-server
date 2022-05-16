import os

# from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
# from pymongo.results import InsertOneResult
import asyncpg

from etelemetry_app.server.types import DateTime, Project

Connection = None

DEFAULT_UUID = "00000000-0000-0000-0000-000000000000"


def db_connect(func):
    """Decorator to ensure we have a valid database connection"""

    async def db_connection(*fargs, **kwargs):
        global Connection
        if Connection is None:
            try:
                Connection = await asyncpg.connect(
                    host=os.getenv("ETELEMETRY_DB_HOSTNAME", "localhost"),
                    port=os.getenv("ETELEMETRY_DB_PORT", 5432),
                    database=os.getenv("ETELEMETRY_DB", "etelemetry"),
                    timeout=10,  # timeout for connection
                    command_timeout=60,  # timeout for future commands
                )
            except Exception as e:
                print("Could not establish connection")
                raise (e)

        await func(*fargs, **kwargs)

    return db_connection


@db_connect
async def create_project_table(table: str) -> None:
    await Connection.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}"(
            id SERIAL NOT NULL PRIMARY KEY,
            language VARCHAR(32) NOT NULL,
            language_version VARCHAR(24) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            session_id UUID NULL,
            user_id UUID NULL,
            status VARCHAR(7) NOT NULL
        );'''
    )


@db_connect
async def create_user_table(table: str) -> None:
    await Connection.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}"(
            id UUID NOT NULL PRIMARY KEY,
            type VARCHAR(7) NOT NULL,
            platform VARCHAR(8) NULL,
            container VARCHAR(9) NOT NULL
        );'''
    )


# @db_connect
# async def create_tables(owner: str, repo: str) -> None:
#     await create_project_table(owner, repo)
#     await create_user_table(owner, repo)


@db_connect
async def add_project(
    table: str,
    language: str,
    language_version: str,
    timestamp: DateTime,
    session: str | None,
    user_id: str | None,
    status: str,
):
    """Add to project table"""
    await Connection.execute(
        f'INSERT INTO "{table}" (language, language_version, timestamp, session_id, user_id, status) VALUES ($1, $2, $3, $4, $5, $6);',
        language,
        language_version,
        timestamp,
        session,  # or DEFAULT_UUID,
        user_id,  # or DEFAULT_UUID,
        status,
    )


@db_connect
async def add_user(table, user_id: str, user_type: str, platform: str, container: str) -> None:
    await Connection.execute(
        f'INSERT INTO "{table}" VALUES ($1, $2, $3, $4);',
        user_id,  # or DEFAULT_UUID,
        user_type,
        platform,
        container,
    )


@db_connect
async def process_project(project: Project) -> bool:
    # await create_tables(project.owner, project.repo)
    ptable = f"{project.owner}/{project.repo}"
    data = await _serialize(project.__dict__)
    # skip this call in the future
    await create_project_table(ptable)
    print(data)
    await add_project(
        ptable,
        data['language'],
        data['language_version'],
        data['timestamp'],
        data['session'],
        data['context']['user_id'],
        data['process']['status'],
    )
    if data['context']['user_id'] is not None:
        utable = f"{ptable}/users"
        await create_user_table(utable)
        await add_user(
            utable,
            data['context']['user_id'],
            data['context']['user_type'],
            data['context']['platform'],
            data['context']['container'],
        )
    return True


async def _serialize(data):
    from enum import Enum

    from packaging.version import LegacyVersion, Version

    from etelemetry_app.server.types import Context, Process

    for k, v in data.items():
        # TODO: Is this possible with PEP636?
        # I gave up trying it
        if isinstance(v, (Version, LegacyVersion)):
            data[k] = str(v)
        elif isinstance(v, Enum):
            data[k] = v.name
        # datetime ok?
        elif isinstance(v, (Context, Process)):
            data[k] = await _serialize(v.__dict__)

    return data
