import typing
import strawberry
from strawberry.permission import BasePermission

from fastapi import HTTPException
from ..auth import get_authorized_projects


class RequireRoot(BasePermission):
    message = 'User is not authenticated'

    async def has_permission(self, source: typing.Any, info: strawberry.Info, **kwargs) -> bool:
        request = info.context['request']
        try:
            await get_authorized_projects(request, require_root=True)
            return True
        except HTTPException:
            return False
