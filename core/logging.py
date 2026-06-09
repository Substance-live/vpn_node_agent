import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog with JSON renderer for prod or ConsoleRenderer for dev."""

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        # add_logger_name requires logging.Logger (.name attr); we use PrintLoggerFactory
        # so we bind the logger name manually via structlog.get_logger("name")
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
