"""Module to faciliate connections to etelemetry's helper services"""

import os

import aiohttp
import asyncpg
import redis.asyncio as redis

try:  # do not define unless necessary, to avoid overwriting established sessions
    MEM_CACHE
    REQUESTS_SESSION
    DB_SESSION
except NameError:
    print("Sessions have not yet been initialized")
    MEM_CACHE, REQUESTS_SESSION, DB_SESSION = None, None, None


# establish a redis cache connection
async def get_redis_connection() -> redis.Redis:
    """
    Establish redis connection.

    If deployed on Heroku, play nice with their ssl certificates.
    """
    global MEM_CACHE
    if MEM_CACHE is None:
        print("Creating new redis connection")
        if uri := os.getenv("ETELEMETRY_REDIS_URI") is None:
            raise ConnectionError("`ETELEMETRY_REDIS_URI` is not set.")
        elif os.getenv("HEROKU_DEPLOYED"):
            from urllib.parse import urlparse

            puri = urlparse(uri)
            MEM_CACHE = redis.Redis(
                host=puri.hostname,
                port=puri.port,
                username=puri.username,
                password=puri.password,
                ssl=True,
                ssl_cert_reqs=None,
                decode_responses=True,
            )
        else:
            MEM_CACHE = redis.from_url(uri, decode_responses=True)
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


# PostgreSQL connection pool
async def get_db_connection_pool() -> asyncpg.Pool:
    """Connection can only be initialized asynchronously"""
    global DB_SESSION
    if DB_SESSION is None:
        print("Creating new database connection pool")
        conn_kwargs = {"timeout": 10, "command_timeout": 30}
        if (uri := os.getenv("ETELEMETRY_DB_URI")) is not None:
            conn_kwargs["dsn"] = uri
        else:
            conn_kwargs.update(
                {
                    "host": os.getenv("ETELEMETRY_DB_HOSTNAME", "localhost"),
                    "port": os.getenv("ETELEMETRY_DB_PORT", 5432),
                    "database": os.getenv("ETELEMETRY_DB", "etelemetry"),
                }
            )
        DB_SESSION = await asyncpg.create_pool(**conn_kwargs)
    return DB_SESSION
