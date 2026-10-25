import logging
import sys
from enum import StrEnum
from functools import wraps
from time import perf_counter

from core.error import AppError


_logger = logging.getLogger("observability")


class LogPrefix(StrEnum):
    """Category tag prepended to a component's observability logs.
    Add the components you want to distinguish in the logs."""

    CONTAINER = "CONTAINER"
    DB_ENGINE = "DB_ENGINE"

    REDIS_MALFORMED_DATA = "REDIS_MALFORMED_DATA"

    AGENT_SERVICE = "AGENT_SERVICE"
    CHAT_SERVICE = "CHAT_SERVICE"
    STORE_SERVICE = "STORE_SERVICE"
    PROJECT_SERVICE = "PROJECT_SERVICE"
    ATLASSIAN_SERVICE = "ATLASSIAN_SERVICE"
    GIT_SERVICE = "GIT_SERVICE"
    CHATBOT_SERVICE = "CHATBOT_SERVICE"
    CHAT_ROUTE_SERVICE = "CHAT_ROUTE_SERVICE"
    DEFINITION_SERVICE = "DEFINITION_SERVICE"
    PROCESS_SERVICE = "PROCESS_SERVICE"
    PIPELINE_SERVICE = "PIPELINE_SERVICE"
    PIPELINE_RUNNER = "PIPELINE_RUNNER"
    WORKER = "WORKER"
    MODEL_SERVICE = "MODEL_SERVICE"
    BACKUP_SERVICE = "BACKUP_SERVICE"


def configure_logging(log_level: str) -> None:
    """Attach a single root StreamHandler at the given level. Idempotent: a
    second call does not stack handlers. Also makes the console UTF-8: on
    Windows the default code page cannot print characters such as → or emoji,
    and datapizza prints each agent's answer: that print would fail the run."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]


def log_info(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an info message with the observability logger."""
    if prefix:
        _logger.info("[%s] " + message, prefix, *args, **kwargs)
    else:
        _logger.info(message, *args, **kwargs)


def log_warning(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log a warning message with the observability logger."""
    if prefix:
        _logger.warning("[%s] " + message, prefix, *args, **kwargs)
    else:
        _logger.warning(message, *args, **kwargs)


def log_error(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an error message with the observability logger."""
    if prefix:
        _logger.error("[%s] " + message, prefix, *args, **kwargs)
    else:
        _logger.error(message, *args, **kwargs)


def log_exception(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an exception message (with traceback) with the observability logger."""
    if prefix:
        _logger.exception("[%s] " + message, prefix, *args, **kwargs)
    else:
        _logger.exception(message, *args, **kwargs)


def observed(prefix: LogPrefix):
    """Log the outcome + duration of a method, tagged with `prefix`.
    `[PREFIX] Class.method ok (N ms)` on success; expected AppErrors are logged
    at INFO without a traceback, anything else at ERROR with a traceback.
    Always re-raises."""

    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            label = f"[{prefix}] {type(self).__name__}.{method.__name__}"
            start = perf_counter()
            _logger.info("%s started", label)
            try:
                result = method(self, *args, **kwargs)
            except AppError as exc:
                _logger.info("%s failed: %s", label, exc)
                raise
            except Exception:
                _logger.exception("%s crashed", label)
                raise
            _logger.info("%s ok (%.1f ms)", label, (perf_counter() - start) * 1000)
            return result

        return wrapper

    return decorator
