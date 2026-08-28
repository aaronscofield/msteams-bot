"""Guard 0 as a FastAPI security dependency: the Bot Framework JWT on …/messages.

Uses the SDK's own validator (`_authorize_request`, the function behind its middleware/decorator) so
the checks are identical — signature via Bot Framework's JWKS, audience = this bot's App ID, issuer,
expiry — and stores the resulting ClaimsIdentity where the SDK adapter expects it
(`request.state.claims_identity`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from microsoft_agents.hosting.core.authorization import ClaimsIdentity
from microsoft_agents.hosting.core.authorization.jwt import _authorize_request
from microsoft_agents.hosting.core.http import HttpResponse

from ..runtime import Runtime
from .runtime_dependency import get_runtime

bot_framework_jwt = HTTPBearer(
    scheme_name="BotFrameworkJWT",
    description="JWT issued by Bot Framework Service for this bot's App ID. Only Bot Framework can mint one.",
    auto_error=False,  # let the SDK validator produce the 401 (it also handles ANONYMOUS_ALLOWED for dev)
)


async def require_bot_framework_jwt(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bot_framework_jwt)],
    rt: Annotated[Runtime, Depends(get_runtime)],
) -> ClaimsIdentity:
    """FastAPI security dependency: validate the Bot Framework JWT and expose its claims.

    Args:
        request: The current request; the claims are stored on ``request.state.claims_identity``.
        credentials: The parsed ``Authorization: Bearer …`` header, or ``None`` if absent.
        rt: Injected runtime, for the SDK auth configuration (expected audience, issuers, …).

    Returns:
        ClaimsIdentity: The validated claims (or the SDK's anonymous identity when
        ``ANONYMOUS_ALLOWED`` is on and no header was sent — dev only).

    Raises:
        HTTPException: With the SDK validator's status (``401``) and reason when the header is
            missing, malformed, or the token fails signature / audience / issuer / expiry checks.
    """
    header = f"Bearer {credentials.credentials}" if credentials else request.headers.get("Authorization")
    result = await _authorize_request(header, rt.auth_config)
    if isinstance(result, HttpResponse):
        detail = result.body.get("error") if isinstance(result.body, dict) else str(result.body)
        raise HTTPException(status_code=result.status_code, detail=detail or "unauthorized")
    request.state.claims_identity = result
    return result
