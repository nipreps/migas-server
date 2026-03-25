"""FastAPI dependencies for REST API endpoints."""

from fastapi import Depends, HTTPException, Request


async def require_root(request: Request) -> None:
    """Verify the request carries a valid root-level Bearer token.

    Raises HTTPException(401) if the token is missing, invalid, or
    does not have root privileges.
    """
    from ..database import authenticate_token

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing or malformed Authorization header.')

    token = auth_header.split(' ', 1)[1]
    valid, projects = await authenticate_token(token, require_root=True)
    if not valid or not projects:
        raise HTTPException(status_code=401, detail='Invalid or insufficient token.')
