from fastapi import HTTPException, Request
from .database import authenticate_token
from .utils import env_to_bool


async def get_authorized_projects(request: Request, require_root: bool = False) -> list[str]:
    """Extract token from request headers and return list of authorized projects.

    Raises HTTPException(401) if token is missing, invalid, or lacks required permissions.
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing or malformed Authorization header.')

    token = auth_header.split(' ', 1)[1]

    # Dev mode bypass
    if token == 'dev_token' and env_to_bool('MIGAS_DEV'):
        return ['*']

    valid, projects = await authenticate_token(token, require_root=require_root)
    if not valid or not projects:
        raise HTTPException(status_code=401, detail='Invalid or insufficient token.')

    return projects
