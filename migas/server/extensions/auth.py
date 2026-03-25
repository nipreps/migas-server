import typing
import strawberry
from strawberry.permission import BasePermission

from ..database import authenticate_token


class RequireRoot(BasePermission):
    message = 'User is not authenticated'

    async def has_permission(
        self, source: typing.Any, info: strawberry.Info, **kwargs
    ) -> bool:
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False

        token = auth_header.split(" ", 1)[1]
        valid, projects = await authenticate_token(token, require_root=True)
        return valid and len(projects) > 0
