from unittest.mock import MagicMock
from fastapi import Request
from migas.server.utils import get_client_ip


def create_mock_request(host=None, headers=None):
    request = MagicMock(spec=Request)
    if host:
        request.client = MagicMock()
        request.client.host = host
    else:
        request.client = None

    request.headers = headers or {}
    return request


def test_get_client_ip_no_header():
    request = create_mock_request(host='1.2.3.4')
    assert get_client_ip(request) == '1.2.3.4'


def test_get_client_ip_single_proxy():
    request = create_mock_request(
        host='169.254.169.126', headers={'X-Forwarded-For': '111.111.111.111'}
    )
    assert get_client_ip(request) == '111.111.111.111'


def test_get_client_ip_spoof_protection():
    request = create_mock_request(
        host='169.254.169.126', headers={'X-Forwarded-For': '8.8.8.8, 111.111.111.111'}
    )
    assert get_client_ip(request) == '111.111.111.111'


def test_get_client_ip_fallback():
    request = create_mock_request(host=None)
    assert get_client_ip(request) == 'unknown'
