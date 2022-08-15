"""Module to faciliate connections to migas's helper services"""

import os

import aiohttp
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine

try:  # do not define unless necessary, to avoid overwriting established sessions
    MEM_CACHE
    REQUESTS_SESSION
    DB_ENGINE
except NameError:
    print("Connections and sessions have not yet been initialized")
    MEM_CACHE, REQUESTS_SESSION, DB_ENGINE = None, None, None


# establish a redis cache connection
async def get_redis_connection() -> redis.Redis:
    """
    Establish redis connection.

    If deployed on Heroku, play nice with their ssl certificates.
    """
    global MEM_CACHE
    if MEM_CACHE is None:
        print("Creating new redis connection")

        # Check for both REDIS_TLS_URL (prioritized) and MIGAS_REDIS_URI
        if (uri := os.getenv("REDIS_TLS_URL")) is None and (
            uri := os.getenv("MIGAS_REDIS_URI")
        ) is None:
            raise ConnectionError("Redis environmental variable is not set.")

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
    """Establish connection to SQLAlchemy engine."""
    global DB_ENGINE
    if DB_ENGINE is None:
        if (db_url := os.getenv("DATABASE_URL")) is None:
            raise ConnectionError("DATABASE_URL is not defined.")
        from sqlalchemy.ext.asyncio import create_async_engine

        DB_ENGINE = create_async_engine(
            # Ensure the engine uses asyncpg driver
            db_url.replace("postgres://", "postgresql+asyncpg://"),
            echo=bool(os.getenv("MIGAS_DEBUG")),
        )
    return DB_ENGINE
