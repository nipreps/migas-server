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


@router.get('/usage/{project:path}', response_model=list[UsageData])
async def get_usage(project: str, request: Request, _auth=Depends(require_access())):
    if not await project_exists(project):
        raise HTTPException(status_code=404, detail=f'Project {project} not found.')

    redis = request.app.cache
    cache_key = f'migas:viz:hist:{project}'

    # 1. Fetch from Redis
    historical = []
    last_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cached = await redis.get(cache_key)
    if cached:
        cached_data = json.loads(cached)
        historical = cached_data['data']
        last_date = datetime.fromisoformat(cached_data['last_date'])
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)

    # 48h provisional window
    provisional_boundary = now() - timedelta(hours=48)

    # 2. Delta update if needed
    if last_date < provisional_boundary:
        # Fill gap: (last_date, provisional_boundary]
        delta = await get_viz_data(
            project, start_ts=last_date + timedelta(milliseconds=1), end_ts=provisional_boundary
        )
        if delta:
            historical.extend(delta)

        # Update cache
        await redis.set(
            cache_key,
            json.dumps({'last_date': provisional_boundary.isoformat(), 'data': historical}),
        )
        last_date = provisional_boundary

    # 3. Provisional query (always fresh)
    provisional = await get_viz_data(project, start_ts=last_date + timedelta(milliseconds=1))

    return historical + provisional


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
