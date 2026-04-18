import os
import pytest
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Import modules to ensure they can be patched
from .. import fetchers
from ..app import create_app
from ..connection_context import set_connection_context, ConnectionContext

TEST_PROJECT = 'nipreps/nipreps'

# Canonical UUIDs for tests — stable across runs, easy to eyeball in query output.
USER_A = '00000000-0000-0000-0000-00000000000a'
USER_B = '00000000-0000-0000-0000-00000000000b'
USER_C = '00000000-0000-0000-0000-00000000000c'
SESSION_1 = '11111111-1111-1111-1111-111111111111'
SESSION_2 = '22222222-2222-2222-2222-222222222222'
SESSION_3 = '33333333-3333-3333-3333-333333333333'


queries = {
    'add_project': f'mutation {{ add_project(p: {{project: "{TEST_PROJECT}", project_version: "0.5.0", language: "python", language_version: "3.12"}}) }}',
    'add_breadcrumb': f'mutation {{ add_breadcrumb(project: "{TEST_PROJECT}", project_version: "1.0.0", proc: {{status: C}}) }}',
    'get_usage': f'query {{ get_usage(project: "{TEST_PROJECT}") }}',
    'get_projects': 'query { get_projects }',
}


@pytest.fixture
def _redis_available():
    if not os.getenv('MIGAS_REDIS_URI'):
        pytest.skip('Could not establish redis connection')


@pytest.fixture
def _postgres_available():
    if not (
        os.getenv('DATABASE_URL')
        or all(
            [
                os.getenv('DATABASE_USER'),
                os.getenv('DATABASE_PASSWORD'),
                os.getenv('DATABASE_NAME'),
            ]
        )
    ):
        pytest.skip('Could not establish postgres connection')


@pytest.fixture(scope='function')
def client(_redis_available, _postgres_available) -> Iterator[TestClient]:
    import os

    original_values = {'MIGAS_BYPASS_RATE_LIMIT': os.getenv('MIGAS_BYPASS_RATE_LIMIT')}

    os.environ['MIGAS_BYPASS_RATE_LIMIT'] = '1'

    # Create isolated context for this test
    test_context = ConnectionContext()
    original_context = set_connection_context(test_context)

    try:
        app = create_app()
        with TestClient(app) as c:
            yield c
    finally:
        # Restore original context
        set_connection_context(original_context)

        for key, value in original_values.items():
            if value is None:
                del os.environ[key]
                continue
            os.environ[key] = value


class DBSeeder:
    """Test-data helper with defaulted fields.

    Hides the ~10-kwarg insert_crumb / insert_user signature behind a minimal
    call surface. Every method is async; each manages its own session.
    """

    def __init__(self, client):
        self._client = client

    async def register(self, name: str) -> None:
        from ..database import add_new_project

        await add_new_project(name)

    async def user(
        self,
        user_id: str,
        *,
        user_type: str = 'hash',
        platform: str = 'Linux-x86_64',
        container: str = 'unknown',
        geoloc_idx: int | None = None,
    ) -> None:
        from ..database import insert_user

        await insert_user(
            user_id=user_id,
            user_type=user_type,
            platform=platform,
            container=container,
            geoloc_idx=geoloc_idx,
        )

    async def crumb(
        self,
        project: str,
        *,
        status: str,
        session_id: str,
        user_id: str,
        timestamp: datetime | None = None,
        version: str = '1.0.0',
        language: str = 'python',
        language_version: str = '3.12',
        status_desc: str | None = None,
        error_type: str | None = None,
        error_desc: str | None = None,
        is_ci: bool = False,
        ensure_user: bool = True,
    ) -> None:
        from ..database import insert_crumb

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        if ensure_user:
            await self.user(user_id=user_id)
        await insert_crumb(
            project,
            version=version,
            language=language,
            language_version=language_version,
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id,
            status=status,
            status_desc=status_desc,
            error_type=error_type,
            error_desc=error_desc,
            is_ci=is_ci,
        )

    async def token(self, project: str) -> dict[str, str]:
        """Create a project-scoped token and return a ready-to-use auth header."""
        from ..database import create_token

        raw = await create_token(project)
        return {'Authorization': f'Bearer {raw}'}


@pytest.fixture
def db(client) -> DBSeeder:
    """Database-seeding helper; depends on `client` to ensure connection context is set."""
    return DBSeeder(client)


@pytest.fixture(autouse=True)
def mock_fetchers(request):
    if request.node.get_closest_marker('network'):
        yield None
        return

    with patch.object(fetchers, 'fetch_response', new_callable=AsyncMock) as mock_resp:

        async def fetch_response_side_effect(url, **kwargs):
            if 'releases/latest' in url:
                return 200, {'tag_name': 'v0.5.0'}
            if 'tags' in url:
                return 200, [{'name': 'v0.5.0'}]
            if '.migas.json' in url:
                return 200, {'bad_versions': []}
            return 200, {}

        mock_resp.side_effect = fetch_response_side_effect

        yield mock_resp
