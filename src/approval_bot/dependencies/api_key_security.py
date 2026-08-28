"""The internal API's guard as a FastAPI security dependency: `Authorization: Bearer <APPROVALS_API_KEY>`.

When no key is configured the dependency is a no-op (dev). Constant-time comparison.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..runtime import Runtime
from .runtime_dependency import get_runtime

approvals_api_key = HTTPBearer(
    scheme_name="ApprovalsApiKey",
    description="The value of APPROVALS_API_KEY. Required only when the bot has one configured.",
    auto_error=False,
)


async def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(approvals_api_key)],
    rt: Annotated[Runtime, Depends(get_runtime)],
) -> None:
    """FastAPI security dependency: require the configured API key on the route.

    Args:
        credentials: The parsed ``Authorization: Bearer …`` header, or ``None`` if absent.
        rt: Injected runtime, for ``settings.api_key``.

    Raises:
        HTTPException: ``401 unauthorized`` when a key is configured and the presented bearer token
            does not match it (compared in constant time). Never raised when no key is configured.
    """
    key = rt.settings.api_key
    if not key:
        return
    presented = credentials.credentials if credentials else ""
    if not hmac.compare_digest(presented, key):
        raise HTTPException(status_code=401, detail="unauthorized")
