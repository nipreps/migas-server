import os
import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from .conftest import queries


def test_server_headers(client: TestClient) -> None:
    res = client.get('/')
    assert res.status_code == 200
    for header in ('X-Backend-Server', 'X-Backend-Geolocation', 'X-Backend-Mode'):
        assert header in res.headers
    assert res.headers['X-Backend-Server'].startswith('migas@')
    assert res.headers['X-Backend-Geolocation'] in ('true', 'false')
    assert res.headers['X-Backend-Mode'] in ('dev', 'production')


def test_server_landing(client: TestClient) -> None:
    res = client.get('/')
    assert res.status_code == 200
    assert 'html' in res.headers.get('Content-Type')


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
