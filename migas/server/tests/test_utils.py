from migas.server.utils import get_client_ip


def test_get_client_ip_no_header(mock_request):
    request = mock_request(host='192.0.2.1')
    assert get_client_ip(request) == '192.0.2.1'


def test_get_client_ip_single_proxy(mock_request):
    request = mock_request(host='192.0.2.2', headers={'X-Forwarded-For': '198.51.100.42'})
    assert get_client_ip(request) == '198.51.100.42'


def test_get_client_ip_spoof_protection(mock_request):
    request = mock_request(
        host='192.0.2.2', headers={'X-Forwarded-For': '203.0.113.55, 198.51.100.42'}
    )
    assert get_client_ip(request) == '198.51.100.42'


def test_get_client_ip_fallback(mock_request):
    request = mock_request(host=None)
    assert get_client_ip(request) == 'unknown'
