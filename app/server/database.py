import os

from motor.motor_asyncio import AsyncIOMotorClient

from app.server.utils import get_current_time


async def verify_db_connection(client: AsyncIOMotorClient) -> bool:
    await client.admin.command("ping")
    print("Connection to database established!")
    return True


Client = AsyncIOMotorClient(
    os.getenv("ET_DB_HOSTNAME", "localhost"),
    os.getenv("ET_DB_PORT", 27017),
)
