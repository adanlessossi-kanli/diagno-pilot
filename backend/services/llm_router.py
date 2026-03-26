"""LLMRouter — routes to MedicalQwen3 (primary) with GPT-5 fallback.

A CircuitBreaker protects the primary LLM: after 5 consecutive failures the
circuit opens and all requests are routed directly to the fallback without
attempting the primary.  If both LLMs are unavailable, HTTP 503 is raised.
"""
from __future__ import annotations

import logging
import time

import httpx
from fastapi import HTTPException

from backend.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from backend.core.config import settings
from backend.core.metrics import llm_duration_seconds, llm_requests_total
logger = logging.getLogger(__name__)


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
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
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
    """Routes generation requests to MedicalQwen3; falls back to GPT-5 on failure.

    A CircuitBreaker wraps the primary LLM call.  Once the circuit opens
    (after ``failure_threshold`` consecutive failures), requests bypass the
    primary entirely and go straight to the fallback.  If the fallback also
    fails, HTTP 503 is raised and a CRITICAL log entry is emitted.
    """

    PRIMARY_MODEL = "MedicalQwen3-Reasoning-14B"
    FALLBACK_MODEL = "gpt-5"

    def __init__(
        self,
        primary_url: str | None = None,
        primary_api_key: str | None = None,
        fallback_url: str | None = None,
        fallback_api_key: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        primary_url = primary_url or settings.LLM_PRIMARY_URL or ""
        primary_api_key = primary_api_key or settings.LLM_PRIMARY_API_KEY or ""
        fallback_url = fallback_url or settings.LLM_FALLBACK_URL or ""
        fallback_api_key = fallback_api_key or settings.LLM_FALLBACK_API_KEY or ""

        self._primary = _LLMClient(primary_url, primary_api_key, self.PRIMARY_MODEL)
        self._fallback = _LLMClient(fallback_url, fallback_api_key, self.FALLBACK_MODEL)
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self.last_used: str = ""

    async def generate(self, prompt: str, context: list[dict]) -> str:
        """Generate a response, falling back to GPT-5 if MedicalQwen3 is unavailable.

        The primary call is wrapped in the circuit breaker.  If the circuit is
        OPEN, or if the primary raises LLMUnavailableError, the fallback is
        tried.  If both fail, HTTP 503 is raised.
        """
        primary_skipped = False

        try:
            t0 = time.perf_counter()
            result = await self._circuit_breaker.call_fn(
                self._primary.generate, prompt, context
            )
            llm_duration_seconds.labels(model="qwen3").observe(time.perf_counter() - t0)
            self.last_used = "qwen3"
            return result
        except CircuitOpenError:
            # Circuit is open — skip primary, go straight to fallback
            primary_skipped = True
            logger.warning("Circuit is OPEN — routing directly to fallback LLM.")
        except LLMUnavailableError:
            # Primary failed — increment error counter (REQ 18.2)
            llm_requests_total.labels(model="qwen3", status="error").inc()

        # Attempt fallback
        try:
            t0 = time.perf_counter()
            result = await self._fallback.generate(prompt, context)
            llm_duration_seconds.labels(model="gpt5").observe(time.perf_counter() - t0)
            # Increment success counter for fallback (REQ 18.3)
            llm_requests_total.labels(model="gpt5", status="success").inc()
            self.last_used = "gpt5"
            return result
        except LLMUnavailableError as exc:
            logger.critical(
                "Both LLMs are unavailable. primary_skipped=%s, error=%s",
                primary_skipped,
                exc,
            )
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc
