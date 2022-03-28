from fastapi import FastAPI

from . import __version__

app = FastAPI(version=__version__)


@app.get("/")
async def root():
    return {"etelemetry server version": __version__}
