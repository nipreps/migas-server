"""FastAPI dependencies for REST API endpoints."""

from fastapi import HTTPException, Request

from ..extensions.ratelimit import RateLimitError, check_rate_limit, check_request_size
from ..auth import get_authorized_projects


def require_access(root: bool = False):
    """Dependency factory to verify token access.

    If root=True, ensures the token has master privileges.
    If root=False, ensures the token has access to the 'project' path parameter.
    """

    async def _require_access(request: Request, project: str | None = None) -> None:
        projects = await get_authorized_projects(request, require_root=root)
        if not root and project:
            if project not in projects and '*' not in projects:
                raise HTTPException(
                    status_code=403, detail=f'Token does not have access to project {project}.'
                )

    return _require_access


async def rate_limit(request: Request) -> None:
    try:
        await check_rate_limit(request)
        await check_request_size(request)
    except RateLimitError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
