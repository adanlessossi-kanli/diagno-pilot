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
        """Return the embedding vector for *text*."""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": text}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
