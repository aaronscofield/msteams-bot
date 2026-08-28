"""Registers the bot's routes on the AgentApplication.

The bot never talks unprompted: the only routes are the two Action.Execute verbs (and, in dev, the
`/approval` chat command that posts a card into the current conversation).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from microsoft_agents.activity import AdaptiveCardInvokeResponse
from microsoft_agents.hosting.core import CardFactory, MessageFactory, TurnContext, TurnState
from microsoft_agents.hosting.core.app.adaptive_card import factory as invoke_response

from . import cards
from .guards import Refused
from .runtime import Runtime
from .service import ApprovalService

log = logging.getLogger(__name__)


def register(rt: Runtime, service: ApprovalService) -> None:
    """Register the click handlers (and the dev command) on the SDK agent.

    When an SSO handler is configured the click routes are registered with ``auth_handlers`` so the
    SDK runs the Teams SSO sign-in flow before the handler executes.

    Args:
        rt: Runtime whose ``agent`` receives the routes and whose settings decide SSO / dev mode.
        service: The service the handlers delegate to.
    """
    sso = rt.settings.sso_handler
    for verb in ("approve", "reject"):
        rt.agent.adaptive_card.action_execute(verb, auth_handlers=[sso] if sso else None)(_action(service, verb))
    if rt.settings.dev_commands:
        rt.agent.message(re.compile(r"/approval\b.*", re.S))(_dev_card(service))


def _action(
    service: ApprovalService, verb: str
) -> Callable[[TurnContext, TurnState, dict], Awaitable[AdaptiveCardInvokeResponse]]:
    """Build the Action.Execute handler for one verb.

    Args:
        service: The service that verifies and records decisions.
        verb: ``"approve"`` or ``"reject"``.

    Returns:
        Callable: An async handler ``(context, state, data)`` returning the invoke response — the
        result card on success, a toast message on refusal or unexpected failure. Never raises.
    """

    async def handler(context: TurnContext, _: TurnState, data: dict) -> AdaptiveCardInvokeResponse:
        try:
            decision = await service.decide(context, verb, data)
            return invoke_response.adaptive_card(cards.result_card(decision))  # replaces the card in place
        except Refused as e:
            log.warning("[approval] refused %s from %s: %s", verb, context.activity.from_property.aad_object_id, e)
            return invoke_response.message(str(e))  # toast; the card keeps its buttons
        except Exception:
            log.exception("[approval] failed")
            return invoke_response.message("Something went wrong recording your decision. Please try again.")

    return handler


def _dev_card(service: ApprovalService) -> Callable[[TurnContext, TurnState], Awaitable[None]]:
    """Build the dev ``/approval <text>`` message handler.

    Args:
        service: The service that records the local request.

    Returns:
        Callable: An async handler ``(context, state)`` that posts an approval card into the current
        conversation, bound to the sender.
    """

    async def handler(context: TurnContext, _: TurnState) -> None:
        text = (context.activity.text or "").partition(" ")[2].strip() or "Deploy release 1.2.3 to production"
        _, card = service.create_local(context, text)
        await context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(card)))

    return handler
