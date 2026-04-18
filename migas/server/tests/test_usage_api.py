import pytest
from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_usage_api_auth(client: TestClient, db):
    project = 'test/api-auth'
    other_project = 'test/other-project'
    await db.register(project)
    await db.register(other_project)

    auth = await db.token(project)

    # 1. Access project with its own token (OK)
    res = client.get(f'/api/usage/{project}', headers=auth)
    assert res.status_code == 200

    # 2. Access project with no token (Unauthorized)
    res = client.get(f'/api/usage/{project}')
    assert res.status_code == 401

    # 3. Access project with wrong token (Forbidden)
    other_auth = await db.token(other_project)
    res = client.get(f'/api/usage/{project}', headers=other_auth)
    assert res.status_code == 403


@pytest.mark.anyio
async def test_usage_api_cache_logic(client: TestClient, db):
    project = 'test/api-cache'
    await db.register(project)
    auth = await db.token(project)

    # Initial request (Cache MISS)
    res = client.get(f'/api/usage/{project}', headers=auth)
    assert res.status_code == 200

    # Second request (Cache HIT or DELTA)
    res = client.get(f'/api/usage/{project}', headers=auth)
    assert res.status_code == 200


@pytest.mark.anyio
async def test_usage_api_dev_bypass(client: TestClient, db, monkeypatch):
    project = 'test/api-dev'
    await db.register(project)
    monkeypatch.setenv('MIGAS_DEV', '1')

    res = client.get(f'/api/usage/{project}', headers={'Authorization': 'Bearer dev_token'})
    assert res.status_code == 200
