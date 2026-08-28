from datetime import datetime
from typing import Literal

from .base import CamelModel


class Approver(CamelModel):
    """Who answered a request.

    Attributes:
        name: Display name as reported by Teams.
        aad_object_id: Entra object id as reported by Teams (and confirmed by SSO when enabled).
        upn: The address the card was sent to.
    """

    name: str | None = None
    aad_object_id: str | None = None
    upn: str


class Decision(CamelModel):
    """A recorded approve/reject. Logged as JSON, POSTed to the webhook, rendered as the result card.

    Attributes:
        request_id: The card's request id.
        request_text: What was being approved.
        decision: ``approved`` or ``rejected``.
        comment: Optional comment typed on the card.
        by: Who decided.
        verified_by: ``entra`` when an SSO token proved the identity, ``teams`` when only asserted.
        at: When the decision was recorded (UTC).
        trace_id: Correlation id of the trigger that created the request.
    """

    request_id: str
    request_text: str
    decision: Literal["approved", "rejected"]
    comment: str = ""
    by: Approver
    verified_by: Literal["entra", "teams"]
    at: datetime
    trace_id: str | None = None
    """X-Request-ID of the trigger that sent the card (the click itself has its own request id)."""
