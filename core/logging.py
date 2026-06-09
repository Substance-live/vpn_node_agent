import logging
import sys

import structlog
from structlog.dev import Column, ConsoleRenderer


def _build_console_renderer() -> ConsoleRenderer:
    """Console renderer: no padding, bold colored HTTP status right after the event.

    Uses structlog 23.3+ Columns API.  Only affects LOG_FORMAT=console (dev).
    JSON renderer used in production is untouched.
    """
    # Build a base renderer with padding removed.  Its _configure_columns() call
    # wires up the correct ANSI styles and initialises colorama (Windows).
    base = ConsoleRenderer(pad_event_to=0, pad_level=False)
    styles = base._styles  # ColumnStyles: reset/bright/kv_key/kv_value/level_*/…

    def _status_formatter(key: str, value: object) -> str:
        """Bold colored status code: green 2xx, cyan 3xx, yellow 4xx, red 5xx."""
        try:
            code = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            color = styles.kv_value
        else:
            if code < 300:
                color = styles.level_info    # green
            elif code < 400:
                color = styles.kv_key        # cyan
            elif code < 500:
                color = styles.level_warn    # yellow
            else:
                color = styles.level_error   # red
        return (
            f"{styles.kv_key}{key}{styles.reset}="
            f"{color}{styles.bright}{value}{styles.reset}"
        )

    # base.columns = [Column("", default_fmt), timestamp, level, event, logger, logger_name].
    # Appending status here makes it render immediately after the event name;
    # remaining keys (method, path, duration_ms, client_ip) fall through
    # the default kv-formatter, sorted alphabetically.
    base.columns = list(base.columns) + [Column("status", _status_formatter)]
    return base


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
        renderer = _build_console_renderer()

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
