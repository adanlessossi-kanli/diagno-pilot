from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.core.config import settings


class Database:
    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        self._client = AsyncIOMotorClient(settings.MONGODB_URI)
        db_name = settings.MONGODB_URI.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"
        self._db = self._client[db_name]

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    def get_db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db


db = Database()
