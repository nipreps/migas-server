from collections import defaultdict
import os
import typing as ty

import strawberry
from fastapi import Request, Response
from graphql import ExecutionResult as GraphQLExecutionResult
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension
from strawberry.scalars import JSON
from strawberry.schema.config import StrawberryConfig
from strawberry.types import Info

from .connections import get_redis_connection
from .database import (
    get_viz_data,
    ingest_project,
    project_exists,
    query_projects,
    query_usage_by_datetimes,
    verify_token,
)
from .fetchers import fetch_project_info
from .models import get_project_tables
from .types import (
    AuthenticationResult,
    BreadcrumbResult,
    CheckProjectResult,
    Context,
    ContextInput,
    DateTime,
    Process,
    ProcessInput,
    Project,
    ProjectInput,
)
from .utils import now


@strawberry.type
class Query:
    @strawberry.field
    async def get_projects(self) -> list[str]:
        '''Return projects that are being tracked'''
        projs = await query_projects()
        return projs

    @strawberry.field
    async def check_project(self, project: str, project_version: str) -> CheckProjectResult:
        '''Check version of project for latest version, developer notes, etc.'''
        fetched = await fetch_project_info(project)
        is_flagged = project_version in fetched['bad_versions']
        return CheckProjectResult(
            success=fetched['success'],
            flagged=is_flagged,
            latest=fetched['version'],
            # TODO: Parse/relay message
        )

    @strawberry.field
    async def get_usage(
        self,
        project: str,
        start: DateTime,
        end: DateTime | None = None,
        unique: bool = False,
    ) -> JSON:
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
        exists = await project_exists(project)
        if not exists:
            count = 0
            message = f'Project "{project}" is not being tracked'
        else:
            project_table, _ = await get_project_tables(project, create=False)
            count = await query_usage_by_datetimes(project_table, start, end, unique)
            message = ''
        return {
            'hits': count,
            'message': message,
            'unique': unique,
            'success': exists,
        }

    @strawberry.field
    async def login(self, token: str) -> AuthenticationResult:
        valid, projects = await verify_token(token)
        if not valid:
            success = False
            msg = 'Authentication Error: token is either invalid or expired.'
        else:
            success = True
            msg = 'Authentication successful.'
        return AuthenticationResult(
            success=success,
            projects=projects,
            message=msg,
        )

    @strawberry.field
    async def usage_stats(
        self,
        project: str,
        token: str,
        version: str | None = None,
        date_group: str = 'month',  # TODO: Literal incompatibility with strawberry - enum?
    ) -> JSON:
        'Generate different usage information'
        _, projects = await verify_token(token)
        if project not in projects:
            raise Exception('Invalid token.')
        usage = await get_viz_data(project, version, date_group)

        data = {}
        for ver, date, comp, fail, susp, inc in usage:
            if ver not in data:
                data[ver] = {}
                data[ver]['date_grouping'] = date_group
                for f in ('dates', 'completed', 'failed', 'suspended', 'incomplete'):
                    data[ver][f] = []

            data[ver]['dates'].append(date)
            data[ver]['completed'].append(comp)
            data[ver]['failed'].append(fail)
            data[ver]['suspended'].append(susp)
            data[ver]['incomplete'].append(inc)
        return data


@strawberry.type
class Mutation:
    @strawberry.field
    async def add_breadcrumb(
        self,
        info: Info,
        project: str,
        project_version: str,
        language: str,
        language_version: str,
        ctx: ContextInput,
        proc: ProcessInput,
    ) -> BreadcrumbResult:
        if not '/' in project:
            return BreadcrumbResult(success=False)

        context = Context(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            platform=ctx.platform,
            container=ctx.container,
            is_ci=ctx.is_ci,
        )
        process = Process(
            status=proc.status,
            status_desc=proc.status_desc,
            error_type=proc.error_type,
            error_desc=proc.error_desc,
        )

        project = Project(
            project=project,
            project_version=project_version,
            language=language,
            language_version=language_version,
            timestamp=now(),
            context=context,
            process=process,
        )

        bg_tasks = info.context['background_tasks']
        bg_tasks.add_task(ingest_project, project)
        return BreadcrumbResult(success=True)


    @strawberry.field
    async def add_project(self, p: ProjectInput, info: Info) -> JSON:
        # validate project
        if not p.project or '/' not in p.project:
            return {'success': False}

        # convert to Project and set defaults
        project = Project(
            project=p.project,
            project_version=p.project_version,
            language=p.language,
            language_version=p.language_version,
            timestamp=now(),
            context=Context(
                user_id=p.user_id,
                session_id=p.session_id,
                user_type=p.user_type,
                platform=p.platform,
                container=p.container,
                is_ci=p.is_ci,
            ),
            process=Process(
                status=p.status,
                status_desc=p.status_desc,
                error_type=p.error_type,
                error_desc=p.error_desc,
            ),
        )

        fetched = await fetch_project_info(p.project)

        # return project info ASAP, assign data ingestion as background tasks
        bg_tasks = info.context['background_tasks']
        bg_tasks.add_task(ingest_project, project)

        return {
            'bad_versions': fetched['bad_versions'],
            'cached': fetched['cached'],
            'latest_version': fetched['version'],
            'message': '',  # TODO: Allow message for bad_versions
            'success': fetched['success'],
        }


class RateLimiter(SchemaExtension):
    """
    A GraphQL schema extension to implement sliding window rate limiting.

    This class has fine-grain control of the GraphQL execution stack.
    This extension verifies that incoming requests:
    - Have a reasonable sized request body
    - Are not clobbering the GQL endpoint
    """

    def __init__(self, *args, **kwargs):
        self.set_attrs()
        super().__init__(*args, **kwargs)

    def set_attrs(self):
        self.request_window = int(os.getenv("MIGAS_REQUEST_WINDOW", "60"))
        self.max_requests = int(os.getenv("MIGAS_MAX_REQUESTS_PER_WINDOW", "100"))
        self.max_request_size = int(os.getenv("MIGAS_MAX_REQUEST_SIZE", "2500"))

    async def on_operation(self):
        """
        Hook into the GraphQL request stack, and validate data at the start.
        """
        if os.getenv("MIGAS_TESTING"):
            self.set_attrs()
        request = self.execution_context.context['request']
        response = self.execution_context.context['response']
        if not os.getenv("MIGAS_BYPASS_RATE_LIMIT"):
            await self.sliding_window_rate_limit(request, response)
        # check request size
        body = await request.body()
        if len(body) > self.max_request_size:
            response.status_code = 413
            self.execution_context.result = GraphQLExecutionResult(
                data=None,
                errors=[
                    GraphQLError(
                        f'Request body ({len(body)}) exceeds maximum size ({self.max_request_size})'
                    )
                ],
            )
        yield  # any logic after yield for post operation


    async def sliding_window_rate_limit(self, request: Request, response: Response):
        """
        Use a sliding window to verify incoming responses are not overloading the server.

        Requests are checked to be in the range set by two environmental variables:
        `MIGAS_REQUEST_WINDOW` and `MIGAS_MAX_REQUESTS_PER_WINDOW`
        """
        import time

        cache = await get_redis_connection()
        # the sliding window key
        key = f'rate-limit-{request.client.host}'
        time_ = time.time()

        async with cache.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, time_ - self.request_window)
            pipe.zrange(key, 0, -1)
            pipe.zadd(key, {time_: time_})
            pipe.expire(key, self.request_window)
            res = await pipe.execute()

        timestamps = res[1]
        if len(timestamps) > self.max_requests:
            response.status_code = 429  # Too many requests
            self.execution_context.result = GraphQLExecutionResult(
                data=None,
                errors=[GraphQLError('Too many requests, wait a minute.')],
            )


SCHEMA = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[RateLimiter],
    config=StrawberryConfig(auto_camel_case=False),
)
