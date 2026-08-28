"""The checks every click must pass, in the order the service runs them.

    Guard 0 — "did this come from Microsoft?"   → `dependencies.bot_framework_security`, not here
    Guard 1 — check_binding : right card, right conversation, right person, first time, token origin
    Guard 2 — check_group   : addressee is (transitively) in the approvers group
    Guard 3 — check_sso     : an Entra-issued token for this bot proves the clicker's identity

Each raises `Refused` with a message safe to show the user. Anything else propagating is a bug.
"""

from __future__ import annotations

import logging

import httpx
import jwt
from jwt import PyJWKClient
from microsoft_agents.hosting.core import TurnContext

from .clients import GraphClient, GraphError
from .config import GRAPH
from .models import PendingRequest
from .runtime import Runtime

log = logging.getLogger(__name__)


class Refused(Exception):
    """A click that must not be accepted.

    The message is shown to the user as a toast; the card keeps its buttons and nothing is recorded.
    """


# ---- Guard 1 ------------------------------------------------------------------------------------
def check_binding(context: TurnContext, pending: PendingRequest | None, request_id: str | None) -> None:
    """Guard 1 — confirm the click belongs to a card we sent and is the first answer to it.

    Args:
        context: The turn carrying the click; its activity and validated claims are inspected.
        pending: The stored request the click names, or ``None`` if unknown/expired.
        request_id: The request id from the click (for the message only).

    Raises:
        Refused: If the request is unknown or expired; already decided or closed; answered from a different
            conversation than the card was posted to; answered by someone other than the addressee;
            or the Bot Framework token's ``serviceurl`` claim does not match the activity's origin.
    """
    a = context.activity
    if pending is None:
        raise Refused(f"Unknown or expired request {request_id!r}.")
    if pending.decided:
        raise Refused(f"Request {request_id} was already {pending.decided.decision}.")
    if pending.closed:
        raise Refused(pending.closed)
    if pending.conversation_id and a.conversation.id != pending.conversation_id:
        raise Refused("This card was answered from a different conversation than it was sent to.")
    oid = a.from_property.aad_object_id
    if pending.approver_oid and oid != pending.approver_oid:
        raise Refused("Only the person this request was sent to can answer it.")
    # The Bot Framework JWT names the channel it was issued for; it must match the activity's origin.
    claims = getattr(context.identity, "claims", None) or {}
    if (svc := claims.get("serviceurl")) and svc.rstrip("/") != (a.service_url or "").rstrip("/"):
        raise Refused("Request origin does not match its token.")


# ---- Guard 2 ------------------------------------------------------------------------------------
async def check_group(rt: Runtime, oid: str | None) -> None:
    """Guard 2 — confirm the clicker is a (transitive) member of the approvers group.

    A no-op when ``APPROVERS_GROUP_ID`` is not configured.

    Args:
        rt: Runtime, for settings and an app-only Graph token.
        oid: Entra object id of the clicker, as asserted by Teams.

    Raises:
        Refused: If no object id is present, the Graph lookup fails, or the user is not a member.
        ValueError: If the app-only Graph token cannot be acquired.
    """
    group_id = rt.settings.approvers_group_id
    if not group_id:
        return
    if not oid:
        raise Refused("Your identity could not be determined.")
    token = await rt.app_token(GRAPH)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            member = await GraphClient(client, token).is_transitive_member(group_id, oid)
    except GraphError as e:
        log.warning("[group] membership lookup failed: %s", e)
        raise Refused("Could not verify your group membership. Please try again.") from e
    if not member:
        raise Refused("You are not a member of the approvers group.")


# ---- Guard 3 ------------------------------------------------------------------------------------
class EntraTokenValidator:
    """Validates tokens Entra issues for this bot's own API (``api://botid-<app>/…``).

    Checks the RS256 signature against the tenant's JWKS, the issuer, the audience, and expiry
    (with 5 minutes of clock leeway). Keys are cached by ``PyJWKClient``.

    Attributes:
        _jwks: Client for the tenant's JWKS endpoint.
        _audiences: Accepted ``aud`` values (the API URI and the bare app id).
        _issuers: Accepted ``iss`` values (v2 and v1 endpoints for the tenant).
    """

    def __init__(self, tenant_id: str, bot_app_id: str) -> None:
        """Bind the validator to one tenant and one bot app.

        Args:
            tenant_id: Entra tenant id the token must come from.
            bot_app_id: The bot's Entra application (client) id.
        """
        self._jwks = PyJWKClient(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys", cache_keys=True)
        self._audiences = [f"api://botid-{bot_app_id}", bot_app_id]
        self._issuers = [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        ]

    def validate(self, token: str) -> dict:
        """Validate a token and return its claims.

        Args:
            token: The compact JWS string obtained through the SDK's SSO token exchange.

        Returns:
            dict: The verified claims (``oid``, ``tid``, ``scp``, …).

        Raises:
            jwt.PyJWTError: If the signature, issuer, audience, or expiry is invalid, or the signing
                key cannot be fetched.
        """
        key = self._jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key=key, algorithms=["RS256"], audience=self._audiences, issuer=self._issuers, leeway=300
        )


async def check_sso(rt: Runtime, validator: EntraTokenValidator, context: TurnContext, oid: str | None) -> str:
    """Guard 3 — prove the clicker's identity with a token Entra issued for this bot.

    When no SSO handler is configured the identity is accepted as Teams-asserted.

    Args:
        rt: Runtime, for settings and the SDK's user-token cache.
        validator: Validator for tokens issued to this bot's API.
        context: The turn; the SDK has already completed the silent token exchange for it.
        oid: Entra object id of the clicker, as asserted by Teams.

    Returns:
        str: ``"entra"`` when an SSO token proved the identity, ``"teams"`` when SSO is off.

    Raises:
        Refused: If no token is available (sign-in required), the token fails validation, or its
            ``oid`` does not match the clicker.
    """
    handler = rt.settings.sso_handler
    if not handler:
        return "teams"
    tr = await rt.agent.auth.get_token(context, handler)
    if not tr or not tr.token:
        raise Refused("Sign-in is required to answer this request. Please try again.")
    try:
        claims = validator.validate(tr.token)
    except jwt.PyJWTError as e:
        log.warning("[sso] token rejected: %s", e)
        raise Refused("Your sign-in token could not be verified.") from e
    if claims.get("oid") != oid:
        raise Refused("Signed-in identity does not match the responding user.")
    return "entra"
