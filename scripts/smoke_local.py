"""Local smoke test — no Azure, no Teams, no browser.

Runs against `make dev` (bot on :3979, anonymous inbound, SSO/group off, /approval command on):
  1. starts a fake Bot Connector on :3980 that records whatever the bot sends to it
  2. posts a `/approval …` message → expects the bot to send an approval card to the fake connector
  3. posts a click from a different conversation → expects the conversation-binding refusal
  4. posts the real Action.Execute click → expects the result card in the invoke response
  5. posts the click again → expects the "already approved" refusal

    uv run scripts/smoke_local.py [--bot http://localhost:3979]
"""

import argparse
import asyncio
import json
import sys
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from approval_bot.models import Settings

FAKE_PORT = 3980
dumps = partial(json.dumps, ensure_ascii=False)
sent: list[dict] = []


class _FakeConnector(BaseHTTPRequestHandler):
    """Accepts whatever the bot sends (card, conversation create) and records POST bodies."""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        sent.append(json.loads(self.rfile.read(length) or b"{}"))
        self._ok()

    def do_PUT(self) -> None:
        self.do_POST()

    def do_GET(self) -> None:
        self._ok()

    def _ok(self) -> None:
        body = json.dumps({"id": f"fake-{len(sent)}"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


CONNECTOR_HOST = "localhost"  # what the *bot* must dial to reach the fake connector; set by --connector-host


def _activity(kind: str, conv: str, **extra) -> dict:
    return {
        "type": kind,
        "id": "act-1",
        "channelId": "msteams",
        "serviceUrl": f"http://{CONNECTOR_HOST}:{FAKE_PORT}/",
        "from": {"id": "29:user", "name": "Smoke Tester", "aadObjectId": "11111111-1111-1111-1111-111111111111"},
        "recipient": {"id": "28:bot", "name": "bot"},
        "conversation": {"id": conv, "conversationType": "personal"},
        **extra,
    }


def _click(conv: str, verb: str, request_id: str) -> dict:
    action = {"type": "Action.Execute", "verb": verb, "data": {"requestId": request_id}}
    return _activity("invoke", conv, name="adaptiveCard/action", value={"action": action})


async def main(bot: str, prefix: str, connector_host: str) -> int:
    global CONNECTOR_HOST
    CONNECTOR_HOST = connector_host
    server = ThreadingHTTPServer(("0.0.0.0", FAKE_PORT), _FakeConnector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")

    async with httpx.AsyncClient(timeout=30) as s:
        url = f"{bot}{prefix}/messages"
        r = await s.get(f"{bot}{prefix}/health", headers={"X-Request-ID": "smoke-abc123"})
        check("health", r.status_code == 200)
        check("X-Request-ID echoed", r.headers.get("X-Request-ID") == "smoke-abc123", str(dict(r.headers))[:120])
        r = await s.get(f"{bot}{prefix}/health")
        check("X-Request-ID generated", bool(r.headers.get("X-Request-ID")))

        r = await s.post(url, json=_activity("message", "conv-A", text="/approval Smoke: approve it"))
        check("/approval accepted", r.status_code in (200, 201, 202), f"status {r.status_code}")
        await asyncio.sleep(0.5)
        card = next((a for a in sent if a.get("attachments")), None)
        check("card sent to connector", card is not None)
        if card is None:
            server.shutdown()
            return 1
        request_id = card["attachments"][0]["content"]["actions"][0]["data"]["requestId"]

        body = (await s.post(url, json=_click("conv-B", "approve", request_id))).json()
        is_toast = body.get("type") == "application/vnd.microsoft.activity.message"
        check("wrong conversation refused", is_toast and "different conversation" in dumps(body), dumps(body)[:120])

        body = (await s.post(url, json=_click("conv-A", "approve", request_id))).json()
        is_card = body.get("type") == "application/vnd.microsoft.card.adaptive"
        check("approve → result card", is_card and "✅ Approved" in dumps(body), dumps(body)[:120])
        check("verifiedBy teams (SSO off)", '"teams"' in dumps(body))

        body = (await s.post(url, json=_click("conv-A", "reject", request_id))).json()
        check("second click refused (already approved)", "already approved" in dumps(body), dumps(body)[:120])

        # a second card (as if sent to another approver) gets replaced with a notice and closed
        r = await s.post(url, json=_activity("message", "conv-C", text="/approval Smoke: second approver"))
        await asyncio.sleep(0.5)
        card2 = [a for a in sent if a.get("attachments")][-1]
        request_id2 = card2["attachments"][0]["content"]["actions"][0]["data"]["requestId"]
        r = await s.put(
            f"{bot}{prefix}/cards",
            json={
                "conversationId": "conv-C",
                "activityId": "fake-1",
                "notice": {"decision": "approved", "by": "Smoke Tester", "requestText": "Smoke: approve it"},
                "requestId": request_id2,
            },
        )
        check("PUT /cards → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        check("card update reached connector", any(a.get("id") == "fake-1" for a in sent))
        body = (await s.post(url, json=_click("conv-C", "approve", request_id2))).json()
        check(
            "closed request refused with notice", "Already approved by Smoke Tester" in dumps(body), dumps(body)[:120]
        )
        r = await s.put(f"{bot}{prefix}/cards", json={"conversationId": "x", "activityId": "y"})
        check("PUT /cards without content → 422", r.status_code == 422)

    server.shutdown()
    print("\n" + ("ALL PASS" if failures == 0 else f"{failures} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bot", default="http://localhost:3979")
    p.add_argument("--prefix", default=Settings().route_prefix, help="route prefix of the bot under test")
    p.add_argument(
        "--connector-host",
        default="localhost",
        help="hostname the bot dials to reach this script's fake connector "
        "(host.docker.internal when the bot runs in Docker)",
    )
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.bot, a.prefix, a.connector_host)))
