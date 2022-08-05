import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from migas_server import __version__
from migas_server.connections import (
    get_db_engine,
    get_redis_connection,
    get_requests_session,
)
from migas_server.models import create_tables
from migas_server.schema import SCHEMA


def _create_app() -> FastAPI:
    app = FastAPI(version=__version__)
    graphql_app = GraphQLRouter(SCHEMA)
    app.include_router(graphql_app, prefix="/graphql")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # only add scout monitoring if environmental variables are present
    if all(os.getenv(x) for x in ("SCOUT_NAME", "SCOUT_MONITOR", "SCOUT_KEY")):
        from scout_apm.async_.starlette import ScoutMiddleware

        app.add_middleware(ScoutMiddleware)

    return app


app = _create_app()


@app.on_event("startup")
async def startup():
    # Connect to Redis
    app.cache = await get_redis_connection()
    # Connect to PostgreSQL
    app.db = await get_db_engine()
    # Establish aiohttp session
    app.requests = await get_requests_session()
    await create_tables(app.db)


@app.on_event("shutdown")
async def shutdown():
    # close connections
    await app.cache.close()
    await app.db.dispose()
    await app.requests.close()


@app.get("/")
async def root():
    return {
        "package": "migas",
        "version": __version__,
        "message": "Visit /graphql for GraphiQL interface",
    }
