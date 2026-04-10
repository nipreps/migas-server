import logging.config
import os
import typing as ty
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from strawberry.fastapi import GraphQLRouter

from . import __version__, __root__
from .api.routes import router as api_router
from .connections import (
    get_db_engine,
    get_redis_connection,
    get_requests_session,
    get_mmdb_reader,
    close_geoloc_dbs,
)
from .models import init_db
from .schema import SCHEMA
from .utils import env_to_bool


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'default': {'format': 'INFO:     %(name)s - %(message)s'}},
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'stream': 'ext://sys.stdout',
        }
    },
    'loggers': {'migas': {'handlers': ['console'], 'level': 'INFO'}},
}


@asynccontextmanager
async def lifespan(
    app: FastAPI,
    on_startup: ty.Callable[[FastAPI], ty.Awaitable[None]] = None,
    on_shutdown: ty.Callable[[FastAPI], ty.Awaitable[None]] = None,
    **kwargs,
):
    """Handle startup and shutdown logic"""
    logging.config.dictConfig(LOGGING_CONFIG)
    # Connect to Redis
    app.cache = await get_redis_connection()
    # Connect to PostgreSQL and initialize tables
    app.db = await get_db_engine()
    await init_db()
    # Establish aiohttp session
    app.requests = await get_requests_session()
    app.geodbs = await get_mmdb_reader()
    if on_startup:
        await on_startup(app)
    yield
    if on_shutdown:
        await on_shutdown(app)
    await app.cache.aclose()
    await app.db.dispose()
    await app.requests.close()
    await close_geoloc_dbs()


def create_app(lifespan_func=lifespan, **lifespan_kwargs) -> FastAPI:
    app = FastAPI(
        title='migas',
        version=__version__,
        lifespan=lambda app: lifespan_func(app, **lifespan_kwargs),
    )
    graphql_app = GraphQLRouter(SCHEMA)
    app.include_router(graphql_app, prefix='/graphql')
    app.include_router(api_router)

    app.add_middleware(
        CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*']
    )

    @app.middleware('http')
    async def add_backend_header(request: Request, call_next):
        from packaging.version import Version

        response = await call_next(request)
        v = Version(__version__)
        response.headers['X-Backend-Server'] = f'migas-{v.major}.{v.minor}'
        return response

    # only add scout monitoring if environment variables are present
    if all(os.getenv(x) for x in ('SCOUT_NAME', 'SCOUT_MONITOR', 'SCOUT_KEY')):
        from scout_apm.async_.starlette import ScoutMiddleware

        app.add_middleware(ScoutMiddleware)

    # TODO: Create separate app for frontend?
    static = str(__root__ / '..' / 'static')
    app.mount('/static', StaticFiles(directory=static), name='static')
    templates = Jinja2Templates(directory=static)

    @app.get('/', response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(request, 'home.html', {'version': __version__})

    @app.get('/info')
    async def info():
        return {
            'package': 'migas',
            'version': __version__,
            'message': 'Visit /graphql for GraphiQL interface',
            'geoloc_enabled': env_to_bool('MIGAS_GEOLOC'),
            'dev_mode': env_to_bool('MIGAS_DEV'),
        }

    @app.get('/viz', response_class=HTMLResponse)
    async def viz(request: Request):
        return templates.TemplateResponse(
            request, 'viz.html', {'version': __version__, 'dev_mode': bool(os.getenv('MIGAS_DEV'))}
        )

    @app.get('/viz/dashboard', response_class=HTMLResponse)
    async def viz_dashboard(request: Request):
        return templates.TemplateResponse(
            request,
            'dashboard.html',
            {'version': __version__, 'dev_mode': bool(os.getenv('MIGAS_DEV'))},
        )

    return app


app = create_app()
