# Implementation Plan: Caching and Performance

## Overview

Introduce a Redis-backed `CacheService` singleton to the Diagno-Pilot backend, integrate it into `PrescriptionService`, `AlertService`, `EmbeddingModel`, and `RAGService`, migrate rate-limit storage to Redis, add Prometheus observability, and wire everything together via the lifespan handler.

## Tasks

- [x] 1. Extend Settings with cache configuration fields
  - Add `REDIS_URL`, `CACHE_TTL_PROTOCOLS`, `CACHE_TTL_INTERACTIONS`, `CACHE_TTL_EMBEDDINGS`, `CACHE_TTL_RAG`, `CACHE_KEY_VERSION` fields to `backend/core/config.py` using `pydantic-settings`
  - Add `@model_validator(mode="after")` to set `RATE_LIMIT_STORAGE_URI` from `REDIS_URL` when `REDIS_URL` is set and `RATE_LIMIT_STORAGE_URI` is still `memory://`
  - _Requirements: 7.1, 7.2, 7.3, 9.4, 6.1, 6.2_

  - [x] 1.1 Write property test for TTL validation (Property 11)
    - **Property 11: TTL settings reject non-integer values**
    - **Validates: Requirements 7.3**

  - [x] 1.2 Write unit tests for Settings defaults and rate-limit migration
    - Assert all new fields have correct defaults when env vars are absent
    - Assert `RATE_LIMIT_STORAGE_URI` equals `REDIS_URL` when `REDIS_URL` is set
    - _Requirements: 7.1, 7.2, 6.1, 6.2_

- [x] 2. Implement `CacheService` core in `backend/core/cache.py`
  - Create `CacheService` class with `connect()`, `disconnect()`, `get()`, `set()`, `delete()`, `flush_pattern()`, `make_key()`, `is_degraded` property, and `ping()` method
  - Register Prometheus metrics at module level: `cache_hits_total` (Counter, label `cache`), `cache_misses_total` (Counter, label `cache`), `cache_degraded` (Gauge)
  - Implement degraded mode: entered on `connect()` failure or any Redis operation exception; `get()` returns `None`, `set()`/`delete()`/`flush_pattern()` are no-ops; `cache_degraded` gauge set to `1`
  - Implement `flush_pattern()` using `SCAN` + batched `DEL` (not `KEYS`)
  - Implement deserialisation error handling in `get()`: catch `json.JSONDecodeError`, delete corrupt key, return `None`
  - Expose module-level `cache_service` singleton
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2, 8.3, 9.1, 9.2_

  - [x] 2.1 Write property test for degraded mode bypass (Property 1)
    - **Property 1: Degraded mode is a transparent no-op**
    - **Validates: Requirements 1.4, 2.6, 3.5, 4.5, 5.6**

  - [x] 2.2 Write property test for cache key format invariant (Property 7)
    - **Property 7: Cache key format invariant**
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [x] 2.3 Write unit tests for `CacheService`
    - Test `make_key()` output for known inputs
    - Test degraded mode: mock Redis to raise `ConnectionError`; assert `get()` returns `None` and `set()` is a no-op
    - Test `cache_degraded` gauge is `1` in degraded mode and `0` when healthy
    - _Requirements: 1.3, 1.4, 8.3_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Integrate `CacheService` into `PrescriptionService`
  - Modify `load_protocols_from_db()` in `PrescriptionService` to store each protocol under `v1:protocol:<name>` with `CACHE_TTL_PROTOCOLS` TTL after loading from MongoDB
  - Modify `_get_protocol(name)` to check Redis first, then fall back to in-process dict, then built-in fallback
  - Modify `reload_protocols()` (admin endpoint handler) to call `cache_service.delete(make_key("protocol", name))` for single-key invalidation and `cache_service.flush_pattern(make_key("protocol", "*"))` for full reload
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 4.1 Write property test for protocol cache round-trip (Property 2)
    - **Property 2: Protocol cache round-trip**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 4.2 Write property test for cache invalidation on admin write (Property 9)
    - **Property 9: Cache invalidation on admin write**
    - **Validates: Requirements 2.4, 3.4**

  - [x] 4.3 Write unit tests for `PrescriptionService` cache integration
    - Test cache hit path: mock `cache_service.get()` to return serialised protocol; assert MongoDB is not queried
    - Test cache miss path: assert protocol is fetched from MongoDB and stored in cache
    - Test degraded mode fallback to in-process dict
    - _Requirements: 2.2, 2.3, 2.6_

- [x] 5. Integrate `CacheService` into `AlertService`
  - Modify `load_interactions_from_db()` to store the full interaction list under `v1:drug_interactions:all` with `CACHE_TTL_INTERACTIONS` TTL
  - Modify `_get_interactions()` to check Redis first, then fall back to in-process list
  - Modify the admin drug-interaction update handler to call `cache_service.delete(make_key("drug_interactions", "all"))`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.1 Write property test for interaction cache round-trip (Property 3)
    - **Property 3: Interaction cache round-trip**
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 5.2 Write unit tests for `AlertService` cache integration
    - Test cache hit path: mock `cache_service.get()` to return serialised list; assert MongoDB is not queried
    - Test cache miss path: assert list is fetched from MongoDB and stored in cache
    - Test degraded mode fallback to in-process list
    - _Requirements: 3.2, 3.3, 3.5_

- [x] 6. Integrate `CacheService` into `EmbeddingModel`
  - Wrap `encode(text)` with cache logic: compute `sha256(text.encode()).hexdigest()`, build key `v1:embedding:<digest>`, check cache, return cached vector on hit, call OpenAI API on miss and store result with `CACHE_TTL_EMBEDDINGS` TTL
  - Increment `cache_hits_total{cache="embedding"}` on hit and `cache_misses_total{cache="embedding"}` on miss
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 6.1 Write property test for embedding cache round-trip (Property 4)
    - **Property 4: Embedding cache round-trip**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.6**

  - [x] 6.2 Write property test for deterministic key derivation (Property 6)
    - **Property 6: Deterministic cache key derivation**
    - **Validates: Requirements 4.1, 5.1**

  - [x] 6.3 Write unit tests for `EmbeddingModel` cache integration
    - Test cache hit: mock `cache_service.get()` to return serialised vector; assert OpenAI API is not called
    - Test cache miss: assert OpenAI API is called and result is stored in cache
    - Test degraded mode: assert OpenAI API is called directly without error
    - _Requirements: 4.2, 4.3, 4.5_

- [x] 7. Integrate `CacheService` into `RAGService`
  - Wrap `query(question, context, top_k)` with cache logic: compute question hash, optionally incorporate `sha256(context.model_dump_json().encode()).hexdigest()` when `context` is not `None`, build key `v1:rag:<identifier>`, check cache, return `RAGResponse.model_validate_json(cached)` on hit, execute full pipeline on miss and store `response.model_dump_json()` with `CACHE_TTL_RAG` TTL
  - Increment `cache_hits_total{cache="rag"}` on hit and `cache_misses_total{cache="rag"}` on miss
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7_

  - [x] 7.1 Write property test for RAG response cache round-trip (Property 5)
    - **Property 5: RAG response cache round-trip**
    - **Validates: Requirements 5.2, 5.3, 5.4**

  - [x] 7.2 Write property test for patient context key isolation (Property 8)
    - **Property 8: Patient context key isolation**
    - **Validates: Requirements 5.7**

  - [x] 7.3 Write unit tests for `RAGService` cache integration
    - Test cache hit: mock `cache_service.get()` to return serialised `RAGResponse`; assert pipeline is not executed
    - Test cache miss: assert pipeline is executed and result is stored in cache
    - Test degraded mode: assert full pipeline executes without error
    - Test patient context produces different keys for different patients
    - _Requirements: 5.2, 5.3, 5.6, 5.7_

- [x] 8. Add RAG cache flush to the documents router
  - After successful document ingestion in the documents router, call `await cache_service.flush_pattern(cache_service.make_key("rag", "*"))` and log the number of flushed entries
  - _Requirements: 5.5_

  - [x] 8.1 Write unit test for RAG cache flush on document upload
    - Mock `cache_service.flush_pattern`; assert it is called with `v1:rag:*` after successful ingestion
    - _Requirements: 5.5_

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Wire `CacheService` into the lifespan handler and `/health` endpoint
  - In `backend/main.py` lifespan handler: call `await cache_service.connect()` before yielding, fire `asyncio.create_task(_warm_up_cache())` as a non-blocking background task, call `await cache_service.disconnect()` after yielding
  - Implement `_warm_up_cache()` with `asyncio.timeout(10)` wrapping calls to `prescription_service.load_protocols_from_db()` and `alert_service.load_interactions_from_db()`; catch `TimeoutError` and log warning; catch `Exception` and log error
  - Extend the `/health` endpoint to call `await cache_service.ping()` and include `redis` field (`"ok"` or `"degraded"`) and update `status` to `"degraded"` when Redis is unhealthy
  - _Requirements: 1.1, 1.3, 1.5, 1.6, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 10.1 Write unit tests for lifespan and health endpoint
    - Test `/health` response includes `redis` field with `"ok"` or `"degraded"`
    - Test warm-up timeout: mock `load_protocols_from_db` to sleep > 10 s; assert warm-up exits without blocking the application
    - _Requirements: 1.5, 10.5, 10.6_

- [x] 11. Add Prometheus metrics to `/metrics` endpoint
  - Verify that `cache_hits_total`, `cache_misses_total`, and `cache_degraded` are included in the Prometheus exposition output at `/metrics` (metrics are registered at module import time in `cache.py`; confirm the existing metrics middleware picks them up)
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 11.1 Write property test for metrics counter increments (Property 10)
    - **Property 10: Metrics counters increment on every hit and miss**
    - **Validates: Requirements 8.1, 8.2**

  - [x] 11.2 Write unit test for `/metrics` endpoint
    - Assert response body contains `cache_hits_total`, `cache_misses_total`, `cache_degraded`
    - _Requirements: 8.4_

- [x] 12. Write integration tests using `fakeredis`
  - Create `backend/tests/test_cache_integration.py` using `fakeredis` async variant
  - Cover: full get/set/delete/flush_pattern cycle, key versioning, degraded mode recovery, warm-up with mocked MongoDB
  - _Requirements: 1.1, 1.4, 1.6, 9.3, 10.1_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All property tests use `@settings(max_examples=100)` and are tagged with `# Feature: caching-and-performance, Property N: <text>`
- Use `fakeredis` (async variant) for all tests requiring a Redis instance — no live Redis needed in CI
- `flush_pattern()` must use `SCAN` + batched `DEL` to avoid blocking Redis
