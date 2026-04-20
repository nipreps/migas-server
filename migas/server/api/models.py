"""Pydantic request/response models for REST API endpoints."""

from datetime import datetime

from pydantic import BaseModel
from ..types import Status, User, Container


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


class UsageData(BaseModel):
    date: str
    version: str
    status: str
    count: int
