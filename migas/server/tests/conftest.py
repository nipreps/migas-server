import os
import pytest
from typing import Iterator
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Import modules to ensure they can be patched
from .. import fetchers, connections
from ..app import create_app
from ..database import add_new_project
from ..connection_context import set_connection_context, ConnectionContext

TEST_PROJECT = 'nipreps/migas-server'


async def create_db(_):
    """Helper function to register a project on application startup."""
    from ..connections import get_redis_connection

    cache = await get_redis_connection()
    await cache.flushdb()
    await add_new_project(TEST_PROJECT)


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

    original_values = {
        'MIGAS_BYPASS_RATE_LIMIT': os.getenv('MIGAS_BYPASS_RATE_LIMIT'),
        'MIGAS_TESTING': os.getenv('MIGAS_TESTING'),
    }

    os.environ['MIGAS_BYPASS_RATE_LIMIT'] = '1'
    os.environ['MIGAS_TESTING'] = '1'

    # Create isolated context for this test
    test_context = ConnectionContext()
    original_context = set_connection_context(test_context)

    try:
        app = create_app(on_startup=create_db)
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


@pytest.fixture(autouse=True)
def mock_fetchers(request):
    if request.node.get_closest_marker('network'):
        yield None, None
        return

    with (
        patch.object(fetchers, 'fetch_response', new_callable=AsyncMock) as mock_resp,
        patch.object(fetchers, 'fetch_gzipped_bytes', new_callable=AsyncMock) as mock_gzip,
    ):

        async def fetch_response_side_effect(url, **kwargs):
            if 'releases/latest' in url:
                return 200, {'tag_name': 'v0.5.0'}
            if 'tags' in url:
                return 200, [{'name': 'v0.5.0'}]
            if '.migas.json' in url:
                return 200, {'bad_versions': []}
            return 200, {}

        mock_resp.side_effect = fetch_response_side_effect
        mock_gzip.return_value = b''

        yield mock_resp, mock_gzip


@pytest.fixture(autouse=True)
def mock_geoloc_db(request, tmp_path):
    """Bypass geolocation database downloads and loading in tests if missing."""
    if request.node.get_closest_marker('geoloc'):
        if not request.node.get_closest_marker('network'):
            from pathlib import Path

            if not Path('asn.mmdb').exists() or not Path('city.mmdb').exists():
                pytest.fail(
                    'Geolocation tests require the database files to exist locally. Run with `@pytest.mark.network` to download them, or download them manually.'
                )
        yield None, None
        return

    with (
        patch.object(fetchers, 'download_geoloc_db', new_callable=AsyncMock) as mock_download,
        patch.object(connections, 'get_mmdb_reader', new_callable=AsyncMock) as mock_reader,
    ):
        # Return a dummy path for download
        dummy_db = tmp_path / 'dummy.mmdb'
        dummy_db.write_bytes(b'')
        mock_download.return_value = dummy_db

        # Return None, None for readers to disable geoloc info but avoid errors
        mock_reader.return_value = (None, None)

        yield mock_download, mock_reader
