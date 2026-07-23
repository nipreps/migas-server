"""Pydantic request/response models for REST API endpoints."""

import re
from datetime import datetime

from pydantic import BaseModel, field_validator
from ..types import Status, User, Container
from typing import Any

# dash last so it is a literal, not a range
_VERSION_RE = re.compile(r'^[A-Za-z0-9._+-]+$')


def _validate_version(value: str) -> str:
    return value if _VERSION_RE.fullmatch(value) else 'unknown'


class ContextPayload(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    user_type: User = User.general
    platform: str = 'unknown'
    container: Container = Container.unknown
    is_ci: bool = False


class ProcessPayload(BaseModel):
    status: Status = Status.R
    status_desc: str | None = None
    error_type: str | None = None
    error_desc: str | None = None


class BreadcrumbRequest(BaseModel):
    project: str
    project_version: str
    language: str = 'python'
    language_version: str = '0.0.0'
    ctx: ContextPayload = ContextPayload()
    proc: ProcessPayload = ProcessPayload()
    params: dict[str, Any] | None = None
    _check_versions = field_validator('project_version', 'language_version')(_validate_version)


class BreadcrumbResponse(BaseModel):
    success: bool
    message: str = ''


class RegisterRequest(BaseModel):
    project: str


class RegisterResponse(BaseModel):
    success: bool
    message: str = ''


class IssueTokenRequest(BaseModel):
    project: str
    description: str | None = None


class TokenResponse(BaseModel):
    success: bool
    token: str | None = None
    message: str = ''


class RevokeTokenRequest(BaseModel):
    token: str


class RevokeTokenResponse(BaseModel):
    success: bool


class TokenModel(BaseModel):
    project: str
    token: str
    description: str | None = None
    created_at: datetime
    last_used: datetime | None = None


class ListTokensResponse(BaseModel):
    success: bool
    tokens: list[TokenModel]


class AuthProjectsResponse(BaseModel):
    """Projects accessible to the authenticated token.

    Status code already signals validity (200 OK vs 401), so no success flag.
    """

    projects: list[str]


class UsageData(BaseModel):
    date: str
    version: str
    status: str
    count: int
