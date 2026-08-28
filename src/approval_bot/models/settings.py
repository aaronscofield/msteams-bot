"""Settings: everything the bot reads from the environment, with its env var name, type and default.

Sources, highest precedence first: real environment variables, then a `.env` file in the working
directory (dev convenience — the container gets plain env vars). Nothing here writes to `os.environ`.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from functools import cached_property

from microsoft_agents.activity import load_configuration_from_env
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

CERT_SETTING_KEY = "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CERTPFXFILE"


class Settings(BaseSettings):
    """Everything the bot reads from the environment (or ``.env``), validated once at startup.

    Attributes:
        host: Bind address for uvicorn.
        port: Bind port for uvicorn.
        log_level: Root logging level name.
        api_domain: First path segment of every route.
        api_subdomain: Second path segment of every route.
        api_version: Third path segment of every route.
        catalog_app_id: Teams org-catalog App ID of the bot (needed to install it for users).
        service_url: Teams regional Bot Connector base URL for proactive sends.
        api_key: Bearer key required on the approvals API; ``None`` leaves it open (dev).
        approvers_group_id: Entra group whose transitive members may approve; ``None`` disables the check.
        request_ttl_hours: How long a sent card stays answerable.
        webhook_url: Where decisions are POSTed; ``None`` disables notifications.
        sso_handler_name: Explicit SDK auth-handler name for Teams SSO.
        disable_sso: Force SSO off even if a handler is configured (dev).
        dev_commands: Enable the ``/approval <text>`` chat command (Playground / Web Chat).
        enable_docs: Serve Swagger UI / ReDoc / OpenAPI.
        cert_pfx_base64: The bot certificate as base64 PFX (containers); written to a temp file for the SDK.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",  # undeclared keys from .env (the SDK's CONNECTIONS__* etc.) are kept in model_extra
        frozen=True,
        populate_by_name=True,
    )

    host: str = "localhost"
    port: int = 3978
    log_level: str = "INFO"

    api_domain: str = Field(default="company", validation_alias="API_DOMAIN")
    api_subdomain: str = Field(default="bot", validation_alias="API_SUBDOMAIN")
    api_version: str = Field(default="v1", validation_alias="API_VERSION")

    catalog_app_id: str | None = Field(default=None, validation_alias="TEAMS_CATALOG_APP_ID")
    """Teams org-catalog App ID (admin center → Manage apps → app → "App ID"). Needed to install for users."""
    service_url: str = Field(default="https://smba.trafficmanager.net/amer/", validation_alias="TEAMS_SERVICE_URL")
    """Teams regional Bot Connector base URL used for proactive sends."""

    api_key: str | None = Field(default=None, validation_alias="APPROVALS_API_KEY")
    """Bearer key for POST …/approvals. Unset → open (dev only)."""
    approvers_group_id: str | None = Field(default=None, validation_alias="APPROVERS_GROUP_ID")
    """Entra group whose transitive members may approve. Unset → no group check."""
    request_ttl_hours: int = Field(default=168, ge=1, validation_alias="APPROVAL_TTL_HOURS")
    webhook_url: str | None = Field(default=None, validation_alias="APPROVAL_WEBHOOK_URL")

    sso_handler_name: str | None = Field(default=None, validation_alias="SSO_HANDLER")
    """Explicit SDK auth-handler name for Teams SSO; defaults to the first handler configured."""
    disable_sso: bool = Field(default=False, validation_alias="DISABLE_SSO")
    dev_commands: bool = Field(default=False, validation_alias="DEV_COMMANDS")
    """`/approval <text>` in chat posts a card into the current conversation (Playground / Web Chat)."""
    enable_docs: bool = Field(default=False, validation_alias="ENABLE_DOCS")
    """Serve Swagger UI at /docs, ReDoc at /redoc and the schema at /openapi.json. Off by default."""

    cert_pfx_base64: str | None = Field(default=None, validation_alias="CERT_PFX_BASE64", repr=False)
    """Containers get secrets as env vars: the PFX, base64-encoded. Overrides the CERTPFXFILE path setting."""

    @field_validator(
        "catalog_app_id",
        "api_key",
        "approvers_group_id",
        "webhook_url",
        "sso_handler_name",
        "cert_pfx_base64",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, v: str) -> str:
        return str(v).upper()

    @property
    def route_prefix(self) -> str:
        """The path every router is mounted under.

        Returns:
            str: ``/<api_domain>/<api_subdomain>/<api_version>``.
        """
        return f"/{self.api_domain}/{self.api_subdomain}/{self.api_version}".rstrip("/")

    @property
    def request_ttl_s(self) -> int:
        """``request_ttl_hours`` in seconds.

        Returns:
            int: Seconds.
        """
        return self.request_ttl_hours * 3600

    @cached_property
    def sdk(self) -> dict:
        """The Agents SDK configuration mapping.

        Merges ``CONNECTIONS__*`` / ``CONNECTIONSMAP__*`` / ``AGENTAPPLICATION__*`` keys from ``.env``
        (captured in ``model_extra``) with the real environment (which wins), materialising the
        certificate first if ``cert_pfx_base64`` is set.

        Returns:
            dict: As produced by ``load_configuration_from_env``.
        """
        raw = {k.upper(): v for k, v in (self.model_extra or {}).items() if isinstance(v, str)}
        raw.update(os.environ)
        if path := self._materialise_certificate():
            raw[CERT_SETTING_KEY] = path
        return load_configuration_from_env(raw)

    @cached_property
    def sso_handler(self) -> str | None:
        """Name of the SDK auth handler used for Teams SSO.

        Returns:
            str | None: ``sso_handler_name`` if set, else the first handler configured under
            ``AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS``; ``None`` if none or ``disable_sso``.
        """
        if self.disable_sso:
            return None
        handlers = (self.sdk.get("AGENTAPPLICATION", {}).get("USERAUTHORIZATION", {}).get("HANDLERS")) or {}
        return self.sso_handler_name or next(iter(handlers), None)

    def _materialise_certificate(self) -> str | None:
        """Write ``cert_pfx_base64`` to a private temp file the SDK can read.

        Returns:
            str | None: The file path, or ``None`` if no base64 certificate is configured.

        Raises:
            binascii.Error: If the value is not valid base64.
        """
        if not self.cert_pfx_base64:
            return None
        path = os.path.join(tempfile.mkdtemp(prefix="bot-cert-"), "bot.pfx")
        with open(path, "wb") as f:
            f.write(base64.b64decode(self.cert_pfx_base64))
        os.chmod(path, 0o400)
        log.info("certificate loaded from CERT_PFX_BASE64")
        return path
