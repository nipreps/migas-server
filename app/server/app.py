from fastapi import FastAPI, Depends
from strawberry.fastapi import GraphQLRouter

from app import __version__
from app.server.schema.project import Project, project_schema

app = FastAPI(version=__version__)

graphql_app = GraphQLRouter(project_schema)
app.include_router(graphql_app, prefix="/graphql")

@app.get("/")
async def root():
    return {"etelemetry server version": __version__}

@app.get("/project/{name}")
async def get_project(name: Project = Depends()):
    return {}