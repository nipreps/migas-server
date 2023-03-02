import os

from pkg_resources import resource_filename
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from migas_server import __version__
from migas_server.connections import (
    get_db_engine,
    get_redis_connection,
    get_requests_session,
)
from migas_server.models import init_db, verify_token
from migas_server.schema import SCHEMA


def _create_app() -> FastAPI:
    app = FastAPI(title="migas", version=__version__)
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
# TODO: Create separate app for frontend?
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
templates = Jinja2Templates(directory="frontend")


@app.on_event("startup")
async def startup():
    # Connect to Redis
    app.cache = await get_redis_connection()
    # Connect to PostgreSQL and initialize tables
    app.db = await get_db_engine()
    await init_db(app.db)
    # Establish aiohttp session
    app.requests = await get_requests_session()


@app.on_event("shutdown")
async def shutdown():
    # close connections
    await app.cache.close()
    await app.db.dispose()
    await app.requests.close()


@app.get("/info")
async def info():
    return {
        "package": "migas",
        "version": __version__,
        "message": "Visit /graphql for GraphiQL interface",
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/viz", response_class=HTMLResponse)
async def viz(request: Request):
    return templates.TemplateResponse("viz.html", {"request": request})