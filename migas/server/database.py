import typing as ty
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert

from .connections import gen_session, AsyncSession
from .models import Table, get_project_tables, projects, GeoLoc, Authentication
from .types import Project, serialize
from .utils import now


async def add_new_project(project: str) -> bool:
    """Create new tables, and add project to master projects table."""
    ptable, utable = await get_project_tables(project, create=True)
    if ptable is None or utable is None:
        return False
    await insert_master(project)
    return True


# Table insertion
async def insert_master(project: str, session: AsyncSession | None = None) -> None:
    """Add project to master table."""
    async with gen_session(session) as session:
        await session.execute(insert(projects).on_conflict_do_nothing(), {'project': project})


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
    session: AsyncSession | None = None,
) -> None:
    """Add to project table"""
    async with gen_session(session) as session:
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


async def insert_user(
    users: Table,
    *,
    user_id: str,
    user_type: str,
    platform: str,
    container: str,
    asn_idx: int | None,
    city_idx: int | None,
    geoloc_idx: int | None,
    session: AsyncSession | None = None,
) -> None:
    async with gen_session(session) as session:
        await session.execute(
            insert(users).on_conflict_do_nothing(),
            {
                'user_id': user_id,
                'user_type': user_type,
                'platform': platform,
                'container': container,
                'asn_idx': asn_idx,
                'city_idx': city_idx,
                'geoloc_idx': geoloc_idx,
            },
        )


async def insert_query_geoloc(ip: str, session: AsyncSession | None = None) -> int | None:
    """
    Query geolocation database, and insert result into geoloc table if new.
    """
    from .fetchers import geoloc

    if not ip or ip == 'testclient':
        return None

    info = await geoloc(ip)
    if not info:
        return None

    async with gen_session(session) as session:
        # Check if already exists
        # We can use an on-conflict-do-update
        stmt = (
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
            .on_conflict_do_update(
                index_elements=['country_code', 'state_province_name', 'city_name', 'lat', 'lon'],
                set_={'asn': info.get('asn'), 'asn_org': info.get('aso')},
            )
            .returning(GeoLoc.idx)
        )

        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def ingest_project(project: Project, ip: str | None = None) -> None:
    """Dump information into database tables."""
    data = await serialize(project.__dict__)
    # check version lengths
    for vers in ('project_version', 'language_version'):
        if len(data[vers]) > 24:
            print(f'Shortening {project.project} version: {data[vers]}')
            data[vers] = data[vers][:24]

    ptable, utable = await get_project_tables(project.project, create=True)
    if ptable is None or utable is None:
        # Don't error but complain loudly
        # TODO: Log > print
        print(f'One or more missing tables:\n\n"Project table: {ptable}\nUsers table: {utable}')
        return

    geoloc_idx = await insert_query_geoloc(ip)
    async with gen_session() as session:
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
            session=session,
        )
        if data['context']['user_id'] is not None:
            await insert_user(
                utable,
                user_id=data['context']['user_id'],
                user_type=data['context']['user_type'],
                platform=data['context']['platform'],
                container=data['context']['container'],
                asn_idx=None,  # TODO: Remove these two
                city_idx=None,
                geoloc_idx=geoloc_idx,
                session=session,
            )


async def query_usage_by_datetimes(
    project: Table,
    start: datetime,
    end: datetime,
    session: AsyncSession | None = None,
    unique: bool = False,
) -> int:
    async with gen_session(session) as session:
        query = select(func.count()).where(
            project.c.timestamp >= start, project.c.timestamp <= end
        )
        if unique:
            query = select(func.count(distinct(project.c.user_id))).where(
                project.c.timestamp.between(start, end)
            )
        res = await session.execute(query)
        return res.scalar_one_or_none() or 0


async def query_usage(project: Table, session: AsyncSession | None = None) -> int:
    async with gen_session(session) as session:
        res = await session.execute(select(func.count(project.c.idx)))
        return res.scalars().one()


async def query_usage_unique(project: Table, session: AsyncSession | None = None) -> int:
    """TODO: What to do with all NULLs (unique users)?"""
    async with gen_session(session) as session:
        res = await session.execute(select(func.count(distinct(project.c.user_id))))
        return res.scalars().one()


async def query_projects(session: AsyncSession | None = None) -> list[str]:
    async with gen_session(session) as session:
        res = await session.execute(select(projects.c.project))
        return res.scalars().all()


async def project_exists(project: str, session: AsyncSession | None = None) -> bool:
    async with gen_session(session) as session:
        res = await session.execute(projects.select().where(projects.c.project == project))
        return bool(res.one_or_none())


async def get_viz_data(
    project_name: str,
    version: str | None = None,
    date_group: ty.Literal['day', 'week', 'month', 'year'] = 'month',
    session: AsyncSession | None = None,
) -> list:
    """
    Filter project usage into groups, based on versions and dates.
    """
    project, _ = await get_project_tables(project_name, create=True, session=session)

    if project is None:
        return []

    # Always use YYYY-MM-DD for the frontend to parse easily
    # date_trunc already returns the first day of the period
    date_trunc = func.date_trunc(date_group, project.c.timestamp)
    date_str = func.to_char(date_trunc, 'YYYY-MM-DD')

    subq0 = (
        select(project.c.version, project.c.session_id, date_str.label('date'), project.c.status)
        .distinct(project.c.session_id)
        .where(project.c.status.is_not(None))
        .order_by(project.c.session_id, project.c.timestamp.desc())
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
        select(subq0.c.version, subq0.c.date, subq0.c.status, func.count().label('count'))
        .group_by(subq0.c.status, subq0.c.date, subq0.c.version)
        .order_by(subq0.c.date.desc(), subq0.c.version.desc())
    )

    async with gen_session(session) as session:
        res = await session.execute(query)
        return [
            {'version': row[0], 'date': row[1], 'status': row[2], 'count': row[3]}
            for row in res.all()
        ]


async def valid_location_dbs(session: AsyncSession | None = None) -> tuple[bool, bool]:
    from .connections import get_mmdb_reader

    city, asn = await get_mmdb_reader()
    return asn is not None, city is not None


def hash_token(token: str) -> str:
    """Hash token using BLAKE2b (64 chars)."""
    import hashlib

    return hashlib.blake2b(token.encode(), digest_size=32).hexdigest()


async def _get_auth_by_token(
    token: str, session: AsyncSession | None = None
) -> Authentication | None:
    """Retrieve an Authentication record by token (hashed or unhashed)."""
    async with gen_session(session) as session:
        hashed = hash_token(token)
        res = await session.execute(
            select(Authentication).where(
                # In case legacy tokens are still unhashed
                # TODO: Remove this once all tokens are hashed
                (Authentication.token == hashed) | (Authentication.token == token)
            )
        )
        return res.scalar_one_or_none()


async def authenticate_token(
    token: str, require_root: bool = False, session: AsyncSession | None = None
) -> tuple[bool, list[str]]:
    """Verify token and return list of projects it has access to."""
    # verify project is within token scope
    valid, projects_list = False, []
    async with gen_session(session) as session:
        auth = await _get_auth_by_token(token, session)
        if not auth:
            return valid, projects_list

        auth.last_used = now()
        if auth.project == 'master':
            projects_list = await query_projects(session=session) or ['*']
            valid = True
        elif not require_root:
            projects_list = [auth.project]
            valid = True

    return valid, projects_list


async def get_tokens(
    project: str | None = None, session: AsyncSession | None = None
) -> list[Authentication]:
    """Retrieve tokens, optionally filtered by project."""

    async with gen_session(session) as session:
        stmt = select(Authentication)
        if project:
            stmt = stmt.where(Authentication.project == project)
        res = await session.execute(stmt)
        return res.scalars().all()


async def create_token(
    project: str, description: str | None = None, session: AsyncSession | None = None
) -> str:
    """Generate a new secure token and store its hash."""
    from secrets import token_urlsafe

    if project == 'master':
        raise ValueError('Cannot create new master tokens via this API.')

    raw_token = f'm_{token_urlsafe(32)}'
    hashed = hash_token(raw_token)

    async with gen_session(session) as session:
        new_auth = Authentication(project=project, token=hashed, description=description)
        session.add(new_auth)

    return raw_token


async def revoke_token(token: str, session: AsyncSession | None = None) -> bool:
    """Deactivate a token."""
    async with gen_session(session) as session:
        auth = await _get_auth_by_token(token, session)
        if auth and auth.project != 'master':
            await session.delete(auth)
            return True
    return False
