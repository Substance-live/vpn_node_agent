import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from adapters.xui_adapter import XuiAdapter
from core.config import settings

# auto_error=False: FastAPI passes None when the header is absent instead of
# auto-raising 401. We raise 403 ourselves so both "missing" and "wrong" return
# the same status code (403 Forbidden, as specified in the ТЗ).
api_key_header = APIKeyHeader(name="X-Agent-Secret", auto_error=False)


async def verify_agent_secret(
    provided: str | None = Depends(api_key_header),
) -> None:
    """FastAPI dependency that enforces X-Agent-Secret on protected endpoints.

    Use as:
        @router.get("/...", dependencies=[Depends(verify_agent_secret)])
    or inject directly into a handler signature.

    Raises HTTP 403 when the header is absent OR the secret is incorrect.
    Uses secrets.compare_digest to prevent timing attacks on the secret value.
    """
    if not provided or not secrets.compare_digest(provided, settings.AGENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: missing or invalid agent secret",
        )


def get_xui(request: Request) -> XuiAdapter:
    """Return the XuiAdapter singleton created in lifespan."""
    return request.app.state.xui
