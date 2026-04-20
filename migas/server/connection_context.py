import contextlib
import contextvars


from dataclasses import dataclass
from typing import Any


@dataclass
class ConnectionContext:
    mem_cache: Any = None
    requests_session: Any = None
    db_engine: Any = None
    db_engine_loop: Any = None
    geoloc_city: Any = None
    geoloc_asn: Any = None


_current_context: contextvars.ContextVar[ConnectionContext | None] = contextvars.ContextVar(
    'connection_context', default=None
)


def get_connection_context() -> ConnectionContext | None:
    return _current_context.get()


def set_connection_context(ctx: ConnectionContext | None) -> ConnectionContext | None:
    token = _current_context.get()
    _current_context.set(ctx)
    return token


@contextlib.asynccontextmanager
async def isolated_connection_context():
    token = _current_context.set(ConnectionContext())
    try:
        yield _current_context.get()
    finally:
        _current_context.reset(token)
