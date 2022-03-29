import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

class MongoClientHelper:
    """Helper class for writing to mongo database"""

    def __init__(self):
        self.client = AsyncIOMotorClient(
            os.getenv("DB_HOSTNAME", "localhost"), os.getenv("DB_PORT", 27017),
        )
        # self.db = self.client[os.getenv("MASTER_ET_DB", "test_db")]
        # self.requests = self.db["requests"]
        # self.geoloc = self.db["geo"]

    async def is_valid(self):
        """Run mongo command to ensure valid connection"""
        await asyncio.wait_for(self.client.admin.command("ping"), 10)
        print("Database connection established!")
