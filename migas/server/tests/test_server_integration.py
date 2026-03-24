import pytest
from fastapi.testclient import TestClient

from .conftest import queries


@pytest.mark.network
@pytest.mark.geoloc
@pytest.mark.parametrize('query', [queries['add_project']])
def test_graphql_add_project_integration(query: str, client: TestClient) -> None:
    """Test with both real network and real geoloc databases."""
    res = client.post('/graphql', json={'query': query})
    assert res.status_code == 200
    output = res.json()['data']['add_project']
    assert output['success'] is True
    # If real network, it might be cached or not depending on previous runs
    # but the important part is that it doesn't fail.
    for k in ('bad_versions', 'cached', 'latest_version', 'message'):
        assert k in output
