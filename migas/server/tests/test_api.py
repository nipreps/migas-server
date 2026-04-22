"""Tests for the REST API endpoints (Phase 1)."""

from fastapi.testclient import TestClient

from .conftest import TEST_PROJECT, auth_header


class TestBreadcrumb:
    url = '/api/breadcrumb'

    def test_success(self, client: TestClient):
        res = client.post(
            self.url,
            json={
                'project': TEST_PROJECT,
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
            },
        )
        assert res.status_code == 202
        assert res.json()['success'] is True

    def test_success_wait(self, client: TestClient):
        res = client.post(
            self.url + '?wait=true',
            json={
                'project': TEST_PROJECT,
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
            },
        )
        assert res.status_code == 200
        assert res.json()['success'] is True

    def test_failure_wait(self, client: TestClient, monkeypatch):
        from migas.server.api import routes

        async def boom(*args, **kwargs):
            raise RuntimeError('DB Error')

        monkeypatch.setattr(routes, 'ingest_project', boom)

        res = client.post(
            self.url + '?wait=true',
            json={
                'project': TEST_PROJECT,
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
            },
        )
        assert res.status_code == 500
        data = res.json()
        assert data['success'] is False
        assert data['message'] == 'Error during ingestion.'

    def test_invalid_project_format(self, client: TestClient):
        res = client.post(
            self.url,
            json={
                'project': 'invalid',
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
            },
        )
        assert res.status_code == 400
        assert 'Invalid project format' in res.json()['detail']

    def test_unregistered_project(self, client: TestClient):
        res = client.post(
            self.url,
            json={
                'project': 'unknown/repo',
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
            },
        )
        assert res.status_code == 400
        assert 'not registered' in res.json()['detail']


class TestAdminRegister:
    url = '/api/admin/register'

    def test_success(self, client: TestClient, master_token):
        import uuid

        project = f'new-org/new-repo-{uuid.uuid4().hex[:6]}'
        res = client.post(self.url, json={'project': project}, headers=auth_header(master_token))
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert 'now registered' in data['message']

    def test_already_exists(self, client: TestClient, master_token):
        res = client.post(
            self.url, json={'project': TEST_PROJECT}, headers=auth_header(master_token)
        )
        assert res.status_code == 200
        assert 'already registered' in res.json()['message']

    def test_no_auth(self, client: TestClient):
        res = client.post(self.url, json={'project': 'org/repo'})
        assert res.status_code == 401


class TestAdminListTokens:
    url = '/api/admin/list-tokens'

    def test_list_all(self, client: TestClient, master_token):
        res = client.get(self.url, headers=auth_header(master_token))
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert len(data['tokens']) >= 1
        assert any(t['project'] == 'master' for t in data['tokens'])

    def test_list_filtered(self, client: TestClient, master_token):
        import uuid

        project = f'test/project-{uuid.uuid4().hex[:6]}'
        client.post(
            '/api/admin/register', json={'project': project}, headers=auth_header(master_token)
        )
        client.post(
            '/api/admin/issue-token', json={'project': project}, headers=auth_header(master_token)
        )

        res = client.get(f'{self.url}?project={project}', headers=auth_header(master_token))
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert len(data['tokens']) == 1
        assert data['tokens'][0]['project'] == project

    def test_no_auth(self, client: TestClient):
        res = client.get(self.url)
        assert res.status_code == 401


class TestAdminIssueToken:
    url = '/api/admin/issue-token'

    def test_success(self, client: TestClient, master_token):
        res = client.post(
            self.url, json={'project': TEST_PROJECT}, headers=auth_header(master_token)
        )
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert data['token'].startswith('m_')

    def test_master_project_rejected(self, client: TestClient, master_token):
        res = client.post(self.url, json={'project': 'master'}, headers=auth_header(master_token))
        assert res.status_code == 400

    def test_no_auth(self, client: TestClient):
        res = client.post(self.url, json={'project': TEST_PROJECT})
        assert res.status_code == 401


class TestAdminRevokeToken:
    url = '/api/admin/revoke-token'

    def test_success(self, client: TestClient, master_token):
        issue_res = client.post(
            '/api/admin/issue-token',
            json={'project': TEST_PROJECT},
            headers=auth_header(master_token),
        )
        issued_token = issue_res.json()['token']

        res = client.post(
            self.url, json={'token': issued_token}, headers=auth_header(master_token)
        )
        assert res.status_code == 200
        assert res.json()['success'] is True

    def test_nonexistent_token(self, client: TestClient, master_token):
        res = client.post(self.url, json={'token': 'NaN'}, headers=auth_header(master_token))
        assert res.status_code == 200
        assert res.json()['success'] is False

    def test_no_auth(self, client: TestClient):
        res = client.post(self.url, json={'token': 'some_token'})
        assert res.status_code == 401


class TestAuthProjects:
    """GET /api/auth/projects — token-validity + project-scope discovery.

    Called once per dashboard open to populate the project dropdown. Replaces
    the GraphQL `login` resolver.
    """

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
