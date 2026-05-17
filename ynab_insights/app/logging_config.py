"""Structured logging configuration. JSON output in stage/prod for log
aggregation; human-readable in dev/test for easy reading."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render each LogRecord as a single-line JSON object."""

    # LogRecord attributes we never want to emit as duplicate top-level fields.
    _RESERVED = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
            "msg",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Surface caller-supplied extras (logger.info(..., extra={"k": v}))
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(app_env: str) -> None:
    """Replace the root logger's handlers with one configured for this env.

    Call once during process startup, before any logger emits records, so
    uvicorn's own loggers inherit the same formatter via propagation."""
    use_json = app_env in {"stage", "prod"}
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if use_json
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
