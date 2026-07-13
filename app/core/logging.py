"""Structured logging.

Replaces ~35 print() calls scattered across the codebase. print() writes
unattributable text to stdout; under a concurrent server those lines interleave
into garbage, and nothing can be filtered, levelled, or correlated to a request.

A request_id contextvar threads an id through every log line emitted while
handling one request, which is what makes the logs greppable once there is an
API in front of this.
"""
import logging
import sys
from contextvars import ContextVar

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_logger, _name, event_dict: dict) -> dict:
    request_id = request_id_var.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Call once, from the entrypoint. Importing a module must not configure logging."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
