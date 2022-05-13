import os

# from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
# from pymongo.results import InsertOneResult
import asyncpg

from etelemetry_app.server.types import Project

Connection = None


def db_connect(func):
    """Decorator to ensure we have a valid database connection"""

    async def db_connection(fargs):
        if Connection is None:
            try:
                global Connection
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

        await func(fargs)

    return db_connection


@db_connect
async def create_project_table(owner, repo):
    table = f"{owner}/{repo}"
    await Connection.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}"(
            id SERIAL NOT NULL PRIMARY KEY,
            language VARCHAR(32) NOT NULL,
            language_version VARCHAR(24) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            session_id UUID,
            user_id UUID,
        );'''
    )


@db_connect
async def create_user_table(owner: str, repo: str) -> str:
    table = f"{owner}/{repo}/users"
    await Connection.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}"(
            id
        );'''
    )
    return table


@db_connect
async def add_project(project: Project, table):
    """Add to project table, and optionally user table."""
    await Connection.execute(
        f'''
        INSERT INTO "{table}" (
            language,
            language_version,
            session_id,
            user_id
        ) VALUES ($1), ($2), ($3), ($4);''',
        project.language,
        project.language_version,
        project.session,
        project.user_id,
    )


# async def add_collection()
async def collection_insert(project: Project) -> InsertOneResult:
    # Use @ as separator since it cannot be present in GH IDs
    col_name = f"{project.owner}@{project.repo}"

    # MAYBE: rate limit creation?
    if col_name not in await DB.list_collection_names():
        print(f"Creating new collection {col_name}")
        await DB.create_collection(col_name, capped=True, size=1000)
    else:
        print("Using existing collection")

    col = DB[col_name]

    inserted = await insert_project(col, project)
    print(f"Inserted new entry {inserted} in {col_name}")
    return inserted


async def insert_project(col: AsyncIOMotorCollection, project: Project) -> InsertOneResult:
    doc = await _serialize_to_mongo(project.__dict__.copy())
    inserted = await col.insert_one(doc)
    return inserted


async def _serialize_to_mongo(data):
    from enum import Enum

    from packaging.version import LegacyVersion, Version

    from etelemetry_app.server.types import Context, Process

    for k, v in data.items():
        # TODO: Is this possible with PEP636?
        # I gave up trying it
        if isinstance(v, str):
            data[k] = await _sanitize(v)
        elif isinstance(v, (Version, LegacyVersion)):
            data[k] = await _sanitize(str(v))
        elif isinstance(v, Enum):
            data[k] = v.name
        # datetime ok?
        elif isinstance(v, (Context, Process)):
            data[k] = await _serialize_to_mongo(v.__dict__)
    return data


# character limit
# replace $ characters
async def _sanitize(s, char_lim=99):
    if len(s) > char_lim:
        print(f"String {s} is over character limit")
    return s[:char_lim]
