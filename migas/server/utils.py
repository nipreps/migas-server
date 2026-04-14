"""Utility functions"""

import os
from datetime import date, datetime, time, timezone

from fastapi import Request

DATETIME_FMT = '%Y-%m-%dT%H:%M:%SZ'


def get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For header or fallback to client host."""
    if x_forwarded_for := request.headers.get('X-Forwarded-For'):
        # On GCP, the last IP is the one appended by the trusted infrastructure
        return x_forwarded_for.split(',')[-1].strip()
    return request.client.host if request.client else 'unknown'


def str_to_dt(timestamp) -> datetime:
    """Helper method to convert between str / datetime objects"""
    try:
        dt = datetime.strptime(timestamp, DATETIME_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.combine(date.fromisoformat(timestamp), time(tzinfo=timezone.utc))
    return dt


def dt_to_str(dt) -> str:
    return dt.strftime(DATETIME_FMT)


def now() -> str | datetime:
    """Return current datetime timestamp. ISO-8601 string"""
    return datetime.now(timezone.utc).replace(microsecond=0)  # ms seems excessive


def env_to_bool(key: str | None) -> bool:
    val = os.getenv(key)
    return bool(val and val.lower() in ('t', 'true', '1', 'yes', 'on', 'y'))
