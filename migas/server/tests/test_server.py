import os
from typing import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from ..app import create_app
from ..database import add_new_project
from ..connection_context import (
    isolated_connection_context,
    set_connection_context,
    ConnectionContext,
)

if not os.getenv('MIGAS_REDIS_URI'):
    pytest.skip(reason='Could not establish redis connection', allow_module_level=True)

if not (
    os.getenv('DATABASE_URL')
    or all(
        [os.getenv('DATABASE_USER'), os.getenv('DATABASE_PASSWORD'), os.getenv('DATABASE_NAME')]
    )
):
    pytest.skip(reason='Could not establish postgres connection', allow_module_level=True)

TEST_PROJECT = 'nipreps/migas-server'


async def create_db(app):
    """Helper function to register a project on application startup."""
    from ..connections import get_redis_connection

    cache = await get_redis_connection()
    await cache.flushdb()
    await add_new_project(TEST_PROJECT)


queries = {
    'add_project': f'mutation{{add_project(p:{{project:"{TEST_PROJECT}",project_version:"0.5.0",language:"python",language_version:"3.12"}})}}'
}


# Test client
@pytest.fixture(scope='function')
def client() -> Iterator[TestClient]:
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


def test_server_landing(client: TestClient) -> None:
    res = client.get('/')
    assert res.status_code == 200
    assert 'html' in res.headers.get('Content-Type')


def test_server_info(client: TestClient) -> None:
    res = client.get('/info')
    assert res.status_code == 200
    obj = res.json()
    assert obj['package'] == 'migas'
    assert obj['geoloc_enabled'] is False


@pytest.mark.parametrize('query', [queries['add_project']])
def test_graphql_add_project(query: str, client: TestClient) -> None:
    res = client.post('/graphql', json={'query': query})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output


def test_graphql_big_request(client: TestClient) -> None:
    res = client.post(
        '/graphql', json={'query': queries['add_project'].replace('python', 'x' * 5000)}
    )
    assert res.status_code == 413
    errors = res.json()['errors']
    assert 'exceeds maximum size' in errors[0]['message']


def test_graphql_overload(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delitem(os.environ, 'MIGAS_BYPASS_RATE_LIMIT')
    monkeypatch.setitem(os.environ, 'MIGAS_MAX_REQUESTS_PER_WINDOW', '5')  # Cap # of requests
    client.post('/graphql', json={'query': queries['add_project']})
    for _ in range(5):
        res = client.post('/graphql', json={'query': queries['add_project']})
        assert res.status_code == 200
    # anything more is not
    res = client.post('/graphql', json={'query': queries['add_project']})
    assert res.status_code == 429
