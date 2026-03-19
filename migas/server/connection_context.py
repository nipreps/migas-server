import contextlib
import contextvars
from typing import Optional


class ConnectionContext:
    def __init__(self):
        self.mem_cache = None
        self.requests_session = None
        self.db_engine = None
        self.geoloc_city = None
        self.geoloc_asn = None


_current_context: contextvars.ContextVar[Optional[ConnectionContext]] = contextvars.ContextVar(
    'connection_context', default=None
)


def get_connection_context() -> Optional[ConnectionContext]:
    return _current_context.get()


def set_connection_context(ctx: Optional[ConnectionContext]) -> Optional[ConnectionContext]:
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
