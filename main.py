import time

import uvicorn
from fastapi import Depends, FastAPI

from api.dependencies import verify_agent_secret
from api.routers import health
from core.config import settings
from core.logging import configure_logging

# Configure logging before anything else
configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

app = FastAPI(
    title="VPN Node Agent",
    version="0.1.0",
    description=(
        "Lightweight stateless service that wraps 3x-ui (VLESS) and mtg (MTProto) "
        "and exposes a unified REST API for the Orchestrator."
    ),
)

# Record the startup moment for uptime calculation
app.state.start_monotonic = time.monotonic()

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)          # Stage 1 — GET /api/v1/health (public)
# app.include_router(mtproto.router)       # Stage 3 — GET /api/v1/mtproto/info
# app.include_router(vless.router)         # Stage 5 — CRUD /api/v1/vless/users


# ── TEMP: Stage 2 verification endpoint — remove when Stage 3 starts ─────────
@app.get(
    "/api/v1/ping",
    tags=["debug"],
    dependencies=[Depends(verify_agent_secret)],
    summary="[TEMP] Auth check — remove in Stage 3",
)
async def ping() -> dict:
    return {"pong": True}
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
    )
