from graphql import ExecutionResult as GraphQLExecutionResult, GraphQLError
import strawberry
from strawberry.extensions import Extension
from strawberry.scalars import JSON
from strawberry.schema.config import StrawberryConfig
from strawberry.types import Info

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
            project=p.project,
            project_version=p.project_version,
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

        fetched = await fetch_project_info(p.project)

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


class Watchdog(Extension):
    """
    An extension to the GraphQL schema.

    This class has fine-grain control of the GraphQL execution stack.


    Order of operations:

    GraphQL request start  # set max length for request body
    GraphQL parsing start
    GraphQL parsing end
    GraphQL validation start
    GraphQL validation end
    GraphQL execution start
    GraphQL resolve
    GraphQL execution end
    GraphQL request end
    """

    LOG = {}
    MAX_REQUEST_BYTES = 300  # TODO: Revisit this as testing goes on

    async def on_request_start(self):
        """
        Ensure requests are:
        - decently sized
        - not from the same user
        """
        request = self.execution_context.context['request']
        # rate limit first
        # this PoC uses a python dictionary to track # of times a user visited this endpoint
        # TODO: Implement leaky bucket rate limiter with redis
        rip = request.client.host
        if rip in self.LOG:
            self.LOG[rip] += 1
            if self.LOG[rip] > 3:
                self.execution_context.context['response'].status_code = 429  # Too many requests
                self.execution_context.result = GraphQLExecutionResult(
                    data=None,
                    errors=[GraphQLError('Too many requests')],
                )
                return
        else:
            self.LOG[rip] = 1

        # check request size
        body = await request.body()
        if len(body) > self.MAX_REQUEST_BYTES:
            self.execution_context.context['response'].status_code = 413
            self.execution_context.result = GraphQLExecutionResult(
                data=None,
                errors=[GraphQLError(
                    f'Request body ({len(body)}) exceeds maximum size ({self.MAX_REQUEST_BYTES})'
                )],
            )
            return


SCHEMA = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[Watchdog],
    config=StrawberryConfig(auto_camel_case=False),
)
