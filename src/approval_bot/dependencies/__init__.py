"""FastAPI dependencies.

runtime_dependency       get_runtime  — the SDK wiring for this app instance (from app.state)
service_dependency       get_service  — the ApprovalService for this app instance (from app.state)
bot_framework_security   require_bot_framework_jwt — Guard 0: Bot Framework JWT on …/messages
api_key_security         require_api_key           — APPROVALS_API_KEY on …/approvals
"""

from .api_key_security import approvals_api_key, require_api_key
from .bot_framework_security import bot_framework_jwt, require_bot_framework_jwt
from .logger_dependency import RequestLogger, configure_logging, current_request_id, get_logger
from .runtime_dependency import get_runtime
from .service_dependency import get_service

__all__ = [
    "RequestLogger",
    "approvals_api_key",
    "bot_framework_jwt",
    "configure_logging",
    "current_request_id",
    "get_logger",
    "get_runtime",
    "get_service",
    "require_api_key",
    "require_bot_framework_jwt",
]
