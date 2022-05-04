import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.results import InsertOneResult

from app.server.types import Project

_Client = AsyncIOMotorClient(
    os.getenv("ETELEMETRY_DB_HOSTNAME", "localhost"),
    os.getenv("ETELEMETRY_DB_PORT", 27017),
)

DB = _Client[os.getenv("ETELEMETRY_DB", "etelemetry")]

# default collections
# collections = {
#     _Client["etelemetry"]
# }


async def verify_db_connection() -> bool:
    await _Client.admin.command("ping")
    print("Connection to database established!")
    return True


# async def add_collection()
async def collection_insert(project: Project) -> InsertOneResult:
    # Use @ as separator since it cannot be present in GH IDs
    col_name = f"{project.owner}@{project.repo}"

    # MAYBE: rate limit creation?
    if col_name not in await DB.list_collection_names():
        print(f"Creating new collection {col_name}")
        await DB.create_collection(col_name, capped=True, size=1000)
    else:
        print("Using existing collection")

    col = DB[col_name]

    inserted = await insert_project(col, project)
    print(f"Inserted new entry {inserted} in {col_name}")
    return inserted


async def insert_project(col: AsyncIOMotorCollection, project: Project) -> InsertOneResult:
    doc = await _serialize_to_mongo(project.__dict__.copy())
    inserted = await col.insert_one(doc)
    return inserted


async def _serialize_to_mongo(data):
    from enum import Enum

    from packaging.version import LegacyVersion, Version

    from app.server.types import Context, Process

    for k, v in data.items():
        # TODO: Is this possible with PEP636?
        # I gave up trying it
        if isinstance(v, str):
            data[k] = await _sanitize(v)
        elif isinstance(v, (Version, LegacyVersion)):
            data[k] = await _sanitize(str(v))
        elif isinstance(v, Enum):
            data[k] = v.name
        # datetime ok?
        elif isinstance(v, (Context, Process)):
            data[k] = await _serialize_to_mongo(v.__dict__)
    return data


# character limit
# replace $ characters
async def _sanitize(s, char_lim=99):
    if len(s) > char_lim:
        print(f"String {s} is over character limit")
    return s[:char_lim]
