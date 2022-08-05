from typing import List

# from asyncpg import Record
from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert

from migas_server.fetchers import fetch_ipstack_data
from migas_server.models import Table, db_session, geolocs, get_project_tables, projects
from migas_server.types import DateTime, Project, serialize


# Table insertion
async def insert_master(project: str) -> None:
    """Add project to master table."""
    async with await db_session() as session:
        res = await session.execute(
            insert(projects).on_conflict_do_nothing(),
            {'project': project},
        )
        await session.commit()


async def insert_project(
    table: Table,
    *,
    version: str,
    language: str,
    language_version: str,
    timestamp: DateTime,
    session_id: str | None,
    user_id: str | None,
    status: str,
    is_ci: bool,
) -> None:
    """Add to project table"""
    async with await db_session() as session:
        res = await session.execute(
            table.insert(),
            {
                'version': version,
                'language': language,
                'language_version': language_version,
                'timestamp': timestamp,
                'session_id': session_id,
                'user_id': user_id,
                'status': status,
                'is_ci': is_ci,
            },
        )
        await session.commit()


async def insert_user(
    users: Table,
    *,
    user_id: str,
    user_type: str,
    platform: str,
    container: str,
) -> None:
    async with await db_session() as session:
        stmt = insert(users).on_conflict_do_nothing(), {
            'user_id': user_id,
            'user_type': user_type,
            'platform': platform,
            'container': container,
        }
        await session.commit()


async def ingest_project(project: Project) -> None:
    """Dump information into database tables."""
    data = await serialize(project.__dict__)
    # replace with a cache to avoid excessive db calls
    await insert_master(project.project)
    ptable, utable = get_project_tables(project.project)
    await insert_project(
        ptable,
        version=data['project_version'],
        language=data['language'],
        language_version=data['language_version'],
        timestamp=data['timestamp'],
        session_id=data['session_id'],
        user_id=data['context']['user_id'],
        status=data['process']['status'],
        is_ci=data['context']['is_ci'],
    )
    if data['context']['user_id'] is not None:
        await insert_user(
            utable,
            user_id=data['context']['user_id'],
            user_type=data['context']['user_type'],
            platform=data['context']['platform'],
            container=data['context']['container'],
        )


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
    """Insert geolocation data to table."""
    async with await db_session() as session:
        res = await session.execute(
            geolocs.insert(),
            {
                "id": ip,
                "continent": continent,
                "country": country,
                "region": region,
                "city": city,
                "postal_code": postal_code,
                "latitude": latitude,
                "longitude": longitude,
            },
        )
        await session.commit()


# Table query
async def geoloc_request(ip: str) -> None:
    """
    Check to see if the address has already been geolocated.

    If so, nothing to do.
    If not, spend an `ipstack` API call and store the resulting data.

    We store geolocation information to avoid overloading our limited
    IPStack API calls, since we are using the free tier.
    """
    from hashlib import sha256

    hip = sha256(ip.encode()).hexdigest()
    async with await db_session() as session:
        res = await session.execute(geolocs.select().where(geolocs.c.id == hip))
        if res.one_or_none():
            return

    # No user data found
    data = await fetch_ipstack_data(ip)
    # Do not add to DB if IPStack call failed
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


async def query_usage_by_datetimes(
    project: Table,
    start: DateTime,
    end: DateTime,
    unique: bool = False,
) -> int:
    async with await db_session() as session:
        # break up into 2 SELECT calls
        subq = (
            select((project.c.timestamp, project.c.user_id))
            .where(project.c.timestamp.between(start, end))
            .subquery()
        )
        if unique:
            stmt = select(func.count(distinct(subq.c.user_id)))
        else:
            stmt = select(func.count(subq.c.user_id))
        res = await session.execute(stmt)
    return res.scalars().one()


async def query_usage(project: Table) -> int:
    async with await db_session() as session:
        res = await session.execute(select(func.count(project.c.idx)))
    return res.scalars().one()


async def query_usage_unique(project: Table) -> int:
    """TODO: What to do with all NULLs (unique users)?"""
    async with await db_session() as session:
        res = await session.execute(select(func.count(distinct(project.c.user_id))))
    return res.scalars().one()


async def query_projects() -> List[str]:
    async with await db_session() as session:
        res = await session.execute(select(projects.c.project))
    return res.scalars.all()


async def project_exists(project: str) -> bool:
    async with await db_session() as session:
        res = await session.execute(projects.select().where(projects.c.project == project))
    return bool(res.one_or_none())
