import os
import pytest
from datetime import datetime, timezone
from pathlib import Path
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


def auth_header(token: str) -> dict[str, str]:
    """Build a Bearer-auth header dict for a raw token."""
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def master_token() -> str:
    """Raw master token seeded by deploy/docker/init.sql."""
    return 'my_test_token'


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


async def _setup_geoloc(app):
    """on_startup hook for geoloc-marked tests: flush redis + load real mmdb."""
    from ..connections import get_redis_connection, get_mmdb_reader

    cache = await get_redis_connection()
    await cache.flushdb()

    geodb_dir = Path(os.getenv('MIGAS_GEOLOC_DIR', 'geodb')).absolute()
    if not (geodb_dir / 'city.mmdb').exists():
        import subprocess

        subprocess.run(['python3', 'scripts/download_geodbs.py', str(geodb_dir)], check=True)

    await get_mmdb_reader()


@pytest.fixture(scope='function')
def client(request, _redis_available, _postgres_available, mock_fetchers) -> Iterator[TestClient]:
    """Shared FastAPI test client. Honors the `geoloc` marker: when present,
    MIGAS_GEOLOC is enabled, the real mmdb reader is loaded on startup, and
    the TestClient is given a real source IP for lookups."""

    geoloc = request.node.get_closest_marker('geoloc') is not None

    tracked_keys = ['MIGAS_BYPASS_RATE_LIMIT']
    if geoloc:
        tracked_keys += ['MIGAS_GEOLOC', 'MIGAS_GEOLOC_DIR']
    original_values = {k: os.getenv(k) for k in tracked_keys}

    os.environ['MIGAS_BYPASS_RATE_LIMIT'] = '1'
    if geoloc:
        os.environ['MIGAS_GEOLOC'] = '1'
        geodb_dir = os.getenv('MIGAS_GEOLOC_DIR')
        if not geodb_dir or not (Path(geodb_dir) / 'city.mmdb').exists():
            os.environ['MIGAS_GEOLOC_DIR'] = str(Path('geodb').absolute())

    test_context = ConnectionContext()
    original_context = set_connection_context(test_context)

    try:
        if geoloc:
            app = create_app(on_startup=_setup_geoloc, close_connections=False)
            tc_kwargs = {'client': ('8.8.8.8', 12345)}
        else:
            app = create_app()
            tc_kwargs = {}
        with TestClient(app, **tc_kwargs) as c:
            yield c
    finally:
        set_connection_context(original_context)
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
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
def flush_redis():
    """Flush Redis before each test to prevent rate-limit and cache state leakage."""
    uri = os.getenv('MIGAS_REDIS_URI')
    if not uri:
        yield
        return
    import redis as sync_redis

    r = sync_redis.from_url(uri, decode_responses=True)
    r.flushdb()
    yield
    r.close()


@pytest.fixture
def mock_fetchers(request):
    """Stub fetchers.fetch_response so GitHub isn't hit during tests.

    Consumed by the `client` fixture below so every integration test that
    uses the FastAPI app picks it up automatically. The `network` marker
    opts out — those tests hit real GitHub.
    """
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
