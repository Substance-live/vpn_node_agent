from pydantic import BaseModel


# ── Stage 1 ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    vless_backend: str
    mtproto_backend: str
    uptime_seconds: int


# ── Stage 3 ──────────────────────────────────────────────────────────────────

class MtprotoInfoResponse(BaseModel):
    server: str
    port: int
    secret: str
    tg_link: str


# ── Stage 5 ── VlessCreateRequest, VlessUserResponse, VlessUpdateRequest
