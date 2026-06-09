import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from adapters.mtg_adapter import MtgConfigError
from adapters.xui_adapter import XuiAdapter, XuiError, XuiUnavailableError
from api.routers import health, mtproto
from core.config import settings
from core.logging import configure_logging, get_logger

# Configure logging before anything else
configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create long-lived resources on startup; clean them up on shutdown."""
    app.state.start_monotonic = time.monotonic()

    # XuiAdapter holds an httpx.AsyncClient with cookie-jar; login is lazy.
    app.state.xui = XuiAdapter(
        base_url=settings.XUI_BASE_URL,
        username=settings.XUI_USERNAME,
        password=settings.XUI_PASSWORD,
        inbound_id=settings.XUI_VLESS_INBOUND_ID,
    )
    logger.info("xui_adapter_created", base_url=settings.XUI_BASE_URL)

    yield  # application runs here

    await app.state.xui.close()
    logger.info("xui_adapter_closed")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="VPN Node Agent",
    version="0.1.0",
    description=(
        "Lightweight stateless service that wraps 3x-ui (VLESS) and mtg (MTProto) "
        "and exposes a unified REST API for the Orchestrator."
    ),
    lifespan=lifespan,
)


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(MtgConfigError)
async def _mtg_config_error_handler(request, exc: MtgConfigError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "mtg_config_error",
            "message": "Cannot read MTProto config",
            "details": str(exc),
        },
    )


@app.exception_handler(XuiUnavailableError)
async def _xui_unavailable_handler(request, exc: XuiUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "xui_unavailable",
            "message": "Cannot connect to 3x-ui",
            "details": str(exc),
        },
    )


@app.exception_handler(XuiError)
async def _xui_error_handler(request, exc: XuiError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "xui_error",
            "message": "3x-ui API error",
            "details": str(exc),
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)     # Stage 1 — GET /api/v1/health (public)
app.include_router(mtproto.router)    # Stage 3 — GET /api/v1/mtproto/info (auth required)
# app.include_router(vless.router)    # Stage 5 — CRUD /api/v1/vless/users


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
    )
