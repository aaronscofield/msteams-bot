"""Adaptive Card payloads. Pure functions: values in, dict out."""

from __future__ import annotations

from datetime import UTC, datetime

from .models import Decision

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"


def request_card(request_id: str, text: str) -> dict:
    """Build the card an approver sees.

    Buttons are Universal Actions (``Action.Execute``) so the click arrives as an invoke and the bot
    can replace the card synchronously. Only the request id travels with the click; the optional
    comment box is submitted alongside it.

    Args:
        request_id: Short id the click will carry back.
        text: What is being approved.

    Returns:
        dict: Adaptive Card 1.5 JSON.
    """
    return {
        "$schema": _SCHEMA,
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": "🔔 Approval requested"},
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Request", "value": text},
                    {"title": "Request ID", "value": request_id},
                    {"title": "Requested", "value": datetime.now(UTC).isoformat()},
                ],
            },
            {"type": "Input.Text", "id": "comment", "placeholder": "Optional comment", "isMultiline": True},
        ],
        "actions": [
            _action("approve", "✅ Approve", "positive", request_id),
            _action("reject", "❌ Reject", "destructive", request_id),
        ],
    }


def result_card(d: Decision) -> dict:
    """Build the card that replaces the request card once a decision is recorded.

    It has no actions, so it cannot be clicked again.

    Args:
        d: The recorded decision.

    Returns:
        dict: Adaptive Card 1.5 JSON showing the outcome, who decided, how they were verified, and when.
    """
    approved = d.decision == "approved"
    facts = [
        {"title": "Request", "value": d.request_text},
        {"title": "Request ID", "value": d.request_id},
        {"title": "By", "value": d.by.name or "unknown"},
        {"title": "Verified", "value": d.verified_by},
        {"title": "At", "value": d.at.isoformat()},
    ]
    if d.comment:
        facts.append({"title": "Comment", "value": d.comment})
    return {
        "$schema": _SCHEMA,
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": "✅ Approved" if approved else "❌ Rejected",
                "color": "Good" if approved else "Attention",
            },
            {"type": "FactSet", "facts": facts},
        ],
    }


def notice_card(title: str, text: str, facts: dict[str, str] | None = None) -> dict:
    """Build a read-only card that replaces a request card for people who no longer need to act.

    Typical use: after one approver decides, the other approvers' cards become
    "Already approved by Jane Doe".

    Args:
        title: Headline, e.g. ``"✅ Already approved"``.
        text: One line of explanation.
        facts: Optional label → value pairs shown under the text.

    Returns:
        dict: Adaptive Card 1.5 JSON with no actions.
    """
    body: list[dict] = [
        {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": title},
        {"type": "TextBlock", "text": text, "wrap": True},
    ]
    if facts:
        body.append({"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in facts.items()]})
    return {"$schema": _SCHEMA, "type": "AdaptiveCard", "version": "1.5", "body": body}


def _action(verb: str, title: str, style: str, request_id: str) -> dict:
    """Build one ``Action.Execute`` button.

    Args:
        verb: The verb the click handler is registered for (``approve`` / ``reject``).
        title: Button label.
        style: Adaptive Card action style (``positive`` / ``destructive``).
        request_id: Carried in ``data`` so the bot can find the pending request.

    Returns:
        dict: The action JSON.
    """
    return {"type": "Action.Execute", "verb": verb, "title": title, "style": style, "data": {"requestId": request_id}}
