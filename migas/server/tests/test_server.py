import os
from typing import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from ..app import create_app
from ..database import add_new_project

if not os.getenv("MIGAS_REDIS_URI"):
    pytest.skip(allow_module_level=True)

os.environ["MIGAS_BYPASS_RATE_LIMIT"] = "1"
os.environ["MIGAS_TESTING"] = "1"

TEST_PROJECT = "nipreps/migas-server"

queries = {
    'add_project': f'mutation{{add_project(p:{{project:"{TEST_PROJECT}",project_version:"0.5.0",language:"python",language_version:"3.12"}})}}',
}

@pytest.fixture(scope="module")
def test_app():
    async def create_db(app):
        await add_new_project(TEST_PROJECT)

    app = create_app(on_startup=create_db)
    return app

# Test client
@pytest.fixture(scope="module")
def client(test_app) -> Iterator[TestClient]:
    with TestClient(test_app) as c:
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
        "/graphql", json={'query': queries['add_project'].replace('python', 'x' * 5000)}
    )
    assert res.status_code == 413
    errors = res.json()['errors']
    assert 'exceeds maximum size' in errors[0]['message']


def test_graphql_overload(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delitem(os.environ, 'MIGAS_BYPASS_RATE_LIMIT')
    monkeypatch.setitem(os.environ, 'MIGAS_MAX_REQUESTS_PER_WINDOW', '5')  # Cap # of requests
    client.post("/graphql", json={'query': queries['add_project']})
    for _ in range(5):
        res = client.post("/graphql", json={'query': queries['add_project']})
        assert res.status_code == 200
    # anything more is not
    res = client.post("/graphql", json={'query': queries['add_project']})
    assert res.status_code == 429
