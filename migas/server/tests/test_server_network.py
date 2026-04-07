import pytest
from fastapi.testclient import TestClient

from .conftest import queries


@pytest.mark.network
@pytest.mark.parametrize('query', [queries['add_project']])
def test_graphql_add_project_network(query: str, client: TestClient) -> None:
    """Test with real network connectivity to GitHub."""
    res = client.post('/graphql', json={'query': query})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output
