from fastapi import APIRouter

from .health import router as health_router
from .mtproto import router as mtproto_router
from .vless import router as vless_router

main_router = APIRouter()
main_router.include_router(health_router, tags=["health"])
main_router.include_router(mtproto_router, tags=["mtproto"])
main_router.include_router(vless_router, tags=["vless"])
