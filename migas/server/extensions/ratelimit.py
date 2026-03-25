import os
import time

from fastapi import Request

from ..connections import get_redis_connection


class RateLimitError(Exception):
    def __init__(self, message: str, status_code: int = 429):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class RequestTooLargeError(RateLimitError):
    def __init__(self, message: str):
        super().__init__(message, status_code=413)


class RateLimitExceededError(RateLimitError):
    def __init__(self, message: str = 'Too many requests, wait a minute.'):
        super().__init__(message, status_code=429)


async def check_request_size(request: Request, max_size: int = None) -> None:
    if max_size is None:
        max_size = int(os.getenv('MIGAS_MAX_REQUEST_SIZE', '2500'))

    body = await request.body()
    if len(body) > max_size:
        raise RequestTooLargeError(
            f'Request body ({len(body)}) exceeds maximum size ({max_size})'
        )


async def check_rate_limit(
    request: Request,
    window: int = None,
    max_requests: int = None,
) -> None:
    if os.getenv('MIGAS_BYPASS_RATE_LIMIT'):
        return

    if window is None:
        window = int(os.getenv('MIGAS_REQUEST_WINDOW', '60'))
    if max_requests is None:
        max_requests = int(os.getenv('MIGAS_MAX_REQUESTS_PER_WINDOW', '100'))

    cache = await get_redis_connection()
    if cache is None:
        return

    host = request.client.host if request.client else 'no-client'
    key = f'rate-limit-{host}'
    time_ = time.time()

    async with cache.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, time_ - window)
        pipe.zrange(key, 0, -1)
        pipe.zadd(key, {time_: time_})
        pipe.expire(key, window)
        res = await pipe.execute()

    timestamps = res[1]
    if len(timestamps) > max_requests:
        raise RateLimitExceededError()
