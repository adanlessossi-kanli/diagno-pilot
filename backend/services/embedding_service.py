"""EmbeddingModel — encodes text to float vectors via an OpenAI-compatible API."""
from __future__ import annotations

import httpx

from backend.core.config import settings


class EmbeddingModel:
    """Encodes text into embedding vectors using the configured embedding API."""

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
        """Return the embedding vector for *text*, trying primary then fallback URL."""
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
