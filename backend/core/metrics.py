"""Custom Prometheus metrics for Diagno-Pilot.

Defines all application-level metrics so they can be imported by any module.
HTTP metrics are handled by prometheus-fastapi-instrumentator (see main.py).
"""
from prometheus_client import Counter, Histogram

# LLM request counter — labels: model (qwen3 | gpt5), status (success | error)
llm_requests_total = Counter(
    "diagno_pilot_llm_requests_total",
    "Total LLM requests by model and status",
    ["model", "status"],
)

# LLM request duration histogram — label: model
llm_duration_seconds = Histogram(
    "diagno_pilot_llm_duration_seconds",
    "LLM request duration in seconds by model",
    ["model"],
)

# Circuit breaker open counter — label: service
circuit_breaker_open_total = Counter(
    "diagno_pilot_circuit_breaker_open_total",
    "Number of times the circuit breaker has opened by service",
    ["service"],
)
