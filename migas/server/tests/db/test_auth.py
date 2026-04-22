"""Tests for authenticate_token.

Master tokens must not eagerly enumerate every project on every
authenticated request. Each /api/usage call re-authenticates, so a
per-auth O(projects) scan compounds into visible request-path latency.
"""

import pytest

from migas.server import database
from migas.server.database import authenticate_token, create_token


@pytest.mark.anyio
async def test_master_auth_does_not_enumerate_projects(client, monkeypatch, master_token):
    """Master auth must succeed without touching query_projects.

    Any master token has access to any project — the '*' sentinel encodes
    that without a DB scan.
    """

    async def boom(*args, **kwargs):
        raise AssertionError('query_projects must not be called during auth')

    monkeypatch.setattr(database, 'query_projects', boom)

    valid, projects = await authenticate_token(master_token)
    assert valid is True
    assert projects == ['*']


@pytest.mark.anyio
async def test_project_auth_returns_scoped_project(db):
    project = 'test/auth-scope'
    await db.register(project)
    raw = await create_token(project)

    valid, projects = await authenticate_token(raw)
    assert valid is True
    assert projects == [project]


@pytest.mark.anyio
async def test_invalid_token_fails(client):
    valid, projects = await authenticate_token('definitely-not-a-real-token')
    assert valid is False
    assert projects == []
