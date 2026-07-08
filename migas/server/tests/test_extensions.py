"""App-level middleware and extensions."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

FAKE_HOST = '203.0.113.5'


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


def _fake_redis(timestamps: list) -> MagicMock:
    """Redis stand-in whose pipeline().execute() yields `timestamps` as the zrange result."""
    pipe = MagicMock()
    pipe.__aenter__.return_value = pipe
    pipe.execute = AsyncMock(return_value=[None, timestamps, None, None])

    redis = MagicMock()
    redis.pipeline.return_value = pipe
    return redis


@pytest.mark.anyio
@pytest.mark.parametrize('num_requests,should_raise', [(4, False), (5, True)])
async def test_check_rate_limit_rejects_at_configured_cap(
    monkeypatch, mock_request, num_requests, should_raise
) -> None:
    from migas.server.extensions import ratelimit

    monkeypatch.setattr(
        ratelimit,
        'get_redis_connection',
        AsyncMock(return_value=_fake_redis(list(range(num_requests)))),
    )

    if should_raise:
        with pytest.raises(ratelimit.RateLimitExceededError):
            await ratelimit.check_rate_limit(mock_request(host=FAKE_HOST), max_requests=5)
    else:
        await ratelimit.check_rate_limit(mock_request(host=FAKE_HOST), max_requests=5)


@pytest.mark.anyio
async def test_check_rate_limit_logs_when_cap_exceeded(monkeypatch, mock_request, caplog) -> None:
    from migas.server.extensions import ratelimit

    monkeypatch.setattr(
        ratelimit, 'get_redis_connection', AsyncMock(return_value=_fake_redis(list(range(5))))
    )

    with caplog.at_level('WARNING', logger='migas'):
        with pytest.raises(ratelimit.RateLimitExceededError):
            await ratelimit.check_rate_limit(mock_request(host=FAKE_HOST), max_requests=5)

    assert any('rate limit' in r.message.lower() for r in caplog.records)
    assert FAKE_HOST in caplog.text
