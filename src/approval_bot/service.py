"""ApprovalService — the two things the bot does.

create(upn, text)         install the bot for the user if needed, open their chat, post the card,
                          remember the request
decide(context, verb, …)  run the guards on a click, record the decision, return it
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx
from asgi_correlation_id import correlation_id
from microsoft_agents.hosting.core import TurnContext

from . import cards
from .clients import ConnectorClient, GraphClient, oid_from_chat_id
from .config import BOT_CONNECTOR, GRAPH
from .guards import EntraTokenValidator, check_binding, check_group, check_sso
from .models import ApprovalCreated, Approver, CardUpdated, CardUpdateRequest, Decision, PendingRequest
from .runtime import Runtime
from .store import PendingStore

log = logging.getLogger(__name__)


class ApprovalService:
    """Creates approval requests (outbound) and decides them from card clicks (inbound).

    Attributes:
        rt: The SDK runtime (settings, tokens, agent).
        store: Where pending requests live between the send and the click.
    """

    def __init__(self, rt: Runtime, store: PendingStore) -> None:
        """Initialise the service.

        Args:
            rt: The SDK runtime providing settings, app-only tokens, and the bot's identity.
            store: The pending-request store shared with the click handlers.
        """
        self.rt = rt
        self.store = store
        self._validator = EntraTokenValidator(rt.tenant_id, rt.bot_app_id)

    # ---- outbound ------------------------------------------------------------------------------
    async def create(self, upn: str, text: str) -> ApprovalCreated:
        """Send an approval card to a Teams user.

        Installs the bot for the user if it is not already installed (Graph), resolves the 1:1 chat,
        creates/resolves the Bot Framework conversation, posts the Adaptive Card, and records the
        request so the eventual click can be verified against it.

        Args:
            upn: User principal name of the approver, e.g. ``someone@company.com``.
            text: What is being approved; shown on the card.

        Returns:
            ApprovalCreated: The request id, the Graph chat id, the card's activity id, and the
            correlation (trace) id of this call.

        Raises:
            RuntimeError: If ``TEAMS_CATALOG_APP_ID`` is not configured (the bot cannot be installed).
            GraphError: If Graph refuses the install check, the install, or the chat lookup
                (permissions, unknown user, app not in the org catalog).
            ConnectorError: If the Bot Connector rejects the card post.
            ValueError: If the app-only token cannot be acquired (certificate / tenant misconfiguration).
        """
        s = self.rt.settings
        if not s.catalog_app_id:
            raise RuntimeError("TEAMS_CATALOG_APP_ID is not set")
        request_id = str(uuid.uuid7())

        async with httpx.AsyncClient(timeout=30) as client:
            graph = GraphClient(client, await self.rt.app_token(GRAPH))
            install = await graph.installed_app(upn, s.catalog_app_id)
            if install is None:
                log.info("[approvals] installing bot for %s", upn)
                await graph.install_app(upn, s.catalog_app_id)
                install = await graph.installed_app(upn, s.catalog_app_id)
            chat = await graph.personal_chat(upn, install["id"])

            approver_oid = oid_from_chat_id(chat["id"], self.rt.bot_app_id)
            connector = ConnectorClient(
                client, await self.rt.app_token(BOT_CONNECTOR), s.service_url, self.rt.bot_app_id, self.rt.tenant_id
            )
            conversation_id = await connector.create_personal_conversation(approver_oid) if approver_oid else None
            target = conversation_id or chat["id"]
            activity_id = await connector.send_card(
                target, cards.request_card(request_id, text), summary=f"Approval requested: {text}"
            )

        if not approver_oid:
            log.warning("[approvals] no approver oid from chat id %s — user binding check disabled", chat["id"])
        if not conversation_id:
            log.warning("[approvals] no Bot Framework conversation id for %s — conversation check disabled", request_id)
        trace_id = correlation_id.get()
        self.store.add(
            PendingRequest(
                request_id=request_id,
                text=text,
                upn=upn,
                approver_oid=approver_oid,
                conversation_id=conversation_id,
                chat_id=chat["id"],
                service_url=s.service_url,
                trace_id=trace_id,
            )
        )
        log.info(
            "[approvals] sent request %s to %s (conversation %s, activity %s)", request_id, upn, target, activity_id
        )
        return ApprovalCreated(
            request_id=request_id,
            user=upn,
            chat_id=chat["id"],
            conversation_id=target,
            activity_id=activity_id,
            service_url=s.service_url,
            trace_id=trace_id,
        )

    def create_local(self, context: TurnContext, text: str) -> tuple[str, dict]:
        """Record a request bound to the *current* conversation and sender (dev ``/approval`` command).

        Nothing is sent here; the caller posts the returned card into the conversation it came from.

        Args:
            context: The turn whose conversation and sender the request is bound to.
            text: What is being approved; shown on the card.

        Returns:
            tuple[str, dict]: The new request id and the Adaptive Card payload to send.
        """
        a = context.activity
        request_id = str(uuid.uuid7())
        self.store.add(
            PendingRequest(
                request_id=request_id,
                text=text,
                upn=a.from_property.name or "",
                approver_oid=a.from_property.aad_object_id,
                conversation_id=a.conversation.id,
                service_url=a.service_url,
                trace_id=correlation_id.get(),
            )
        )
        log.info(
            "[approvals] dev card %s in conversation %s for %s", request_id, a.conversation.id, a.from_property.name
        )
        return request_id, cards.request_card(request_id, text)

    async def update_card(self, req: CardUpdateRequest) -> CardUpdated:
        """Replace a posted card's content, optionally closing the pending request behind it.

        Used after one approver has decided, to turn the other approvers' cards into an
        "already approved by X" notice so nobody acts twice.

        Args:
            req: Where the card is, the new content (``notice`` or raw ``card``), and optionally the
                request id to close.

        Returns:
            CardUpdated: The conversation/activity that was updated and the request closed, if any.

        Raises:
            ConnectorError: If the Bot Connector refuses the update (unknown activity, not our message).
            ValueError: If the app-only token cannot be acquired.
        """
        if req.card is not None:
            card, summary = req.card, "Card updated"
        else:
            n = req.notice
            headline = "✅ Already approved" if n.decision == "approved" else "❌ Already rejected"
            facts = {"Request": n.request_text} if n.request_text else None
            card = cards.notice_card(headline, f"{n.by} has {n.decision} this request; no action is needed.", facts)
            summary = f"Already {n.decision} by {n.by}"

        pending = self.store.get(req.request_id) if req.request_id else None
        service_url = req.service_url or (pending.service_url if pending else None) or self.rt.settings.service_url
        async with httpx.AsyncClient(timeout=30) as client:
            connector = ConnectorClient(
                client, await self.rt.app_token(BOT_CONNECTOR), service_url, self.rt.bot_app_id, self.rt.tenant_id
            )
            await connector.update_card(req.conversation_id, req.activity_id, card, summary)

        closed = None
        if pending and not pending.decided:
            pending.closed = summary + "." if req.notice else "This request has been closed."
            closed = req.request_id
        log.info("[cards] updated activity %s in %s (closed request %s)", req.activity_id, req.conversation_id, closed)
        return CardUpdated(conversation_id=req.conversation_id, activity_id=req.activity_id, closed_request_id=closed)

    # ---- inbound ---------------------------------------------------------------------------------
    async def decide(self, context: TurnContext, verb: str, data: dict | None) -> Decision:
        """Verify a card click and record the decision.

        Runs the guards in order — binding/replay, group membership, SSO identity — then marks the
        pending request decided, logs the decision as JSON, and notifies the webhook if configured.

        Args:
            context: The turn carrying the ``adaptiveCard/action`` invoke.
            verb: ``"approve"`` or ``"reject"`` (the Action.Execute verb that was clicked).
            data: The action's ``data`` payload; ``requestId`` is required, ``comment`` optional.

        Returns:
            Decision: The recorded decision, including who decided, how their identity was verified,
            and the trace id of the trigger that created the request.

        Raises:
            Refused: If any guard rejects the click — unknown/expired/already-decided request, wrong
                conversation or user, token/activity origin mismatch, not in the approvers group,
                missing or invalid SSO token, or SSO identity not matching the clicker.
            ValueError: If an app-only token for Graph cannot be acquired during the group check.
        """
        a = context.activity
        data = data or {}
        request_id = data.get("requestId")
        pending = self.store.get(request_id)
        check_binding(context, pending, request_id)
        oid = a.from_property.aad_object_id
        await check_group(self.rt, oid)
        verified_by = await check_sso(self.rt, self._validator, context, oid)

        decision = Decision(
            request_id=request_id,
            request_text=pending.text,
            decision="approved" if verb == "approve" else "rejected",
            comment=data.get("comment") or "",
            by=Approver(name=a.from_property.name, aad_object_id=oid, upn=pending.upn),
            verified_by=verified_by,
            at=datetime.now(UTC),
            trace_id=pending.trace_id,
        )
        pending.decided = decision
        log.info("[approval] %s", decision.model_dump_json())
        await self._notify(decision)
        return decision

    async def _notify(self, decision: Decision) -> None:
        """POST the decision to ``APPROVAL_WEBHOOK_URL`` if one is configured.

        Failures are logged, never raised — a broken webhook must not turn a recorded decision into a
        user-facing error.

        Args:
            decision: The decision to deliver, serialised as camelCase JSON.
        """
        url = self.rt.settings.webhook_url
        if not url:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                (await client.post(url, json=decision.model_dump(mode="json"))).raise_for_status()
        except httpx.HTTPError as e:
            log.error("[approval] webhook failed: %s", e)
