import time

from pydantic import BaseModel, Field

from .decision import Decision


class PendingRequest(BaseModel):
    """A card that has been sent and may still be answered. A request is decided at most once.

    Attributes:
        request_id: Short id carried by the card's buttons.
        text: What is being approved.
        upn: Who the card was addressed to (display name for dev cards).
        approver_oid: Entra object id of the addressee; ``None`` disables the user-binding check.
        conversation_id: Bot Framework conversation the card was posted to; ``None`` disables the check.
        chat_id: Graph chat id (informational).
        service_url: Bot Connector base URL the card was posted through.
        trace_id: Correlation id of the trigger — links the click's log lines back to it.
        created: Unix time the request was stored; used for TTL pruning.
        decided: The recorded decision once one exists.
        closed: Refusal message set when the request was closed from outside (PUT …/cards).
    """

    request_id: str
    text: str
    upn: str
    """Who the card was addressed to (display name for dev cards)."""
    approver_oid: str | None
    """Entra object id of the addressee; None disables the user-binding check."""
    conversation_id: str | None
    """Bot Framework conversation id the card was posted to; None disables the conversation check."""
    chat_id: str | None = None
    """Graph chat id (informational)."""
    service_url: str | None = None
    """Bot Connector base URL the card was posted through; needed to update the card later."""
    trace_id: str | None = None
    """X-Request-ID of the trigger that created this request — links the click's log lines back to it."""
    created: float = Field(default_factory=time.time)
    decided: Decision | None = None
    closed: str | None = None
    """Set when the request was closed without a decision here (e.g. decided elsewhere); the message
    shown to anyone who still clicks."""
