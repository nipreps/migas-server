"""GraphQL integration tests — operations against the /graphql endpoint."""

import os
import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from ..conftest import queries


@pytest.mark.parametrize(
    'variant',
    [
        pytest.param('mocked', id='mocked'),
        pytest.param('network', marks=pytest.mark.network, id='real-network'),
        pytest.param('geoloc', marks=pytest.mark.geoloc, id='real-geoloc'),
        pytest.param(
            'full', marks=[pytest.mark.network, pytest.mark.geoloc], id='real-network-and-geoloc'
        ),
    ],
)
def test_graphql_add_project(variant: str, client: TestClient) -> None:
    """add_project round-trip across the four marker combinations.

    The `client` fixture already honors the `geoloc` marker (loads real mmdb);
    the `mock_fetchers` autouse honors the `network` marker (real GitHub vs
    stubbed fetcher). So this one test covers what used to be four files.
    """
    res = client.post('/graphql', json={'query': queries['add_project']})
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
    monkeypatch.setitem(os.environ, 'MIGAS_MAX_REQUESTS_PER_WINDOW', '5')
    client.post('/graphql', json={'query': queries['add_project']})
    for _ in range(5):
        res = client.post('/graphql', json={'query': queries['add_project']})
        assert res.status_code == 200
    res = client.post('/graphql', json={'query': queries['add_project']})
    assert res.status_code == 429
