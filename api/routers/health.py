import time

from fastapi import APIRouter, Request

from adapters.mtg_adapter import mtg_adapter
from api.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service liveness check")
async def health(request: Request) -> HealthResponse:
    """
    Returns service status and uptime.
    No authorization required.

    Backend status values: "ok" | "degraded" | "offline" | "unknown".
    - `mtproto_backend`: real check against mtg config file (Stage 3+).
    - `vless_backend`: real check against 3x-ui (Stage 5+).
    """
    uptime = time.monotonic() - request.app.state.start_monotonic
    vless_ok = await request.app.state.xui.ping()
    return HealthResponse(
        status="ok",
        vless_backend="ok" if vless_ok else "offline",
        mtproto_backend=mtg_adapter.check_health(),
        uptime_seconds=int(uptime),
    )
