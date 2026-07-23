"""POST /api/breadcrumb — telemetry ingestion endpoint."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from migas.server.api.models import BreadcrumbRequest
from ..conftest import TEST_PROJECT


@pytest.mark.parametrize('field', ['project_version', 'language_version'])
@pytest.mark.parametrize(
    'value, valid',
    [
        ('1.0.0', True),
        ('2.0.0rc1', True),
        ('0.8.1.dev17+gcaf8859', True),
        ('1.2.3-4-gabcdef', True),
        ('v1.0.0_custom', True),
        ('<iframe onload=alert(1)>', False),
        ("');eval(name)//", False),
        ('<script>x</script>', False),
        ('has spaces', False),
        ('1.0"onerror=x', False),
        ('', False),
    ],
)
def test_versions(field: str, value: str, valid: bool):
    model = BreadcrumbRequest(**{'project': 'o/r', 'project_version': '1.0.0', field: value})
    assert getattr(model, field) == (value if valid else 'unknown')


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
                'params': {'iam': 'anewparam'}
            },
        )
        assert res.status_code == 202
        assert res.json()['success'] is True

    @pytest.mark.anyio
    async def test_success_wait(self, client: TestClient, db):
        user_id = str(uuid4())
        session_id = str(uuid4())
        res = client.post(
            self.url + '?wait=true',
            json={
                'project': TEST_PROJECT,
                'project_version': '1.0.0',
                'language': 'python',
                'language_version': '3.12',
                'params': {'iam': 'anewparam'},
                'ctx': {
                    'user_id': user_id,
                    'session_id': session_id,
                    'platform': 'Linux-x86_64',
                    'container': 'docker',
                },
                'proc': {'status': 'C'},
            },
        )
        assert res.status_code == 200
        assert res.json()['success'] is True

        user = await db.get_user(user_id)
        assert user is not None, 'ingest did not populate the users table'
        assert user['platform'] == 'Linux-x86_64'
        assert user['container'] == 'docker'

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

    @pytest.mark.anyio
    async def test_retrieve_params(self, client: TestClient):
        from sqlalchemy import select
        from migas.server.connections import gen_session
        from migas.server.models import Crumb

        session_id = str(uuid4())
        expected_params = {'iam': 'atestparam'}
        res = client.post(
            self.url + '?wait=true',
            json={
                'project': TEST_PROJECT,
                'project_version': '1.2.3',
                'language': 'python',
                'language_version': '3.12',
                'params': expected_params,
                'ctx': {
                    'session_id': session_id
                }
            },
        )

        assert res.status_code == 200
        assert res.json()['success'] is True

        async with gen_session() as session:
            result = await session.execute(
                select(Crumb.params).where(Crumb.session_id == session_id)
            )
            stored_params = result.scalar_one()

        assert stored_params == expected_params
