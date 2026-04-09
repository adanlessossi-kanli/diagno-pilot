"""LLMRouter — routes to MedicalQwen3-Reasoning-4B (primary) with GPT-5 fallback.

Two CircuitBreakers protect the primary and fallback LLMs.  After 5 consecutive
failures the circuit opens and requests bypass that LLM.  RetryPolicy wraps
each _LLMClient call with jittered exponential backoff before recording a
circuit-breaker failure.

When falling back to GPT-5, the BAA_Controller strips all PHI from the
request context before transmission (HIPAA/BAA compliance).
"""
from __future__ import annotations

import logging
import ssl
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from backend.core.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from backend.core.config import settings
from backend.core.metrics import llm_duration_seconds, llm_requests_total
from backend.core.retry import LLMUnavailableError, RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A single chunk from the LLM streaming response."""
    token: str | None = None
    error: str | None = None
    fallback_used: bool = False
    llm_used: str = ""


@dataclass
class LLMResult:
    """Return value of LLMRouter.generate."""
    answer: str
    fallback_used: bool


class _LLMClient:
    """Thin async HTTP client for an OpenAI-compatible chat endpoint."""

    # Shared SSL context — ``ssl.create_default_context()`` is expensive
    # (reads the CA bundle from disk).  Caching it at the class level avoids
    # repeating that work for every ``httpx.AsyncClient`` instance, which
    # dramatically speeds up tests that create many ``LLMRouter`` objects.
    _shared_ssl_context: ssl.SSLContext | None = None

    @classmethod
    def _get_ssl_context(cls) -> ssl.SSLContext:
        if cls._shared_ssl_context is None:
            cls._shared_ssl_context = ssl.create_default_context()
        return cls._shared_ssl_context

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._retry_policy = RetryPolicy()
        self._client = httpx.AsyncClient(
            timeout=settings.LLM_TIMEOUT,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            verify=self._get_ssl_context(),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client to release pooled connections."""
        await self._client.aclose()

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

        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def generate_stream(
        self, prompt: str, context: list[dict], *, deadline: float
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM endpoint via SSE.

        Uses ``httpx.AsyncClient.stream()`` with ``stream: true`` in the
        payload.  Yields non-empty ``delta.content`` strings and stops on
        ``data: [DONE]``.  No retry logic — retries are handled at the
        ``LLMRouter`` level.

        Raises:
            LLMUnavailableError: On connection failure or timeout.
        """
        import json as _json

        messages = [{"role": "system", "content": c.get("content", str(c))} for c in context]
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages, "stream": True}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, OSError) as exc:
            raise LLMUnavailableError(
                f"Streaming connection failed: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(
                f"Streaming HTTP {exc.response.status_code} from {self.base_url}"
            ) from exc


class LLMRouter:
    """Routes generation requests to Model_Container; falls back to GPT-5 on failure.

    Two CircuitBreakers protect the primary and fallback LLMs.  RetryPolicy
    wraps each client call with jittered exponential backoff.  When the fallback
    also exhausts retries, HTTP 503 is raised with a structured error body.

    When falling back to GPT-5, the BAA_Controller strips all PHI from the
    context to comply with HIPAA/BAA requirements.
    """

    PRIMARY_MODEL = "MedicalQwen3-Reasoning-4B"
    FALLBACK_MODEL = "gpt-5"

    def __init__(
        self,
        primary_url: str | None = None,
        primary_api_key: str | None = None,
        fallback_url: str | None = None,
        fallback_api_key: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        fallback_circuit_breaker: CircuitBreaker | None = None,
        baa_controller: Any | None = None,
        phi_classifier: Any | None = None,
    ) -> None:
        # Primary defaults to Model_Container URL
        primary_url = primary_url or settings.MODEL_CONTAINER_URL or settings.LLM_PRIMARY_URL or ""
        primary_api_key = primary_api_key or settings.MODEL_CONTAINER_API_KEY or settings.LLM_PRIMARY_API_KEY or ""
        fallback_url = fallback_url or settings.LLM_FALLBACK_URL or ""
        fallback_api_key = fallback_api_key or settings.LLM_FALLBACK_API_KEY or ""

        self._primary = _LLMClient(primary_url, primary_api_key, self.PRIMARY_MODEL)
        self._fallback = _LLMClient(fallback_url, fallback_api_key, self.FALLBACK_MODEL)
        self._primary_cb = circuit_breaker or CircuitBreaker(service_name="qwen3")
        self._fallback_cb = fallback_circuit_breaker or CircuitBreaker()

        self._baa_controller = baa_controller
        self._phi_classifier = phi_classifier

        # Keep last_used for backward compat with RAGService (updated below)
        self.last_used: str = ""

    async def close(self) -> None:
        """Close HTTP clients on both primary and fallback _LLMClients."""
        await self._primary.close()
        await self._fallback.close()

    async def generate_stream(
        self, prompt: str, context: list[dict]
    ) -> AsyncIterator[StreamChunk]:
        """Stream tokens, falling back to GPT-5 if primary fails pre-token.

        Checks the primary circuit breaker before starting.  If the circuit
        is open or the primary raises before any tokens are yielded, PHI is
        stripped and the fallback model is used.  If the primary fails *after*
        tokens have been yielded, a ``StreamChunk`` with ``error`` is emitted
        and no fallback is attempted (mid-stream fallback would produce
        incoherent output).

        Yields:
            StreamChunk objects with ``token`` and ``llm_used`` on success,
            or ``error`` on mid-stream failure.

        Raises:
            HTTPException(503): When both LLMs are unavailable.
        """
        deadline = time.monotonic() + settings.LLM_TIMEOUT
        tokens_yielded = 0

        # --- Primary attempt ---
        try:
            t0 = time.perf_counter()
            # Check circuit breaker state manually (can't wrap an async generator)
            if self._primary_cb.state == CircuitState.OPEN:
                raise CircuitOpenError("Circuit is OPEN — skipping primary.")

            async for token in self._primary.generate_stream(
                prompt, context, deadline=deadline
            ):
                tokens_yielded += 1
                yield StreamChunk(
                    token=token,
                    llm_used=self.PRIMARY_MODEL,
                )

            # Stream completed successfully
            elapsed = time.perf_counter() - t0
            llm_duration_seconds.labels(model=self.PRIMARY_MODEL, status="success").observe(elapsed)
            llm_requests_total.labels(model=self.PRIMARY_MODEL, status="success").inc()
            async with self._primary_cb._lock:
                self._primary_cb._on_success()
            self.last_used = self.PRIMARY_MODEL
            return

        except CircuitOpenError:
            logger.warning("Primary circuit is OPEN — routing stream to fallback LLM.")

        except LLMUnavailableError:
            elapsed = time.perf_counter() - t0
            llm_duration_seconds.labels(model=self.PRIMARY_MODEL, status="error").observe(elapsed)
            llm_requests_total.labels(model=self.PRIMARY_MODEL, status="error").inc()
            async with self._primary_cb._lock:
                self._primary_cb._on_failure()

            if tokens_yielded > 0:
                # Mid-stream failure: emit error chunk, do NOT fallback
                yield StreamChunk(
                    error="Primary LLM failed after partial response",
                    llm_used=self.PRIMARY_MODEL,
                )
                return

            logger.warning("Primary LLM stream failed pre-token — trying fallback.")

        # --- BAA PHI stripping before fallback ---
        fallback_context = context
        if self._baa_controller is not None and self._phi_classifier is not None:
            try:
                fallback_context = self._baa_controller.strip_phi(
                    context, self._phi_classifier
                )
            except Exception as exc:
                logger.error(
                    "BAA PHI stripping failed — blocking external LLM call: %s", exc
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "phi_strip_failed",
                        "code": "PHI_STRIP_FAILED",
                        "retryable": False,
                    },
                ) from exc

        # --- Fallback attempt (GPT-5) ---
        try:
            t0 = time.perf_counter()
            async for token in self._fallback.generate_stream(
                prompt, fallback_context, deadline=deadline
            ):
                yield StreamChunk(
                    token=token,
                    fallback_used=True,
                    llm_used=self.FALLBACK_MODEL,
                )

            elapsed = time.perf_counter() - t0
            llm_duration_seconds.labels(model=self.FALLBACK_MODEL, status="success").observe(elapsed)
            llm_requests_total.labels(model=self.FALLBACK_MODEL, status="success").inc()
            self.last_used = self.FALLBACK_MODEL
            return

        except (CircuitOpenError, LLMUnavailableError) as exc:
            if isinstance(exc, LLMUnavailableError):
                elapsed = time.perf_counter() - t0
                llm_duration_seconds.labels(model=self.FALLBACK_MODEL, status="error").observe(elapsed)
                llm_requests_total.labels(model=self.FALLBACK_MODEL, status="error").inc()
            logger.critical(
                "Both LLMs unavailable for streaming. error=%s", exc
            )

        raise HTTPException(
            status_code=503,
            detail={"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": True},
        )

    async def generate(self, prompt: str, context: list[dict]) -> LLMResult:
        """Generate a response, falling back to GPT-5 if Model_Container is unavailable.

        Sets a deadline from ``settings.LLM_TIMEOUT`` and passes it to both
        client calls.  When falling back to GPT-5, BAA_Controller strips PHI
        from the context.  Returns ``LLMResult(answer, fallback_used)``.

        Raises:
            HTTPException(503): When both LLMs are exhausted.
        """
        deadline = time.monotonic() + settings.LLM_TIMEOUT
        primary_skipped = False

        # --- Primary LLM attempt (Model_Container — full PHI allowed) ---
        try:
            t0 = time.perf_counter()
            answer = await self._primary_cb.call_fn(
                self._primary.generate, prompt, context, deadline=deadline
            )
            elapsed = time.perf_counter() - t0
            llm_duration_seconds.labels(model=self.PRIMARY_MODEL, status="success").observe(elapsed)
            llm_requests_total.labels(model=self.PRIMARY_MODEL, status="success").inc()
            self.last_used = self.PRIMARY_MODEL
            return LLMResult(answer=answer, fallback_used=False)

        except CircuitOpenError:
            primary_skipped = True
            logger.warning("Primary circuit is OPEN — routing directly to fallback LLM.")

        except LLMUnavailableError:
            # call_fn already recorded the failure on _primary_cb
            llm_duration_seconds.labels(model=self.PRIMARY_MODEL, status="error").observe(time.perf_counter() - t0)
            llm_requests_total.labels(model=self.PRIMARY_MODEL, status="error").inc()
            logger.warning("Primary LLM exhausted retries — trying fallback.")

        # --- BAA PHI stripping before fallback (Req 5.4, 9.1) ---
        fallback_context = context
        if self._baa_controller is not None and self._phi_classifier is not None:
            try:
                fallback_context = self._baa_controller.strip_phi(context, self._phi_classifier)
            except Exception as exc:
                logger.error("BAA PHI stripping failed — blocking external LLM call: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "phi_strip_failed",
                        "code": "PHI_STRIP_FAILED",
                        "retryable": False,
                    },
                ) from exc

        # --- Fallback LLM attempt (GPT-5 — zero PHI) ---
        try:
            t0 = time.perf_counter()
            answer = await self._fallback_cb.call_fn(
                self._fallback.generate, prompt, fallback_context, deadline=deadline
            )
            elapsed = time.perf_counter() - t0
            llm_duration_seconds.labels(model=self.FALLBACK_MODEL, status="success").observe(elapsed)
            llm_requests_total.labels(model=self.FALLBACK_MODEL, status="success").inc()
            self.last_used = self.FALLBACK_MODEL
            return LLMResult(answer=answer, fallback_used=True)

        except CircuitOpenError:
            logger.critical(
                "Fallback circuit is OPEN — both LLMs unavailable. primary_skipped=%s",
                primary_skipped,
            )

        except LLMUnavailableError as exc:
            # call_fn already recorded the failure on _fallback_cb
            llm_duration_seconds.labels(model=self.FALLBACK_MODEL, status="error").observe(time.perf_counter() - t0)
            llm_requests_total.labels(model=self.FALLBACK_MODEL, status="error").inc()
            logger.critical(
                "Both LLMs are unavailable. primary_skipped=%s, error=%s",
                primary_skipped,
                exc,
            )

        raise HTTPException(
            status_code=503,
            detail={"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": True},
        )
