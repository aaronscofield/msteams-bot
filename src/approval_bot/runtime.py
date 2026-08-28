"""Microsoft 365 Agents SDK wiring.

One `Runtime` holds the SDK objects every other layer needs: the connection manager (mints app-only
tokens with the bot's certificate), the channel adapter, and the `AgentApplication` routes are
registered on. It also knows the bot's own identity (app id, tenant id) as configured in the SDK.
"""

from __future__ import annotations

from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage, TurnState
from microsoft_agents.hosting.core.authorization import AgentAuthConfiguration
from microsoft_agents.hosting.fastapi import CloudAdapter
from pydantic import BaseModel, ConfigDict

from .config import Settings


class Runtime(BaseModel):
    """The SDK objects and identity the rest of the bot works with.

    Attributes:
        settings: The loaded configuration.
        connection_manager: Acquires app-only tokens for the bot (certificate via MSAL).
        adapter: Channel adapter that turns HTTP requests into SDK turns and sends replies.
        agent: The AgentApplication the click handlers are registered on.
        auth_config: The default connection's configuration (client id, tenant, …).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    settings: Settings
    connection_manager: MsalConnectionManager
    adapter: CloudAdapter
    agent: AgentApplication
    auth_config: AgentAuthConfiguration

    @property
    def bot_app_id(self) -> str:
        """The bot's Entra application (client) id."""
        return self.auth_config.CLIENT_ID

    @property
    def tenant_id(self) -> str:
        """The Entra tenant the bot belongs to."""
        return self.auth_config.TENANT_ID

    async def app_token(self, resource: str) -> str:
        """Acquire an app-only access token for a Microsoft resource.

        Args:
            resource: Resource base URL, e.g. ``https://graph.microsoft.com``; the scope requested is
                ``<resource>/.default``.

        Returns:
            str: A bearer token (cached and refreshed by MSAL).

        Raises:
            ValueError: If MSAL cannot acquire a token (bad certificate, tenant, or consent).
        """
        provider = self.connection_manager.get_default_connection()
        return await provider.get_access_token(resource, [f"{resource}/.default"])


def build_runtime(settings: Settings) -> Runtime:
    """Construct the SDK objects from settings.

    Args:
        settings: The loaded configuration; ``settings.sdk`` carries the CONNECTIONS__* config.

    Returns:
        Runtime: Ready for ``server.create_app``.

    Raises:
        ValueError: If the SDK connection configuration is incomplete (no ``SERVICE_CONNECTION``,
            or certificate auth without a PFX path).
    """
    connection_manager = MsalConnectionManager(**settings.sdk)
    adapter = CloudAdapter(connection_manager=connection_manager)
    agent = AgentApplication[TurnState](
        storage=MemoryStorage(), adapter=adapter, connection_manager=connection_manager, **settings.sdk
    )
    return Runtime(
        settings=settings,
        connection_manager=connection_manager,
        adapter=adapter,
        agent=agent,
        auth_config=connection_manager.get_default_connection_configuration(),
    )
