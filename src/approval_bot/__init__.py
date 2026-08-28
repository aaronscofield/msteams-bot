"""Company Teams approval bot.

Layers (each module depends only on the ones above it):

    models/    — pydantic models: Settings · ApprovalRequest · Decision/Approver · PendingRequest
    config     — loads the environment into Settings; certificate materialisation; startup log
    runtime    — Microsoft 365 Agents SDK wiring (connection manager, adapter, AgentApplication, app tokens)
    clients    — thin async clients for Microsoft Graph and the Bot Connector
    store      — pending-request store (in-memory)
    cards      — Adaptive Card payloads
    guards     — the four click checks (binding/replay, group, SSO identity) and `Refused`
    service    — ApprovalService: create a request, decide a request
    handlers   — registers Action.Execute routes and the dev `/approval` command on the agent
    dependencies/ — FastAPI dependencies: get_runtime · get_service · get_logger ·
                    require_bot_framework_jwt · require_api_key
    routers/   — FastAPI routers: messages (Bot Framework) · approvals (trigger) · cards (update) · health
    server     — FastAPI app factory + entry point (uvicorn)
"""

__version__ = "1.5.0"
