from typing import List

# from asyncpg import Record
from sqlalchemy import distinct, func, select, text
from sqlalchemy.dialects.postgresql import insert

from .models import Table, gen_session, get_project_tables, projects
from .types import DateTime, Project, serialize


# Table insertion
async def insert_master(project: str) -> None:
    """Add project to master table."""
    async with gen_session() as session:
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
    status_desc: str | None,
    error_type: str | None,
    error_desc: str | None,
    is_ci: bool,
) -> None:
    """Add to project table"""
    async with gen_session() as session:
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
                'status_desc': status_desc,
                'error_type': error_type,
                'error_desc': error_desc,
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
    async with gen_session() as session:
        res = await session.execute(
            insert(users).on_conflict_do_nothing(),
            {
                'user_id': user_id,
                'user_type': user_type,
                'platform': platform,
                'container': container,
            },
        )
        await session.commit()


async def ingest_project(project: Project) -> None:
    """Dump information into database tables."""
    data = await serialize(project.__dict__)
    # check version lengths
    for vers in ('project_version', 'language_version'):
        if len(data[vers]) > 24:
            print(f"Shortening {project.project} version: {data[vers]}")
            data[vers] = data[vers][:24]
    await insert_master(project.project)
    ptable, utable = await get_project_tables(project.project)
    await insert_project(
        ptable,
        version=data['project_version'],
        language=data['language'],
        language_version=data['language_version'],
        timestamp=data['timestamp'],
        session_id=data['session_id'],
        user_id=data['context']['user_id'],
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
        )


async def query_usage_by_datetimes(
    project: Table,
    start: DateTime,
    end: DateTime,
    unique: bool = False,
) -> int:
    async with gen_session() as session:
        # break up into 2 SELECT calls
        subq = (
            select(project.c['timestamp', 'user_id'])
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
    async with gen_session() as session:
        res = await session.execute(select(func.count(project.c.idx)))
    return res.scalars().one()


async def query_usage_unique(project: Table) -> int:
    """TODO: What to do with all NULLs (unique users)?"""
    async with gen_session() as session:
        res = await session.execute(select(func.count(distinct(project.c.user_id))))
    return res.scalars().one()


async def query_projects() -> List[str]:
    async with gen_session() as session:
        res = await session.execute(select(projects.c.project))
    return res.scalars().all()


async def project_exists(project: str) -> bool:
    async with gen_session() as session:
        res = await session.execute(projects.select().where(projects.c.project == project))
    return bool(res.one_or_none())


async def get_viz_data(project: str) -> list:
    """
    TODO: Implement bucket sorting.

    Implements the following SQL pseudocode:
    - select distinct version from <project> where version not like '%+%';
    - for vers in ^:
        - select count(distinct session_id) from <project> where is_ci = false and version = ver;
        - select count(distinct session_id) from <project> where is_ci = false and version = ver and status = 'C';
        - select count(distinct user_id) from <project> where is_ci = false and version = ver;
        - select count(*), date_part('isoyear', timestamp) as year, date_part('week', timestamp) as week from <project> where status = 'C' group by year, week order by year, week;
    """
    p, _ = await get_project_tables(project)

    async with gen_session() as session:
        # we want to return a table with:
        # version | total_runs (unique session_id) | sucessful_runs | users (unique user_id)
        # TODO: index should be applied to version, session_id, user_id columns
        # TODO: this should be done within a single query

        # first grab all different versions
        versions = await session.execute(
            select(distinct(p.c.version)).where(p.c.version.not_like('%+%'))
        )
        data = {v: {} for v in versions.scalars().all()}

        for vers in data.keys():
            total = await session.execute(
                select(func.count(distinct(p.c.session_id)))
                .where(p.c.is_ci == False)
                .where(p.c.version == vers)
            )
            data[vers]['total_runs'] = total.scalar()
            success = await session.execute(
                select(func.count(distinct(p.c.session_id)))
                .where(p.c.is_ci == False)
                .where(p.c.version == vers)
                .where(text("status='C'"))
            )
            data[vers]['successful_runs'] = success.scalar()
            uusers = await session.execute(
                select(func.count(distinct(p.c.user_id)))
                .where(p.c.is_ci == False)
                .where(p.c.version == vers)
            )
            data[vers]['unique_users'] = uusers.scalar()
    return data


async def verify_token(token: str) -> tuple[bool, list[str]]:
    '''Query table for usage access'''
    from sqlalchemy import select
    from .models import Authentication

    # verify token pertains to project
    projects = []
    async with gen_session() as session:
        res = await session.execute(
            select(Authentication.project).where(Authentication.token == token)
        )
        if (project := res.one_or_none()) is not None:
            if project[0] == 'master':
                projects = await query_projects()
            else:
                projects = [project[0]]
    return bool(project), projects
