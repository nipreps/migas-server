import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from migas.server.connections import get_mmdb_reader


def test_geoloc_disabled_by_default():
    # Ensure MIGAS_GEOLOC is not set
    with patch.dict(os.environ, {}, clear=True):
        with patch('migas.server.connections._get_val', return_value=None):
            city, asn = asyncio.run(get_mmdb_reader())
            assert city is None
            assert asn is None


def test_geoloc_enabled_truthy():
    # Mock Path.exists and maxminddb
    for truthy in ('t', 'true', '1', 'yes', 'on', 'y'):
        with patch.dict(os.environ, {'MIGAS_GEOLOC': truthy}):
            with (
                patch('migas.server.connections._get_val', return_value=None),
                patch('migas.server.connections._set_val') as mock_set,
                patch('pathlib.Path.exists', return_value=True),
                patch('maxminddb.open_database') as mock_open,
            ):
                mock_open.return_value = MagicMock()
                city, asn = asyncio.run(get_mmdb_reader())

                assert mock_open.call_count == 2
                assert mock_set.call_count == 2


def test_geoloc_fail_fast():
    # Test that it raises RuntimeError when databases are missing
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
