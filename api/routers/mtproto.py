from fastapi import APIRouter, Depends

from adapters.mtg_adapter import mtg_adapter
from api.dependencies import verify_agent_secret
from api.schemas import MtprotoInfoResponse

# Authorization applied at router level — every endpoint here requires X-Agent-Secret.
router = APIRouter(
    prefix="/api/v1/mtproto",
    tags=["mtproto"],
    dependencies=[Depends(verify_agent_secret)],
)


@router.get("/info", response_model=MtprotoInfoResponse, summary="Get MTProto proxy info")
async def mtproto_info() -> MtprotoInfoResponse:
    """Return the MTProto proxy connection details for this server.

    Reads `/etc/mtg/config.toml`, extracts the shared secret and builds the
    `tg://proxy?...` link. Since mtg v2 has no per-user API, this is a
    single shared link for the entire server.

    Returns HTTP 502 if the config file is absent or malformed (handled globally
    in main.py via the MtgConfigError exception handler).
    """
    return MtprotoInfoResponse(**mtg_adapter.get_proxy_info())
