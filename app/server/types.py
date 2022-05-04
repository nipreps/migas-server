"""Custom types"""

import json
import typing
from datetime import datetime
from enum import Enum
from uuid import UUID

import strawberry
from graphql.utilities import value_from_ast_untyped
from packaging.version import Version as _Version
from packaging.version import parse as parse_version

# from strawberry.scalars import Base64, JSON
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

# Version must be PEP440 compliant
Version = scalar(
    _Version,
    name="Version",
    description="Version information (PEP440 compliant)",
    serialize=lambda v: str(v),
    parse_value=parse_version,
)

# Arguments = scalar(
#     str,
#     name="Argument",
#     description="Argument/Value pairs",
#     serialize=json.dumps,
#     parse_value=json.loads
# )
Arguments = scalar(
    typing.NewType("JSONScalar", typing.Any),
    serialize=lambda v: json.dumps(v),
    parse_value=lambda v: json.loads(v),
    parse_literal=value_from_ast_untyped,
)


@strawberry.enum
class Container(Enum):
    unknown = 0
    docker = 1
    apptainer = 2


@strawberry.enum
class User(Enum):
    general = 0
    dev = 1
    ci = 2


@strawberry.enum
class Status(Enum):
    pending = 2
    success = 0
    error = 1


# @strawberry.type
# class Argument:
#     name: str
#     value: str

# @strawberry.type
# class Arguments:
#     typing.List[Argument]


@strawberry.type
class Process:
    status: Status = Status.pending
    # args: Arguments = "{}"


@strawberry.type
class Context:
    user_id: str | None = None
    user_type: User = User.general
    platform: str = "unknown"
    container: Container = Container.unknown


@strawberry.type
class Project:
    owner: str
    repo: str
    version: Version
    language: str
    language_version: Version
    timestamp: DateTime
    # optional
    session: UUID | None = None
    context: Context | None = None
    process: Process = Process


@strawberry.input
class ProjectInput:
    owner: str = strawberry.field(description="GitHub name that owns the project")
    repo: str = strawberry.field(description="GitHub repository name of the project")
    version: Version = strawberry.field(description="Project version being used")
    language: str = strawberry.field(description="Programming language of project")
    language_version: Version = strawberry.field(description="Programming language version")
    # optional
    session: str = strawberry.field(description="Unique identifier for run", default=None)
    # context args
    user_id: str = strawberry.field(description="GitHub repository name", default=None)
    user_type: 'User' = strawberry.field(
        description="GitHub repository name", default=User.general
    )
    platform: str = strawberry.field(description="Unique identifier for run", default=None)
    container: 'Container' = strawberry.field(
        description="Unique identifier for run", default=Container.unknown
    )
    # process args
    status: 'Status' = strawberry.field(
        description="Unique identifier for run", default=Status.pending
    )
    arguments: Arguments = strawberry.field(
        description="Unique identifier for run", default_factory=lambda: "{}"
    )


## Example Data store

PROJECTS = [
    Project('mgxd', 'test', '1.0', 'python', '3.10.4', str_to_dt("2022-03-28T13:04:24Z")),
    Project(
        'git',
        'hub',
        '2.0',
        'python',
        '3.8.3',
        str_to_dt("2022-04-28T13:04:24Z"),
        Context(platform='darwin', user_type=0),
    ),
    Project(
        'nipy',
        'nipype',
        '0.5',
        'python',
        '2.7.14',
        str_to_dt("2022-04-21T13:04:24Z"),
        Context(platform='linux', user_type=1, container=2),
    ),
    Project(
        'nipreps',
        'nibabies',
        '22.0.2',
        'python',
        '3.9.10',
        str_to_dt("2022-04-28T13:00:24Z"),
        Context(user_type=1),
    ),
]
