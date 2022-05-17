import os

import asyncpg
from asyncpg import Record

from etelemetry_app.server.types import DateTime, Project, serialize
from etelemetry_app.server.utils import now

Connection = None

TABLES = {
    "projects": "{repo}/{owner}",
    "users": "{repo}/{owner}/users",
    "geolocs": "geolocs",
}


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
            idx SERIAL NOT NULL PRIMARY KEY,
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
            idx SERIAL NOT NULL PRIMARY KEY,
            id UUID NOT NULL,
            type VARCHAR(7) NOT NULL,
            platform VARCHAR(8) NULL,
            container VARCHAR(9) NOT NULL
        );'''
    )


@db_connect
async def create_geoloc_table(table: str = 'geolocs') -> None:
    await Connection.execute(
        f'''
        CREATE TABLE IF NOT EXISTS {table}(
            idx SERIAL NOT NULL,
            id CHAR(64) NOT NULL PRIMARY KEY,
            continent VARCHAR(13) NOT NULL,
            country VARCHAR(56) NOT NULL,
            region VARCHAR(58) NOT NULL,
            city VARCHAR(58) NOT NULL,
            zip VARCHAR(10) NOT NULL,
            location POINT NOT NULL
        );'''
    )


@db_connect
async def create_tables(owner: str, repo: str) -> None:
    table = f"{owner}/{repo}"
    await create_project_table(table)
    await create_user_table(f"{table}/users")


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
        f'''INSERT INTO "{table}" (language, language_version, timestamp, session_id, user_id, status) VALUES ($1, $2, $3, $4, $5, $6);''',
        language,
        language_version,
        timestamp,
        session,
        user_id,
        status,
    )


@db_connect
async def add_user(table, user_id: str, user_type: str, platform: str, container: str) -> None:
    await Connection.execute(
        f'''INSERT INTO "{table}" (id, type, platform, container) VALUES ($1, $2, $3, $4);''',
        user_id,
        user_type,
        platform,
        container,
    )


@db_connect
async def insert_data(project: Project) -> bool:
    data = await serialize(project.__dict__)
    # replace with a cache to avoid excessive db calls
    await create_tables(project.owner, project.repo)
    ptable = f"{project.owner}/{project.repo}"
    utable = f"{ptable}/users"
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
        await add_user(
            utable,
            data['context']['user_id'],
            data['context']['user_type'],
            data['context']['platform'],
            data['context']['container'],
        )
    return True


@db_connect
async def query_or_insert_geoloc(ip: str) -> Record:
    """
    Check to see if the address has already been geolocated.

    If so, return the matching record.
    If not, spend an `ipstack` API call and store the resulting data.

    We store geolocation information to avoid overloading our limited
    IPStack API calls, since we are using the free tier.
    """
    from hashlib import sha256

    hip = sha256(ip.encode()).hexdigest()
    cmd = f"""SELECT * FROM geolocs WHERE id = $1"""
    record = await Connection.fetchrow(cmd, hip)
    if not record:
        # query IPStack
        # add result
        await insert_geoloc(hip)


async def insert_geoloc(ip):
    """ """
    await Connection.execute(
        f"INSERT INTO geolocs (id, continent, country, region, city, zip, location) VALUES ('$1', '$2', '$3', '$4', '$5', '$6', '$7' );",
        ip,
        continent,
        country,
        region,
        city,
        zipc,
        (latitude, longitude),
    )


@db_connect
async def query_between_dates(table: str, starttime: DateTime, endtime: DateTime = None) -> Record:
    if endtime is None:
        endtime = now()
    cmd = f"""SELECT * FROM "{table}" WHERE timestamp BETWEEN '$1' AND '$2';"""
    records = await Connection.fetch(cmd, starttime, endtime)


@db_connect
async def query_total_uses(table: str):
    cmd = f"""SELECT COUNT(*) FROM "{table}";"""
    records = await Connection.fetch(f"""SELECT COUNT(*) FROM "{table}";""")


@db_connect
async def query_unique_users(table: str):
    """TODO: What to do with all NULLs (unique users)?"""
    cmd = f"""SELECT DISTINCT user_id FROM "{table}";"""
    records = await Connection.fetch(cmd)
