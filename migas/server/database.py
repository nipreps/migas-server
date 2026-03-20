import typing as ty
from datetime import datetime

from sqlalchemy import distinct, func, select, case, cast
from sqlalchemy.dialects.postgresql import insert, INET

from .connections import inject_db_session, gen_session, AsyncSession
from .models import Table, get_project_tables, projects, GeoLoc
from .types import Project, serialize


async def add_new_project(project: str) -> bool:
    """Create new tables, and add project to master projects table."""
    ptable, utable = await get_project_tables(project, create=True)
    if ptable is None or utable is None:
        return False
    await insert_master(project)
    return True


# Table insertion
@inject_db_session
async def insert_master(project: str, session: AsyncSession) -> None:
    """Add project to master table."""
    await session.execute(insert(projects).on_conflict_do_nothing(), {'project': project})


@inject_db_session
async def insert_project(
    table: Table,
    *,
    version: str,
    language: str,
    language_version: str,
    timestamp: datetime,
    session_id: str | None,
    user_id: str | None,
    status: str,
    status_desc: str | None,
    error_type: str | None,
    error_desc: str | None,
    is_ci: bool,
    session: AsyncSession,
) -> None:
    """Add to project table"""
    await session.execute(
        table.insert(),
        {
            'version': version,
            'language': language,
            'language_version': language_version,
            'timestamp': timestamp,
            'session_id': session_id,
            'user_id': user_id,
            'status': status,
            'status_desc': status_desc,
            'error_type': error_type,
            'error_desc': error_desc,
            'is_ci': is_ci,
        },
    )


@inject_db_session
async def insert_user(
    users: Table,
    *,
    user_id: str,
    user_type: str,
    platform: str,
    container: str,
    asn_idx: int | None,
    city_idx: int | None,
    session: AsyncSession,
) -> None:
    await session.execute(
        insert(users).on_conflict_do_nothing(),
        {
            'user_id': user_id,
            'user_type': user_type,
            'platform': platform,
            'container': container,
            'asn_idx': asn_idx,
            'city_idx': city_idx,
        },
    )


async def ingest_project(project: Project, ip: str | None = None) -> None:
    """Dump information into database tables."""
    data = await serialize(project.__dict__)
    # check version lengths
    for vers in ('project_version', 'language_version'):
        if len(data[vers]) > 24:
            print(f'Shortening {project.project} version: {data[vers]}')
            data[vers] = data[vers][:24]

    ptable, utable = await get_project_tables(project.project)
    if ptable is None or utable is None:
        # Don't error but complain loudly
        # TODO: Log > print
        print(f'One or more missing tables:\n\n"Project table: {ptable}\nUsers table: {utable}')
        return

    geoloc_idx = await insert_query_geoloc(ip)
    await insert_project(
        ptable,
        version=data['project_version'],
        language=data['language'],
        language_version=data['language_version'],
        timestamp=data['timestamp'],
        user_id=data['context']['user_id'],
        session_id=data['context']['session_id'],
        status=data['process']['status'],
        status_desc=data['process']['status_desc'],
        error_type=data['process']['error_type'],
        error_desc=data['process']['error_desc'],
        is_ci=data['context']['is_ci'],
    )
    if data['context']['user_id'] is not None:
        await insert_user(
            utable,
            user_id=data['context']['user_id'],
            user_type=data['context']['user_type'],
            platform=data['context']['platform'],
            container=data['context']['container'],
            asn_idx=None,  # Not used anymore
            city_idx=None,  # Not used anymore
            geoloc_idx=geoloc_idx,
        )


@inject_db_session
async def query_usage_by_datetimes(
    project: Table, start: datetime, end: datetime, session: AsyncSession, unique: bool = False
) -> int:
    query = select(func.count()).where(project.c.timestamp >= start, project.c.timestamp <= end)
    if unique:
        query = select(func.count(distinct(project.c.user_id))).where(
            project.c.timestamp.between(start, end)
        )
    res = await session.execute(query)
    return res.scalar_one_or_none() or 0


@inject_db_session
async def query_usage(project: Table, session: AsyncSession) -> int:
    res = await session.execute(select(func.count(project.c.idx)))
    return res.scalars().one()


@inject_db_session
async def query_usage_unique(project: Table, session: AsyncSession) -> int:
    """TODO: What to do with all NULLs (unique users)?"""
    res = await session.execute(select(func.count(distinct(project.c.user_id))))
    return res.scalars().one()


@inject_db_session
async def query_projects(session: AsyncSession) -> list[str]:
    res = await session.execute(select(projects.c.project))
    return res.scalars().all()


@inject_db_session
async def project_exists(project: str, session: AsyncSession) -> bool:
    res = await session.execute(projects.select().where(projects.c.project == project))
    return bool(res.one_or_none())


async def get_viz_data(
    project_name: str,
    version: str | None = None,
    date_group: ty.Literal['day', 'week', 'month', 'year'] = 'month',
) -> list:
    """
    Filter project usage into groups, based on versions and dates.
    """
    project, _ = await get_project_tables(project_name, create=True)

    if project is None:
        return []

    # Always use YYYY-MM-DD for the frontend to parse easily
    # date_trunc already returns the first day of the period
    date_trunc = func.date_trunc(date_group, project.c.timestamp)
    date_str = func.to_char(date_trunc, 'YYYY-MM-DD')

    subq0 = (
        select(
            project.c.version,
            project.c.session_id,
            date_str.label('date'),
            project.c.status
        )
        .distinct(project.c.session_id)
        .where(project.c.status is not None)
    )

    if version:
        subq0 = subq0.where(project.c.version == version)
    else:
        # Filter out "unofficial" versions
        subq0 = subq0.where(project.c.version.not_like('%+%')).where(
            project.c.version.not_like('%rc%')
        )
    subq0 = subq0.subquery()

    query = (
        select(
            subq0.c.version,
            subq0.c.date,
            subq0.c.status,
            func.count().label("count")
        )
        .group_by(subq0.c.status, subq0.c.date, subq0.c.version)
        .order_by(subq0.c.date.desc(), subq0.c.version.desc())
    )

    async with gen_session() as session:
        res = await session.execute(query)
        return [
            {
                "version": row[0],
                "date": row[1],
                "status": row[2],
                "count": row[3],
            }
            for row in res.all()
        ]


@inject_db_session
async def valid_location_dbs(session: AsyncSession) -> tuple[bool, bool]:
    from .connections import get_mmdb_reader

    city, asn = await get_mmdb_reader()
    return asn is not None, city is not None


async def verify_token(token: str, require_root: bool = False) -> tuple[bool, list[str]]:
    """Query table for usage access"""
    from .models import Authentication

    project, projects = None, []

    # verify token pertains to project
    async with gen_session() as session:
        res = await session.execute(
            select(Authentication.project).where(Authentication.token == token)
        )
        project = res.one_or_none()

    if project:
        if project[0] == 'master':
            projects = await query_projects()
        elif not require_root:
            projects = [project[0]]
    return bool(project), projects


async def insert_query_geoloc(ip: str | None) -> int | None:
    """
    Gather geolocation information from an IP, and preserve in a dedicated table.

    Initially will query the MMDB databases for geolocation information.
    If found, will attempt to insert geolocation information into the GeoLoc table, but if
    already present, will simply fetch the existing index.

    The index returned will be inserted into the specific `Project` table.
    """
    from .fetchers import geoloc

    info = await geoloc(ip)
    if not info:
        return

    # Insert into geoloc table
    from .models import GeoLoc

    async with gen_session() as session:
        res = await session.execute(
            insert(GeoLoc)
            .values(
                asn=info.get('asn'),
                asn_org=info.get('aso'),
                continent_code=info.get('continent_code'),
                country_code=info.get('country_code'),
                state_province_name=info.get('state_or_province'),
                city_name=info.get('city'),
                lat=info.get('lat'),
                lon=info.get('lon'),
            )
            .on_conflict_do_nothing()
            .returning(GeoLoc.idx)
        )
        geoloc_idx = res.scalar_one_or_none()

        if geoloc_idx is None:
            # Fetch existing index
            res = await session.execute(
                select(GeoLoc.idx).where(
                    GeoLoc.country_code == info.get('country_code'),
                    GeoLoc.state_province_name == info.get('state_or_province'),
                    GeoLoc.city_name == info.get('city'),
                    GeoLoc.lat == info.get('lat'),
                    GeoLoc.lon == info.get('lon'),
                )
            )
            geoloc_idx = res.scalar_one_or_none()

        return geoloc_idx
