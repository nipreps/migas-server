"""Custom types"""

import uuid
from datetime import datetime
from enum import Enum

import strawberry
from strawberry.custom_scalar import scalar

from app.server.utils import dt_to_str, str_to_dt

# Strawberry has a Date object, but etelemetry's time format
# slightly differs from datetime.datetime.isoformat()
DateTime = scalar(
    datetime,
    name="DateTime",
    description="Date and time information in UTC, compliant with ISO-8601",
    serialize=dt_to_str,
    parse_value=str_to_dt,
)


@strawberry.enum
class Environment(Enum):
    unknown = 0
    docker = 1
    apptainer = 2


@strawberry.enum
class User(Enum):
    general = 0
    dev = 1
    ci = 2


@strawberry.enum
class ProcessStatus(Enum):
    success = 0
    error = 1
    pending = 2


@strawberry.type
class Context:
    platform: str | None = None
    environment: Environment = Environment.unknown
    user: User = User.general


@strawberry.type
class Project:
    owner: str
    repo: str
    version: str
    language: str
    language_version: str
    timestamp: DateTime
    # optional
    session: uuid.UUID | None = None
    context: Context | None = None
