"""Utility functions"""
import os
from datetime import date, datetime, time, timezone

DATETIME_FMT = "%Y-%m-%dT%H:%M:%SZ"


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
