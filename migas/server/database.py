import logging
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert

from .connections import gen_session, AsyncSession
from .models import User, Crumb, projects, GeoLoc, Authentication
from .types import Project, serialize
from .utils import now

logger = logging.getLogger('migas')


async def add_new_project(project: str) -> bool:
    """Add project to master projects table."""
    await insert_master(project)
    return True


# Table insertion
async def insert_master(project: str, session: AsyncSession | None = None) -> None:
    """Add project to master table."""
    async with gen_session(session) as session:
        await session.execute(insert(projects).on_conflict_do_nothing(), {'project': project})


async def insert_crumb(
    project: str,
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
    """Add to crumbs table"""
    async with gen_session(session) as session:
        await session.execute(
            insert(Crumb),
            {
                'project': project,
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
    *,
    user_id: str,
    user_type: str,
    platform: str,
    container: str,
    geoloc_idx: int | None,
    session: AsyncSession | None = None,
) -> None:
    """Add to users table (global users)"""
    async with gen_session(session) as session:
        await session.execute(
            insert(User).on_conflict_do_nothing(),
            {
                'user_id': user_id,
                'user_type': user_type,
                'platform': platform,
                'container': container,
                'geoloc_idx': geoloc_idx,
            },
        )


async def insert_query_geoloc(ip: str, session: AsyncSession | None = None) -> int | None:
    """
    Query geolocation database, and insert result into geoloc table if new.
    """
    from .fetchers import geoloc

    try:
        info = await geoloc(ip)
    except Exception as e:
        logger.error(f'Geolocation failed for IP {ip}: {e}')
        return None

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
            logger.warning(f'Shortening {project.project} version: {data[vers]}')
            data[vers] = data[vers][:24]

    if not await project_exists(project.project):
        logger.warning(f'Project {project.project} is not registered.')
        return

    geoloc_idx = await insert_query_geoloc(ip)
    async with gen_session() as session:
        # 1. Upsert user (for foreign key availability)
        if data['context']['user_id'] is not None:
            await insert_user(
                user_id=data['context']['user_id'],
                user_type=data['context']['user_type'],
                platform=data['context']['platform'],
                container=data['context']['container'],
                geoloc_idx=geoloc_idx,
                session=session,
            )

        # 2. Insert crumb
        await insert_crumb(
            project.project,
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


async def query_usage_by_datetimes(
    project_name: str,
    start: datetime,
    end: datetime,
    session: AsyncSession | None = None,
    unique: bool = False,
) -> int:
    async with gen_session(session) as session:
        if unique:
            query = select(func.count(distinct(Crumb.user_id))).where(
                Crumb.project == project_name, Crumb.timestamp.between(start, end)
            )
        else:
            query = select(func.count()).where(
                Crumb.project == project_name, Crumb.timestamp >= start, Crumb.timestamp <= end
            )
        res = await session.execute(query)
        return res.scalar_one_or_none() or 0


async def query_usage(project_name: str, session: AsyncSession | None = None) -> int:
    async with gen_session(session) as session:
        res = await session.execute(
            select(func.count(Crumb.idx)).where(Crumb.project == project_name)
        )
        return res.scalars().one()


async def query_usage_unique(project_name: str, session: AsyncSession | None = None) -> int:
    async with gen_session(session) as session:
        res = await session.execute(
            select(func.count(distinct(Crumb.user_id))).where(Crumb.project == project_name)
        )
        return res.scalars().one()


async def query_projects(session: AsyncSession | None = None) -> list[str]:
    async with gen_session(session) as session:
        # Exclude sentinel 'master' project from general queries
        res = await session.execute(
            select(projects.c.project).where(projects.c.project != 'master')
        )
        return res.scalars().all()


async def project_exists(project: str, session: AsyncSession | None = None) -> bool:
    async with gen_session(session) as session:
        res = await session.execute(projects.select().where(projects.c.project == project))
        return bool(res.one_or_none())


async def get_viz_data(
    project_name: str,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    session: AsyncSession | None = None,
) -> list:
    """Day-bucketed session counts per (version, status).

    Sessions are bucketed by their START date (MIN(timestamp)).
    Status and version are read from the LATEST crumb (MAX(timestamp)).
    Pre-release and build-metadata versions (containing ``rc`` or ``+``) are excluded.
    """

    # Stage 1: per-session start date and latest timestamp
    subq_bounds = select(
        Crumb.session_id,
        func.min(Crumb.timestamp).label('start_ts'),
        func.max(Crumb.timestamp).label('last_ts'),
    ).where(Crumb.project == project_name)

    if start_ts:
        # Use the (project, timestamp) index: push the filter down, then
        # look back 30 days to guarantee we see the true MIN for any session
        # whose start may qualify for the HAVING clause.
        subq_bounds = subq_bounds.where(Crumb.timestamp >= start_ts - timedelta(days=30))

    subq_bounds = subq_bounds.group_by(Crumb.session_id)

    if start_ts and end_ts:
        subq_bounds = subq_bounds.having(
            (func.min(Crumb.timestamp) >= start_ts) & (func.min(Crumb.timestamp) <= end_ts)
        )
    elif start_ts:
        subq_bounds = subq_bounds.having(func.min(Crumb.timestamp) >= start_ts)
    elif end_ts:
        subq_bounds = subq_bounds.having(func.min(Crumb.timestamp) <= end_ts)

    subq_bounds = subq_bounds.subquery()

    # Stage 2: join back for version + status of the latest crumb; drop pre-releases.
    subq_latest = (
        select(subq_bounds.c.session_id, subq_bounds.c.start_ts, Crumb.version, Crumb.status)
        .join(
            Crumb,
            (Crumb.session_id == subq_bounds.c.session_id)
            & (Crumb.timestamp == subq_bounds.c.last_ts)
            & (Crumb.project == project_name),
        )
        .where(Crumb.version.not_like('%+%'))
        .where(Crumb.version.not_like('%rc%'))
        .subquery()
    )

    # Stage 3: bucket by start date (day granularity); client rolls up further if needed.
    date_bucket = func.date_trunc('day', subq_latest.c.start_ts)
    date_str = func.to_char(date_bucket, 'YYYY-MM-DD').label('date')

    query = (
        select(
            subq_latest.c.version.label('version'),
            date_str,
            subq_latest.c.status.label('status'),
            func.count(distinct(subq_latest.c.session_id)).label('count'),
        )
        .group_by(date_bucket, subq_latest.c.version, subq_latest.c.status)
        .order_by(date_bucket.desc(), subq_latest.c.version.desc())
    )

    async with gen_session(session) as session:
        res = await session.execute(query)
        return [
            {'version': row.version, 'date': row.date, 'status': row.status, 'count': row.count}
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
