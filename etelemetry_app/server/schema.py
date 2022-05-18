import typing

import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from etelemetry_app.server.database import insert_project_data, query_or_insert_geoloc
from etelemetry_app.server.fetchers import fetch_project_info
from etelemetry_app.server.types import (
    Context,
    DateTime,
    Process,
    Project,
    ProjectInput,
)
from etelemetry_app.server.utils import now


@strawberry.type
class Query:
    @strawberry.field
    async def get_projects(self, info: Info) -> typing.List[Project]:
        request = info.context['request']
        print(f"Hello person at {request.client.host}!")
        return PROJECTS

    # # This is the query we want!
    # @strawberry.field
    # async def get_project_from_name(self, name: str) -> Project:
    #     for p in PROJECTS:
    #         if p.name == name:
    #             return p

    # and this!
    # @strawberry.field
    # async def from_date_range(
    #     self, date0: DateTime, date1: DateTime = None
    # ) -> typing.List[Project]:
    #     # date0 = Date.str_to_dt(date0)
    #     if date1 is None:
    #         date1 = now()

    #     # TEST: this will be replaced by a much more efficient database query
    #     projects = []
    #     for p in PROJECTS:
    #         date = p.timestamp
    #         if date0 < date < date1:
    #             projects.append(p)

    #     return projects


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def add_project(self, p: ProjectInput, info: Info) -> JSON:

        # convert to Project and set defaults
        project = Project(
            owner=p.owner,
            repo=p.repo,
            version=p.version,
            language=p.language,
            language_version=p.language_version,
            session=p.session,
            timestamp=now(),
            context=Context(
                user_id=p.user_id,
                user_type=p.user_type,
                platform=p.platform,
                container=p.container,
            ),
            process=Process(status=p.status),
        )
        # PROJECTS.append(project)
        request = info.context['request']
        print(f"Hello person at {request.client.host}!")
        fetched = await fetch_project_info(p.owner, p.repo)

        # we should return the
        # most up to date version
        # as soon as possible >>
        # For the rest of the behavior,
        # add as FastAPI background tasks:
        # - geoloc lookup
        # - adding to database
        bg_tasks = info.context["background_tasks"]
        bg_tasks.add_task(query_or_insert_geoloc, request.client.host)
        bg_tasks.add_task(insert_project_data, project)

        return {
            "success": True,
            "latest_version": fetched["version"],
            "bad_versions": [],
            "message": [],
        }


SCHEMA = strawberry.Schema(query=Query, mutation=Mutation)
