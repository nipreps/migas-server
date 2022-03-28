from fastapi import FastAPI, Depends

from app import __version__
from app.server.schema.project import Project

app = FastAPI(version=__version__)


@app.get("/")
async def root():
    return {"etelemetry server version": __version__}


@app.get("/project/{name}")
async def get_project():
    return {"message": "Hi"}