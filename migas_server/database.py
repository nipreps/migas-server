from typing import List

from asyncpg import Record

from migas_server.connections import get_db_connection_pool
from migas_server.fetchers import fetch_ipstack_data
from migas_server.types import DateTime, Project, serialize

TABLES = {
    "projects": "{repo}/{owner}",
    "users": "{repo}/{owner}/users",
    "geolocs": "geolocs",
}


# Table creation
async def create_project_table(table: str) -> None:
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
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


async def create_user_table(table: str) -> None:
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f'''
            CREATE TABLE IF NOT EXISTS "{table}"(
                idx SERIAL NOT NULL PRIMARY KEY,
                id UUID NOT NULL,
                type VARCHAR(7) NOT NULL,
                platform VARCHAR(8) NULL,
                container VARCHAR(9) NOT NULL
            );'''
        )


async def create_geoloc_table(table: str = 'geolocs') -> None:
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
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


async def create_project_tables(project) -> None:
    await create_project_table(project)
    await create_user_table(f"{project}/users")


# Table insertion
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
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
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


async def insert_user(
    table, *, user_id: str, user_type: str, platform: str, container: str
) -> None:
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f'''INSERT INTO "{table}" (id, type, platform, container) VALUES ($1, $2, $3, $4);''',
            user_id,
            user_type,
            platform,
            container,
        )


async def insert_project_data(project: Project) -> bool:
    data = await serialize(project.__dict__)
    # replace with a cache to avoid excessive db calls
    await create_project_tables(project.project)
    utable = f"{project.project}/users"
    await insert_project(
        project.project,
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
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute(
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
async def query_or_insert_geoloc(ip: str) -> Record:
    """
    Check to see if the address has already been geolocated.

    If so, return the matching record.
    If not, spend an `ipstack` API call and store the resulting data.

    We store geolocation information to avoid overloading our limited
    IPStack API calls, since we are using the free tier.
    """
    from hashlib import sha256

    await create_geoloc_table()
    hip = sha256(ip.encode()).hexdigest()
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(f'SELECT * FROM geolocs WHERE id = $1;', hip)

    if not record:
        data = await fetch_ipstack_data(ip)
        if data.get("success", True) is False:
            print(f"Unable to fetch geoloc data: {data}")
            return

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


async def query_project_by_datetimes(
    project: str,
    start: DateTime,
    end: DateTime,
) -> int:
    cmd = f"""SELECT COUNT(*) FROM "{project}" WHERE timestamp BETWEEN $1 AND $2;"""
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(cmd, start, end)
    return records[0]['count']


async def query_total_uses(table: str) -> List[Record]:
    cmd = f"""SELECT COUNT(*) FROM "{table}";"""
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(f"""SELECT COUNT(*) FROM "{table}";""")
    return records


async def query_unique_users(table: str) -> List[Record]:
    """TODO: What to do with all NULLs (unique users)?"""
    cmd = f"""SELECT DISTINCT user_id FROM "{table}";"""
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(cmd)
    return records


async def query_projects() -> List[str]:
    pool = await get_db_connection_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(
            """SELECT tablename FROM pg_catalog.pg_tables
            WHERE tablename like '%/%' and tablename not like '%users';"""
        )
    return [r['tablename'] for r in records]
