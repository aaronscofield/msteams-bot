"""Thin async clients (httpx) for the two Microsoft APIs the bot calls itself.

Both take an already-acquired app-only token; `Runtime.app_token` provides it. Kept deliberately small
and explicit — these are the only outbound HTTP calls outside the SDK.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from .config import GRAPH


class GraphError(RuntimeError):
    """Microsoft Graph answered with an error status; the message carries method, path, status, body."""


class ConnectorError(RuntimeError):
    """The Bot Connector answered with an error status; the message carries status and body."""


class GraphClient:
    """Microsoft Graph, app-only.

    Permissions used: ``TeamsAppInstallation.ReadWriteSelfForUser.All`` (install / chat) and
    ``GroupMember.Read.All`` (membership).

    Attributes:
        _c: The shared httpx client.
        _h: Authorization header.
    """

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        """Bind the client to a session and a token.

        Args:
            client: An open ``httpx.AsyncClient``.
            token: App-only bearer token for ``https://graph.microsoft.com``.
        """
        self._c = client
        self._h = {"Authorization": f"Bearer {token}"}

    async def _call(self, method: str, path: str, **kw) -> dict | None:
        """Issue one Graph v1.0 request.

        Args:
            method: HTTP method.
            path: Path under ``/v1.0``, including any query string.
            **kw: Passed to ``httpx`` (``json``, extra ``headers``, …).

        Returns:
            dict | None: The JSON body, or ``None`` for an empty body.

        Raises:
            GraphError: On any 4xx/5xx response.
        """
        headers = {**self._h, **kw.pop("headers", {})}
        r = await self._c.request(method, f"{GRAPH}/v1.0{path}", headers=headers, **kw)
        if r.is_error:
            raise GraphError(f"Graph {method} {path} → {r.status_code}: {r.text}")
        return r.json() if r.content else None

    async def installed_app(self, upn: str, catalog_app_id: str) -> dict | None:
        """Find the bot's installation for a user.

        Under the *Self* permission Graph only matches installations by catalog id (``teamsApp/id``),
        not by manifest id.

        Args:
            upn: The user's principal name.
            catalog_app_id: The bot's org-catalog App ID.

        Returns:
            dict | None: The ``teamsAppInstallation`` (with ``teamsApp`` expanded), or ``None`` if the
            bot is not installed for the user.

        Raises:
            GraphError: If Graph refuses the query.
        """
        q = f"/users/{quote(upn)}/teamwork/installedApps?$expand=teamsApp&$filter=teamsApp/id eq '{catalog_app_id}'"
        items = (await self._call("GET", q))["value"]
        return items[0] if items else None

    async def install_app(self, upn: str, catalog_app_id: str) -> None:
        """Install the bot for a user from the org catalog.

        Args:
            upn: The user's principal name.
            catalog_app_id: The bot's org-catalog App ID.

        Raises:
            GraphError: If Graph refuses — e.g. ``403 Caller is not authorized`` when the catalog entry's
                ``webApplicationInfo.id`` does not match the calling app, or ``409`` if already installed.
        """
        await self._call(
            "POST",
            f"/users/{quote(upn)}/teamwork/installedApps",
            json={"teamsApp@odata.bind": f"{GRAPH}/v1.0/appCatalogs/teamsApps/{catalog_app_id}"},
        )

    async def personal_chat(self, upn: str, installation_id: str) -> dict:
        """Get the 1:1 chat between the bot and a user.

        Args:
            upn: The user's principal name.
            installation_id: The installation's id from ``installed_app``.

        Returns:
            dict: The ``chat`` resource; ``id`` is of the form ``19:<user oid>_<bot app id>@unq.gbl.spaces``.

        Raises:
            GraphError: If Graph refuses the lookup.
        """
        return await self._call("GET", f"/users/{quote(upn)}/teamwork/installedApps/{installation_id}/chat")

    async def is_transitive_member(self, group_id: str, oid: str) -> bool:
        """Check (transitive) membership of a user in a group.

        Args:
            group_id: The group's object id.
            oid: The user's object id.

        Returns:
            bool: True if the user is a direct or nested member.

        Raises:
            GraphError: If Graph refuses the query (missing ``GroupMember.Read.All``, unknown group,
                or a malformed object id).
        """
        res = await self._call(
            "GET",
            f"/groups/{group_id}/transitiveMembers?$count=true&$select=id&$filter=id eq '{oid}'",
            headers={"ConsistencyLevel": "eventual"},
        )
        return bool((res or {}).get("value"))


class ConnectorClient:
    """Bot Connector (Teams regional endpoint), used only for proactive sends.

    Replies to clicks go through the SDK, not this class.

    Attributes:
        _c: The shared httpx client.
        _h: Authorization header.
        _base: Service URL with a trailing slash.
        _bot_app_id: The bot's app id (``28:<id>`` on the wire).
        _tenant_id: The tenant to create conversations in.
    """

    def __init__(
        self, client: httpx.AsyncClient, token: str, service_url: str, bot_app_id: str, tenant_id: str
    ) -> None:
        """Bind the client to a session, token, and region.

        Args:
            client: An open ``httpx.AsyncClient``.
            token: App-only bearer token for ``https://api.botframework.com``.
            service_url: Regional Bot Connector base, e.g. ``https://smba.trafficmanager.net/amer/``.
            bot_app_id: The bot's Entra app id.
            tenant_id: The Entra tenant id.
        """
        self._c = client
        self._h = {"Authorization": f"Bearer {token}"}
        self._base = service_url.rstrip("/") + "/"
        self._bot_app_id = bot_app_id
        self._tenant_id = tenant_id

    async def create_personal_conversation(self, user_oid: str) -> str | None:
        """Create or resolve the Bot Framework 1:1 conversation with a user.

        Teams delivers clicks with this id (``a:…``), not the Graph chat id, so it is the one requests
        are bound to.

        Args:
            user_oid: The user's Entra object id (accepted by Teams as a member id).

        Returns:
            str | None: The conversation id, or ``None`` if the Connector refused (the caller falls
            back to the Graph chat id and disables the conversation check).
        """
        r = await self._c.post(
            f"{self._base}v3/conversations",
            headers=self._h,
            json={
                "bot": {"id": f"28:{self._bot_app_id}"},
                "members": [{"id": user_oid}],
                "isGroup": False,
                "tenantId": self._tenant_id,
                "channelData": {"tenant": {"id": self._tenant_id}},
            },
        )
        return None if r.is_error else r.json().get("id")

    async def send_card(self, conversation_id: str, card: dict, summary: str) -> str | None:
        """Post an Adaptive Card into a conversation.

        Args:
            conversation_id: Bot Framework conversation id (or a Graph chat id as a fallback).
            card: Adaptive Card JSON.
            summary: Plain-text summary shown in notifications.

        Returns:
            str | None: The activity id of the posted message, if the Connector returned one.

        Raises:
            ConnectorError: On any 4xx/5xx response.
        """
        r = await self._c.post(
            f"{self._base}v3/conversations/{quote(conversation_id, safe='')}/activities",
            headers=self._h,
            json={
                "type": "message",
                "summary": summary,
                "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
            },
        )
        if r.is_error:
            raise ConnectorError(f"Bot Connector send → {r.status_code}: {r.text}")
        return r.json().get("id")

    async def update_card(self, conversation_id: str, activity_id: str, card: dict, summary: str) -> str | None:
        """Replace the content of a card the bot posted earlier.

        Args:
            conversation_id: Bot Framework conversation id the card lives in.
            activity_id: The card message's activity id (as returned by ``send_card``).
            card: The new Adaptive Card JSON.
            summary: Plain-text summary for notifications.

        Returns:
            str | None: The activity id, if the Connector returned one.

        Raises:
            ConnectorError: On any 4xx/5xx response (e.g. ``404`` unknown activity, ``403`` not our message).
        """
        r = await self._c.put(
            f"{self._base}v3/conversations/{quote(conversation_id, safe='')}/activities/{quote(activity_id, safe='')}",
            headers=self._h,
            json={
                "type": "message",
                "id": activity_id,
                "summary": summary,
                "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
            },
        )
        if r.is_error:
            raise ConnectorError(f"Bot Connector update → {r.status_code}: {r.text}")
        return r.json().get("id") if r.content else activity_id


def oid_from_chat_id(chat_id: str, bot_app_id: str) -> str | None:
    """Extract the user's Entra object id from a Graph 1:1 bot-chat id.

    Args:
        chat_id: Graph chat id of the form ``19:<oid>_<bot app id>@unq.gbl.spaces``.
        bot_app_id: The bot's app id, used to confirm the id has the expected shape.

    Returns:
        str | None: The object id, or ``None`` if the id is not a 1:1 chat with this bot.
    """
    head = chat_id.split(":", 1)[-1].split("@", 1)[0]
    user, _, bot = head.partition("_")
    return user if bot.lower() == bot_app_id.lower() and len(user) == 36 else None
