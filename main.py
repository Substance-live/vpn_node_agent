import uvicorn
from fastapi import FastAPI

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

# Routers are registered here as each stage is completed:
#   Stage 1 — health router
#   Stage 3 — mtproto router
#   Stage 5 — vless router


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
    )
