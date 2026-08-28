"""GET …/health — liveness probe used by the container HEALTHCHECK and the platform."""

from fastapi import APIRouter

from .. import __version__
from ..models import Health

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=Health, summary="Liveness probe")
async def health() -> Health:
    """Report that the process is up.

    Returns:
        Health: ``{"status": "ok", "version": <package version>}``.
    """
    return Health(version=__version__)
