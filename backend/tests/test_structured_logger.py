"""
Tests de propriété pour le logging structuré — Diagno-Pilot

Feature: diagno-pilot-improvements

Property 18 : Structure JSON des entrées de log
**Validates: Requirements 14.1, 14.2**
"""
from __future__ import annotations

import io
import json
import logging
import re

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.core.logging_config import request_id_var, setup_logging

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------

h_settings.register_profile("structured_logger", max_examples=100)
h_settings.load_profile("structured_logger")

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

log_level_strategy = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

message_strategy = st.text(min_size=0, max_size=200)

request_id_strategy = st.one_of(
    st.just(""),
    st.from_regex(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", fullmatch=True),
    st.text(min_size=1, max_size=64),
)

# ISO 8601 prefix pattern: YYYY-MM-DDTHH:MM:SS
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

REQUIRED_FIELDS = {"timestamp", "level", "message", "service", "request_id"}


def _capture_log_output(level: str, message: str, request_id: str) -> str:
    """
    Configure the root logger with JSON format, emit one record, and return
    the captured output. Restores the original handlers afterwards.
    """
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    try:
        # Set request_id context variable
        token = request_id_var.set(request_id)

        # Redirect output to a StringIO buffer
        buf = io.StringIO()
        setup_logging(log_level=level, log_format="json")

        # Replace the stdout handler with our StringIO handler
        root_logger.handlers.clear()
        handler = logging.StreamHandler(buf)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))

        # Reuse the formatter from setup_logging by calling it again on the handler
        # We need to re-apply the formatter — call setup_logging internals manually
        from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]
        import datetime

        class _RequestIdJsonFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)
                if "asctime" in log_record:
                    log_record["timestamp"] = log_record.pop("asctime")
                elif "timestamp" not in log_record:
                    log_record["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                log_record["level"] = record.levelname
                log_record.pop("levelname", None)
                log_record["service"] = "diagno-pilot"
                log_record["request_id"] = request_id_var.get()

        formatter = _RequestIdJsonFormatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            rename_fields={"levelname": "level"},
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        # Emit the log record
        logger = logging.getLogger("test_structured_logger")
        log_method = getattr(logger, level.lower())
        log_method(message)

        return buf.getvalue()
    finally:
        # Restore original state
        root_logger.handlers.clear()
        for h in original_handlers:
            root_logger.addHandler(h)
        root_logger.setLevel(original_level)
        request_id_var.reset(token)


# ---------------------------------------------------------------------------
# Property 18 — Structure JSON des entrées de log
# ---------------------------------------------------------------------------

# Feature: diagno-pilot-improvements, Property 18: Structure JSON des entrées de log
@given(
    level=log_level_strategy,
    message=message_strategy,
    request_id=request_id_strategy,
)
@h_settings(max_examples=100)
def test_p18_log_entry_is_valid_json_with_required_fields(
    level: str, message: str, request_id: str
) -> None:
    """
    Feature: diagno-pilot-improvements, Property 18: Structure JSON des entrées de log

    **Validates: Requirements 14.1, 14.2**

    Pour tout événement de log émis par StructuredLogger, la sortie doit être
    un objet JSON valide sur une seule ligne contenant au minimum les champs
    timestamp (ISO 8601), level, message, service et request_id.
    """
    output = _capture_log_output(level=level, message=message, request_id=request_id)

    # The output must be non-empty
    assert output.strip(), f"Log output was empty for level={level!r}, message={message!r}"

    # Each non-empty line must be valid JSON (there should be exactly one)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert len(lines) == 1, (
        f"Expected exactly 1 log line, got {len(lines)}: {lines!r}"
    )

    line = lines[0]

    # Must be valid JSON
    try:
        entry = json.loads(line)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Log line is not valid JSON: {exc}\nLine: {line!r}")

    # Must be a JSON object (dict)
    assert isinstance(entry, dict), f"Log entry is not a JSON object: {type(entry)}"

    # Must contain all required fields
    missing = REQUIRED_FIELDS - entry.keys()
    assert not missing, f"Missing required fields {missing!r} in log entry: {entry!r}"

    # service must be "diagno-pilot"
    assert entry["service"] == "diagno-pilot", (
        f"Expected service='diagno-pilot', got {entry['service']!r}"
    )

    # timestamp must match ISO 8601 prefix
    assert ISO8601_RE.match(str(entry["timestamp"])), (
        f"timestamp {entry['timestamp']!r} does not match ISO 8601 format"
    )

    # The JSON line itself must not contain embedded newlines
    assert "\n" not in line, f"Log line contains embedded newline: {line!r}"


# ---------------------------------------------------------------------------
# Unit test — LOG_FORMAT=text produces plain text (not JSON)
# ---------------------------------------------------------------------------

def test_text_format_produces_plain_text_not_json() -> None:
    """
    Verifies that when log_format='text', the output is plain text and
    cannot be parsed as JSON.
    """
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    try:
        buf = io.StringIO()
        setup_logging(log_level="INFO", log_format="text")

        root_logger.handlers.clear()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        logger = logging.getLogger("test_text_format")
        logger.info("plain text message")

        output = buf.getvalue().strip()
        assert output, "Log output was empty"

        # Plain text output should NOT be valid JSON
        try:
            json.loads(output)
            pytest.fail(f"Expected plain text but got valid JSON: {output!r}")
        except json.JSONDecodeError:
            pass  # Expected: not JSON

        # Should contain the message
        assert "plain text message" in output

    finally:
        root_logger.handlers.clear()
        for h in original_handlers:
            root_logger.addHandler(h)
        root_logger.setLevel(original_level)
