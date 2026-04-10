import os
import typing as ty

import pytest
from fastapi.testclient import TestClient

from ..app import create_app
from ..fetchers import fetch_loc_dbs
from ..connection_context import set_connection_context, ConnectionContext

from .conftest import queries

pytestmark = pytest.mark.geoloc


async def setup_geoloc_test(app):
    from ..connections import get_redis_connection

    cache = await get_redis_connection()
    await cache.flushdb()
    await fetch_loc_dbs(app)


if not os.getenv('MIGAS_REDIS_URI'):
    pytest.skip(reason='Could not establish redis connection', allow_module_level=True)

if not (
    os.getenv('DATABASE_URL')
    or all(
        [os.getenv('DATABASE_USER'), os.getenv('DATABASE_PASSWORD'), os.getenv('DATABASE_NAME')]
    )
):
    pytest.skip(reason='Could not establish postgres connection', allow_module_level=True)


@pytest.fixture(scope='function')
def client() -> ty.Iterator[TestClient]:
    original_values = {
        'MIGAS_BYPASS_RATE_LIMIT': os.getenv('MIGAS_BYPASS_RATE_LIMIT'),
        'MIGAS_GEOLOC': os.getenv('MIGAS_GEOLOC'),
    }

    os.environ['MIGAS_BYPASS_RATE_LIMIT'] = '1'
    os.environ['MIGAS_GEOLOC'] = '1'

    # Create isolated context for this test
    test_context = ConnectionContext()
    original_context = set_connection_context(test_context)

    try:
        app = create_app(on_startup=setup_geoloc_test, close_connections=False)
        with TestClient(app, client=('8.8.8.8', 12345)) as c:
            yield c
    finally:
        # Restore original context
        set_connection_context(original_context)

        for key, value in original_values.items():
            if value is None:
                del os.environ[key]
                continue
            os.environ[key] = value


def test_geoloc_enabled(client: TestClient):
    res = client.get('/info')
    assert res.status_code == 200
    obj = res.json()
    assert obj['geoloc_enabled'] is True


@pytest.mark.parametrize('query', [queries['add_project']])
def test_graphql_add_project(query: str, client: TestClient) -> None:
    res = client.post('/graphql', json={'query': query})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output


def test_geoloc_lookup():
    import asyncio
    from ..fetchers import geoloc

    res = asyncio.run(geoloc('8.8.8.8'))
    assert res is not None
    assert res['country_code'] == 'US'
    assert 'continent_code' in res
