"""Module to faciliate connections to migas's helper services"""

import os
from functools import wraps
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiohttp import ClientSession, ClientTimeout
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_UNSET = object()

try:  # do not define unless necessary, to avoid overwriting established sessions
    MEM_CACHE
    REQUESTS_SESSION
    DB_ENGINE
    GEOLOC_CITY
    GEOLOC_ASN
except NameError:
    print("Connections and sessions have not yet been initialized")
    MEM_CACHE = _UNSET
    REQUESTS_SESSION = _UNSET
    DB_ENGINE = _UNSET
    GEOLOC_CITY = _UNSET
    GEOLOC_ASN = _UNSET


# establish a redis cache connection
async def get_redis_connection() -> redis.Redis:
    """
    Establish redis connection.

    If deployed on Heroku, play nice with their ssl certificates.
    """
    global MEM_CACHE
    if MEM_CACHE is _UNSET:
        print("Creating new redis connection")

        # Check for both REDIS_TLS_URL (prioritized) and MIGAS_REDIS_URI
        if (uri := os.getenv("REDIS_TLS_URL")) is None and (
            uri := os.getenv("MIGAS_REDIS_URI")
        ) is None:
            raise ConnectionError("Redis environment variable is not set.")

        rkwargs = {'decode_responses': True}
        if os.getenv("HEROKU_DEPLOYED") and uri.startswith('rediss://'):
            rkwargs['ssl_cert_reqs'] = None
        MEM_CACHE = redis.from_url(uri, **rkwargs)
        # ensure the connection is valid
        try:
            await MEM_CACHE.ping()
        except Exception as e:
            raise ConnectionError("Cannot connect to Redis server") from e
    return MEM_CACHE


# GH requests
async def get_requests_session() -> ClientSession:
    """Initialize within an async function, since sync initialization is deprecated."""
    global REQUESTS_SESSION
    if REQUESTS_SESSION is _UNSET:
        print("Creating new aiohttp session")
        REQUESTS_SESSION = ClientSession(
            timeout=ClientTimeout(total=3),  # maximum wait time for a request
        )
    return REQUESTS_SESSION


async def get_db_engine() -> AsyncEngine:
    """Establish connection to SQLAlchemy engine."""
    global DB_ENGINE
    if DB_ENGINE is _UNSET:
        from sqlalchemy.ext.asyncio import create_async_engine

        if (db_url := os.getenv("DATABASE_URL")) is None:
            # Create URL from environment variables
            from sqlalchemy.engine import URL

            db_url = URL.create(
                drivername="postgresql+asyncpg",
                username=os.getenv("DATABASE_USER"),
                password=os.getenv("DATABASE_PASSWORD"),
                database=os.getenv("DATABASE_NAME"),
            )

        else:
            # Convert string to sqlalchemy URL
            from sqlalchemy.engine import make_url

            db_url = make_url(db_url)

        db_url = db_url.set(drivername="postgresql+asyncpg")
        if gcp_conn := os.getenv("GCP_SQL_CONNECTION"):
            db_url = db_url.set(query={"host": f"/cloudsql/{gcp_conn}/.s.PGSQL.5432"})

        DB_ENGINE = create_async_engine(
            db_url,
            echo=bool(os.getenv("MIGAS_DEBUG")),
        )
    return DB_ENGINE


@asynccontextmanager
async def gen_session() -> AsyncGenerator[AsyncSession, None]:
    """Generate a database session, and close once finished."""
    # do not expire on commit to allow use of data afterwards
    session = AsyncSession(await get_db_engine(), future=True, expire_on_commit=False)
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        print(f"Transaction failed. Rolling back the session. Error: {e}")
    finally:
        await session.close()


def inject_sync_conn(func):
    """
    Decorator to run async database functions synchronously.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        conn = kwargs.get('conn')
        if conn:
            return await conn.run_sync(func, *args, **kwargs)

        engine = await get_db_engine()
        async with engine.begin() as conn:
            return await conn.run_sync(func, *args, **kwargs)
    return wrapper


def inject_db_conn(func):
    """
    Decorator that creates a connection.

    Generally used when ORM mapping is not needed.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        conn = kwargs.get('conn')
        if conn:
            return await func(*args, **kwargs)

        engine = await get_db_engine()
        async with engine.begin() as conn:
            return await func(*args, conn=conn, **kwargs)
    return wrapper


def inject_db_session(func):
    """
    Decorator that creates a session for database interaction.

    This is generally used when working with ORM level transactions.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        cur_session = kwargs.get('session')
        if cur_session:
            # if chaining, committing and closing need to be handled
            return await func(*args, **kwargs)

        async with gen_session() as session:
            return await func(*args, session=session, **kwargs)
    return wrapper


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


async def get_geoloc_dbs():
    global GEOLOC_CITY
    global GEOLOC_ASN

    try:
        import maxminddb
    except ImportError:
        GEOLOC_CITY, GEOLOC_ASN = None, None
        return

    if os.getenv('MIGAS_DISABLE_GEOLOC'):
        GEOLOC_CITY, GEOLOC_ASN = None, None
        return

    from .fetchers import download_geoloc_db
    print('Establishing geolocation databases')

    if GEOLOC_CITY is _UNSET:
        print('Downloading city MMDB')
        city_url = os.getenv('MIGAS_GEOLOC_CITY_URL')
        if not city_url:
            from .constants import LOC_CITY_URL as city_url

        city = await download_geoloc_db(city_url, 'city')
        GEOLOC_CITY = maxminddb.open_database(city, mode=maxminddb.MODE_MMAP_EXT)

    if GEOLOC_ASN is _UNSET:
        print('Downloading asn MMDB')
        asn_url = os.getenv('MIGAS_GEOLOC_ASN_URL')
        if not asn_url:
            from .constants import LOC_ASN_URL as asn_url

        asn = await download_geoloc_db(asn_url, 'asn')
        GEOLOC_ASN = maxminddb.open_database(asn, mode=maxminddb.MODE_MMAP_EXT)


async def close_geoloc_dbs():
    global GEOLOC_CITY
    global GEOLOC_ASN

    if GEOLOC_CITY and GEOLOC_CITY is not _UNSET:
        GEOLOC_CITY.close()

    if GEOLOC_ASN and GEOLOC_ASN is not _UNSET:
        GEOLOC_ASN.close()