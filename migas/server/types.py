"""Custom types"""

import json
import typing
from datetime import datetime
from enum import Enum
from uuid import UUID

# from strawberry.scalars import Base64, JSON
import strawberry
from graphql.utilities import value_from_ast_untyped
from packaging.version import Version as _Version
from packaging.version import _BaseVersion
from packaging.version import parse as parse_version
from strawberry.custom_scalar import scalar

from .utils import dt_to_str, str_to_dt

# Strawberry has a Date object, but migas's time format
# slightly differs from datetime.datetime.isoformat()
DateTime = scalar(
    datetime,
    name="DateTime",
    description="Date and time information in UTC, compliant with ISO-8601",
    serialize=dt_to_str,
    parse_value=str_to_dt,
)

# Version must be PEP440 compliant
Version = scalar(
    _Version,
    name="Version",
    description="Version information (PEP440 compliant)",
    serialize=lambda v: str(v),
    parse_value=parse_version,
)


@strawberry.enum
class Container(Enum):
    unknown = 'unknown'
    docker = 'docker'
    apptainer = 'apptainer'


@strawberry.enum
class User(Enum):
    general = 'general'
    dev = 'dev'
    ci = 'ci'


@strawberry.enum
class Status(Enum):
    R = 'R'
    running = strawberry.enum_value('R')
    C = 'C'
    completed = strawberry.enum_value('C')
    F = 'F'
    failed = strawberry.enum_value('F')
    S = 'S'
    suspended = strawberry.enum_value('S')

    # Deprecations, to be removed in 0.4.0
    pending = strawberry.enum_value('R', deprecation_reason="Pending is now running")
    success = strawberry.enum_value('C', deprecation_reason="Success is now completed")
    error = strawberry.enum_value('F', deprecation_reason="Error is now failed")


# @strawberry.type
# class Argument:
#     name: str
#     value: str

# @strawberry.type
# class Arguments:
#     typing.List[Argument]


@strawberry.type
class Process:
    status: Status = Status.running
    status_desc: str | None = None
    error_type: str | None = None
    error_desc: str | None = None
    # args: Arguments = "{}"


@strawberry.type
class Context:
    user_id: str | None = None
    session_id: str | None = None
    user_type: User = User.general
    platform: str = "unknown"
    container: Container = Container.unknown
    is_ci: bool = False


@strawberry.type
class Project:
    project: str
    project_version: Version
    language: str
    language_version: Version
    timestamp: DateTime
    # optional
    context: Context
    process: Process


@strawberry.input
class ContextInput:
    session_id: str | None = strawberry.field(
        description="Unique identifier for telemetry session", default=None
    )
    user_id: str | None = strawberry.field(description="Unique identifier for migas client", default=None)
    user_type: User = strawberry.field(
        description="Identifier of user role", default=User.general
    )
    platform: str = strawberry.field(description="Client platform type", default="unknown")
    container: Container = strawberry.field(
        description="Check if client pings from inside a container", default=Container.unknown
    )
    is_ci: bool = strawberry.field(
        description="Client is pinging from continous integration", default=False
    )

@strawberry.input
class ProcessInput:
    status: Status = strawberry.field(
        description="For timeseries pings, the current process status", default=Status.R
    )
    status_desc: str | None = strawberry.field(description="Description of status ping", default=None)
    error_type: str | None = strawberry.field(description="Type of error encountered", default=None)
    error_desc: str | None = strawberry.field(description="Description of error", default=None)


@strawberry.input
class ProjectInput:
    project: str = strawberry.field(description="GitHub project in the form of 'owner/repo'")
    project_version: Version = strawberry.field(description="Project version being used")
    language: str = strawberry.field(description="Programming language of project")
    language_version: Version = strawberry.field(description="Programming language version")
    # optional
    session_id: str | None = strawberry.field(
        description="Unique identifier for telemetry session", default=None
    )
    # context args
    user_id: str | None = strawberry.field(description="Unique identifier for migas client", default=None)
    user_type: User = strawberry.field(
        description="Identifier of user role", default=User.general
    )
    platform: str = strawberry.field(description="Client platform type", default="unknown")
    container: Container = strawberry.field(
        description="Check if client pings from inside a container", default=Container.unknown
    )
    is_ci: bool = strawberry.field(
        description="Client is pinging from continous integration", default=False
    )
    # process args
    status: Status = strawberry.field(
        description="For timeseries pings, the current process status", default=Status.R
    )
    status_desc: str | None = strawberry.field(description="Description of status ping", default=None)
    error_type: str | None = strawberry.field(description="Type of error encountered", default=None)
    error_desc: str | None = strawberry.field(description="Description of error", default=None)
    # arguments: Arguments = strawberry.field(
    #     description="Client side arguments used", default_factory=lambda: "{}"
    # )


@strawberry.type
class AuthenticationResult:
    success: bool
    projects: typing.List[str]
    message: str


async def serialize(data: dict) -> dict:
    """Serialize data into database-friendly types"""
    for k, v in data.items():
        # TODO: Is this possible with PEP636?
        # I gave up trying it
        if isinstance(v, _BaseVersion):
            data[k] = str(v)
        elif isinstance(v, Enum):
            data[k] = v.value
        # datetime ok?
        elif isinstance(v, (Context, Process)):
            data[k] = await serialize(v.__dict__)
    return data
