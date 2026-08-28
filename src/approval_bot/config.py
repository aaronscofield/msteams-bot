"""Startup helpers around `models.Settings`."""

from __future__ import annotations

import logging

from .models import Settings

log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com"
BOT_CONNECTOR = "https://api.botframework.com"


def load_settings() -> Settings:
    """Load settings from the environment and the project ``.env``.

    Returns:
        Settings: The validated configuration.

    Raises:
        pydantic.ValidationError: If a value fails validation (e.g. non-integer ``APPROVAL_TTL_HOURS``).
    """
    return Settings()


def log_settings(s: Settings) -> None:
    """Log one line per security-relevant setting so a startup log shows which guards are active.

    Args:
        s: The loaded settings.
    """
    if not s.api_key:
        log.warning("APPROVALS_API_KEY is not set — POST …/approvals accepts unauthenticated requests")
    if not s.approvers_group_id:
        log.warning("APPROVERS_GROUP_ID is not set — any addressed user may approve")
    if s.sso_handler:
        log.info("Teams SSO enabled via auth handler %r", s.sso_handler)
    else:
        log.warning("no SSO auth handler configured — approver identity is Teams-asserted, not Entra-verified")
    log.info("routes mounted under %s", s.route_prefix)
    if s.enable_docs:
        log.info("API docs enabled at /docs and /redoc")
    if s.dev_commands:
        log.warning("DEV_COMMANDS is on — '/approval <text>' in chat sends a card to the current conversation")
