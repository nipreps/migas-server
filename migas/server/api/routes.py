import json
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from ..auth import get_authorized_projects
from ..database import (
    add_new_project,
    create_token,
    get_tokens,
    get_viz_data,
    ingest_project,
    project_exists,
    query_projects,
    revoke_token,
)
from ..types import Context, Process, Project
from ..utils import now
from .deps import rate_limit, require_access
from .models import (
    AuthProjectsResponse,
    BreadcrumbRequest,
    BreadcrumbResponse,
    IssueTokenRequest,
    RegisterRequest,
    RegisterResponse,
    RevokeTokenRequest,
    RevokeTokenResponse,
    TokenResponse,
    ListTokensResponse,
    UsageData,
)

router = APIRouter(prefix='/api', tags=['api'])
logger = logging.getLogger('migas')


@router.get('/auth/projects', response_model=AuthProjectsResponse)
async def auth_projects(request: Request):
    """Return the projects the caller's token is allowed to see.

    Used by the dashboard to populate the project selector after login. Master
    tokens get the enumerated list; scoped tokens get their single project.
    Token validity is communicated by status code (200 vs 401), not a body flag.
    """
    projects = await get_authorized_projects(request)
    if projects == ['*']:
        projects = await query_projects()
    return AuthProjectsResponse(projects=projects)


# Data within this window is too recent to cache — always fetched live.
# 48 h accounts for long-running pipeline sessions whose final breadcrumb
# may arrive well after the session started.
PROVISIONAL_HOURS = 48


def _utc(dt: datetime) -> datetime:
    """Coerce a naive datetime to UTC (guards against legacy cache values)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _read_cache(
    redis, cache_key: str
) -> tuple[list[dict], datetime | None, datetime | None]:
    """Deserialize a cached usage histogram.

    Returns ``(data, oldest_date, last_date)``.  Handles legacy entries
    that lack an ``oldest_date`` field.
    """
    raw = await redis.get(cache_key)
    if not raw:
        return [], None, None

    entry = json.loads(raw)
    data: list[dict] = entry['data']
    last_date = _utc(datetime.fromisoformat(entry['last_date']))

    if 'oldest_date' in entry:
        oldest_date = _utc(datetime.fromisoformat(entry['oldest_date']))
    elif data:
        # Legacy cache migration: derive from earliest row
        oldest_date = _utc(datetime.fromisoformat(min(r['date'] for r in data)))
    else:
        oldest_date = None

    return data, oldest_date, last_date


async def _write_cache(
    redis, cache_key: str, data: list[dict], oldest_date: datetime, last_date: datetime
) -> None:
    """Serialize a usage histogram into Redis."""
    await redis.set(
        cache_key,
        json.dumps(
            {
                'oldest_date': oldest_date.isoformat(),
                'last_date': last_date.isoformat(),
                'data': data,
            }
        ),
    )


async def _extend_historical(
    project: str,
    data: list[dict],
    oldest_date: datetime | None,
    last_date: datetime | None,
    requested_start: datetime,
    provisional_boundary: datetime,
) -> tuple[list[dict], datetime, datetime, bool]:
    """Fill cache gaps via backward extension and forward delta.

    Returns ``(data, oldest_date, last_date, dirty)``.
    """
    dirty = False

    # Backward extension — query only the uncached gap
    if oldest_date is None or oldest_date > requested_start:
        gap_end = oldest_date if oldest_date is not None else provisional_boundary
        logger.debug(
            'Backward extension for %s: querying %s → %s',
            project,
            requested_start.date(),
            gap_end.date(),
        )
        backward = await get_viz_data(project, start_ts=requested_start, end_ts=gap_end)
        if backward:
            data = backward + data
        oldest_date = requested_start
        # Advance last_date past the backward range so the forward-delta
        # step does not re-query data we just fetched.
        last_date = max(last_date, gap_end) if last_date is not None else gap_end
        dirty = True

    # Forward delta — fill from last cached date to provisional boundary
    if last_date < provisional_boundary:
        delta = await get_viz_data(
            project, start_ts=last_date + timedelta(milliseconds=1), end_ts=provisional_boundary
        )
        if delta:
            data.extend(delta)
        last_date = provisional_boundary
        dirty = True

    return data, oldest_date, last_date, dirty


@router.get('/usage/{project:path}', response_model=list[UsageData])
async def get_usage(
    project: str, request: Request, weeks: int = 1, _auth=Depends(require_access())
):
    if not await project_exists(project):
        raise HTTPException(status_code=404, detail=f'Project {project} not found.')

    start_time = now()
    redis = request.app.cache
    cache_key = f'migas:viz:hist:{project}'

    data, oldest_date, last_date = await _read_cache(redis, cache_key)
    logger.debug(
        'Cache %s for %s: oldest=%s last=%s rows=%d',
        'hit' if last_date is not None else 'miss',
        project,
        oldest_date.date() if oldest_date else None,
        last_date.date() if last_date else None,
        len(data),
    )

    requested_start = start_time - timedelta(weeks=weeks)
    provisional_boundary = start_time - timedelta(hours=PROVISIONAL_HOURS)

    data, oldest_date, last_date, dirty = await _extend_historical(
        project, data, oldest_date, last_date, requested_start, provisional_boundary
    )
    if dirty:
        await _write_cache(redis, cache_key, data, oldest_date, last_date)

    # Provisional — always fresh (too recent to cache)
    provisional = await get_viz_data(project, start_ts=last_date + timedelta(milliseconds=1))

    # Slice to requested window
    cutoff = requested_start.date().isoformat()
    return [r for r in data if r['date'] >= cutoff] + provisional


@router.post(
    '/breadcrumb',
    response_model=BreadcrumbResponse,
    status_code=202,
    dependencies=[Depends(rate_limit)],
    responses={
        200: {'model': BreadcrumbResponse, 'description': 'Synchronous ingestion (wait=true)'},
        400: {'description': 'Invalid or untracked project'},
    },
)
async def add_breadcrumb(
    body: BreadcrumbRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response,
    wait: bool = False,
):
    if '/' not in body.project:
        raise HTTPException(
            status_code=400, detail='Invalid project format (expected owner/repo).'
        )

    if not await project_exists(body.project):
        raise HTTPException(status_code=400, detail='Project is not registered.')

    context = Context(
        user_id=body.ctx.user_id,
        session_id=body.ctx.session_id,
        platform=body.ctx.platform,
        container=body.ctx.container,
        is_ci=body.ctx.is_ci,
    )
    process = Process(
        status=body.proc.status,
        status_desc=body.proc.status_desc,
        error_type=body.proc.error_type,
        error_desc=body.proc.error_desc,
    )
    project = Project(
        project=body.project,
        project_version=body.project_version,
        language=body.language,
        language_version=body.language_version,
        timestamp=now(),
        context=context,
        process=process,
    )

    ip = request.client.host if request.client else None

    if wait:
        try:
            await ingest_project(project, ip)
            response.status_code = 200
        except Exception as e:
            logger.error(f'Error ingesting project {project.project}: {e}')
            response.status_code = 500
            return BreadcrumbResponse(success=False, message='Error during ingestion.')
    else:
        background_tasks.add_task(ingest_project, project, ip)

    return BreadcrumbResponse(success=True)


@router.post(
    '/admin/register',
    response_model=RegisterResponse,
    dependencies=[Depends(require_access(root=True))],
)
async def register_project(body: RegisterRequest):
    if await project_exists(body.project):
        return RegisterResponse(success=True, message='Project is already registered.')
    await add_new_project(body.project)
    return RegisterResponse(success=True, message='Project is now registered.')


@router.get(
    '/admin/list-tokens',
    response_model=ListTokensResponse,
    dependencies=[Depends(require_access(root=True))],
)
async def list_tokens(project: str | None = None):
    from .models import TokenModel

    db_tokens = await get_tokens(project)
    tokens = [
        TokenModel(
            project=t.project,
            token=t.token,
            description=t.description,
            created_at=t.created_at,
            last_used=t.last_used,
        )
        for t in db_tokens
    ]
    return ListTokensResponse(success=True, tokens=tokens)


@router.post(
    '/admin/issue-token',
    response_model=TokenResponse,
    dependencies=[Depends(require_access(root=True))],
)
async def issue_token(body: IssueTokenRequest):
    if body.project == 'master':
        raise HTTPException(status_code=400, detail='Cannot issue tokens for the master project.')
    if not await project_exists(body.project):
        raise HTTPException(status_code=400, detail='Project is not registered.')
    token = await create_token(body.project, body.description)
    return TokenResponse(success=True, token=token, message='Token issued successfully.')


@router.post(
    '/admin/revoke-token',
    response_model=RevokeTokenResponse,
    dependencies=[Depends(require_access(root=True))],
)
async def revoke_token_endpoint(body: RevokeTokenRequest):
    revoked = await revoke_token(body.token)
    return RevokeTokenResponse(success=revoked)
