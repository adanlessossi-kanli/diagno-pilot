# Implementation Plan: LLM Resilience

## Overview

Harden the Diagno-Pilot backend against transient LLM and Vector Search failures by implementing retry with exponential backoff, keyword fallback for RAG, extended health checks, and degraded-response flagging.

## Tasks

- [x] 1. Add retry configuration to Settings and update RAGResponse model
  - [x] 1.1 Add `LLM_RETRY_MAX`, `LLM_RETRY_BASE_DELAY`, `LLM_RETRY_MAX_DELAY` fields to `Settings` in `backend/core/config.py`
    - Defaults: `3`, `1.0`, `30.0`
    - _Requirements: 1.9_
  - [x] 1.2 Add `degraded_warning: str | None = None` and `fallback_used: bool = False` fields to `RAGResponse` in `backend/models/document.py`
    - _Requirements: 2.4, 4.1_

- [x] 2. Implement `RetryPolicy` in `backend/core/retry.py`
  - [x] 2.1 Create `backend/core/retry.py` with `RetryPolicy` class
    - Constructor accepts `max_retries`, `base_delay`, `max_delay` (read from `settings` by default)
    - `retryable_status_codes = frozenset({429, 503})`, `non_retryable_status_codes = frozenset({400, 401})`
    - `execute(fn, *args, deadline: float, **kwargs)` method: runs `fn`, retries on retryable HTTP errors or network exceptions, aborts on non-retryable status codes, aborts when `time.monotonic() >= deadline`
    - Delay formula: `min(base_delay * 2^attempt, max_delay) + uniform(0, 1)`
    - Log each attempt at DEBUG with `attempt_number`, `endpoint_url`, `status_code`/exception type, `delay_seconds`
    - Log successful retry at INFO with attempt count and endpoint
    - Raise `LLMUnavailableError` on exhaustion or deadline exceeded
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.10, 1.12_
  - [x] 2.2 Write property test for retry count bound (Property 1)
    - **Property 1: Retry count is bounded**
    - **Validates: Requirements 1.1**
    - File: `backend/tests/test_retry_policy.py`
  - [x] 2.3 Write property test for retry delay bounds (Property 2)
    - **Property 2: Retry delay is within expected bounds**
    - **Validates: Requirements 1.2, 1.3**
    - File: `backend/tests/test_retry_policy.py`
  - [x] 2.4 Write property test for retry classification by HTTP status (Property 3)
    - **Property 3: Retry classification by HTTP status code**
    - **Validates: Requirements 1.4, 1.5**
    - File: `backend/tests/test_retry_policy.py`
  - [x] 2.5 Write property test for deadline aborting retries (Property 5)
    - **Property 5: Deadline aborts remaining retries**
    - **Validates: Requirements 1.10**
    - File: `backend/tests/test_retry_policy.py`

- [x] 3. Integrate `RetryPolicy` into `_LLMClient` and update `LLMRouter`
  - [x] 3.1 Modify `_LLMClient.generate` in `backend/services/llm_router.py` to accept a `deadline: float` parameter and delegate to `RetryPolicy.execute`
    - Extract HTTP status code from `httpx.HTTPStatusError` to pass to retry logic
    - _Requirements: 1.1–1.5, 1.8, 1.10, 1.12_
  - [x] 3.2 Add a second `CircuitBreaker` instance `_fallback_cb` to `LLMRouter` for the fallback LLM
    - _Requirements: 1.7, 1.13_
  - [x] 3.3 Update `LLMRouter.generate` to:
    - Set `deadline = time.monotonic() + settings.LLM_TIMEOUT` before first call
    - Pass `deadline` to both `_primary` and `_fallback` client calls
    - Wrap fallback call with `_fallback_cb`
    - Record failure on `_fallback_cb` when fallback exhausts retries
    - Return `LLMResult(answer: str, fallback_used: bool)` instead of bare `str`
    - Raise `HTTPException(503, {"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": True})` when fallback also fails
    - _Requirements: 1.6, 1.7, 1.10, 1.11, 1.13, 4.1_
  - [x] 3.4 Write property test for circuit breaker failure count on retry exhaustion (Property 4)
    - **Property 4: Circuit breaker records failure on retry exhaustion**
    - **Validates: Requirements 1.6, 1.13**
    - File: `backend/tests/test_retry_policy.py`
  - [x] 3.5 Write unit tests for 503 structured error body when both LLMs are exhausted
    - Assert response body contains `error`, `code`, and `retryable` fields
    - File: `backend/tests/test_llm_router_resilience.py`
    - _Requirements: 1.11_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement keyword fallback in `RAGService`
  - [x] 5.1 Modify `RAGService.query` in `backend/services/rag_service.py` to wrap the `$vectorSearch` aggregation in `try/except`
    - On exception: attempt `$text` search on `content` field limited to `top_k`
    - If keyword fallback returns results: set `degraded_warning = "Vector Search unavailable — response based on keyword retrieval only"`
    - If both return zero results: generate answer with no chunks and set `degraded_warning = "Vector Search and keyword retrieval unavailable — response generated without document context"`
    - Log degradation reason at WARNING with original exception message
    - If `EmbeddingModel.encode` raises, propagate immediately without fallback
    - Populate `fallback_used` on `RAGResponse` from `LLMRouter` result
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.8_
  - [x] 5.2 Write property test for vector search failure triggering degraded_warning round-trip (Property 6)
    - **Property 6: Vector search failure triggers degraded_warning round-trip**
    - **Validates: Requirements 2.1, 2.2, 2.6**
    - File: `backend/tests/test_rag_service_degraded.py`
  - [x] 5.3 Write property test for keyword fallback respecting top_k (Property 7)
    - **Property 7: Keyword fallback respects top_k**
    - **Validates: Requirements 2.8**
    - File: `backend/tests/test_rag_service_degraded.py`
  - [x] 5.4 Write unit test for embedding exception propagation without fallback
    - Assert that an exception from `EmbeddingModel.encode` propagates to the caller unchanged
    - File: `backend/tests/test_rag_service_degraded.py`
    - _Requirements: 2.7_

- [x] 6. Extend `/health` endpoint with LLM and embedding probes
  - [x] 6.1 Add private probe functions `_probe_llm_primary`, `_probe_llm_fallback`, `_probe_embedding` in `backend/main.py`
    - Each sends a minimal probe (e.g. `GET /models`) with a 5 s `httpx` timeout
    - Returns `"ok"`, `"not_configured"` (when URL not set), or `"unreachable: <reason>"`
    - Logs failure at WARNING with component name and error detail
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.8, 3.9, 3.11_
  - [x] 6.2 Update the `/health` route to run all four probes concurrently via `asyncio.gather`
    - Derive top-level `status` as `"ok"` only when all four components are `"ok"`, otherwise `"degraded"`
    - Always return HTTP 200
    - _Requirements: 3.5, 3.6, 3.7, 3.10_
  - [x] 6.3 Write property test for health response structure and status derivation (Property 8)
    - **Property 8: Health response structure and overall status derivation**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6**
    - File: `backend/tests/test_health_endpoint.py`
  - [x] 6.4 Write property test for health endpoint always returning HTTP 200 (Property 9)
    - **Property 9: Health endpoint always returns HTTP 200**
    - **Validates: Requirements 3.7**
    - File: `backend/tests/test_health_endpoint.py`
  - [x] 6.5 Write unit test for `"not_configured"` fields when URLs are absent
    - File: `backend/tests/test_health_endpoint.py`
    - _Requirements: 3.8, 3.9_
  - [x] 6.6 Write unit test for concurrent probe execution
    - Mock all probes with `asyncio.sleep` delays and assert total time ≈ max(delays)
    - File: `backend/tests/test_health_endpoint.py`
    - _Requirements: 3.10_

- [x] 7. Propagate warning fields through the API response layer
  - [x] 7.1 Update `RAGService.query` callers (`DiagnosticService`, `ChatService`) to pass `fallback_used` and `degraded_warning` through to the API response without modification
    - _Requirements: 4.4_
  - [x] 7.2 Update the `/api/v1/chat/message` response model and handler to include `fallback_warning`, `degraded_warning`, and `warnings_present` fields
    - `fallback_warning = "Réponse générée par le modèle de secours (GPT-5) — vérification clinique recommandée"` when `fallback_used=True`
    - `warnings_present = True` when either warning field is present
    - _Requirements: 4.2, 4.3, 4.5_
  - [x] 7.3 Update the `/api/v1/diagnose/symptoms` response model and handler identically
    - _Requirements: 4.2, 4.3, 4.5_
  - [x] 7.4 Write property test for fallback_used flag correctness (Property 10)
    - **Property 10: fallback_used flag is set when fallback LLM is used**
    - **Validates: Requirements 4.1**
    - File: `backend/tests/test_llm_router_resilience.py`
  - [x] 7.5 Write property test for warning fields propagating unchanged to API response (Property 11)
    - **Property 11: Warning fields propagate unchanged to API response**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    - File: `backend/tests/test_llm_router_resilience.py`

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use Hypothesis (`@settings(max_examples=100)`) — the `.hypothesis/` directory already exists in the project
- Each property test must include a comment: `# Feature: llm-resilience, Property {N}: {property_text}`
- `LLMRouter.generate` return type changes from `str` to `LLMResult` — update all call sites in `RAGService` accordingly
