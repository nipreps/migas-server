import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from strawberry.fastapi import GraphQLRouter

from . import __version__, __root__
from .connections import (
    get_db_engine,
    get_redis_connection,
    get_requests_session,
)
from .models import init_db
from .schema import SCHEMA


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown logic"""
    # Connect to Redis
    app.cache = await get_redis_connection()
    # Connect to PostgreSQL and initialize tables
    app.db = await get_db_engine()
    await init_db(app.db)
    # Establish aiohttp session
    app.requests = await get_requests_session()
    yield
    await app.cache.aclose()
    await app.db.dispose()
    await app.requests.close()


def _create_app() -> FastAPI:
    app = FastAPI(title="migas", version=__version__, lifespan=lifespan)
    graphql_app = GraphQLRouter(SCHEMA)
    app.include_router(graphql_app, prefix="/graphql")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # only add scout monitoring if environment variables are present
    if all(os.getenv(x) for x in ("SCOUT_NAME", "SCOUT_MONITOR", "SCOUT_KEY")):
        from scout_apm.async_.starlette import ScoutMiddleware

        app.add_middleware(ScoutMiddleware)

    return app


app = _create_app()
# TODO: Create separate app for frontend?
static = str(__root__ / '..' / 'static')
app.mount("/static", StaticFiles(directory=static), name="static")
templates = Jinja2Templates(directory=static)

@app.get("/info")
async def info():
    return {
        "package": "migas",
        "version": __version__,
        "message": "Visit /graphql for GraphiQL interface",
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@app.get("/viz", response_class=HTMLResponse)
async def viz(request: Request):
    return templates.TemplateResponse(request, "viz.html")
