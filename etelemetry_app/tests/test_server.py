import os

from fastapi.testclient import TestClient
import pytest

from etelemetry_app.server.app import app


os.environ["ETELEMETRY_BYPASS_RATE_LIMIT"] = "1"

queries = {
    'add_project': 'mutation{add_project(p:{project:"github/fetch",project_version:"3.6.2",language:"javascript",language_version:"1.7"})}',
}


client = TestClient(app)

def test_server_startup_shutdown():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["package"] == "etelemetry"


@pytest.mark.parametrize(
    'resolver_str',
    [
        queries['add_project'],
    ],
)
def test_graphql_add_project(resolver_str):
    res = client.post("/graphql", json={'query': resolver_str})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output


def test_graphql_big_request():
    res = client.post(
        "/graphql", json={'query': queries['add_project'].replace('javascript', 'x' * 300)}
    )
    assert res.status_code == 413
    errors = res.json()['errors']
    assert 'exceeds maximum size' in errors[0]['message']


# def test_graphql_overload(monkeypatch):
#     monkeypatch.delitem(os.environ, 'ETELEMETRY_BYPASS_RATE_LIMIT')
#     client.post("/graphql", json={'query': queries['add_project']})
    # with client as client_:
    #     # 5 requests are fine
    #     for i in range(5):
    #         print(i)
    #         res = client_.post("/graphql", json={'query': queries['add_project']})
    #         res.status_code == 200
    #     # anything more is not
    #     res = client_.post("/graphql", json={'query': queries['add_project']})
    #     assert res.status_code == 429
