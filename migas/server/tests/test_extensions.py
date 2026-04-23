"""App-level middleware and extensions."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    'path,size',
    [
        ('/', 'large'),  # HTML landing page, >1 KB
        ('/api/auth/projects', 'small'),  # 401 JSON, <1 KB
    ],
)
def test_server_response_compression(client: TestClient, path: str, size: str) -> None:
    res = client.get(path, headers={'Accept-Encoding': 'gzip'})
    if size == 'large':
        assert res.headers.get('content-encoding') == 'gzip'
    else:
        assert res.headers.get('content-encoding') != 'gzip'
