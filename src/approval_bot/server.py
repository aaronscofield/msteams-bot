"""FastAPI application factory and entry point. Routes live in `routers/`."""

from __future__ import annotations

import logging

import uvicorn
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__, handlers, routers
from .config import load_settings, log_settings
from .dependencies import configure_logging
from .dependencies.logger_dependency import REQUEST_ID_HEADER, is_acceptable_request_id, new_request_id
from .models import ErrorResponse
from .runtime import Runtime, build_runtime
from .service import ApprovalService
from .store import PendingStore

log = logging.getLogger(__name__)


def create_app(rt: Runtime) -> FastAPI:
    """Build the FastAPI application around an initialised runtime.

    Creates the ``ApprovalService`` and its store, registers the SDK click handlers, installs the
    request-correlation middleware and the ``ErrorResponse`` exception handler, and mounts every router
    under ``Settings.route_prefix``. Runtime and service are placed on ``app.state`` for the
    dependencies in ``dependencies/``.

    Args:
        rt: The runtime produced by ``build_runtime``.

    Returns:
        FastAPI: The configured application (docs routes only when ``ENABLE_DOCS`` is set).
    """
    service = ApprovalService(rt, PendingStore(rt.settings.request_ttl_s))
    handlers.register(rt, service)  # Action.Execute routes (+ dev command) on the SDK agent

    docs = rt.settings.enable_docs
    app = FastAPI(
        title="Company approval bot",
        version=__version__,
        description="Sends approval cards to Teams users and records their Approve / Reject decisions.",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.runtime = rt
    app.state.service = service
    app.state.agent_configuration = rt.auth_config  # read by the SDK's JWT decorator

    # One correlation id per request (X-Request-ID: honoured if acceptable, else generated); kept in a
    # ContextVar for the request's lifetime so every log line carries it, and echoed on the response.
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name=REQUEST_ID_HEADER,
        generator=new_request_id,
        validator=is_acceptable_request_id,
    )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        """Render any HTTPException (notably the security dependencies' 401s) in the ErrorResponse shape.

        Args:
            _: The request (unused).
            exc: The raised exception; ``detail`` becomes ``error``.

        Returns:
            JSONResponse: ``{"error": <detail>}`` with the exception's status code.
        """
        return JSONResponse(ErrorResponse(error=str(exc.detail)).model_dump(), status_code=exc.status_code)

    prefix = rt.settings.route_prefix  # /<domain>/<subdomain>/<version>
    app.include_router(routers.messages.router, prefix=prefix)
    app.include_router(routers.approvals.router, prefix=prefix)
    app.include_router(routers.cards.router, prefix=prefix)
    app.include_router(routers.health.router, prefix=prefix)
    return app


def main() -> None:
    """Process entry point: load settings, configure logging, build the runtime, serve with uvicorn.

    Raises:
        pydantic.ValidationError: If the environment / ``.env`` holds an invalid value.
        ValueError: If the SDK connection configuration is incomplete (e.g. no ``SERVICE_CONNECTION``).
    """
    settings = load_settings()
    configure_logging(settings)
    log_settings(settings)
    rt = build_runtime(settings)
    uvicorn.run(create_app(rt), host=settings.host, port=settings.port, log_config=None, access_log=True)
