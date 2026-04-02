# Requirements Document

## Introduction

This feature extends the observability stack of Diagno-Pilot across three areas:

1. **Extended Prometheus metrics** — the existing `prometheus-fastapi-instrumentator` only captures HTTP request metrics. This feature adds application-level metrics for LLM latency, embedding time, MongoDB query duration, and cache hit/miss rates (building on the caching-and-performance spec).
2. **Log aggregation for local development** — structured JSON logs are already emitted via `python-json-logger` but are not collected or visualised. This feature adds Loki and Grafana to `docker-compose.yml` so developers can query and explore logs locally without external tooling.
3. **Production deployment guide** — a reference document covering environment variables, secrets management, and scaling considerations tailored to the West African deployment context (bandwidth constraints, limited infrastructure).

The backend is Python 3.12 + FastAPI. Prometheus metrics are already exposed at `/metrics` with optional Basic Auth via `METRICS_AUTH`. Docker Compose already runs MongoDB, LocalStack, frontend, backend, and seed services.

---

## Glossary

- **Metrics_Service**: The Prometheus metrics layer in the backend, built on `prometheus_client` and `prometheus-fastapi-instrumentator`.
- **LLM_Router**: The `LLMRouter` class that routes generation requests to MedicalQwen3 (primary) or GPT-5 (fallback).
- **Embedding_Model**: The `EmbeddingModel` class that calls the OpenAI-compatible embeddings API.
- **Cache_Service**: The Redis-backed caching component defined in the caching-and-performance spec.
- **DB_Client**: The MongoDB async client (`AsyncIOMotorClient`) used throughout the backend.
- **Loki**: The log aggregation system (Grafana Loki) that ingests structured JSON log lines.
- **Promtail**: The log shipping agent that tails Docker container logs and forwards them to Loki.
- **Grafana**: The visualisation platform used to query Loki logs and Prometheus metrics.
- **Ops_Guide**: The production deployment reference document.
- **Histogram**: A Prometheus metric type that records observations in configurable buckets and exposes count, sum, and quantile data.
- **Counter**: A Prometheus metric type that only increases, used for totals and rates.
- **Gauge**: A Prometheus metric type that can increase or decrease, used for current state.
- **Label**: A key-value pair attached to a Prometheus metric that enables filtering and aggregation.
- **Scrape_Interval**: The frequency at which Prometheus pulls metrics from a target endpoint.
- **Log_Pipeline**: The path a log line takes from the backend process through Promtail into Loki.

---

## Requirements

### Requirement 1: LLM Latency Metrics

**User Story:** As a backend engineer, I want Prometheus histograms for LLM request duration broken down by model and outcome, so that I can detect latency regressions and measure fallback frequency.

#### Acceptance Criteria

1. THE Metrics_Service SHALL expose a Histogram named `diagno_pilot_llm_duration_seconds` with labels `model` and `status` (values: `success`, `error`). The `model` label value SHALL match the actual model identifier string used by `LLM_Router` (e.g. `qwen3`, `gpt-5`, or `gpt-5-turbo`) rather than a hardcoded alias.
2. WHEN `LLM_Router` completes a generation request, THE Metrics_Service SHALL record the wall-clock duration in seconds in `diagno_pilot_llm_duration_seconds` with the appropriate `model` and `status` labels.
3. THE `diagno_pilot_llm_duration_seconds` Histogram SHALL use buckets `[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]` to reflect realistic LLM response times.
4. THE Metrics_Service SHALL expose a Counter named `diagno_pilot_llm_requests_total` with labels `model` and `status` that is incremented on every completed LLM call.
5. WHEN the circuit breaker opens for the primary LLM, THE Metrics_Service SHALL increment a Counter named `diagno_pilot_circuit_breaker_open_total` with label `service` set to `qwen3`.
6. WHEN the `/metrics` endpoint is scraped, all LLM metrics SHALL be present in the Prometheus exposition format.

---

### Requirement 2: Embedding Latency Metrics

**User Story:** As a backend engineer, I want Prometheus metrics for embedding API call duration and outcome, so that I can monitor the cost and reliability of the embedding pipeline.

#### Acceptance Criteria

1. THE Metrics_Service SHALL expose a Histogram named `diagno_pilot_embedding_duration_seconds` with label `status` (values: `success`, `error`).
2. WHEN `Embedding_Model.encode()` completes, THE Metrics_Service SHALL record the wall-clock duration in seconds in `diagno_pilot_embedding_duration_seconds` with the appropriate `status` label.
3. THE `diagno_pilot_embedding_duration_seconds` Histogram SHALL use buckets `[0.1, 0.25, 0.5, 1.0, 2.0, 5.0]`.
4. THE Metrics_Service SHALL expose a Counter named `diagno_pilot_embedding_requests_total` with label `status` that is incremented on every completed embedding call.
5. WHEN the `/metrics` endpoint is scraped, all embedding metrics SHALL be present in the Prometheus exposition format.

---

### Requirement 3: MongoDB Query Duration Metrics

**User Story:** As a backend engineer, I want Prometheus histograms for MongoDB query duration broken down by collection and operation, so that I can identify slow queries and index gaps.

#### Acceptance Criteria

1. THE Metrics_Service SHALL expose a Histogram named `diagno_pilot_db_query_duration_seconds` with labels `collection` and `operation` (values: `find`, `find_one`, `insert_one`, `update_one`, `delete_one`, `aggregate`, `count_documents`).
2. WHEN a MongoDB operation completes, THE Metrics_Service SHALL record the wall-clock duration in seconds in `diagno_pilot_db_query_duration_seconds` with the appropriate `collection` and `operation` labels.
3. THE `diagno_pilot_db_query_duration_seconds` Histogram SHALL use buckets `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]`.
4. THE Metrics_Service SHALL expose a Counter named `diagno_pilot_db_errors_total` with labels `collection` and `operation` that is incremented whenever a MongoDB operation raises an exception.
5. WHEN the `/metrics` endpoint is scraped, all DB metrics SHALL be present in the Prometheus exposition format.
6. THE instrumentation SHALL be implemented as a thin wrapper or decorator applied at the service layer, without modifying the Motor driver internals.
7. THE Metrics_Service SHALL provide a shared utility function or base repository class in `backend/core/` that all service files use to apply DB instrumentation, ensuring consistent metric coverage across every repository without requiring per-file boilerplate.

---

### Requirement 4: Cache Hit/Miss Metrics

**User Story:** As a backend engineer, I want Prometheus counters for cache hits and misses broken down by cache name, so that I can measure cache effectiveness and detect degradation.

#### Acceptance Criteria

1. THE Metrics_Service SHALL expose a Counter named `diagno_pilot_cache_hits_total` with label `cache` (values: `protocol`, `interaction`, `embedding`, `rag`).
2. THE Metrics_Service SHALL expose a Counter named `diagno_pilot_cache_misses_total` with label `cache` using the same label values.
3. WHEN `Cache_Service` returns a cached value, THE Metrics_Service SHALL increment `diagno_pilot_cache_hits_total` with the corresponding `cache` label.
4. WHEN `Cache_Service` does not find a cached value, THE Metrics_Service SHALL increment `diagno_pilot_cache_misses_total` with the corresponding `cache` label.
5. THE Metrics_Service SHALL expose a Gauge named `diagno_pilot_cache_degraded` set to `1` when the Cache_Service is operating in degraded mode (Redis unreachable) and `0` otherwise.
6. WHEN the `/metrics` endpoint is scraped, all cache metrics SHALL be present in the Prometheus exposition format.
7. THE `cache` label values (`protocol`, `interaction`, `embedding`, `rag`) SHALL remain in sync with the cache type definitions in the caching-and-performance spec. WHEN a new cache type is added to `Cache_Service`, THE Metrics_Service SHALL update the permitted label values in `backend/core/metrics.py` before the new cache type is used in production.

---

### Requirement 5: Metrics Centralisation

**User Story:** As a backend engineer, I want all custom Prometheus metrics defined in a single module, so that metric names are consistent and there are no duplicate registration errors.

#### Acceptance Criteria

1. THE Metrics_Service SHALL define all custom Prometheus metrics (LLM, embedding, DB, cache) in `backend/core/metrics.py` as module-level singletons.
2. WHEN any backend module imports a metric, THE Metrics_Service SHALL provide it from `backend/core/metrics.py` without re-instantiating the metric object.
3. IF a metric name is registered more than once in the same process, THEN THE Metrics_Service SHALL raise a `ValueError` at import time to surface the conflict immediately.
4. THE `backend/core/metrics.py` module SHALL include a docstring listing every metric name, type, labels, and purpose.

---

### Requirement 6: Loki and Grafana in Docker Compose

**User Story:** As a developer, I want Loki and Grafana available in the local Docker Compose stack, so that I can query and visualise structured JSON logs without installing external tools.

#### Acceptance Criteria

1. THE `docker-compose.yml` SHALL include a `loki` service using the `grafana/loki` image with a local filesystem storage configuration suitable for development.
2. THE `docker-compose.yml` SHALL include a `promtail` service using the `grafana/promtail` image configured to tail Docker container log files and forward them to the `loki` service.
3. THE `docker-compose.yml` SHALL include a `grafana` service using the `grafana/grafana` image exposed on port `3001` (to avoid conflict with the frontend on port `3000`).
4. WHEN Grafana starts, THE `grafana` service SHALL have Loki pre-configured as a datasource so developers do not need to configure it manually.
5. THE `promtail` service SHALL parse the structured JSON log lines emitted by the backend and extract fields as follows: low-cardinality fields (`level`, `method`, `status_code`) SHALL be stored as Loki labels; high-cardinality fields (`request_id`, `path`, `duration_ms`, `message`) SHALL be stored as Loki structured metadata and MUST NOT be used as Loki labels, to prevent label cardinality explosion.
6. THE Loki and Promtail configurations SHALL be stored as files in `docker/loki/` and `docker/promtail/` respectively and mounted as read-only volumes.
7. THE `grafana` service SHALL depend on `loki` and SHALL not start until `loki` reports healthy.
8. WHILE running in the local Docker Compose stack, THE `loki` service SHALL retain logs for a maximum of 72 hours to limit disk usage on developer machines.
9. THE `grafana` service SHALL use anonymous authentication in the local development configuration so developers can access it without a login.

---

### Requirement 7: Log Pipeline Correctness

**User Story:** As a developer, I want log lines emitted by the backend to be queryable in Grafana within 10 seconds of emission, so that I can use Grafana for real-time debugging during local development.

#### Acceptance Criteria

1. WHEN the backend emits a structured JSON log line, THE Log_Pipeline SHALL deliver it to Loki within 10 seconds.
2. WHEN a log line is delivered to Loki, THE Log_Pipeline SHALL preserve the original `timestamp`, `level`, and `message` fields without modification.
3. IF the `loki` service is unavailable, THEN THE `promtail` service SHALL buffer log lines locally and retry delivery without dropping entries, up to a buffer of approximately 10 MB.
4. THE Log_Pipeline SHALL handle log lines up to 64 KB in size without truncation (to accommodate large LLM response logs).
5. WHEN the Docker Compose stack is restarted, THE Log_Pipeline SHALL resume tailing from the last successfully shipped log position without re-sending previously delivered lines.

---

### Requirement 8: Production Deployment Guide

**User Story:** As a DevOps engineer, I want a production deployment guide covering environment variables, secrets management, and scaling, so that I can deploy Diagno-Pilot safely in a West African clinical environment.

#### Acceptance Criteria

1. THE Ops_Guide SHALL document every environment variable consumed by the backend, including name, type, default value, whether it is required in production, and a description.
2. THE Ops_Guide SHALL specify that `JWT_SECRET` must be generated with `openssl rand -hex 32` and stored in a secrets manager, never in a `.env` file committed to version control.
3. THE Ops_Guide SHALL specify that `METRICS_AUTH` must be set to a non-empty `user:password` value in production to prevent unauthenticated access to the `/metrics` endpoint.
4. THE Ops_Guide SHALL document a recommended Docker Compose production override (`docker-compose.prod.yml`) that removes development-only services (LocalStack, seed) and sets `ENV=production`.
5. THE Ops_Guide SHALL include a section on horizontal scaling that explains the requirement for a shared Redis instance (from the caching-and-performance spec) and a MongoDB replica set or Atlas cluster.
6. THE Ops_Guide SHALL include a section on bandwidth optimisation for West African deployments covering: Prometheus scrape interval recommendations (≥60 s), Loki log volume reduction via `LOG_LEVEL=WARNING` in production, and Grafana dashboard export for offline use.
7. THE Ops_Guide SHALL document the `/health` endpoint response schema and specify that a load balancer health check SHOULD poll `/health` at an interval of no less than 10 seconds.
8. THE Ops_Guide SHALL include a secrets rotation procedure for `JWT_SECRET` that describes the steps to rotate the secret without invalidating active user sessions.
9. THE Ops_Guide SHALL be produced as two separate documents — `ops-guide.en.md` (English) and `ops-guide.fr.md` (French) — so that each language version is independently maintainable. Both documents SHALL cover the same content, given that the target deployment teams operate in Togo and Bénin.

---

### Requirement 9: Prometheus Server in Docker Compose (Optional)

**User Story:** As a developer, I want a Prometheus server available in the local Docker Compose stack, so that I can verify that all custom metrics are correctly scraped and explore them in Grafana.

#### Acceptance Criteria

1. WHERE a Prometheus server is included in the Docker Compose stack, THE `docker-compose.yml` SHALL include a `prometheus` service using the `prom/prometheus` image exposed on port `9090`.
2. WHERE a Prometheus server is included, THE `prometheus` service SHALL be configured with a scrape job targeting the backend `/metrics` endpoint at a 15-second interval for local development.
3. WHERE a Prometheus server is included, THE `grafana` service SHALL have Prometheus pre-configured as a second datasource alongside Loki.
4. WHERE a Prometheus server is included, THE Prometheus configuration file SHALL be stored in `docker/prometheus/` and mounted as a read-only volume.
5. WHERE a Prometheus server is included, THE `prometheus` service SHALL retain metrics data for a maximum of 7 days to limit disk usage on developer machines.

---

### Requirement 10: Alerting Rules

**User Story:** As a backend engineer, I want basic alerting rules for LLM error rate and circuit breaker state, so that I can be notified of critical failures in the clinical pipeline.

#### Acceptance Criteria

1. WHEN the LLM error rate (ratio of `diagno_pilot_llm_requests_total{status="error"}` to all `diagno_pilot_llm_requests_total`) exceeds 5% over a 5-minute window, THE Metrics_Service SHALL fire a Prometheus alert named `LLMHighErrorRate`.
2. WHEN the circuit breaker has been in the open state for more than 60 consecutive seconds (as measured by `diagno_pilot_circuit_breaker_open_total`), THE Metrics_Service SHALL fire a Prometheus alert named `CircuitBreakerOpen`.
3. THE alert rules SHALL be stored in `docker/prometheus/alerts.yml` in standard Prometheus alerting rule format.
4. THE `prometheus` service configuration SHALL reference `alerts.yml` via a `rule_files` entry so that Prometheus loads the alert rules on startup.

---

### Requirement 11: Grafana Dashboard Provisioning

**User Story:** As a developer, I want a pre-built Grafana dashboard available when the stack starts, so that I can immediately visualise LLM latency, cache hit rates, and log volume without manual setup.

#### Acceptance Criteria

1. THE `grafana` service SHALL include a dashboard JSON file stored under `docker/grafana/dashboards/` that is automatically loaded on startup.
2. THE `grafana` service SHALL include a Grafana provisioning configuration file that references the `docker/grafana/dashboards/` directory so that dashboards are loaded without manual import.
3. THE dashboard SHALL include a panel displaying LLM request duration percentiles (p50, p95, p99) sourced from `diagno_pilot_llm_duration_seconds`.
4. THE dashboard SHALL include a panel displaying the cache hit ratio (hits / (hits + misses)) per cache name sourced from `diagno_pilot_cache_hits_total` and `diagno_pilot_cache_misses_total`.
5. THE dashboard SHALL include a panel displaying MongoDB query duration by collection sourced from `diagno_pilot_db_query_duration_seconds`.
6. THE dashboard SHALL include a panel displaying log volume over time sourced from Loki.
