"""Module to faciliate connections to migas's helper services"""

import os
from functools import wraps
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiohttp import ClientSession, ClientTimeout
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from .connection_context import get_connection_context
from .utils import env_to_bool

_UNSET = object()

try:  # do not define unless necessary, to avoid overwriting established sessions
    MEM_CACHE
    REQUESTS_SESSION
    DB_ENGINE
    GEOLOC_CITY
    GEOLOC_ASN
except NameError:
    print('Connections and sessions have not yet been initialized')
    MEM_CACHE = _UNSET
    REQUESTS_SESSION = _UNSET
    DB_ENGINE = _UNSET
    GEOLOC_CITY = _UNSET
    GEOLOC_ASN = _UNSET


def _get_val(name):
    if ctx := get_connection_context():
        return getattr(ctx, name)
    return globals().get(name.upper())


def _set_val(name, val):
    if ctx := get_connection_context():
        setattr(ctx, name, val)
    else:
        globals()[name.upper()] = val


# establish a redis cache connection
async def get_redis_connection() -> redis.Redis:
    """
    Establish redis connection.

    If deployed on Heroku, play nice with their ssl certificates.
    """
    mem_cache = _get_val('mem_cache')
    if mem_cache is None or mem_cache is _UNSET:
        print('Creating new redis connection')

        # Check for both REDIS_TLS_URL (prioritized) and MIGAS_REDIS_URI
        if (uri := os.getenv('REDIS_TLS_URL')) is None and (
            uri := os.getenv('MIGAS_REDIS_URI')
        ) is None:
            raise ConnectionError('Redis environment variable is not set.')

        rkwargs = {'decode_responses': True}
        if os.getenv('HEROKU_DEPLOYED') and uri.startswith('rediss://'):
            rkwargs['ssl_cert_reqs'] = None
        mem_cache = redis.from_url(uri, **rkwargs)
        # ensure the connection is valid
        try:
            await mem_cache.ping()
        except Exception as e:
            raise ConnectionError('Cannot connect to Redis server') from e
        _set_val('mem_cache', mem_cache)
    return _get_val('mem_cache')


# GH requests
async def get_requests_session() -> ClientSession:
    """Initialize within an async function, since sync initialization is deprecated."""
    requests_session = _get_val('requests_session')
    if requests_session is None or requests_session is _UNSET:
        print('Creating new aiohttp session')
        requests_session = ClientSession(
            timeout=ClientTimeout(total=3)  # maximum wait time for a request
        )
        _set_val('requests_session', requests_session)
    return _get_val('requests_session')


async def get_db_engine() -> AsyncEngine:
    """Establish connection to SQLAlchemy engine."""
    db_engine = _get_val('db_engine')
    if db_engine is None or db_engine is _UNSET:
        from sqlalchemy.ext.asyncio import create_async_engine

        if (db_url := os.getenv('DATABASE_URL')) is None:
            # Create URL from environment variables
            from sqlalchemy.engine import URL

            db_url = URL.create(
                drivername='postgresql+asyncpg',
                username=os.getenv('DATABASE_USER'),
                password=os.getenv('DATABASE_PASSWORD'),
                database=os.getenv('DATABASE_NAME'),
            )

        else:
            # Convert string to sqlalchemy URL
            from sqlalchemy.engine import make_url

            db_url = make_url(db_url)

        db_url = db_url.set(drivername='postgresql+asyncpg')
        if gcp_conn := os.getenv('GCP_SQL_CONNECTION'):
            db_url = db_url.set(query={'host': f'/cloudsql/{gcp_conn}/.s.PGSQL.5432'})

        db_engine = create_async_engine(db_url, echo=bool(os.getenv('MIGAS_DEV')))
        _set_val('db_engine', db_engine)
    return _get_val('db_engine')


@asynccontextmanager
async def gen_session(
    current_session: AsyncSession | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Generate a database session, and close once finished.

    If a session is provided, it is yielded as-is.
    If no session is provided, a new one is created, committed on success,
    rolled back on error, and closed when finished.
    """
    if current_session:
        yield current_session
        return

    # do not expire on commit to allow use of data afterwards
    session = AsyncSession(await get_db_engine(), future=True, expire_on_commit=False)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def inject_aiohttp_session(func):
    """
    Decorator that ensures an aiohttp session is provided.

    Will default to use the global application session, unless one is provided.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        session = kwargs.pop('session', None)
        if not session:
            from .connections import get_requests_session

            session = await get_requests_session()
        return await func(*args, session=session, **kwargs)

    return wrapper


async def get_mmdb_reader():
    geoloc_city = _get_val('geoloc_city')
    geoloc_asn = _get_val('geoloc_asn')

    if not env_to_bool('MIGAS_ENABLE_GEOLOC'):
        _set_val('geoloc_city', None)
        _set_val('geoloc_asn', None)
        return None, None

    import maxminddb

    from .fetchers import download_geoloc_db

    print('Establishing geolocation databases')

    if _get_val('geoloc_city') in (None, _UNSET):
        print('Downloading city MMDB')
        city_url = os.getenv('MIGAS_GEOLOC_CITY_URL')
        if not city_url:
            from .constants import LOC_CITY_URL as city_url

        try:
            city = await download_geoloc_db(city_url, 'city')
            geoloc_city = maxminddb.open_database(city, mode=maxminddb.MODE_MMAP_EXT)
            _set_val('geoloc_city', geoloc_city)
        except Exception as e:
            msg = f'Failed to establish city MMDB: {e}'
            print(msg)
            _set_val('geoloc_city', None)
            raise RuntimeError(msg) from e

    if _get_val('geoloc_asn') in (None, _UNSET):
        print('Downloading asn MMDB')
        asn_url = os.getenv('MIGAS_GEOLOC_ASN_URL')
        if not asn_url:
            from .constants import LOC_ASN_URL as asn_url

        try:
            asn = await download_geoloc_db(asn_url, 'asn')
            geoloc_asn = maxminddb.open_database(asn, mode=maxminddb.MODE_MMAP_EXT)
            _set_val('geoloc_asn', geoloc_asn)
        except Exception as e:
            msg = f'Failed to establish asn MMDB: {e}'
            print(msg)
            _set_val('geoloc_asn', None)
            raise RuntimeError(msg) from e

    return _get_val('geoloc_city'), _get_val('geoloc_asn')


async def close_geoloc_dbs():
    geoloc_city = _get_val('geoloc_city')
    geoloc_asn = _get_val('geoloc_asn')
    if geoloc_city and geoloc_city is not _UNSET:
        geoloc_city.close()
    if geoloc_asn and geoloc_asn is not _UNSET:
        geoloc_asn.close()
