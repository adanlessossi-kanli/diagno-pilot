# Requirements Document

## Introduction

This feature hardens the LLM and Vector Search infrastructure of Diagno-Pilot against transient failures and outages. Three areas are addressed:

1. **Exponential backoff and retry** on LLM calls — the current `LLMRouter` and `_LLMClient` make a single attempt before triggering the circuit breaker or falling back. Transient network errors and rate-limit responses should be retried with jittered exponential backoff before counting as failures.
2. **Graceful degradation when Vector Search is unavailable** — `RAGService` currently propagates any MongoDB Atlas `$vectorSearch` error to the caller. When the vector index is unreachable, the service should fall back to a keyword-based search and clearly flag the response as degraded.
3. **LLM health check endpoints** — the `/health` endpoint only pings MongoDB. Clinicians and operators need visibility into the availability of the primary LLM, the fallback LLM, and the embedding service.

Because this is a medical application, every degraded or fallback response MUST carry an explicit warning so clinicians are never misled about the quality of the information they receive.

---

## Glossary

- **LLMRouter**: The backend service (`backend/services/llm_router.py`) that routes generation requests to the primary LLM (MedicalQwen3-Reasoning-14B) and falls back to GPT-5.
- **Primary_LLM**: The self-hosted MedicalQwen3-Reasoning-14B model, reachable at `LLM_PRIMARY_URL`.
- **Fallback_LLM**: The GPT-5 model accessed via the OpenAI API, reachable at `LLM_FALLBACK_URL`.
- **EmbeddingModel**: The backend service (`backend/services/embedding_service.py`) that encodes text to float vectors via an OpenAI-compatible embeddings API.
- **RAGService**: The backend service (`backend/services/rag_service.py`) that performs retrieval-augmented generation using MongoDB Atlas Vector Search.
- **Vector_Search**: The MongoDB Atlas `$vectorSearch` aggregation stage used by RAGService to retrieve relevant document chunks from the `document_chunks` collection.
- **CircuitBreaker**: The existing circuit-breaker component (`backend/core/circuit_breaker.py`) that opens after consecutive failures and prevents further calls to a failing endpoint.
- **RetryPolicy**: A configurable policy that retries a failed operation with jittered exponential backoff before recording a failure.
- **DegradedResponse**: Any API response produced without full RAG context or using the fallback LLM, which MUST include a `degraded_warning` field visible to clinicians.
- **HealthEndpoint**: The `/health` HTTP endpoint that reports the operational status of backend dependencies.
- **LLM_TIMEOUT**: The existing configuration setting (default 60 s) that caps the total time allowed for a single LLM HTTP request.
- **Keyword_Fallback**: A text-index-based MongoDB query used by RAGService when Vector Search is unavailable.

---

## Requirements

### Requirement 1: Exponential Backoff and Retry for LLM Calls

**User Story:** As a backend engineer, I want LLM calls to be retried with exponential backoff before triggering the circuit breaker or falling back, so that transient network errors and rate-limit responses do not unnecessarily degrade service availability.

#### Acceptance Criteria

1. THE RetryPolicy SHALL retry a failed LLM HTTP request up to 3 times before propagating the failure.
2. WHEN a retry attempt is made, THE RetryPolicy SHALL wait for a delay calculated as `min(base_delay * 2^attempt, max_delay)` seconds, where `base_delay` defaults to 1 s and `max_delay` defaults to 30 s.
3. WHEN computing a retry delay, THE RetryPolicy SHALL add a random jitter of up to 1 s to the calculated delay to prevent thundering-herd effects.
4. WHEN an LLM HTTP response has status code 429 or 503, THE RetryPolicy SHALL treat the response as a retryable failure.
5. WHEN an LLM HTTP response has status code 400 or 401, THE RetryPolicy SHALL treat the response as a non-retryable failure and not retry.
6. WHEN all retry attempts are exhausted without success, THE LLMRouter SHALL record the failure against the CircuitBreaker and proceed to the fallback LLM.
7. THE RetryPolicy SHALL be applied independently to the Primary_LLM and to the Fallback_LLM.
8. WHEN a retry succeeds, THE LLMRouter SHALL log the attempt count and the LLM endpoint that ultimately responded at INFO level.
9. THE RetryPolicy SHALL expose `max_retries`, `base_delay`, and `max_delay` as configurable settings via environment variables `LLM_RETRY_MAX`, `LLM_RETRY_BASE_DELAY`, and `LLM_RETRY_MAX_DELAY`.
10. WHILE the total elapsed time for all retry attempts exceeds `LLM_TIMEOUT`, THE RetryPolicy SHALL abort remaining retries and propagate a timeout failure.

---

### Requirement 2: Graceful Degradation When Vector Search Is Unavailable

**User Story:** As a clinician, I want the diagnostic assistant to continue providing answers even when the Vector Search index is temporarily unavailable, so that I can still receive guidance during infrastructure incidents — with a clear warning that the response quality may be reduced.

#### Acceptance Criteria

1. WHEN a `$vectorSearch` aggregation raises an exception, THE RAGService SHALL catch the exception and attempt a Keyword_Fallback query against the `document_chunks` collection using a MongoDB `$text` search on the `content` field.
2. WHEN the Keyword_Fallback query returns at least one document chunk, THE RAGService SHALL use those chunks as context for LLM generation and set `degraded_warning` to `"Vector Search unavailable — response based on keyword retrieval only"` in the RAGResponse.
3. WHEN both the `$vectorSearch` and the Keyword_Fallback query return zero results, THE RAGService SHALL generate an answer using only the patient context (no retrieved chunks) and set `degraded_warning` to `"Vector Search and keyword retrieval unavailable — response generated without document context"` in the RAGResponse.
4. THE RAGResponse model SHALL include a `degraded_warning` field of type `str | None`, defaulting to `None` for fully successful responses.
5. WHEN `degraded_warning` is not `None`, THE RAGService SHALL log the degradation reason at WARNING level, including the original exception message.
6. WHEN `degraded_warning` is not `None`, THE API response body for `/api/v1/chat/message` and `/api/v1/diagnose/symptoms` SHALL include the `degraded_warning` value in a top-level `degraded_warning` field.
7. IF the EmbeddingModel raises an exception during query encoding, THEN THE RAGService SHALL propagate the exception without attempting Vector Search or Keyword_Fallback, and THE LLMRouter SHALL be called with an empty context list.
8. THE Keyword_Fallback query SHALL limit results to the same `top_k` value used by the Vector Search query.

---

### Requirement 3: LLM and Embedding Health Check Endpoints

**User Story:** As an operator, I want the `/health` endpoint to report the availability of the Primary LLM, Fallback LLM, and Embedding service, so that I can detect LLM outages without waiting for a clinician to report a failure.

#### Acceptance Criteria

1. THE HealthEndpoint SHALL include a `llm_primary` field in its response body, with value `"ok"` when the Primary_LLM is reachable and `"unreachable: <reason>"` otherwise.
2. THE HealthEndpoint SHALL include a `llm_fallback` field in its response body, with value `"ok"` when the Fallback_LLM is reachable and `"unreachable: <reason>"` otherwise.
3. THE HealthEndpoint SHALL include a `embedding` field in its response body, with value `"ok"` when the EmbeddingModel endpoint is reachable and `"unreachable: <reason>"` otherwise.
4. WHEN checking LLM availability, THE HealthEndpoint SHALL send a minimal probe request (e.g., a single-token completion or a `GET /models` request) to the configured endpoint URL within a timeout of 5 s.
5. WHEN any of `llm_primary`, `llm_fallback`, or `embedding` is not `"ok"`, THE HealthEndpoint SHALL set the top-level `status` field to `"degraded"`.
6. WHEN all of `db`, `llm_primary`, `llm_fallback`, and `embedding` are `"ok"`, THE HealthEndpoint SHALL set the top-level `status` field to `"ok"`.
7. THE HealthEndpoint SHALL return HTTP 200 regardless of individual component status, so that load balancers do not remove the instance from rotation on partial degradation.
8. WHEN `LLM_PRIMARY_URL` is not configured, THE HealthEndpoint SHALL set `llm_primary` to `"not_configured"` without attempting a probe.
9. WHEN `LLM_FALLBACK_URL` is not configured, THE HealthEndpoint SHALL set `llm_fallback` to `"not_configured"` without attempting a probe.
10. THE HealthEndpoint SHALL execute the MongoDB ping, Primary_LLM probe, Fallback_LLM probe, and Embedding probe concurrently to keep total response time below 6 s.
11. WHEN the HealthEndpoint probe for any LLM component fails, THE HealthEndpoint SHALL log the failure at WARNING level with the component name and error detail.

---

### Requirement 4: Degraded Response Flagging for Clinicians

**User Story:** As a clinician, I want every degraded or fallback response to carry an explicit, human-readable warning, so that I can apply appropriate clinical judgment when the AI assistant is operating in a reduced-capacity mode.

#### Acceptance Criteria

1. WHEN the LLMRouter uses the Fallback_LLM because the Primary_LLM is unavailable, THE LLMRouter SHALL set a `fallback_used` flag to `True` in the response metadata returned to the caller.
2. WHEN `fallback_used` is `True`, THE API response body for `/api/v1/chat/message` and `/api/v1/diagnose/symptoms` SHALL include a `fallback_warning` field with value `"Réponse générée par le modèle de secours (GPT-5) — vérification clinique recommandée"`.
3. WHEN both `fallback_used` is `True` and `degraded_warning` is not `None`, THE API response body SHALL include both `fallback_warning` and `degraded_warning` fields.
4. THE DiagnosticService and ChatService SHALL propagate `fallback_used` and `degraded_warning` from the LLMRouter and RAGService respectively to the API response layer without modification.
5. IF a response carries any warning field (`fallback_warning` or `degraded_warning`), THEN THE API response body SHALL include a top-level `warnings_present` boolean field set to `True`.
