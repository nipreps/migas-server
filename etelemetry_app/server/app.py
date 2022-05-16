import asyncio

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from etelemetry_app import __version__

# from etelemetry_app.server.database import verify_db_connection
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


# @app.on_event("startup")
# async def startup():
#     # Confirm connection to Mongo
#     try:
#         await asyncio.wait_for(verify_db_connection(), 10)
#     except asyncio.TimeoutError:
#         print("Connection to MongoDB could not be made.")


@app.get("/")
async def root():
    return {
        "package": "etelemetry",
        "version": __version__,
        "message": "Visit /graphql for GraphiQL interface",
    }
