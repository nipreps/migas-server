import typing
import strawberry
from strawberry.permission import BasePermission

from ..database import verify_token


class RequireRoot(BasePermission):
    message = "User is not authenticated"

    async def has_permission(
        self, source: typing.Any, info: strawberry.Info, **kwargs
    ) -> bool:
        request = info.context["request"]
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        # Fallback: try to get token from query params
        if not token:
            token = request.query_params.get("auth")
        if not token:
            return False
        return await verify_token(token, require_root=True)
