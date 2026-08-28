from __future__ import annotations

from fastapi import Request

from ..runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    """FastAPI dependency: the SDK runtime for this app instance.

    Args:
        request: The current request; the runtime is read from ``request.app.state``.

    Returns:
        Runtime: Settings, connection manager, adapter, agent, and the bot's identity.
    """
    return request.app.state.runtime
