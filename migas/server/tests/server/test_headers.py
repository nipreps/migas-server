"""Top-level HTTP surface: landing page, backend headers."""

from fastapi.testclient import TestClient


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
