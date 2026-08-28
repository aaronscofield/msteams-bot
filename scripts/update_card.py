"""Replace a card the bot posted — e.g. tell the other approvers it was already decided.

    uv run scripts/update_card.py <conversationId> <activityId> --by "Jane Doe" [--decision approved|rejected]
                                  [--text "what was approved"] [--request-id <id>] [--service-url <url>]
    uv run scripts/update_card.py <conversationId> <activityId> --card card.json          # raw Adaptive Card instead

`conversationId`, `activityId` and `requestId` come from the response of send_approval.py (ApprovalCreated).
Passing --request-id also closes that request so late clicks are refused with the notice.
Reads BOT_URL (and APPROVALS_API_KEY, if the bot has one) from the environment or the project's .env.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from approval_bot.models import Settings


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore")
    bot_url: str = "http://localhost:3978"
    approvals_api_key: str | None = None

    @property
    def cards_url(self) -> str:
        return f"{self.bot_url}{Settings().route_prefix}/cards"  # same prefix the bot mounts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("conversation_id", help="Bot Framework conversation id (ApprovalCreated.conversationId)")
    p.add_argument("activity_id", help="the card's activity id (ApprovalCreated.activityId)")
    p.add_argument("--by", help="display name of the person who decided (notice mode)")
    p.add_argument("--decision", choices=["approved", "rejected"], default="approved")
    p.add_argument("--text", help="the request text, shown as a fact on the notice")
    p.add_argument("--request-id", help="close this pending request so late clicks are refused")
    p.add_argument("--service-url", help="Bot Connector base URL if different from the bot's default")
    p.add_argument("--card", type=Path, help="JSON file with a full Adaptive Card to use instead of a notice")
    a = p.parse_args()
    if not a.by and not a.card:
        p.error("either --by (notice) or --card (raw Adaptive Card) is required")

    body: dict = {"conversationId": a.conversation_id, "activityId": a.activity_id}
    if a.card:
        body["card"] = json.loads(a.card.read_text())
    else:
        body["notice"] = {"decision": a.decision, "by": a.by, **({"requestText": a.text} if a.text else {})}
    if a.request_id:
        body["requestId"] = a.request_id
    if a.service_url:
        body["serviceUrl"] = a.service_url

    env = Env()
    headers = {"Authorization": f"Bearer {env.approvals_api_key}"} if env.approvals_api_key else {}
    r = httpx.put(env.cards_url, headers=headers, json=body, timeout=60)
    if r.is_error:
        print(f"{r.status_code}: {r.text}", file=sys.stderr)
        return 1
    print(f"updated ✔  {r.json()}\n      X-Request-ID: {r.headers.get('X-Request-ID')}  ← grep this in the bot log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
