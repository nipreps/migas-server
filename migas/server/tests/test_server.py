import asyncio
import os
from typing import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from ..app import app

if not os.getenv("MIGAS_REDIS_URI"):
    pytest.skip(allow_module_level=True)

os.environ["MIGAS_BYPASS_RATE_LIMIT"] = "1"

queries = {
    'add_project': 'mutation{add_project(p:{project:"github/fetch",project_version:"3.6.2",language:"javascript",language_version:"1.7"})}',
}


@pytest.fixture(scope="module")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test client
@pytest.fixture(scope="module")
def client(event_loop: asyncio.BaseEventLoop) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_server_landing(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert 'html' in res.headers.get("Content-Type")


def test_server_info(client: TestClient) -> None:
    res = client.get("/info")
    assert res.status_code == 200
    assert res.json()["package"] == "migas"


@pytest.mark.parametrize(
    'query',
    [
        queries['add_project'],
    ],
)
def test_graphql_add_project(query: str, client: TestClient) -> None:
    res = client.post("/graphql", json={'query': query})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output


def test_graphql_big_request(client: TestClient) -> None:
    res = client.post(
        "/graphql", json={'query': queries['add_project'].replace('javascript', 'x' * 5000)}
    )
    assert res.status_code == 413
    errors = res.json()['errors']
    assert 'exceeds maximum size' in errors[0]['message']


def test_graphql_overload(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delitem(os.environ, 'MIGAS_BYPASS_RATE_LIMIT')
    monkeypatch.setitem(os.environ, 'MIGAS_MAX_REQUESTS_PER_WINDOW', 5)  # Cap # of requests
    client.post("/graphql", json={'query': queries['add_project']})
    for i in range(0, 5):
        res = client.post("/graphql", json={'query': queries['add_project']})
        res.status_code == 200
    # anything more is not
    res = client.post("/graphql", json={'query': queries['add_project']})
    assert res.status_code == 429
