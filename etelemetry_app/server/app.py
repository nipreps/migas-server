from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from etelemetry_app import __version__
from etelemetry_app.server.connections import (
    get_db_connection_pool,
    get_redis_connection,
    get_requests_session,
)
from etelemetry_app.server.schema import SCHEMA


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
    return app


app = _create_app()


@app.on_event("startup")
async def startup():
    # Connect to Redis
    app.cache = await get_redis_connection()
    # Connect to PostgreSQL
    app.db = await get_db_connection_pool()
    # Establish aiohttp session
    app.requests = await get_requests_session()


@app.on_event("shutdown")
async def shutdown():
    # close connections
    await app.cache.close()
    await app.db.close()
    await app.requests.close()


@app.get("/")
async def root():
    return {
        "package": "etelemetry",
        "version": __version__,
        "message": "Visit /graphql for GraphiQL interface",
    }
