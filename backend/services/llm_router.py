"""LLMRouter — routes to MedicalQwen3 (primary) with GPT-5 fallback."""
from __future__ import annotations

import httpx

from backend.core.config import settings


class LLMUnavailableError(Exception):
    """Raised when an LLM endpoint is unavailable or returns an error."""


class _LLMClient:
    """Thin async HTTP client for an OpenAI-compatible chat endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str, context: list[dict]) -> str:
        messages = [{"role": "system", "content": c.get("content", str(c))} for c in context]
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc


class LLMRouter:
    """Routes generation requests to MedicalQwen3; falls back to GPT-5 on failure."""

    PRIMARY_MODEL = "MedicalQwen3-Reasoning-14B"
    FALLBACK_MODEL = "gpt-5"

    def __init__(
        self,
        primary_url: str | None = None,
        primary_api_key: str | None = None,
        fallback_url: str | None = None,
        fallback_api_key: str | None = None,
    ) -> None:
        primary_url = primary_url or settings.LLM_PRIMARY_URL or ""
        primary_api_key = primary_api_key or settings.LLM_PRIMARY_API_KEY or ""
        fallback_url = fallback_url or settings.LLM_FALLBACK_URL or ""
        fallback_api_key = fallback_api_key or settings.LLM_FALLBACK_API_KEY or ""

        self._primary = _LLMClient(primary_url, primary_api_key, self.PRIMARY_MODEL)
        self._fallback = _LLMClient(fallback_url, fallback_api_key, self.FALLBACK_MODEL)
        self.last_used: str = ""

    async def generate(self, prompt: str, context: list[dict]) -> str:
        """Generate a response, falling back to GPT-5 if MedicalQwen3 is unavailable."""
        try:
            result = await self._primary.generate(prompt, context)
            self.last_used = "qwen3"
            return result
        except LLMUnavailableError:
            result = await self._fallback.generate(prompt, context)
            self.last_used = "gpt5"
            return result
