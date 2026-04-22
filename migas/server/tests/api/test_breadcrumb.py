"""POST /api/breadcrumb — telemetry ingestion endpoint."""

from fastapi.testclient import TestClient

from ..conftest import TEST_PROJECT


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
