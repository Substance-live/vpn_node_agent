import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from adapters.xui_adapter import XuiAdapter
from api.errors import AgentError, XuiClientAlreadyExistsError
from api.routers import health, mtproto, vless
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

# Maps common HTTP status codes to stable machine-readable error slugs.
_HTTP_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
}


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap FastAPI/Starlette HTTP errors (auth 403, route 404, …) in unified envelope."""
    code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": code, "message": str(exc.detail), "details": ""},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Wrap Pydantic validation failures (422) in unified envelope with structured details."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(AgentError)
async def _agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    """Convert any AgentError subclass to a uniform JSON error envelope."""
    if exc.status_code >= 500:
        logger.warning(exc.error, details=str(exc), path=str(request.url.path))
    content: dict = {
        "error": exc.error,
        "message": exc.message,
        "details": str(exc),
    }
    # For idempotent create (409): include the existing client payload so the
    # caller doesn't need an extra GET to learn the current state.
    if isinstance(exc, XuiClientAlreadyExistsError) and exc.existing is not None:
        content["existing"] = exc.existing
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors — logs full traceback, returns 500."""
    logger.error("unhandled_exception", path=str(request.url.path), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal server error",
            "details": "",
        },
    )


# ── Access-log middleware ──────────────────────────────────────────────────────

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """Log method, path, status and duration for every request.

    Request body is intentionally NOT logged — it may contain secrets.
    For 403 responses the client IP is included (unauthorized access attempt).
    """
    start = time.monotonic()
    response = await call_next(request)
    fields: dict = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round((time.monotonic() - start) * 1000, 1),
        "client_ip": request.client.host if request.client else None,
    }
    logger.info("request", **fields)
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)     # Stage 1 — GET /api/v1/health (public)
app.include_router(mtproto.router)    # Stage 3 — GET /api/v1/mtproto/info (auth required)
app.include_router(vless.router)      # Stage 5 — CRUD /api/v1/vless/users


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        access_log=False,
    )
