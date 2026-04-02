# Implementation Plan: Observability

## Overview

Extend the observability stack in three areas: (1) application-level Prometheus metrics for LLM, embedding, MongoDB, and cache; (2) Loki + Promtail + Grafana in Docker Compose for local log aggregation; (3) production deployment guide in English and French.

## Tasks

- [x] 1. Centralise and extend Prometheus metrics in `backend/core/metrics.py`
  - [x] 1.1 Rewrite `backend/core/metrics.py` with all custom metrics as module-level singletons
    - Add `diagno_pilot_llm_duration_seconds` Histogram with labels `model`, `status` and buckets `[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]`
    - Add `diagno_pilot_llm_requests_total` Counter with labels `model`, `status` (already exists — verify name and labels match)
    - Add `diagno_pilot_circuit_breaker_open_total` Counter with label `service` (already exists — verify)
    - Add `diagno_pilot_embedding_duration_seconds` Histogram with label `status` and buckets `[0.1, 0.25, 0.5, 1.0, 2.0, 5.0]`
    - Add `diagno_pilot_embedding_requests_total` Counter with label `status`
    - Add `diagno_pilot_db_query_duration_seconds` Histogram with labels `collection`, `operation` and buckets `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]`
    - Add `diagno_pilot_db_errors_total` Counter with labels `collection`, `operation`
    - Add `diagno_pilot_cache_hits_total` Counter with label `cache` (migrate from `cache.py`)
    - Add `diagno_pilot_cache_misses_total` Counter with label `cache` (migrate from `cache.py`)
    - Add `diagno_pilot_cache_degraded` Gauge (migrate from `cache.py`)
    - Add module docstring listing every metric name, type, labels, and purpose
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 3.1, 3.3, 3.4, 4.1, 4.2, 4.5, 5.1, 5.4_

  - [x] 1.2 Write property test for metric singleton uniqueness
    - **Property 1: No duplicate metric registration** — importing `backend.core.metrics` multiple times in the same process must not raise `ValueError`
    - **Validates: Requirements 5.2, 5.3**

- [x] 2. Instrument LLM Router with duration and status metrics
  - [x] 2.1 Update `backend/services/llm_router.py` to record `diagno_pilot_llm_duration_seconds` with `status` label on both success and error paths
    - Import `llm_duration_seconds` from `backend.core.metrics` (already imported — add `status` label to `.observe()` calls)
    - Record duration with `status="success"` on successful generation
    - Record duration with `status="error"` on `LLMUnavailableError` before re-raising
    - Ensure `model` label uses the actual model identifier string (`PRIMARY_MODEL`, `FALLBACK_MODEL`) not a hardcoded alias
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 2.2 Write property test for LLM metrics instrumentation
    - **Property 2: Every completed LLM call increments `diagno_pilot_llm_requests_total` exactly once** — for any sequence of success/error outcomes, the counter total equals the number of calls
    - **Validates: Requirements 1.2, 1.4**

  - [x] 2.3 Update `backend/core/circuit_breaker.py` to use `service` label value matching the actual service name
    - Change hardcoded `service="llm_primary"` to accept a configurable `service_name` parameter in `CircuitBreaker.__init__`
    - Update `LLMRouter` to pass `service_name="qwen3"` for the primary circuit breaker
    - _Requirements: 1.5_

- [x] 3. Instrument `EmbeddingModel.encode()` with duration and status metrics
  - [x] 3.1 Update `backend/services/embedding_service.py` to record embedding metrics
    - Import `embedding_duration_seconds`, `embedding_requests_total` from `backend.core.metrics`
    - Wrap `_call_api()` call in `encode()` with `time.perf_counter()` timing
    - Record `diagno_pilot_embedding_duration_seconds` with `status="success"` on success
    - Record `diagno_pilot_embedding_duration_seconds` with `status="error"` and increment `diagno_pilot_embedding_requests_total{status="error"}` on exception, then re-raise
    - Increment `diagno_pilot_embedding_requests_total{status="success"}` on success
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.2 Write property test for embedding metrics instrumentation
    - **Property 3: `diagno_pilot_embedding_requests_total` count equals number of `encode()` calls** — success and error counts sum to total calls
    - **Validates: Requirements 2.2, 2.4**

- [x] 4. Create DB instrumentation utility and apply to all service files
  - [x] 4.1 Create `backend/core/db_metrics.py` with a `timed_db_op` async context manager
    - Accept `collection: str` and `operation: str` parameters
    - On exit record `diagno_pilot_db_query_duration_seconds` with appropriate labels
    - On exception increment `diagno_pilot_db_errors_total` and re-raise
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

  - [x] 4.2 Write property test for DB instrumentation utility
    - **Property 4: `diagno_pilot_db_query_duration_seconds` observation count equals number of completed DB operations** — both successful and failed operations are recorded
    - **Validates: Requirements 3.2, 3.4**

  - [x] 4.3 Apply `timed_db_op` to `backend/services/patient_service.py`
    - Wrap every Motor call (`find`, `find_one`, `insert_one`, `update_one`, `delete_one`, `aggregate`, `count_documents`) with `timed_db_op`
    - _Requirements: 3.1, 3.2, 3.7_

  - [x] 4.4 Apply `timed_db_op` to `backend/services/consultation_service.py`, `backend/services/audit_service.py`, `backend/services/alert_service.py`, and `backend/services/chat_service.py`
    - Wrap every Motor call in each service with `timed_db_op`
    - _Requirements: 3.1, 3.2, 3.7_

  - [x] 4.5 Apply `timed_db_op` to remaining service files (`backend/services/document_service.py`, `backend/services/rag_service.py`, `backend/services/prescription_service.py`) and any router files that call Motor directly
    - _Requirements: 3.1, 3.2, 3.7_

- [x] 5. Migrate cache metrics to `backend/core/metrics.py` and update `backend/core/cache.py`
  - [x] 5.1 Remove `cache_hits_total`, `cache_misses_total`, `cache_degraded` definitions from `backend/core/cache.py`
    - Import them from `backend.core.metrics` instead
    - Rename to `diagno_pilot_cache_hits_total`, `diagno_pilot_cache_misses_total`, `diagno_pilot_cache_degraded` to match requirements
    - Update all `.labels(cache=...)` call sites in `cache.py` and `embedding_service.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1_

  - [x] 5.2 Write property test for cache metrics
    - **Property 5: For any sequence of cache get operations, `hits + misses == total get calls`**
    - **Validates: Requirements 4.3, 4.4**

- [x] 6. Checkpoint — verify all metrics appear in `/metrics` output
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Add Loki, Promtail, and Grafana services to `docker-compose.yml`
  - [x] 7.1 Create `docker/loki/loki-config.yaml` with local filesystem storage, 72-hour retention, and max line size 64 KB
    - _Requirements: 6.1, 6.6, 7.4, 8.1_

  - [x] 7.2 Create `docker/promtail/promtail-config.yaml` configured to tail Docker container log files and forward to Loki
    - Parse structured JSON log lines from the backend container
    - Store `level`, `method`, `status_code` as Loki labels
    - Store `request_id`, `path`, `duration_ms`, `message` as structured metadata (not labels)
    - Configure `positions` file for resume-on-restart behaviour
    - Set `max_line_size: 65536` (64 KB)
    - _Requirements: 6.2, 6.5, 7.2, 7.4, 7.5_

  - [x] 7.3 Create `docker/grafana/provisioning/datasources/datasources.yaml` with Loki pre-configured as a datasource
    - Set anonymous auth in Grafana config
    - _Requirements: 6.4, 6.9_

  - [x] 7.4 Add `loki`, `promtail`, and `grafana` services to `docker-compose.yml`
    - `loki` on no external port (internal only), with healthcheck
    - `promtail` depends on `loki`, mounts `/var/lib/docker/containers` read-only
    - `grafana` on port `3001`, depends on `loki` healthcheck, mounts provisioning config read-only
    - _Requirements: 6.1, 6.2, 6.3, 6.7, 6.9_

- [x] 8. Add Prometheus server to `docker-compose.yml` (optional per Requirement 9)
  - [x] 8.1 Create `docker/prometheus/prometheus.yml` with scrape job targeting backend `/metrics` at 15-second interval
    - Include `rule_files` entry referencing `alerts.yml`
    - _Requirements: 9.1, 9.2, 9.4, 10.4_

  - [x] 8.2 Create `docker/prometheus/alerts.yml` with `LLMHighErrorRate` and `CircuitBreakerOpen` alert rules
    - `LLMHighErrorRate`: fires when error ratio > 5% over 5-minute window
    - `CircuitBreakerOpen`: fires when circuit breaker has been open > 60 s
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 8.3 Add `prometheus` service to `docker-compose.yml` on port `9090` with 7-day retention
    - Add Prometheus as a second datasource in `docker/grafana/provisioning/datasources/datasources.yaml`
    - _Requirements: 9.1, 9.3, 9.5_

- [x] 9. Add Grafana dashboard provisioning
  - [x] 9.1 Create `docker/grafana/provisioning/dashboards/dashboards.yaml` pointing to the dashboards directory
    - _Requirements: 11.2_

  - [x] 9.2 Create `docker/grafana/dashboards/observability.json` with four panels
    - LLM request duration percentiles (p50, p95, p99) from `diagno_pilot_llm_duration_seconds`
    - Cache hit ratio per cache name from `diagno_pilot_cache_hits_total` / `diagno_pilot_cache_misses_total`
    - MongoDB query duration by collection from `diagno_pilot_db_query_duration_seconds`
    - Log volume over time from Loki
    - _Requirements: 11.1, 11.3, 11.4, 11.5, 11.6_

- [x] 10. Checkpoint — verify Docker Compose stack starts cleanly with all new services
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Write production deployment guide
  - [x] 11.1 Create `docs/ops-guide.en.md` covering all acceptance criteria in Requirement 8
    - Document every environment variable (name, type, default, required, description)
    - `JWT_SECRET` generation and secrets manager guidance
    - `METRICS_AUTH` requirement for production
    - `docker-compose.prod.yml` override removing LocalStack and seed, setting `ENV=production`
    - Horizontal scaling section (shared Redis, MongoDB replica set / Atlas)
    - Bandwidth optimisation section for West African deployments
    - `/health` endpoint response schema and load balancer polling guidance
    - `JWT_SECRET` rotation procedure
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [x] 11.2 Create `docs/ops-guide.fr.md` as a French translation of `docs/ops-guide.en.md` covering the same content
    - _Requirements: 8.9_

- [x] 12. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Metrics in `cache.py` must be renamed with the `diagno_pilot_` prefix to match requirements; update all import sites accordingly
- The `status` label must be added to `diagno_pilot_llm_duration_seconds` — the existing histogram in `metrics.py` only has `model`
- Property tests use `hypothesis` (already present in `.hypothesis/` directory)
