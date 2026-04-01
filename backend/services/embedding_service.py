"""EmbeddingModel — encodes text to float vectors via an OpenAI-compatible API."""
from __future__ import annotations

import hashlib
import json

import httpx

from backend.core.cache import cache_hits_total, cache_misses_total, cache_service
from backend.core.config import settings


class EmbeddingModel:
    """Encodes text into dense float vectors for semantic similarity search.

    This class wraps an OpenAI-compatible ``/embeddings`` endpoint (e.g.
    ``text-embedding-3-small`` or a locally hosted equivalent configured via
    :attr:`~backend.core.config.Settings.EMBED_MODEL`).  The resulting vectors
    are stored in MongoDB Atlas and queried at inference time by
    :class:`~backend.services.rag_service.RAGService`.

    Output dimensionality depends on the underlying model:
        - ``text-embedding-3-small``: 1 536 dimensions.
        - ``text-embedding-3-large``: 3 072 dimensions.
        - Locally hosted models (e.g. ``nomic-embed-text``): typically 768
          dimensions.

    The actual dimension is determined by the model specified in
    :attr:`~backend.core.config.Settings.EMBED_MODEL` and must match the
    dimension configured on the MongoDB Atlas vector index.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        # Reuse the primary LLM endpoint for embeddings (OpenAI-compatible)
        self.base_url = (base_url or settings.LLM_PRIMARY_URL or "").rstrip("/")
        self.api_key = api_key or settings.LLM_PRIMARY_API_KEY or ""
        self.model = model or settings.EMBED_MODEL

    async def encode(self, text: str) -> list[float]:
        """Encode *text* into a dense embedding vector.

        Args:
            text: A single string to embed.  Typical inputs are a clinical
                query, a document chunk, or a symptom description.  The string
                is passed directly to the model without any pre-processing or
                truncation — callers are responsible for keeping the input
                within the model's token limit.

        Returns:
            A ``list[float]`` of length equal to the model's output
            dimensionality (e.g. 1 536 for ``text-embedding-3-small``).  The
            vector is returned as-is from the API response; **no L2
            normalisation** is applied by this method.  If the downstream
            vector index requires normalised vectors, normalisation must be
            performed by the caller before storage or comparison.

        Raises:
            :class:`RuntimeError`: If no embedding endpoints are configured.
            :class:`httpx.HTTPStatusError`: If all configured endpoints return
                a non-2xx HTTP status.
        """
        # Cache lookup
        digest = hashlib.sha256(text.encode()).hexdigest()
        cache_key = cache_service.make_key("embedding", digest)

        cached = await cache_service.get(cache_key)
        if cached is not None:
            cache_hits_total.labels(cache="embedding").inc()
            return json.loads(cached)

        cache_misses_total.labels(cache="embedding").inc()

        vector = await self._call_api(text)
        await cache_service.set(cache_key, json.dumps(vector), ttl=settings.CACHE_TTL_EMBEDDINGS)
        return vector

    async def _call_api(self, text: str) -> list[float]:
        """Call the OpenAI-compatible embeddings API and return the vector."""
        payload = {"model": self.model, "input": text}

        urls_and_keys = []
        if self.base_url:
            urls_and_keys.append((self.base_url, self.api_key))
        fallback_url = (settings.LLM_FALLBACK_URL or "").rstrip("/")
        fallback_key = settings.LLM_FALLBACK_API_KEY or ""
        if fallback_url and fallback_url != self.base_url:
            urls_and_keys.append((fallback_url, fallback_key))

        last_exc: Exception = RuntimeError("No embedding endpoints configured")
        for url, key in urls_and_keys:
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(f"{url}/embeddings", json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["data"][0]["embedding"]
            except Exception as exc:
                last_exc = exc
                continue

        raise last_exc
