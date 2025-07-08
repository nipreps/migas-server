import typing as ty
from functools import wraps
from datetime import datetime

# from asyncpg import Record
from sqlalchemy import distinct, func, select, case
from sqlalchemy.dialects.postgresql import insert

from .models import Table, gen_session, get_project_tables, projects, SessionGen
from .types import Project, serialize

def db_context(func):
    """Decorator that creates a session for database interaction."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        has_session = kwargs.get('session')
        if has_session:
            return await func(*args, **kwargs)
        # no session specified, inject a new one
        async with gen_session() as session:
            kwargs['session'] = session
            return await func(*args, **kwargs)
    return wrapper


async def add_new_project(project: str) -> bool:
    """Create new tables, and add project to master projects table."""
    ptable, utable = await get_project_tables(project, create=True)
    if ptable is None or utable is None:
        return False
    await insert_master(project)
    return True

# Table insertion
@db_context
async def insert_master(project: str, session: SessionGen) -> None:
    """Add project to master table."""
    await session.execute(
        insert(projects).on_conflict_do_nothing(),
        {'project': project},
    )
    await session.commit()


@db_context
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
    session: SessionGen,
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
    await session.commit()


@db_context
async def insert_user(
    users: Table,
    *,
    user_id: str,
    user_type: str,
    platform: str,
    container: str,
    session: SessionGen,
) -> None:
    await session.execute(
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

    ptable, utable = await get_project_tables(project.project)
    if ptable is None or utable is None:
        # Don't error but complain loudly
        # TODO: Log > print
        print(f'One or more missing tables:\n\n"Project table: {ptable}\nUsers table: {utable}')
        return
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
        )


@db_context
async def query_usage_by_datetimes(
    project: Table,
    start: datetime,
    end: datetime,
    session: SessionGen,
    unique: bool = False,
) -> int:
    query = select(func.count()).where(
        project.c.timestamp >= start, project.c.timestamp <= end
    )
    if unique:
        query = select(func.count(distinct(project.c.user_id))).where(
            project.c.timestamp.between(start, end)
        )
    res = await session.execute(query)
    return res.scalar_one_or_none() or 0


@db_context
async def query_usage(project: Table, session: SessionGen) -> int:
    res = await session.execute(select(func.count(project.c.idx)))
    return res.scalars().one()


@db_context
async def query_usage_unique(project: Table, session: SessionGen) -> int:
    """TODO: What to do with all NULLs (unique users)?"""
    res = await session.execute(select(func.count(distinct(project.c.user_id))))
    return res.scalars().one()


@db_context
async def query_projects(session: SessionGen) -> list[str]:
    res = await session.execute(select(projects.c.project))
    return res.scalars().all()


@db_context
async def project_exists(project: str, session: SessionGen) -> bool:
    res = await session.execute(projects.select().where(projects.c.project == project))
    return bool(res.one_or_none())


async def get_viz_data(
    project_name: str,
    version: str | None = None,
    date_group: ty.Literal['day', 'week', 'month', 'year'] = 'month'
) -> list:
    """
    Filter project usage into groups, based on versions and dates.
    """
    project, _ = await get_project_tables(project_name)

    match date_group:
        case 'day':
            datefmt = 'YYYY-MM-DD'
        case 'week':
            datefmt = 'YYYY-WW' #?
        case 'month':
            datefmt = 'YYYY-MM'
        case 'year':
            datefmt = 'YYYY'
        case _:
            raise NotImplementedError

    # Create a subquery to:
    # - filter out version(s)
    # - convert timestamps into YEAR-WEEK values
    subq0 = (
        select(
            project.c.version,
            project.c.session_id,
            func.to_char(project.c.timestamp, datefmt).label('date'),
            project.c.status
        )
        .distinct(project.c.session_id)
        .where(project.c.status is not None)
    )

    if version:
        subq0 = (
            subq0.where(project.c.version == version)
        )
    else:
        # Filter out "unofficial" versions
        subq0 = (
            subq0
            .where(project.c.version.not_like('%+%'))
            .where(project.c.version.not_like('%rc%'))
        )
    subq0 = subq0.subquery()


    subq1 = (
        select(
            subq0.c.version,
            subq0.c.date,
            subq0.c.status,
            func.count().label("status_sum")
        )
        .group_by(subq0.c.status, subq0.c.date, subq0.c.version)
        # .order_by(subq.c.date.desc(), subq.c.version.desc())
        .subquery()
        )

    complete = case((subq1.c.status == 'C', subq1.c.status_sum), else_=0)
    failed = case((subq1.c.status == 'F', subq1.c.status_sum), else_=0)
    suspended = case((subq1.c.status == 'S', subq1.c.status_sum), else_=0)
    incomplete = case((subq1.c.status == 'R', subq1.c.status_sum), else_=0)

    async with gen_session() as session:

        # Group subquery into groups composed of:
        # <version> <date> <status> <count>
        date = await session.execute(
            select(
                subq1.c.version,
                subq1.c.date,
                func.max(complete).label('complete'),
                func.max(failed).label('failed'),
                func.max(suspended).label('suspended'),
                func.max(incomplete).label('incomplete')
            )
            .group_by(subq1.c.version, subq1.c.date)
            .order_by(subq1.c.version.desc(), subq1.c.date.desc())
        )
    return date.all()


async def verify_token(token: str, require_root: bool = False) -> tuple[bool, list[str]]:
    '''Query table for usage access'''
    from sqlalchemy import select
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
