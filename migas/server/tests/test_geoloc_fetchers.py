"""Pure-unit geoloc tests — no external services.

Merges the former test_geoloc_mock.py (fetcher resilience with mocked mmdb
reader) and test_opt_in_behavior.py (MIGAS_GEOLOC env gating).
"""

import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from migas.server.connections import get_mmdb_reader
from migas.server.database import insert_query_geoloc
from migas.server.fetchers import geoloc


# ── fetcher resilience (formerly test_geoloc_mock.py) ──────────────────────


@pytest.fixture(autouse=True)
def setup_geoloc_env(monkeypatch):
    monkeypatch.setenv('MIGAS_GEOLOC', '1')
    yield


@pytest.mark.anyio
async def test_geoloc_resilience_missing_subdivisions():
    """geoloc() does not crash when subdivisions are missing."""
    import migas.server.connections as connections

    mock_city = MagicMock()
    mock_asn = MagicMock()

    mock_city.get.return_value = {
        'city': {'names': {'en': 'Singapore'}},
        'continent': {'code': 'AS'},
        'country': {'iso_code': 'SG'},
        'location': {'latitude': 1.3521, 'longitude': 103.8198},
    }
    mock_asn.get.return_value = None

    with patch.object(connections, 'get_mmdb_reader', new_callable=AsyncMock) as mocked_get:
        mocked_get.return_value = (mock_city, mock_asn)
        res = await geoloc('103.22.200.0')
        assert res is not None
        assert res['city'] == 'Singapore'
        assert 'state_or_province' not in res
        assert res['country_code'] == 'SG'


@pytest.mark.anyio
async def test_geoloc_resilience_partial_data():
    """geoloc() handles extremely sparse records."""
    import migas.server.connections as connections

    mock_city = MagicMock()
    mock_asn = MagicMock()
    mock_city.get.return_value = {'country': {'iso_code': 'XX'}}
    mock_asn.get.return_value = None

    with patch.object(connections, 'get_mmdb_reader', new_callable=AsyncMock) as mocked_get:
        mocked_get.return_value = (mock_city, mock_asn)
        res = await geoloc('1.2.3.4')
        assert res == {'country_code': 'XX'}


@pytest.mark.anyio
async def test_geoloc_bypass_silent():
    """testclient and empty IPs return None early."""
    assert await geoloc('testclient') is None
    assert await geoloc('') is None


@pytest.mark.anyio
async def test_insert_query_geoloc_fault_tolerance(caplog):
    """Database ingestion continues even if geoloc crashes."""
    import logging

    with caplog.at_level(logging.ERROR, logger='migas'):
        with patch('migas.server.fetchers.geoloc', side_effect=RuntimeError('MMDB corrupted')):
            res = await insert_query_geoloc('1.2.3.4')
            assert res is None
            assert 'Geolocation failed for IP 1.2.3.4: MMDB corrupted' in caplog.text


# ── env gating (formerly test_opt_in_behavior.py) ──────────────────────────


def test_geoloc_disabled_by_default():
    with patch.dict(os.environ, {}, clear=True):
        with patch('migas.server.connections._get_val', return_value=None):
            city, asn = asyncio.run(get_mmdb_reader())
            assert city is None
            assert asn is None


def test_geoloc_enabled_truthy():
    for truthy in ('t', 'true', '1', 'yes', 'on', 'y'):
        with patch.dict(os.environ, {'MIGAS_GEOLOC': truthy}):
            with (
                patch('migas.server.connections._get_val', return_value=None),
                patch('migas.server.connections._set_val') as mock_set,
                patch('pathlib.Path.exists', return_value=True),
                patch('maxminddb.open_database') as mock_open,
            ):
                mock_open.return_value = MagicMock()
                asyncio.run(get_mmdb_reader())
                assert mock_open.call_count == 2
                assert mock_set.call_count == 2


def test_geoloc_fail_fast():
    with patch.dict(os.environ, {'MIGAS_GEOLOC': '1', 'MIGAS_GEOLOC_DIR': '/fake/path'}):
        with patch('migas.server.connections._get_val', return_value=None):
            with pytest.raises(RuntimeError, match='Geolocation city database not found'):
                asyncio.run(get_mmdb_reader())


def test_geoloc_explicit_off():
    with patch.dict(os.environ, {'MIGAS_GEOLOC': 'false'}):
        with patch('migas.server.connections._get_val', return_value=None):
            city, asn = asyncio.run(get_mmdb_reader())
            assert city is None
            assert asn is None
