"""POST …/messages — the single door for everything Bot Framework delivers on Teams' behalf.

Card clicks (`adaptiveCard/action` invokes), the SSO `signin/tokenExchange` invoke, membership events,
and typed messages all arrive here; the SDK's AgentApplication dispatches them to the routes registered
in `handlers.py`. Guard 0 (the Bot Framework JWT) is the `require_bot_framework_jwt` security dependency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from microsoft_agents.hosting.core.authorization import ClaimsIdentity
from microsoft_agents.hosting.fastapi import start_agent_process

from ..dependencies import get_runtime, require_bot_framework_jwt
from ..models import Acknowledged, ErrorResponse
from ..runtime import Runtime

router = APIRouter(tags=["bot"])

_ACTIVITY_EXAMPLE = {
    "type": "invoke",
    "name": "adaptiveCard/action",
    "from": {"id": "29:…", "name": "Jane Doe", "aadObjectId": "<entra object id>"},
    "conversation": {"id": "a:1vXk3B…"},
    "serviceUrl": "https://smba.trafficmanager.net/amer/<tenant>/",
    "value": {
        "action": {
            "type": "Action.Execute",
            "verb": "approve",
            "data": {"requestId": "019913a4-2b7d-7c40-9f1d-3e6a7b8c9d01"},
        }
    },
}


@router.post(
    "/messages",
    summary="Bot Framework messaging endpoint",
    responses={
        200: {
            "description": "Invoke response — for a card click, the replacement card "
            "(`application/vnd.microsoft.card.adaptive`) or a toast (`application/vnd.microsoft.activity.message`).",
            "content": {
                "application/json": {
                    "example": {
                        "statusCode": 200,
                        "type": "application/vnd.microsoft.card.adaptive",
                        "value": {"type": "AdaptiveCard", "…": "…"},
                    }
                }
            },
        },
        202: {"model": Acknowledged, "description": "Activity accepted; nothing to return (messages, events)."},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bot Framework JWT."},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": "A Bot Framework **Activity**, sent only by Bot Framework Service (Teams / Direct Line). "
            "Not callable from Swagger: it must carry a JWT issued by Bot Framework for this bot's App ID.",
            "content": {"application/json": {"example": _ACTIVITY_EXAMPLE}},
        }
    },
)
async def messages(
    request: Request,
    rt: Annotated[Runtime, Depends(get_runtime)],
    _claims: Annotated[ClaimsIdentity, Depends(require_bot_framework_jwt)],
) -> Response:
    """Hand a Bot Framework activity to the SDK agent.

    Card clicks are ``adaptiveCard/action`` invokes routed by ``verb`` to the approve / reject
    handlers, which run the guards and answer with the result card in this response. Activities
    with nothing to return are acknowledged with ``202``.

    Args:
        request: The raw request; the SDK parses the Activity from its body.
        rt: Injected runtime (agent + adapter).
        _claims: The validated Bot Framework claims (the dependency also stores them on
            ``request.state`` for the SDK adapter).

    Returns:
        Response: The SDK's invoke response (``200``) or ``Acknowledged`` (``202``). ``401`` is
        produced by the security dependency before this runs.
    """
    return await start_agent_process(request, rt.agent, rt.adapter) or JSONResponse(
        Acknowledged().model_dump(), status_code=202
    )
