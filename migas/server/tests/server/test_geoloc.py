"""Geolocation tests requiring a real MaxMind mmdb. Gated by the `geoloc`
marker, which the shared `client` fixture honors."""

import asyncio
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.geoloc


def test_geoloc_enabled(client: TestClient):
    res = client.get('/')
    assert res.status_code == 200
    assert res.headers.get('X-Backend-Geolocation') == 'true'


def test_geoloc_lookup():
    from ...fetchers import geoloc

    res = asyncio.run(geoloc('8.8.8.8'))
    assert res is not None
    assert res['country_code'] == 'US'
    assert 'continent_code' in res
