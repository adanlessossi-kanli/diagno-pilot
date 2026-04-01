"""LLMRouter — routes to MedicalQwen3 (primary) with GPT-5 fallback.

Two CircuitBreakers protect the primary and fallback LLMs.  After 5 consecutive
failures the circuit opens and requests bypass that LLM.  RetryPolicy wraps
each _LLMClient call with jittered exponential backoff before recording a
circuit-breaker failure.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from backend.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from backend.core.config import settings
from backend.core.metrics import llm_duration_seconds, llm_requests_total
from backend.core.retry import LLMUnavailableError, RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    """Return value of LLMRouter.generate."""
    answer: str
    fallback_used: bool


class _LLMClient:
    """Thin async HTTP client for an OpenAI-compatible chat endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._retry_policy = RetryPolicy()

    async def generate(self, prompt: str, context: list[dict], *, deadline: float) -> str:
        """Generate a response, delegating retries to RetryPolicy.

        Args:
            prompt:   User prompt.
            context:  List of context messages.
            deadline: Monotonic deadline; RetryPolicy aborts if exceeded.

        Returns:
            The LLM-generated text.

        Raises:
            LLMUnavailableError: When all retries are exhausted or deadline exceeded.
        """
        return await self._retry_policy.execute(
            self._do_request, prompt, context, deadline=deadline
        )

    async def _do_request(self, prompt: str, context: list[dict]) -> str:
        """Single HTTP request to the LLM endpoint (no retry logic here)."""
        messages = [{"role": "system", "content": c.get("content", str(c))} for c in context]
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class LLMRouter:
    """Routes generation requests to MedicalQwen3; falls back to GPT-5 on failure.

    Two CircuitBreakers protect the primary and fallback LLMs.  RetryPolicy
    wraps each client call with jittered exponential backoff.  When the fallback
    also exhausts retries, HTTP 503 is raised with a structured error body.
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
        fallback_circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        primary_url = primary_url or settings.LLM_PRIMARY_URL or ""
        primary_api_key = primary_api_key or settings.LLM_PRIMARY_API_KEY or ""
        fallback_url = fallback_url or settings.LLM_FALLBACK_URL or ""
        fallback_api_key = fallback_api_key or settings.LLM_FALLBACK_API_KEY or ""

        self._primary = _LLMClient(primary_url, primary_api_key, self.PRIMARY_MODEL)
        self._fallback = _LLMClient(fallback_url, fallback_api_key, self.FALLBACK_MODEL)
        self._primary_cb = circuit_breaker or CircuitBreaker()
        self._fallback_cb = fallback_circuit_breaker or CircuitBreaker()

        # Keep last_used for backward compat with RAGService (updated below)
        self.last_used: str = ""

    async def generate(self, prompt: str, context: list[dict]) -> LLMResult:
        """Generate a response, falling back to GPT-5 if MedicalQwen3 is unavailable.

        Sets a deadline from ``settings.LLM_TIMEOUT`` and passes it to both
        client calls.  Returns ``LLMResult(answer, fallback_used)``.

        Raises:
            HTTPException(503): When both LLMs are exhausted.
        """
        deadline = time.monotonic() + settings.LLM_TIMEOUT
        primary_skipped = False

        # --- Primary LLM attempt ---
        try:
            t0 = time.perf_counter()
            answer = await self._primary_cb.call_fn(
                self._primary.generate, prompt, context, deadline=deadline
            )
            llm_duration_seconds.labels(model="qwen3").observe(time.perf_counter() - t0)
            llm_requests_total.labels(model="qwen3", status="success").inc()
            self.last_used = "qwen3"
            return LLMResult(answer=answer, fallback_used=False)

        except CircuitOpenError:
            primary_skipped = True
            logger.warning("Primary circuit is OPEN — routing directly to fallback LLM.")

        except LLMUnavailableError:
            # call_fn already recorded the failure on _primary_cb
            llm_requests_total.labels(model="qwen3", status="error").inc()
            logger.warning("Primary LLM exhausted retries — trying fallback.")

        # --- Fallback LLM attempt ---
        try:
            t0 = time.perf_counter()
            answer = await self._fallback_cb.call_fn(
                self._fallback.generate, prompt, context, deadline=deadline
            )
            llm_duration_seconds.labels(model="gpt5").observe(time.perf_counter() - t0)
            llm_requests_total.labels(model="gpt5", status="success").inc()
            self.last_used = "gpt5"
            return LLMResult(answer=answer, fallback_used=True)

        except CircuitOpenError:
            logger.critical(
                "Fallback circuit is OPEN — both LLMs unavailable. primary_skipped=%s",
                primary_skipped,
            )

        except LLMUnavailableError as exc:
            # call_fn already recorded the failure on _fallback_cb
            llm_requests_total.labels(model="gpt5", status="error").inc()
            logger.critical(
                "Both LLMs are unavailable. primary_skipped=%s, error=%s",
                primary_skipped,
                exc,
            )

        raise HTTPException(
            status_code=503,
            detail={"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": True},
        )
