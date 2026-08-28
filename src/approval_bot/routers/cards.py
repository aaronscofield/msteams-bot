"""PUT …/cards — replace the content of a card the bot posted (e.g. "already approved by X")."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ..dependencies import RequestLogger, get_logger, get_service, require_api_key
from ..models import CardUpdated, CardUpdateRequest, ErrorResponse, UpstreamError
from ..service import ApprovalService

router = APIRouter(tags=["approvals"])


@router.put(
    "/cards",
    response_model=CardUpdated,
    summary="Replace a posted card",
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "APPROVALS_API_KEY is set and the bearer token did not match."},
        502: {"model": UpstreamError, "description": "The Bot Connector refused the update."},
    },
)
async def update_card(
    body: CardUpdateRequest,
    service: Annotated[ApprovalService, Depends(get_service)],
    log: Annotated[RequestLogger, Depends(get_logger)],
) -> Response:
    """Replace a card in place.

    When a request was sent to several people and one of them decided, call this for each of the
    other cards (their ``conversationId`` / ``activityId`` from ``ApprovalCreated``) with a ``notice``
    so they read "Already approved by X"; pass ``requestId`` too and any late click on that card is
    refused with the same message. A raw ``card`` may be supplied instead of ``notice``.

    Args:
        body: Which card, what to put there, and optionally which request to close.
        service: Injected ``ApprovalService``.
        log: Injected request-correlated logger.

    Returns:
        Response: ``200`` with ``CardUpdated``; ``502`` with ``UpstreamError`` if the Bot Connector
        refused. (``401`` from ``require_api_key``, ``422`` from validation.)
    """
    log.info("[cards] update %s in %s", body.activity_id, body.conversation_id)
    try:
        updated = await service.update_card(body)
    except Exception as e:
        log.exception("[cards] failed")
        return JSONResponse(UpstreamError(error=str(e)).model_dump(), status_code=502)
    return JSONResponse(updated.model_dump(), status_code=200)
