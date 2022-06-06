import os
from typing import List

import asyncpg
from asyncpg import Record

from etelemetry_app.server.fetchers import fetch_ipstack_data
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
            conn_kwargs = {"timeout": 10, "command_timeout": 60}
            if (uri := os.getenv("ETELEMETRY_DB_URI")) is not None:
                conn_kwargs["dsn"] = uri
            else:
                conn_kwargs.update(
                    {
                        "host": os.getenv("ETELEMETRY_DB_HOSTNAME", "localhost"),
                        "port": os.getenv("ETELEMETRY_DB_PORT", 5432),
                        "database": os.getenv("ETELEMETRY_DB", "etelemetry"),
                    }
                )
            try:
                Connection = await asyncpg.connect(**conn_kwargs)
            except Exception as e:
                print("Could not establish connection")
                raise (e)

        return await func(*fargs, **kwargs)

    return db_connection


# Table creation
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
            postal_code VARCHAR(10) NOT NULL,
            location POINT NOT NULL
        );'''
    )


@db_connect
async def create_project_tables(owner: str, repo: str) -> None:
    table = f"{owner}/{repo}"
    await create_project_table(table)
    await create_user_table(f"{table}/users")


# Table insertion
@db_connect
async def insert_project(
    table: str,
    *,
    language: str,
    language_version: str,
    timestamp: DateTime,
    session: str | None,
    user_id: str | None,
    status: str,
) -> None:
    """Add to project table"""
    await Connection.execute(
        f'''
        INSERT INTO "{table}" (
            language,
            language_version,
            timestamp,
            session_id,
            user_id,
            status
        ) VALUES ($1, $2, $3, $4, $5, $6);''',
        language,
        language_version,
        timestamp,
        session,
        user_id,
        status,
    )


@db_connect
async def insert_user(
    table, *, user_id: str, user_type: str, platform: str, container: str
) -> None:
    await Connection.execute(
        f'''INSERT INTO "{table}" (id, type, platform, container) VALUES ($1, $2, $3, $4);''',
        user_id,
        user_type,
        platform,
        container,
    )


@db_connect
async def insert_project_data(project: Project) -> bool:
    data = await serialize(project.__dict__)
    # replace with a cache to avoid excessive db calls
    await create_project_tables(project.owner, project.repo)
    ptable = f"{project.owner}/{project.repo}"
    utable = f"{ptable}/users"
    await insert_project(
        ptable,
        language=data['language'],
        language_version=data['language_version'],
        timestamp=data['timestamp'],
        session=data['session'],
        user_id=data['context']['user_id'],
        status=data['process']['status'],
    )
    if data['context']['user_id'] is not None:
        await insert_user(
            utable,
            user_id=data['context']['user_id'],
            user_type=data['context']['user_type'],
            platform=data['context']['platform'],
            container=data['context']['container'],
        )
    return True


@db_connect
async def insert_geoloc(
    ip: str,
    *,
    continent: str,
    country: str,
    region: str,
    city: str,
    postal_code: str,
    latitude: float,
    longitude: float,
) -> None:
    """ """
    await Connection.execute(
        f'''INSERT INTO geolocs (
            id,
            continent,
            country,
            region,
            city,
            postal_code,
            location
        ) VALUES ($1, $2, $3, $4, $5, $6, $7 );''',
        ip,
        continent,
        country,
        region,
        city,
        postal_code,
        (latitude, longitude),
    )


# Table query
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

    if ip == '127.0.0.1':
        # ignore localhost testing
        return

    await create_geoloc_table()
    hip = sha256(ip.encode()).hexdigest()
    record = await Connection.fetchrow(f'SELECT * FROM geolocs WHERE id = $1;', hip)
    if not record:
        data = await fetch_ipstack_data(ip)
        print(data)
        await insert_geoloc(
            hip,
            continent=data['continent_name'],
            country=data['country_name'],
            region=data['region_name'],
            city=data['city'],
            postal_code=data['zip'],
            latitude=data['latitude'],
            longitude=data['longitude'],
        )


@db_connect
async def query_project_by_datetimes(
    table: str,
    start: DateTime,
    end: DateTime,
) -> int:
    cmd = f"""SELECT COUNT(*) FROM "{table}" WHERE timestamp BETWEEN $1 AND $2;"""
    records = await Connection.fetch(cmd, start, end)
    return records[0]['count']


@db_connect
async def query_total_uses(table: str) -> List[Record]:
    cmd = f"""SELECT COUNT(*) FROM "{table}";"""
    records = await Connection.fetch(f"""SELECT COUNT(*) FROM "{table}";""")
    return records


@db_connect
async def query_unique_users(table: str) -> List[Record]:
    """TODO: What to do with all NULLs (unique users)?"""
    cmd = f"""SELECT DISTINCT user_id FROM "{table}";"""
    records = await Connection.fetch(cmd)
    return records


@db_connect
async def query_projects() -> List[str]:
    records = await Connection.fetch(
        """SELECT tablename FROM pg_catalog.pg_tables
        WHERE tablename like '%/%' and tablename not like '%users';"""
    )
    return [r['tablename'] for r in records]
