from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from ..database import (
    add_new_project,
    create_token,
    get_tokens,
    ingest_project,
    project_exists,
    revoke_token,
)
from ..types import Context, Process, Project
from ..utils import now
from .deps import rate_limit, require_root
from .models import (
    BreadcrumbRequest,
    BreadcrumbResponse,
    IssueTokenRequest,
    RegisterRequest,
    RegisterResponse,
    RevokeTokenRequest,
    RevokeTokenResponse,
    TokenResponse,
    ListTokensResponse,
)

router = APIRouter(prefix='/api', tags=['api'])


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
        await ingest_project(project, ip)
    else:
        background_tasks.add_task(ingest_project, project, ip)

    return BreadcrumbResponse(success=True)


@router.post(
    '/admin/register', response_model=RegisterResponse, dependencies=[Depends(require_root)]
)
async def register_project(body: RegisterRequest):
    if await project_exists(body.project):
        return RegisterResponse(success=True, message='Project is already registered.')
    await add_new_project(body.project)
    return RegisterResponse(success=True, message='Project is now registered.')


@router.get(
    '/admin/list-tokens', response_model=ListTokensResponse, dependencies=[Depends(require_root)]
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
    '/admin/issue-token', response_model=TokenResponse, dependencies=[Depends(require_root)]
)
async def issue_token(body: IssueTokenRequest):
    if body.project == 'master':
        raise HTTPException(status_code=400, detail='Cannot issue tokens for the master project.')
    if not await project_exists(body.project):
        raise HTTPException(status_code=400, detail='Project is not registered.')
    token = await create_token(body.project, body.description)
    return TokenResponse(success=True, token=token, message='Token issued successfully.')


@router.post(
    '/admin/revoke-token', response_model=RevokeTokenResponse, dependencies=[Depends(require_root)]
)
async def revoke_token_endpoint(body: RevokeTokenRequest):
    revoked = await revoke_token(body.token)
    return RevokeTokenResponse(success=revoked)
