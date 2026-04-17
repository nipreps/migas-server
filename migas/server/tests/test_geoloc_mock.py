import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from migas.server.database import insert_query_geoloc
from migas.server.fetchers import geoloc


@pytest.fixture(autouse=True)
def setup_geoloc_env(monkeypatch):
    monkeypatch.setenv('MIGAS_GEOLOC', '1')
    yield


@pytest.mark.anyio
async def test_geoloc_resilience_missing_subdivisions():
    """Verify that geoloc() does not crash when subdivisions are missing."""
    import migas.server.connections as connections

    mock_city = MagicMock()
    mock_asn = MagicMock()

    # Mock IP found but subdivisions key missing (the original crash scenario)
    mock_city.get.return_value = {
        'city': {'names': {'en': 'Singapore'}},
        'continent': {'code': 'AS'},
        'country': {'iso_code': 'SG'},
        'location': {'latitude': 1.3521, 'longitude': 103.8198},
        # 'subdivisions' is missing
    }
    mock_asn.get.return_value = None

    # Patch in the connections module which is what fetchers imports from
    with patch.object(connections, 'get_mmdb_reader', new_callable=AsyncMock) as mocked_get:
        mocked_get.return_value = (mock_city, mock_asn)
        res = await geoloc('103.22.200.0')
        assert res is not None
        assert res['city'] == 'Singapore'
        assert 'state_or_province' not in res
        assert res['country_code'] == 'SG'


@pytest.mark.anyio
async def test_geoloc_resilience_partial_data():
    """Verify that geoloc() handles extremely sparse records."""
    import migas.server.connections as connections

    mock_city = MagicMock()
    mock_asn = MagicMock()

    # Mock only country info available
    mock_city.get.return_value = {'country': {'iso_code': 'XX'}}
    mock_asn.get.return_value = None

    with patch.object(connections, 'get_mmdb_reader', new_callable=AsyncMock) as mocked_get:
        mocked_get.return_value = (mock_city, mock_asn)
        res = await geoloc('1.2.3.4')
        assert res == {'country_code': 'XX'}


@pytest.mark.anyio
async def test_geoloc_bypass_silent():
    """Verify that testclient and empty IPs return early and silently."""
    res = await geoloc('testclient')
    assert res is None

    res = await geoloc('')
    assert res is None


@pytest.mark.anyio
async def test_insert_query_geoloc_fault_tolerance(caplog):
    """Verify that database ingestion continues even if geoloc crashes completely."""
    import logging

    with caplog.at_level(logging.ERROR, logger='migas'):
        with patch('migas.server.fetchers.geoloc', side_effect=RuntimeError('MMDB corrupted')):
            res = await insert_query_geoloc('1.2.3.4')
            assert res is None
            assert 'Geolocation failed for IP 1.2.3.4: MMDB corrupted' in caplog.text
