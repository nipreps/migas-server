"""FastAPI dependencies for REST API endpoints."""

from fastapi import HTTPException, Request

from ..database import authenticate_token
from ..extensions.ratelimit import RateLimitError, check_rate_limit, check_request_size


async def require_root(request: Request) -> None:
    """Verify the request carries a valid root-level Bearer token.

    Raises HTTPException(401) if the token is missing, invalid, or
    does not have root privileges.
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing or malformed Authorization header.')

    token = auth_header.split(' ', 1)[1]
    valid, projects = await authenticate_token(token, require_root=True)
    if not valid or not projects:
        raise HTTPException(status_code=401, detail='Invalid or insufficient token.')


async def rate_limit(request: Request) -> None:
    try:
        await check_rate_limit(request)
        await check_request_size(request)
    except RateLimitError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
