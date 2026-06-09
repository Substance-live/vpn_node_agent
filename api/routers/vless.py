"""VLESS client management endpoints (full CRUD)."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from adapters.xui_adapter import XuiAdapter, build_vless_link, generate_sub_id
from api.dependencies import get_xui, verify_agent_secret
from api.schemas import VlessCreateRequest, VlessUpdateRequest, VlessUserResponse
from core.config import settings

router = APIRouter(
    prefix="/api/v1/vless",
    tags=["vless"],
    dependencies=[Depends(verify_agent_secret)],
)

_INBOUND_ID = settings.XUI_VLESS_INBOUND_ID


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
) -> VlessUserResponse | JSONResponse:
    inbound = await xui.get_inbound(_INBOUND_ID)
    existing = xui.find_client(inbound, req.external_id)
    if existing:
        # Idempotent: return existing client data with 409 so caller knows it pre-existed
        body = await _build_response(xui, inbound, existing, req.remark)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=body.model_dump(),
        )

    client_data = {
        "id": str(uuid.uuid4()),
        "flow": "xtls-rprx-vision",
        "email": req.external_id,
        "limitIp": 0,
        "totalGB": 0,
        "expiryTime": int((time.time() + req.expire_days * 86400) * 1000),
        "enable": True,
        "tgId": "",
        "subId": generate_sub_id(),
        "reset": 0,
    }
    await xui.add_client(_INBOUND_ID, client_data)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VLESS client not found",
        )
    return await _build_response(xui, inbound, client, external_id)


@router.patch(
    "/users/{external_id}",
    response_model=VlessUserResponse,
    summary="Update VLESS user (extend expiry and/or toggle enabled)",
)
async def update_user(
    external_id: str,
    req: VlessUpdateRequest,
    xui: XuiAdapter = Depends(get_xui),
) -> VlessUserResponse:
    inbound = await xui.get_inbound(_INBOUND_ID)
    client = xui.find_client(inbound, external_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VLESS client not found",
        )

    client = dict(client)  # copy — never mutate the inbound dict in-place

    if req.extend_days is not None:
        now_ms = int(time.time() * 1000)
        old_expiry = client.get("expiryTime") or 0
        # Extend from current expiry if subscription is still active;
        # from now if it has already expired or was set to "never" (0).
        base = old_expiry if old_expiry > now_ms else now_ms
        client["expiryTime"] = base + req.extend_days * 86400 * 1000

    if req.is_enabled is not None:
        client["enable"] = req.is_enabled

    await xui.update_client(_INBOUND_ID, client["id"], client)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VLESS client not found",
        )
    await xui.delete_client(_INBOUND_ID, client["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
