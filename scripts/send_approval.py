"""Ask the running bot to send an approval card to a Teams user.

    uv run scripts/send_approval.py <user@domain> [request text]   (or: make approve USER=… TEXT="…")

All the work (install-if-needed, chat lookup, card send) happens in the bot behind POST …/approvals.
Reads BOT_URL (and APPROVALS_API_KEY, if the bot has one) from the environment or the project's .env.
"""

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
    def approvals_url(self) -> str:
        return f"{self.bot_url}{Settings().route_prefix}/approvals"  # same prefix the bot mounts


if len(sys.argv) < 2:
    sys.exit("usage: scripts/send_approval.py <user@domain> [request text]")
upn = sys.argv[1]
text = " ".join(sys.argv[2:]) or "Deploy release 1.2.3 to production"
env = Env()

headers = {"Authorization": f"Bearer {env.approvals_api_key}"} if env.approvals_api_key else {}
r = httpx.post(env.approvals_url, headers=headers, json={"user": upn, "text": text}, timeout=60)
if r.is_error:
    sys.exit(f"{r.status_code}: {r.text}")
print(f"sent ✔  {r.json()}\n      X-Request-ID: {r.headers.get('X-Request-ID')}  ← grep this in the bot log")
