"""Module to faciliate connections to migas's helper services"""

import os

import aiohttp
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

try:  # do not define unless necessary, to avoid overwriting established sessions
    MEM_CACHE
    REQUESTS_SESSION
    DB_ENGINE
    DB_SESSION
except NameError:
    print("Connections and sessions have not yet been initialized")
    MEM_CACHE, REQUESTS_SESSION, DB_ENGINE, DB_SESSION = None, None, None, None


# establish a redis cache connection
async def get_redis_connection() -> redis.Redis:
    """
    Establish redis connection.

    If deployed on Heroku, play nice with their ssl certificates.
    """
    global MEM_CACHE
    if MEM_CACHE is None:
        print("Creating new redis connection")
        if (uri := os.getenv("MIGAS_REDIS_URI")) is None:
            raise ConnectionError("`MIGAS_REDIS_URI` is not set.")

        rkwargs = {'decode_responses': True}
        if os.getenv("HEROKU_DEPLOYED") and uri.startswith('rediss://'):
            rkwargs['ssl_cert_reqs'] = None
        MEM_CACHE = redis.from_url(uri, **rkwargs)
        # ensure the connection is valid
        await MEM_CACHE.ping()
    return MEM_CACHE


# GH / IPStack requests
async def get_requests_session() -> aiohttp.ClientSession:
    """Initialize within an async function, since sync initialization is deprecated."""
    global REQUESTS_SESSION
    if REQUESTS_SESSION is None:
        print("Creating new aiohttp session")
        REQUESTS_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3),  # maximum wait time for a request
            headers={'Content-Type': 'application/json'},
        )
    return REQUESTS_SESSION


async def get_db_engine() -> AsyncEngine:
    global DB_ENGINE
    if DB_ENGINE is None:
        if (db_url := os.getenv("DATABASE_URL")) is None:
            raise ConnectionError("DATABASE_URL is not defined.")
        from sqlalchemy.ext.asyncio import create_async_engine

        DB_ENGINE = create_async_engine(
            # Ensure the engine uses asyncpg driver
            db_url.replace("postgres://", "postgresql+asyncpg://"),
            echo=bool(os.getenv("MIGAS_DISPLAY_QUERIES")),
        )
    return DB_ENGINE


async def get_db_session() -> AsyncSession:
    """Connection can only be initialized asynchronously"""
    global DB_SESSION
    if DB_SESSION is None:
        DB_ENGINE = get_db_engine()
        DB_SESSION = AsyncSession(DB_ENGINE, expire_on_commit=False)
    return DB_SESSION
