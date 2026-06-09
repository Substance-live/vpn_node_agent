"""VLESS client management endpoints (full CRUD)."""

import time
import uuid

from fastapi import APIRouter, Depends, Response, status

from adapters.xui_adapter import XuiAdapter, build_vless_link, generate_sub_id
from api.dependencies import get_xui, verify_agent_secret
from api.errors import XuiClientAlreadyExistsError, XuiClientNotFoundError
from api.schemas import VlessCreateRequest, VlessUpdateRequest, VlessUserResponse
from core.config import settings
from core.logging import get_logger

router = APIRouter(
    prefix="/api/v1/vless",
    tags=["vless"],
    dependencies=[Depends(verify_agent_secret)],
)

logger = get_logger(__name__)

_INBOUND_ID = settings.XUI_VLESS_INBOUND_ID

# 3x-ui treats any past timestamp as expired; 1 ms past epoch is safely in the past.
_EXPIRED_MS = 1


def _expiry_ms(expire_days: int) -> int:
    """Map expire_days to a 3x-ui expiryTime (Unix ms).

    N > 0  -> now + N days
    N == 0 -> 0 (never expires)
    N < 0  -> 1 (already expired — panel shows "expired" immediately)
    """
    if expire_days > 0:
        return int((time.time() + expire_days * 86400) * 1000)
    if expire_days == 0:
        return 0
    return _EXPIRED_MS


async def _build_response(
    xui: XuiAdapter,
    inbound: dict,
    client: dict,
    remark: str | None,
) -> VlessUserResponse:
    """Assemble a VlessUserResponse from an already-fetched inbound + client dict."""
    traffic = await xui.get_client_traffic(client["email"]) or {}
    return VlessUserResponse(
        external_id=client["email"],
        config_link=build_vless_link(
            inbound, client["id"], remark or client["email"]
        ),
        xui_client_uuid=client["id"],
        expire_timestamp=client.get("expiryTime", 0),
        is_enabled=client.get("enable", True),
        traffic_up_bytes=traffic.get("up", 0),
        traffic_down_bytes=traffic.get("down", 0),
    )


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=VlessUserResponse,
    summary="Create VLESS user (idempotent — returns 409 if already exists)",
)
async def create_user(
    req: VlessCreateRequest,
    xui: XuiAdapter = Depends(get_xui),
) -> VlessUserResponse:
    inbound = await xui.get_inbound(_INBOUND_ID)
    existing = xui.find_client(inbound, req.external_id)
    if existing:
        # Idempotent: raise 409 with full existing-client payload attached
        logger.info("vless_user_exists", external_id=req.external_id)
        body = await _build_response(xui, inbound, existing, req.remark)
        raise XuiClientAlreadyExistsError(existing=body.model_dump())

    client_data = {
        "id": str(uuid.uuid4()),
        "flow": "xtls-rprx-vision",
        "email": req.external_id,
        "limitIp": 0,
        "totalGB": 0,
        "expiryTime": _expiry_ms(req.expire_days),
        "enable": True,
        "tgId": "",
        "subId": generate_sub_id(),
        "reset": 0,
    }
    await xui.add_client(_INBOUND_ID, client_data)
    logger.info("vless_user_created", external_id=req.external_id, expire_days=req.expire_days)
    # Traffic for a brand-new client is always 0/0 (no stats record yet)
    return await _build_response(xui, inbound, client_data, req.remark)


@router.get(
    "/users/{external_id}",
    response_model=VlessUserResponse,
    summary="Get VLESS user info and traffic stats",
)
async def get_user(
    external_id: str,
    xui: XuiAdapter = Depends(get_xui),
) -> VlessUserResponse:
    inbound = await xui.get_inbound(_INBOUND_ID)
    client = xui.find_client(inbound, external_id)
    if client is None:
        raise XuiClientNotFoundError(f"No VLESS client with external_id={external_id!r}")
    return await _build_response(xui, inbound, client, external_id)


@router.patch(
    "/users/{external_id}",
    response_model=VlessUserResponse,
    summary="Update VLESS user (set expiry and/or toggle enabled)",
)
async def update_user(
    external_id: str,
    req: VlessUpdateRequest,
    xui: XuiAdapter = Depends(get_xui),
) -> VlessUserResponse:
    inbound = await xui.get_inbound(_INBOUND_ID)
    client = xui.find_client(inbound, external_id)
    if client is None:
        raise XuiClientNotFoundError(f"No VLESS client with external_id={external_id!r}")

    client = dict(client)  # copy — never mutate the inbound dict in-place

    if req.expire_days is not None:
        client["expiryTime"] = _expiry_ms(req.expire_days)

    if req.is_enabled is not None:
        client["enable"] = req.is_enabled

    await xui.update_client(_INBOUND_ID, client["id"], client)
    logger.info(
        "vless_user_updated",
        external_id=external_id,
        expire_days=req.expire_days,
        is_enabled=req.is_enabled,
    )
    return await _build_response(xui, inbound, client, external_id)


@router.delete(
    "/users/{external_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete VLESS user",
)
async def delete_user(
    external_id: str,
    xui: XuiAdapter = Depends(get_xui),
) -> Response:
    inbound = await xui.get_inbound(_INBOUND_ID)
    client = xui.find_client(inbound, external_id)
    if client is None:
        raise XuiClientNotFoundError(f"No VLESS client with external_id={external_id!r}")
    await xui.delete_client(_INBOUND_ID, client["id"])
    logger.info("vless_user_deleted", external_id=external_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
