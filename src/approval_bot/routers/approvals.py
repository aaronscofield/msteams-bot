"""POST …/approvals — the trigger: ask the bot to send an approval card to a user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ..dependencies import RequestLogger, get_logger, get_service, require_api_key
from ..models import ApprovalCreated, ApprovalRequest, ErrorResponse, UpstreamError
from ..service import ApprovalService

router = APIRouter(tags=["approvals"])


@router.post(
    "/approvals",
    status_code=201,
    response_model=ApprovalCreated,
    summary="Send an approval card",
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "APPROVALS_API_KEY is set and the bearer token did not match."},
        502: {"model": UpstreamError, "description": "Graph or the Bot Connector refused/failed."},
    },
)
async def create_approval(
    body: ApprovalRequest,
    service: Annotated[ApprovalService, Depends(get_service)],
    log: Annotated[RequestLogger, Depends(get_logger)],
) -> Response:
    """Send an approval card to one user.

    Installs the bot for the user if needed, opens their 1:1 chat, and posts an Adaptive Card with
    Approve / Reject buttons. The click comes back on ``…/messages``; the decision is logged as
    ``[approval] {...}`` (with this call's ``traceId``) and POSTed to ``APPROVAL_WEBHOOK_URL`` if set.

    Args:
        body: Who to ask (``user``) and what for (``text``).
        service: Injected ``ApprovalService``.
        log: Injected request-correlated logger.

    Returns:
        Response: ``201`` with ``ApprovalCreated``; ``502`` with ``UpstreamError`` if Graph or the
        Bot Connector failed. (``401`` is produced by the ``require_api_key`` dependency, ``422`` by
        body validation.)
    """
    log.info("[approvals] request for %s", body.user)
    try:
        created = await service.create(body.user, body.text)
    except Exception as e:
        log.exception("[approvals] failed")
        return JSONResponse(UpstreamError(error=str(e)).model_dump(), status_code=502)
    return JSONResponse(created.model_dump(), status_code=201)
