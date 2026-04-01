# Requirements Document

## Introduction

This feature introduces a Redis caching layer to the Diagno-Pilot backend to improve performance and enable horizontal scaling. The scope covers four areas:

1. **Protocol cache** — antibiotic protocols currently loaded from MongoDB into a per-process dict by `PrescriptionService` are moved to Redis so all instances share a single source of truth.
2. **Drug-interaction cache** — drug interactions currently loaded from MongoDB into a per-process list by `AlertService` are moved to Redis for the same reason.
3. **Embedding cache** — `EmbeddingModel.encode()` calls the OpenAI API on every invocation; identical texts should be served from Redis to avoid redundant API calls and latency.
4. **Vector-search result cache** — `RAGService.query()` executes a MongoDB Atlas `$vectorSearch` pipeline on every call; semantically identical queries should be served from Redis.
5. **Rate-limit storage migration** — `slowapi` is currently configured with `memory://` storage, which is per-process and incompatible with multi-instance deployments; it must be migrated to Redis.

---

## Glossary

- **Cache_Service**: The Redis-backed caching component responsible for storing and retrieving serialised data with configurable TTLs.
- **Redis**: The external in-memory data store used as the shared cache and rate-limit backend.
- **PrescriptionService**: The FastAPI service that calculates antibiotic prescriptions and holds the antibiotic-protocol data.
- **AlertService**: The FastAPI service that checks drug interactions, allergies, and contraindications.
- **EmbeddingModel**: The component that calls the OpenAI-compatible embeddings API to convert text to float vectors.
- **RAGService**: The retrieval-augmented generation service that runs `$vectorSearch` against MongoDB Atlas and generates answers via the LLM router.
- **Rate_Limiter**: The `slowapi`-based middleware that enforces per-user/per-IP request rate limits.
- **Cache_Key**: A deterministic string derived from the input data used to look up a cached value.
- **Cache_Key_Version**: A short prefix (e.g. `v1`) embedded at the start of every Cache_Key to namespace entries by serialisation schema version.
- **TTL**: Time-to-live; the duration in seconds after which a cached entry is automatically evicted.
- **Cache_Hit**: A successful retrieval of a value from Redis without querying the origin data source.
- **Cache_Miss**: A failed retrieval that requires the origin data source to be queried and the result stored in Redis.
- **Invalidation**: The act of removing or expiring a cached entry so the next access fetches fresh data.
- **Warm-up**: The process of pre-populating the cache at application startup.

---

## Requirements

### Requirement 1: Redis Connection Management

**User Story:** As a backend engineer, I want the application to manage a single shared Redis connection pool, so that all services can use Redis without creating redundant connections.

#### Acceptance Criteria

1. THE Cache_Service SHALL connect to Redis using the URL provided by the `REDIS_URL` environment variable at application startup.
2. WHEN the `REDIS_URL` environment variable is not set, THE Cache_Service SHALL default to `redis://localhost:6379/0`.
3. WHEN Redis is unreachable at startup, THE Cache_Service SHALL log a warning and allow the application to start in degraded mode without caching.
4. WHILE operating in degraded mode, THE Cache_Service SHALL bypass all cache reads and writes and fall through to the origin data source.
5. THE Cache_Service SHALL expose a health status that the `/health` endpoint includes in its response.
6. WHEN the Redis connection is lost during operation, THE Cache_Service SHALL attempt reconnection with exponential back-off and continue serving requests from origin data sources in the interim.

---

### Requirement 2: Antibiotic Protocol Cache

**User Story:** As a backend engineer, I want antibiotic protocols to be stored in Redis, so that all application instances share the same protocol data and MongoDB is not queried on every startup.

#### Acceptance Criteria

1. WHEN `PrescriptionService` loads protocols at startup, THE Cache_Service SHALL store each protocol serialised as JSON under a key of the form `protocol:<name>` with a TTL of 3600 seconds.
2. WHEN `PrescriptionService` requests a protocol by name, THE Cache_Service SHALL return the cached value if a Cache_Hit occurs, without querying MongoDB.
3. WHEN a Cache_Miss occurs for a protocol key, THE PrescriptionService SHALL fetch the protocol from MongoDB, store it in the Cache_Service, and return it to the caller.
4. WHEN an administrator updates or creates an antibiotic protocol via the admin API, THE admin API SHALL call the Cache_Service directly to delete the corresponding `protocol:<name>` key, and THE Cache_Service SHALL confirm the deletion within 1 second of the write completing.
5. WHEN an administrator triggers a full protocol reload, THE Cache_Service SHALL invalidate all `protocol:*` keys and repopulate them from MongoDB.
6. IF the Cache_Service is in degraded mode, THEN THE PrescriptionService SHALL fall back to its in-process dict cache without raising an error.

---

### Requirement 3: Drug Interaction Cache

**User Story:** As a backend engineer, I want drug interaction data to be stored in Redis, so that all application instances share the same interaction list and MongoDB is not queried on every startup.

#### Acceptance Criteria

1. WHEN `AlertService` loads drug interactions at startup, THE Cache_Service SHALL store the full interaction list serialised as JSON under the key `drug_interactions:all` with a TTL of 3600 seconds.
2. WHEN `AlertService` requests the interaction list, THE Cache_Service SHALL return the cached list if a Cache_Hit occurs, without querying MongoDB.
3. WHEN a Cache_Miss occurs for `drug_interactions:all`, THE AlertService SHALL fetch the list from MongoDB, store it in the Cache_Service, and return it to the caller.
4. WHEN an administrator updates drug interaction data via the admin API, THE admin API SHALL call the Cache_Service directly to delete the `drug_interactions:all` key, and THE Cache_Service SHALL confirm the deletion within 1 second of the write completing.
5. IF the Cache_Service is in degraded mode, THEN THE AlertService SHALL fall back to its in-process list cache without raising an error.

---

### Requirement 4: Embedding Cache

**User Story:** As a backend engineer, I want embedding vectors to be cached in Redis, so that repeated calls to `EmbeddingModel.encode()` with the same text do not incur redundant OpenAI API calls.

#### Acceptance Criteria

1. WHEN `EmbeddingModel.encode()` is called with a text string, THE Cache_Service SHALL compute a Cache_Key as the SHA-256 hex digest of the UTF-8 encoded text prefixed with `embedding:`.
2. WHEN a Cache_Hit occurs for an embedding key, THE EmbeddingModel SHALL return the cached vector without calling the OpenAI API.
3. WHEN a Cache_Miss occurs for an embedding key, THE EmbeddingModel SHALL call the OpenAI API, store the resulting vector serialised as JSON in the Cache_Service with a TTL of 86400 seconds, and return the vector.
4. THE Cache_Service SHALL store embedding vectors as JSON arrays of floats.
5. IF the Cache_Service is in degraded mode, THEN THE EmbeddingModel SHALL call the OpenAI API directly without raising an error.
6. FOR ALL text inputs, encoding then retrieving from cache then decoding SHALL produce a vector equal to the original within floating-point precision (round-trip property).

---

### Requirement 5: Vector Search Result Cache

**User Story:** As a backend engineer, I want RAG query results to be cached in Redis, so that repeated identical or semantically equivalent queries do not trigger redundant MongoDB vector searches and LLM calls.

#### Acceptance Criteria

1. WHEN `RAGService.query()` is called, THE Cache_Service SHALL compute a Cache_Key as the SHA-256 hex digest of the UTF-8 encoded question string prefixed with `rag:`.
2. WHEN a Cache_Hit occurs for a RAG key, THE RAGService SHALL return the cached `RAGResponse` without executing the `$vectorSearch` pipeline or calling the LLM.
3. WHEN a Cache_Miss occurs for a RAG key, THE RAGService SHALL execute the full pipeline, store the serialised `RAGResponse` in the Cache_Service with a TTL of 300 seconds, and return the response.
4. THE Cache_Service SHALL store `RAGResponse` objects serialised as JSON.
5. WHEN a new document is indexed via the documents API, THE Cache_Service SHALL flush all `rag:*` keys to prevent stale answers referencing outdated document chunks. NOTE: This is a deliberate trade-off — flushing all RAG cache entries on any document index event is intentionally aggressive. A targeted per-document invalidation strategy is not implemented because the relationship between a document and the query keys it affects cannot be determined without re-executing the vector search. The operational cost of occasional full flushes is accepted in exchange for correctness guarantees.
6. IF the Cache_Service is in degraded mode, THEN THE RAGService SHALL execute the full pipeline without raising an error.
7. WHERE a `PatientProfile` context is provided to `RAGService.query()`, THE Cache_Service SHALL incorporate a hash of the serialised patient context into the Cache_Key to prevent cross-patient cache collisions.

---

### Requirement 6: Rate Limit Storage Migration

**User Story:** As a backend engineer, I want rate-limit counters to be stored in Redis, so that rate limiting is enforced consistently across all application instances in a multi-instance deployment.

#### Acceptance Criteria

1. WHEN the application starts, THE Rate_Limiter SHALL use the `REDIS_URL` environment variable as its storage URI instead of `memory://`.
2. WHEN `REDIS_URL` is not set, THE Rate_Limiter SHALL fall back to `memory://` storage and log a warning indicating that rate limiting is not shared across instances.
3. WHEN a request is received, THE Rate_Limiter SHALL increment the counter for the resolved key (user ID or IP) in Redis atomically.
4. WHEN Redis is unavailable, THE Rate_Limiter SHALL apply the `swallow_errors=True` behaviour already configured in `slowapi` and allow the request to proceed. NOTE: This is a deliberate trade-off — when Redis is unavailable, rate limiting silently fails open, meaning all requests are permitted regardless of rate limits. This is accepted to preserve availability; operators SHOULD monitor the `cache_degraded` metric and alert on it to detect this condition promptly.
5. THE Rate_Limiter SHALL preserve the existing key function that resolves authenticated requests by JWT `sub` claim and unauthenticated requests by remote IP address.

---

### Requirement 7: Cache Configuration

**User Story:** As a backend engineer, I want all cache TTLs and the Redis URL to be configurable via environment variables, so that I can tune caching behaviour without code changes.

#### Acceptance Criteria

1. THE Cache_Service SHALL read the following settings from environment variables with the specified defaults:
   - `REDIS_URL` → `redis://localhost:6379/0`
   - `CACHE_TTL_PROTOCOLS` → `3600` seconds
   - `CACHE_TTL_INTERACTIONS` → `3600` seconds
   - `CACHE_TTL_EMBEDDINGS` → `86400` seconds
   - `CACHE_TTL_RAG` → `300` seconds
2. THE Settings class SHALL expose these variables via `pydantic-settings` alongside the existing configuration fields.
3. WHEN an environment variable contains a non-integer value for a TTL field, THE Settings class SHALL raise a `ValidationError` at startup.

---

### Requirement 8: Cache Observability

**User Story:** As a backend engineer, I want cache hit/miss metrics to be exposed via Prometheus, so that I can monitor cache effectiveness and detect degradation.

#### Acceptance Criteria

1. THE Cache_Service SHALL increment a Prometheus counter labelled `cache_hits_total` with a `cache` label (e.g. `protocol`, `interaction`, `embedding`, `rag`) on every Cache_Hit.
2. THE Cache_Service SHALL increment a Prometheus counter labelled `cache_misses_total` with a `cache` label on every Cache_Miss.
3. THE Cache_Service SHALL record a Prometheus gauge labelled `cache_degraded` set to `1` when operating in degraded mode and `0` otherwise.
4. WHEN the `/metrics` endpoint is scraped, THE Cache_Service metrics SHALL be included in the Prometheus exposition format alongside existing HTTP metrics.

---

### Requirement 9: Cache Key Versioning

**User Story:** As a backend engineer, I want all cache keys to include a version prefix, so that a change to a serialisation schema (e.g. a `RAGResponse` field rename) automatically invalidates stale cached data and prevents deserialisation errors.

#### Acceptance Criteria

1. THE Cache_Service SHALL prefix every Cache_Key with a Cache_Key_Version string read from the `CACHE_KEY_VERSION` environment variable, defaulting to `v1`.
2. THE Cache_Service SHALL construct Cache_Keys in the form `<version>:<domain>:<identifier>` (e.g. `v1:rag:<sha256>`, `v1:protocol:<name>`, `v1:embedding:<sha256>`, `v1:drug_interactions:all`).
3. WHEN the `CACHE_KEY_VERSION` environment variable is changed and the application is restarted, THE Cache_Service SHALL write all new entries under the new version prefix, leaving old-version keys to expire naturally via their TTLs.
4. THE Settings class SHALL expose `CACHE_KEY_VERSION` via `pydantic-settings` alongside the existing configuration fields.

---

### Requirement 10: Startup Warm-up

**User Story:** As a backend engineer, I want the cache to be pre-populated at startup, so that the first requests after deployment are served from cache rather than hitting MongoDB or the OpenAI API.

#### Acceptance Criteria

1. WHEN the application starts and Redis is reachable, THE Cache_Service SHALL trigger a warm-up that loads antibiotic protocols and drug interactions from MongoDB into Redis before the application begins serving traffic.
2. WHEN the warm-up for protocols completes, THE Cache_Service SHALL log the number of protocol entries written to Redis.
3. WHEN the warm-up for drug interactions completes, THE Cache_Service SHALL log the number of interaction entries written to Redis.
4. IF the warm-up fails for any reason, THEN THE Cache_Service SHALL log the error and allow the application to start without a pre-populated cache.
5. THE warm-up SHALL complete within 10 seconds; IF it exceeds this limit, THEN THE Cache_Service SHALL abort the warm-up, log a timeout warning, and allow the application to start.
6. WHILE the warm-up is in progress, THE application SHALL begin serving incoming requests immediately and accept Cache_Misses for any key not yet populated; THE application SHALL NOT hold or queue requests until warm-up completes.
