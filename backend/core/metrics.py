"""Custom Prometheus metrics for Diagno-Pilot.

All application-level metrics are defined here as module-level singletons.
No other module may instantiate Counter, Histogram, or Gauge for application
metrics — import from this module instead.

HTTP metrics are handled by prometheus-fastapi-instrumentator (see main.py).

Metrics registry:
  diagno_pilot_llm_duration_seconds       Histogram  model, status
    Wall-clock duration of LLM generation requests in seconds.

  diagno_pilot_llm_requests_total         Counter    model, status
    Total completed LLM requests, labelled by model and outcome.

  diagno_pilot_circuit_breaker_open_total Counter    service
    Number of times the circuit breaker has transitioned to open state.

  diagno_pilot_embedding_duration_seconds Histogram  status
    Wall-clock duration of embedding API calls in seconds.

  diagno_pilot_embedding_requests_total   Counter    status
    Total completed embedding API calls, labelled by outcome.

  diagno_pilot_db_query_duration_seconds  Histogram  collection, operation
    Wall-clock duration of MongoDB operations in seconds.

  diagno_pilot_db_errors_total            Counter    collection, operation
    Total MongoDB operations that raised an exception.

  diagno_pilot_cache_hits_total           Counter    cache
    Total cache hits by cache name (protocol, interaction, embedding, rag).

  diagno_pilot_cache_misses_total         Counter    cache
    Total cache misses by cache name.

  diagno_pilot_cache_degraded             Gauge      (none)
    Set to 1 when CacheService is in degraded mode (Redis unreachable), 0 otherwise.
"""
from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

llm_duration_seconds = Histogram(
    "diagno_pilot_llm_duration_seconds",
    "LLM request duration in seconds",
    ["model", "status"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

llm_requests_total = Counter(
    "diagno_pilot_llm_requests_total",
    "Total LLM requests by model and status",
    ["model", "status"],
)

circuit_breaker_open_total = Counter(
    "diagno_pilot_circuit_breaker_open_total",
    "Number of times the circuit breaker has opened by service",
    ["service"],
)

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

embedding_duration_seconds = Histogram(
    "diagno_pilot_embedding_duration_seconds",
    "Embedding API call duration in seconds",
    ["status"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

embedding_requests_total = Counter(
    "diagno_pilot_embedding_requests_total",
    "Total embedding API calls by status",
    ["status"],
)

# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------

db_query_duration_seconds = Histogram(
    "diagno_pilot_db_query_duration_seconds",
    "MongoDB query duration in seconds",
    ["collection", "operation"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

db_errors_total = Counter(
    "diagno_pilot_db_errors_total",
    "Total MongoDB operation errors by collection and operation",
    ["collection", "operation"],
)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

cache_hits_total = Counter(
    "diagno_pilot_cache_hits_total",
    "Cache hits by cache name",
    ["cache"],
)

cache_misses_total = Counter(
    "diagno_pilot_cache_misses_total",
    "Cache misses by cache name",
    ["cache"],
)

cache_degraded = Gauge(
    "diagno_pilot_cache_degraded",
    "1 when cache is in degraded mode (Redis unreachable), 0 otherwise",
)
