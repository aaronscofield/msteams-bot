"""Request-correlated logging, built on `asgi-correlation-id`.

`CorrelationIdMiddleware` (installed in `server.create_app`) gives every request a correlation id —
the caller's `X-Request-ID` if acceptable, else a generated one — keeps it in a ContextVar for the
request's lifetime, and echoes it on the response. `CorrelationIdFilter` stamps it on *every* log
record emitted meanwhile, including the SDK's own loggers:

    INFO approval_bot.service [req=7c1f0a2b9e3d]: [approvals] sent request ebfcfbc7 …

`get_logger` hands a route a logger bound to that id; `configure_logging` installs format + filter once.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from asgi_correlation_id import CorrelationIdFilter, correlation_id
from fastapi import Depends, Request

from ..models import Settings
from ..runtime import Runtime
from .runtime_dependency import get_runtime

REQUEST_ID_HEADER = "X-Request-ID"
LOG_FORMAT = "%(levelname)s %(name)s [req=%(correlation_id)s]: %(message)s"
_configured_level: str | None = None


class RequestLogger(logging.LoggerAdapter):
    """A logger bound to one request.

    Attributes:
        request_id: The request's correlation id — echo it to callers so they can find the log lines.
    """

    def __init__(self, logger: logging.Logger, request_id: str) -> None:
        """Wrap ``logger`` for one request.

        Args:
            logger: The underlying logger (usually named after the route's module).
            request_id: The correlation id of the current request.
        """
        super().__init__(logger, {"request_id": request_id})
        self.request_id = request_id


def new_request_id() -> str:
    """Generate a correlation id for a request that arrived without one.

    Returns:
        str: 12 hex characters — short enough to read in a log, unique enough for correlation.
    """
    return uuid.uuid4().hex[:12]


def is_acceptable_request_id(value: str) -> bool:
    """Decide whether a caller-supplied ``X-Request-ID`` may be used as-is.

    Anything else is replaced by a generated id, so arbitrary caller text never reaches the logs.

    Args:
        value: The header value as sent.

    Returns:
        bool: True for 1-64 ASCII characters made of letters, digits, ``-`` and ``_``.
    """
    return 0 < len(value) <= 64 and value.isascii() and value.replace("-", "").replace("_", "").isalnum()


def configure_logging(settings: Settings) -> logging.Logger:
    """Apply the level and correlated format from ``Settings`` to the root logger.

    Idempotent: reconfigures only when the level changes. Adds the ``CorrelationIdFilter`` to every
    root handler so ``%(correlation_id)s`` is always populated (``-`` outside a request).

    Args:
        settings: Source of ``log_level``.

    Returns:
        logging.Logger: The package logger (``approval_bot``).
    """
    global _configured_level
    if _configured_level != settings.log_level:
        logging.basicConfig(level=settings.log_level, format=LOG_FORMAT, force=_configured_level is not None)
        for handler in logging.getLogger().handlers:
            if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
                handler.addFilter(CorrelationIdFilter(default_value="-"))
        _configured_level = settings.log_level
    return logging.getLogger("approval_bot")


def current_request_id() -> str | None:
    """The correlation id of the request being handled, if any.

    Returns:
        str | None: The id set by ``CorrelationIdMiddleware``, or ``None`` outside a request.
    """
    return correlation_id.get()


def get_logger(request: Request, rt: Annotated[Runtime, Depends(get_runtime)]) -> RequestLogger:
    """FastAPI dependency: a logger named after the route's module and bound to this request's id.

    Args:
        request: The current request; its endpoint's module names the logger.
        rt: Injected runtime, for ``settings.log_level``.

    Returns:
        RequestLogger: Ready to use; every line it emits carries ``[req=<id>]``.
    """
    configure_logging(rt.settings)
    endpoint = request.scope.get("endpoint")
    name = getattr(endpoint, "__module__", None) or "approval_bot.routers"
    return RequestLogger(logging.getLogger(name), correlation_id.get() or "-")
