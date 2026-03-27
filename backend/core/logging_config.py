"""Structured logging configuration for Diagno-Pilot (REQ 14)."""
import logging
import sys
from contextvars import ContextVar

# Context variable holding the current request_id (empty string when outside a request)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure the root logger.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        log_format: "json" for structured JSON output, "text" for plain text.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicate output
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if log_format.lower() == "json":
        from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]

        class _RequestIdJsonFormatter(jsonlogger.JsonFormatter):
            """JsonFormatter that injects service and request_id into every record."""

            def add_fields(
                self,
                log_record: dict,
                record: logging.LogRecord,
                message_dict: dict,
            ) -> None:
                super().add_fields(log_record, record, message_dict)
                # Rename 'asctime' → 'timestamp' and ensure ISO 8601 format
                if "asctime" in log_record:
                    log_record["timestamp"] = log_record.pop("asctime")
                elif "timestamp" not in log_record:
                    import datetime

                    log_record["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                # Normalise level name
                log_record["level"] = record.levelname
                log_record.pop("levelname", None)
                # Fixed service name
                log_record["service"] = "diagno-pilot"
                # Per-request correlation id
                log_record["request_id"] = request_id_var.get()

        formatter: logging.Formatter = _RequestIdJsonFormatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            rename_fields={"levelname": "level"},
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
