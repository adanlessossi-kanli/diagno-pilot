import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.core.config import settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        uri = settings.MONGODB_URI
        # serverSelectionTimeoutMS ensures we fail fast instead of hanging
        self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "diagno_pilot"
        self._db = self._client[db_name]

        # Eagerly verify the connection so a bad URI/unreachable host raises
        # at startup rather than silently failing on the first request.
        try:
            await self._client.admin.command("ping")
        except Exception as exc:
            self._client.close()
            self._client = None
            self._db = None
            raise RuntimeError(
                f"Cannot reach MongoDB at '{uri}'. "
                "Check MONGODB_URI in your .env — use 'localhost:27017' when running "
                "outside Docker, or the service name (e.g. 'mongo:27017') inside Docker. "
                f"Original error: {exc}"
            ) from exc

        logger.info("MongoDB ping OK — connected to '%s'", db_name)

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
