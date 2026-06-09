from pydantic import BaseModel


# ── Stage 1 ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    vless_backend: str
    mtproto_backend: str
    uptime_seconds: int


# ── Stage 3 ── MtprotoInfoResponse (populated in Stage 3)
# ── Stage 5 ── VlessCreateRequest, VlessUserResponse, VlessUpdateRequest (Stage 5)
