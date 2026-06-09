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


# ── Stage 5 ──────────────────────────────────────────────────────────────────

class VlessCreateRequest(BaseModel):
    external_id: str
    expire_days: int
    remark: str | None = None  # #label in vless:// link; defaults to external_id


class VlessUserResponse(BaseModel):
    external_id: str
    config_link: str
    xui_client_uuid: str
    expire_timestamp: int      # Unix ms; 0 = never expires
    is_enabled: bool
    traffic_up_bytes: int
    traffic_down_bytes: int


class VlessUpdateRequest(BaseModel):
    extend_days: int | None = None
    is_enabled: bool | None = None
