"""FastAPI routers, one per inbound door. Paths here are relative; `server.create_app` mounts every
router under `Settings.route_prefix` (/<domain>/<subdomain>/<version>).

    messages   POST …/messages    Bot Framework traffic (Teams clicks, SSO exchange, events) — JWT-guarded
    approvals  POST …/approvals   internal API: send an approval card — API-key-guarded
    cards      PUT  …/cards       internal API: replace a posted card (e.g. "already approved by X") — API-key-guarded
    health     GET  …/health      liveness probe — open
"""

from . import approvals, cards, health, messages

__all__ = ["approvals", "cards", "health", "messages"]
