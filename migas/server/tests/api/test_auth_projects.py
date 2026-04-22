"""GET /api/auth/projects — token-validity + project-scope discovery.

Called once per dashboard open to populate the project selector.
"""

from fastapi.testclient import TestClient

from ..conftest import TEST_PROJECT, auth_header


class TestAuthProjects:
    url = '/api/auth/projects'

    def test_master_token_returns_all_projects(self, client: TestClient, master_token):
        res = client.get(self.url, headers=auth_header(master_token))
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data['projects'], list)
        assert len(data['projects']) > 0
        assert '*' not in data['projects']
        assert 'master' not in data['projects']
        assert TEST_PROJECT in data['projects']

    def test_project_token_returns_scoped_project(self, client: TestClient, master_token):
        import uuid

        project = f'test/scoped-login-{uuid.uuid4().hex[:6]}'
        client.post(
            '/api/admin/register', json={'project': project}, headers=auth_header(master_token)
        )
        token_res = client.post(
            '/api/admin/issue-token', json={'project': project}, headers=auth_header(master_token)
        )
        project_token = token_res.json()['token']

        res = client.get(self.url, headers=auth_header(project_token))
        assert res.status_code == 200
        assert res.json()['projects'] == [project]

    def test_invalid_token_returns_401(self, client: TestClient):
        res = client.get(self.url, headers=auth_header('not-a-real-token'))
        assert res.status_code == 401

    def test_missing_auth_returns_401(self, client: TestClient):
        res = client.get(self.url)
        assert res.status_code == 401
