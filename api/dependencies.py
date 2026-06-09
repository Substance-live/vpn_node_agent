import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from adapters.xui_adapter import XuiAdapter
from core.config import settings

# Declares the X-Agent-Secret header as an API-key security scheme.
# auto_error=True means FastAPI returns 403 automatically when the header is absent.
api_key_header = APIKeyHeader(name="X-Agent-Secret", auto_error=True)


async def verify_agent_secret(provided: str = Depends(api_key_header)) -> None:
    """FastAPI dependency that enforces X-Agent-Secret on protected endpoints.

    Use as:
        @router.get("/...", dependencies=[Depends(verify_agent_secret)])
    or inject directly into a handler signature.

    Raises HTTP 403 when the secret is absent or incorrect.
    Uses secrets.compare_digest to prevent timing attacks.
    """
    if not secrets.compare_digest(provided, settings.AGENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid agent secret",
        )


def get_xui(request: Request) -> XuiAdapter:
    """Return the XuiAdapter singleton created in lifespan."""
    return request.app.state.xui
