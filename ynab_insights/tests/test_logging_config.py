"""Tests for the JSON log formatter and setup_logging environment switch."""

import io
import json
import logging

from app.logging_config import JsonFormatter, setup_logging


def _make_record(
    level: int = logging.INFO, msg: str = "hello", **extra: object
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=None,
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_json_formatter_includes_core_fields() -> None:
    formatter = JsonFormatter()
    output = formatter.format(_make_record(msg="hi"))
    payload = json.loads(output)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == "hi"
    assert "timestamp" in payload


def test_json_formatter_surfaces_extras() -> None:
    formatter = JsonFormatter()
    output = formatter.format(_make_record(msg="hi", request_id="abc-123", user="majed"))
    payload = json.loads(output)
    assert payload["request_id"] == "abc-123"
    assert payload["user"] == "majed"


def test_json_formatter_renders_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=42,
            msg="failed",
            args=None,
            exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "ValueError: boom" in payload["exception"]


def test_setup_logging_uses_json_in_prod_env() -> None:
    setup_logging("prod")
    buf = io.StringIO()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.stream = buf
    logging.getLogger("test").info("structured")
    line = buf.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["message"] == "structured"


def test_setup_logging_uses_human_format_in_test_env() -> None:
    # app_env value "test" (not in {"stage", "prod"}) -> plain text formatter
    setup_logging("test")
    buf = io.StringIO()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.stream = buf
    logging.getLogger("plain").info("readable")
    line = buf.getvalue().strip()
    # Not valid JSON, has the level word
    assert "INFO" in line
    assert "readable" in line
