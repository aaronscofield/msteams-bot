"""Request / response bodies of the HTTP API. These are what Swagger renders."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import CamelModel

# ---- POST …/approvals ---------------------------------------------------------------------


class ApprovalRequest(CamelModel):
    """Ask the bot to send an approval card to one Teams user.

    Attributes:
        user: UPN of the approver.
        text: What is being approved.
    """

    user: str = Field(
        min_length=3,
        description="UPN of the approver. The bot is installed for them if needed.",
        examples=["someone@company.com"],
    )
    text: str = Field(
        min_length=1,
        max_length=2000,
        description="What is being approved — shown on the card.",
        examples=["Deploy release 1.2.3 to production"],
    )


class ApprovalCreated(CamelModel):
    """The card was posted. Keep ``requestId`` — decisions are logged and POSTed to the webhook under it.

    Attributes:
        request_id: Short id binding the card to the eventual decision.
        user: The addressee's UPN.
        chat_id: Graph id of the 1:1 chat between the bot and the user.
        activity_id: Bot Framework id of the card message.
        service_url: Bot Connector base URL the card was posted through.
        trace_id: Correlation id of this call (also the ``X-Request-ID`` response header).
    """

    request_id: str = Field(description="Short id binding this card to the eventual decision.", examples=["ebfcfbc7"])
    user: str = Field(examples=["someone@company.com"])
    chat_id: str = Field(
        description="Graph id of the 1:1 chat between the bot and the user.",
        examples=["19:<user object id>_<bot app id>@unq.gbl.spaces"],
    )
    conversation_id: str | None = Field(
        default=None,
        description="Bot Framework conversation the card was posted in — pass this (with `activityId`) to PUT …/cards.",
        examples=["a:1vXk3BZVFczyb_…"],
    )
    activity_id: str | None = Field(default=None, description="Bot Framework id of the card message.")
    service_url: str | None = Field(
        default=None,
        description="Bot Connector base URL the card was posted through.",
        examples=["https://smba.trafficmanager.net/amer/"],
    )
    trace_id: str | None = Field(
        default=None,
        description="Correlation id of this call (also returned as the X-Request-ID header). "
        "The eventual decision's log line and webhook payload carry it as `traceId`.",
        examples=["7c1f0a2b9e3d"],
    )


# ---- PUT …/cards ---------------------------------------------------------------------------------


class CardNotice(CamelModel):
    """A ready-made replacement: tell the holder of a card that it no longer needs their action.

    Attributes:
        decision: What happened to the request.
        by: Display name of the person who decided.
        request_text: Optional; shown as a fact so the reader knows which request this was.
    """

    decision: Literal["approved", "rejected"]
    by: str = Field(min_length=1, examples=["Jane Doe"])
    request_text: str | None = Field(default=None, examples=["Deploy release 1.2.3 to production"])


class CardUpdateRequest(CamelModel):
    """Replace the content of a card the bot posted. Supply either ``notice`` or a raw ``card``.

    Attributes:
        conversation_id: Bot Framework conversation id (from ``ApprovalCreated.conversationId``).
        activity_id: The card's activity id (from ``ApprovalCreated.activityId``).
        notice: Ready-made "already decided by X" content.
        card: A full Adaptive Card JSON object, used verbatim instead of ``notice``.
        request_id: If given, that pending request is closed so late clicks are refused with the notice.
        service_url: Override of the Bot Connector base URL for the update.
    """

    conversation_id: str = Field(min_length=1, examples=["a:1vXk3BZVFczyb_…"])
    activity_id: str = Field(min_length=1, examples=["1787936059053"])
    notice: CardNotice | None = None
    card: dict | None = Field(default=None, description="Adaptive Card JSON; overrides `notice` if both are given.")
    request_id: str | None = Field(default=None, examples=["ebfcfbc7"])
    service_url: str | None = Field(
        default=None,
        description="Bot Connector base URL the card was posted through. Defaults to the pending request's "
        "(when `requestId` is given) or the configured TEAMS_SERVICE_URL.",
        examples=["https://smba.trafficmanager.net/amer/"],
    )

    @model_validator(mode="after")
    def _one_of(self) -> CardUpdateRequest:
        """Require content.

        Returns:
            CardUpdateRequest: self.

        Raises:
            ValueError: If neither ``notice`` nor ``card`` is supplied.
        """
        if self.notice is None and self.card is None:
            raise ValueError("supply either `notice` or `card`")
        return self


class CardUpdated(CamelModel):
    """The card was replaced.

    Attributes:
        conversation_id: Where the card lives.
        activity_id: The card's activity id.
        closed_request_id: The pending request that was closed, if ``requestId`` was given.
    """

    conversation_id: str
    activity_id: str
    closed_request_id: str | None = None


# ---- shared -------------------------------------------------------------------------------------


class ErrorResponse(CamelModel):
    """A refused or failed call.

    Attributes:
        error: Short reason.
    """

    error: str = Field(examples=["unauthorized"])


class UpstreamError(ErrorResponse):
    """A Microsoft API refused or failed while sending the card.

    Attributes:
        error: The upstream message (Graph or Bot Connector), including status and body.
    """

    error: str = Field(examples=["Graph POST /users/…/teamwork/installedApps → 403: Caller is not authorized."])


# ---- GET /health --------------------------------------------------------------------------------


class Health(CamelModel):
    """Liveness probe body.

    Attributes:
        status: Always ``ok`` when the process answers.
        version: The package version.
    """

    status: Literal["ok"] = "ok"
    version: str = Field(examples=["1.5.0"])


# ---- POST …/messages --------------------------------------------------------------------------


class Acknowledged(CamelModel):
    """Bot Framework activities that need no synchronous reply (messages, events) are acknowledged only.

    Attributes:
        status: Always ``accepted``.
    """

    status: Literal["accepted"] = "accepted"
