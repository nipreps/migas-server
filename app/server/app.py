import asyncio

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from app import __version__
from app.server.database import MongoClientHelper
from app.server.schema.project import Project, project_schema

def _create_app():
    app = FastAPI(version=__version__)
    graphql_app = GraphQLRouter(project_schema)
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
    app.db = MongoClientHelper()
    try:
        await asyncio.wait_for(app.db.is_valid(), 10)
    except asyncio.TimeoutError:
        print("Connection to MongoDB could not be made.")

@app.get("/")
async def root():
    return {"etelemetry server version": __version__}

@app.get("/project/{name}")
async def get_project(name: Project = Depends()):
    return {}
