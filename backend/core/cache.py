"""Redis-backed CacheService for Diagno-Pilot.

Provides a single shared singleton (`cache_service`) used by all services.
Implements degraded-mode-safe caching: if Redis is unavailable, every
operation is a transparent no-op so callers fall through to their origin
data sources without raising errors.
"""
from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from prometheus_client import Counter, Gauge

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics — registered at module level so they are available as
# soon as the module is imported (before any CacheService instance is created).
# ---------------------------------------------------------------------------

cache_hits_total = Counter(
    "cache_hits_total",
    "Cache hits",
    ["cache"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Cache misses",
    ["cache"],
)

cache_degraded = Gauge(
    "cache_degraded",
    "1 when cache is in degraded mode",
)


# ---------------------------------------------------------------------------
# CacheService
# ---------------------------------------------------------------------------

class CacheService:
    """Async Redis cache with degraded-mode fallback and Prometheus metrics."""

    def __init__(self, settings_obj: "settings.__class__") -> None:  # type: ignore[name-defined]
        self._settings = settings_obj
        self._client: aioredis.Redis | None = None
        self._degraded: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Redis. On failure, enter degraded mode."""
        try:
            self._client = aioredis.from_url(
                self._settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._client.ping()  # type: ignore[misc]
            self._degraded = False
            cache_degraded.set(0)
            logger.info("CacheService connected to Redis at %s", self._settings.REDIS_URL)
        except Exception as exc:
            logger.warning(
                "CacheService could not connect to Redis (%s); starting in degraded mode",
                exc,
            )
            self._degraded = True
            cache_degraded.set(1)

    async def disconnect(self) -> None:
        """Close the Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    async def ping(self) -> bool:
        """Return True if Redis is reachable, False otherwise."""
        if self._client is None:
            return False
        try:
            result = bool(await self._client.ping())  # type: ignore[misc]
            if result:
                # Clear degraded mode if Redis has recovered
                if self._degraded:
                    self._degraded = False
                    cache_degraded.set(0)
                    logger.info("CacheService: Redis recovered, exiting degraded mode")
            return result
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        """Retrieve a value from Redis. Returns None on miss or degraded mode."""
        if self._degraded or self._client is None:
            return None
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            # Validate JSON to catch corrupt entries
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("CacheService: corrupt JSON at key %r; deleting", key)
                await self._client.delete(key)
                return None
            return raw
        except Exception as exc:
            self._enter_degraded(exc)
            return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        """Store a value in Redis with a TTL. No-op in degraded mode."""
        if self._degraded or self._client is None:
            return
        try:
            await self._client.set(key, value, ex=ttl)
        except Exception as exc:
            self._enter_degraded(exc)

    async def delete(self, key: str) -> None:
        """Delete a key from Redis. No-op in degraded mode."""
        if self._degraded or self._client is None:
            return
        try:
            await self._client.delete(key)
        except Exception as exc:
            self._enter_degraded(exc)

    async def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern* using SCAN + batched DEL.

        Returns the number of keys deleted. No-op (returns 0) in degraded mode.
        Uses SCAN to avoid blocking Redis on large keyspaces.
        """
        if self._degraded or self._client is None:
            return 0
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as exc:
            self._enter_degraded(exc)
        return deleted

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    def make_key(self, domain: str, identifier: str) -> str:
        """Build a versioned cache key: ``<version>:<domain>:<identifier>``."""
        return f"{self._settings.CACHE_KEY_VERSION}:{domain}:{identifier}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enter_degraded(self, exc: Exception) -> None:
        if not self._degraded:
            logger.warning(
                "CacheService: Redis operation failed (%s); entering degraded mode",
                exc,
            )
            self._degraded = True
            cache_degraded.set(1)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

cache_service = CacheService(settings)
