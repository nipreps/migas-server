import typing

import strawberry
from strawberry.types import Info

from app.server.types import (
    Context,
    DateTime,
    Environment,
    ProcessStatus,
    Project,
    User,
)
from app.server.utils import now, str_to_dt

# Just for testing
PROJECTS = [
    Project('mgxd', 'test', '1.0', 'python', '3.10.4', str_to_dt("2022-03-28T13:04:24Z")),
    Project(
        'git',
        'hub',
        '2.0',
        'python',
        '3.8.3',
        str_to_dt("2022-04-28T13:04:24Z"),
        Context('darwin', user=0),
    ),
    Project(
        'nipy',
        'nipype',
        '0.5',
        'python',
        '2.7.14',
        str_to_dt("2022-04-21T13:04:24Z"),
        Context('linux', 1, 2),
    ),
    Project(
        'nipreps',
        'nibabies',
        '22.0.2',
        'python',
        '3.9.10',
        str_to_dt("2022-04-28T13:00:24Z"),
        Context(user=1),
    ),
]


@strawberry.type
class Query:
    @strawberry.field
    def get_projects(self, info: Info) -> typing.List[Project]:
        request = info.context['request']
        print(f"Hello person at {request.client.host}!")
        return PROJECTS

    # This is the query we want!
    @strawberry.field
    def get_project_from_name(self, name: str) -> Project:
        for p in PROJECTS:
            if p.name == name:
                return p

    # and this!
    @strawberry.field
    def from_date_range(self, date0: DateTime, date1: DateTime = None) -> typing.List[Project]:
        # date0 = Date.str_to_dt(date0)
        if date1 is None:
            date1 = now()

        # TEST: this will be replaced by a much more efficient database query
        projects = []
        for p in PROJECTS:
            date = p.timestamp
            if date0 < date < date1:
                projects.append(p)

        return projects


@strawberry.type
class Mutation:
    @strawberry.mutation
    def add_project(
        self,
        owner: str,
        repo: str,
        version: str,
        language: str,
        language_version: str,
    ) -> Project | None:

        p = Project(owner, repo, version, language, language_version, now())
        print(f"Adding project {owner}/{repo} to DB")
        PROJECTS.append(p)
        return p


SCHEMA = strawberry.Schema(query=Query, mutation=Mutation)
