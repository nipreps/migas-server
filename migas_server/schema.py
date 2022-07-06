import os

from graphql import ExecutionResult as GraphQLExecutionResult, GraphQLError
from fastapi import Request, Response
import strawberry
from strawberry.extensions import Extension
from strawberry.scalars import JSON
from strawberry.schema.config import StrawberryConfig
from strawberry.types import Info

from migas_server.connections import get_redis_connection
from migas_server.database import (
    insert_project_data,
    query_or_insert_geoloc,
    query_project_by_datetimes,
    query_projects,
)
from migas_server.fetchers import fetch_project_info
from migas_server.types import (
    Context,
    DateTime,
    Process,
    Project,
    ProjectInput,
)
from migas_server.utils import now


@strawberry.type
class Query:
    @strawberry.field
    async def get_projects(self) -> list[str]:
        '''Return projects that are being tracked'''
        projs = await query_projects()
        return projs


    @strawberry.field
    async def get_usage(
        self,
        project: str,
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
        count = await query_project_by_datetimes(project, start, end)
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

        # return project info ASAP, assign data ingestion as background tasks
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
    This extension verifies that incoming requests:
    - Have a reasonable sized request body
    - Are not clobbering the GQL endpoint
    """

    REQUEST_WINDOW = 60
    MAX_REQUESTS_MINUTE = 5
    MAX_REQUEST_BYTES = 300  # TODO: Revisit this as testing goes on

    async def on_request_start(self):
        """
        Hook into the GraphQL request stack, and validate data at the start.
        """
        request = self.execution_context.context['request']
        response = self.execution_context.context['response']
        if not os.getenv("MIGAS_BYPASS_RATE_LIMIT", False):
            await self.sliding_window_rate_limit(request, response)
        # check request size
        body = await request.body()
        if len(body) > self.MAX_REQUEST_BYTES:
            response.status_code = 413
            self.execution_context.result = GraphQLExecutionResult(
                data=None,
                errors=[GraphQLError(
                    f'Request body ({len(body)}) exceeds maximum size ({self.MAX_REQUEST_BYTES})'
                )],
            )
            return


    async def sliding_window_rate_limit(self, request: Request, response: Response):
        """
        Use a sliding window to verify incoming responses are not overloading the server.

        Requests are checked to be in the range set by two attributes:
        `self.REQUEST_WINDOW` and `self.MAX_REQUESTS_MINUTE`
        """
        import time

        cache = await get_redis_connection()
        # the sliding window key
        key = f'rate-limit-{request.client.host}'
        time_ = time.time()

        async with cache.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, time_ - self.REQUEST_WINDOW)
            pipe.zrange(key, 0, -1)
            pipe.zadd(key, {time_: time_})
            pipe.expire(key, self.REQUEST_WINDOW)
            res = await pipe.execute()

        timestamps = res[1]
        if len(timestamps) >= self.MAX_REQUESTS_MINUTE:
            response.status_code = 429  # Too many requests
            self.execution_context.result = GraphQLExecutionResult(
                data=None,
                errors=[GraphQLError('Too many requests, wait a minute.')],
            )


SCHEMA = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[Watchdog],
    config=StrawberryConfig(auto_camel_case=False),
)
