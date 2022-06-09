import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from etelemetry_app.server.connections import get_redis_connection
from etelemetry_app.server.database import (
    insert_project_data,
    query_or_insert_geoloc,
    query_project_by_datetimes,
    query_projects,
)
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
    async def get_projects(self) -> list[str]:
        '''Return projects that are being tracked'''
        projs = await query_projects()
        return projs

    # This is the query we want!
    # @strawberry.field
    # async def get_project_from_name(self, name: str) -> Project:

    # and this!
    @strawberry.field
    async def from_date_range(
        self,
        pid: str,
        start: DateTime,
        end: DateTime = None,
        unique: bool = False,
    ) -> int:
        '''
        Query project uses.

        `start` and `end` can be in either of the following formats:
        - `YYYY-MM-DD`
        - `YYYY-MM-DDTHH:MM:SSZ'

        If `endtime` is not provided, current time is used.
        If `unique`, only unique users will be included.
        '''

        if end is None:
            end = now()
        # TODO: add unique support
        count = await query_project_by_datetimes(pid, start, end)
        # Currently returns a count of matches.
        # This can probably be expanded into a dedicated strawberry type
        return count


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

        project_key = f'{project.owner}/{project.repo}'
        fetched = await fetch_project_info(project_key)

        # return project info ASAP, assign data ingestion as a background task
        request = info.context['request']
        bg_tasks = info.context['background_tasks']
        bg_tasks.add_task(query_or_insert_geoloc, request.client.host)
        bg_tasks.add_task(insert_project_data, project)

        return {
            'bad_versions': fetched['bad_versions'],
            'cached': fetched['cached'],
            'latest_version': fetched['version'],
            'message': '',  # TODO: Allow message for bad_versions
            'success': fetched['success'],
        }


SCHEMA = strawberry.Schema(query=Query, mutation=Mutation)
