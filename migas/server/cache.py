"""Centralized Redis cache keys and TTLs"""

from datetime import date

# Namespace for all viz/usage cache entries.
viz_prefix = 'migas:viz'

# Short TTL to avoid DB queries on dashboard reloads
RESPONSE_TTL = 60


def historical_key(project: str) -> str:
    """Key for the per-project historical usage histogram (no TTL)."""
    return f'{viz_prefix}:hist:{project}'


def usage_key(project: str, weeks: int, since: date | None) -> str:
    """Key for the assembled ``/api/usage`` response, varying by query params."""
    return f'{viz_prefix}:usage:{project}:{weeks}:{since.isoformat() if since else ""}'
