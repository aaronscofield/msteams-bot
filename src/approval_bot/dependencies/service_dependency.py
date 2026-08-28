from __future__ import annotations

from fastapi import Request

from ..service import ApprovalService


def get_service(request: Request) -> ApprovalService:
    """FastAPI dependency: the ApprovalService (and its pending-request store) for this app instance.

    Args:
        request: The current request; the service is read from ``request.app.state``.

    Returns:
        ApprovalService: The service created in ``server.create_app``.
    """
    return request.app.state.service
