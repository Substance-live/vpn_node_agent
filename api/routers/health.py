import time

from fastapi import APIRouter, Request

from api.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service liveness check")
async def health(request: Request) -> HealthResponse:
    """
    Returns service status and uptime.
    No authorization required.

    `vless_backend` and `mtproto_backend` are `"unknown"` until Stages 3 and 5
    wire up real backend checks.
    """
    uptime = time.monotonic() - request.app.state.start_monotonic
    return HealthResponse(
        status="ok",
        vless_backend="unknown",
        mtproto_backend="unknown",
        uptime_seconds=int(uptime),
    )
