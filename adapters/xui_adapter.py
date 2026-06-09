"""HTTP client adapter for 3x-ui panel API (VLESS client management).

3x-ui uses cookie-based session auth.  This adapter performs a lazy login on the
first request and automatically re-authenticates on 401/403 or HTML login-page
redirect (one retry per request).

URL note: XUI_BASE_URL must include the secret base path if the panel is configured
with one (e.g. http://127.0.0.1:13371/fast_speed). We build full URLs manually
instead of using httpx's base_url because a leading "/" in a path would strip
the base-path segment.
"""

import json
import secrets
import string
from urllib.parse import quote, urlencode

import httpx


# ── Exceptions ────────────────────────────────────────────────────────────────

class XuiError(Exception):
    """Raised when 3x-ui returns an error response or success=false."""


class XuiUnavailableError(XuiError):
    """Raised when the 3x-ui panel cannot be reached at all."""


# ── Module-level helpers ──────────────────────────────────────────────────────

def generate_sub_id(length: int = 16) -> str:
    """Return a random lowercase alphanumeric subId for new 3x-ui clients."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_vless_link(
    inbound: dict,
    client_uuid: str,
    remark: str,
    flow: str = "xtls-rprx-vision",
) -> str:
    """Build a vless:// URI from inbound Reality stream settings.

    Expects `inbound["streamSettings"]` to already be a parsed dict
    (as returned by XuiAdapter.get_inbound).

    Reality parameter mapping (from 05_XUI_API_SAMPLES.md):
        type   ← streamSettings.network
        security ← streamSettings.security
        pbk    ← realitySettings.settings.publicKey
        fp     ← realitySettings.settings.fingerprint
        sni    ← realitySettings.serverNames[0]
        sid    ← realitySettings.shortIds[0]
        spx    ← realitySettings.settings.spiderX  (URL-encoded)
        flow   ← client.flow (xtls-rprx-vision for Reality+TCP)

    Example output:
        vless://UUID@138.124.79.175:443?type=tcp&security=reality&pbk=F6y-...
        &fp=firefox&sni=ign.com&sid=d9e35618ee&spx=%2F&flow=xtls-rprx-vision#remark
    """
    ss = inbound["streamSettings"]          # already a dict
    rs = ss["realitySettings"]
    reality_cfg = rs["settings"]

    host = inbound.get("listen") or ""
    port = inbound["port"]

    params = {
        "type": ss["network"],
        "security": ss["security"],
        "pbk": reality_cfg["publicKey"],
        "fp": reality_cfg["fingerprint"],
        "sni": rs["serverNames"][0] if rs.get("serverNames") else "",
        "sid": rs["shortIds"][0] if rs.get("shortIds") else "",
        "spx": reality_cfg.get("spiderX", "/"),
        "flow": flow,
    }

    # urlencode encodes spx="/" → "spx=%2F"; quote() handles remark special chars
    query = urlencode(params, quote_via=quote)
    fragment = quote(remark, safe="")
    return f"vless://{client_uuid}@{host}:{port}?{query}#{fragment}"


# ── Adapter ───────────────────────────────────────────────────────────────────

class XuiAdapter:
    """Async HTTP client for 3x-ui REST API.

    Lifecycle: create in lifespan startup, call close() in lifespan shutdown.
    Login is lazy (first real API request triggers it).
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        inbound_id: int,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._inbound_id = inbound_id
        self._client = httpx.AsyncClient(timeout=10.0)
        self._logged_in = False

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def login(self) -> None:
        """POST {base}/login (form-urlencoded) and persist the session cookie."""
        url = f"{self._base}/login"
        try:
            resp = await self._client.post(
                url,
                data={"username": self._username, "password": self._password},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise XuiUnavailableError(f"Cannot reach 3x-ui at {url}: {exc}") from exc

        data = resp.json()
        if not data.get("success"):
            raise XuiError(
                f"3x-ui login failed (wrong credentials?): {data.get('msg', data)}"
            )
        self._logged_in = True

    async def ensure_logged_in(self) -> None:
        """Trigger a login on the first call; no-op afterwards."""
        if not self._logged_in:
            await self.login()

    def _needs_relogin(self, resp: httpx.Response) -> bool:
        """Return True when the response indicates an expired/invalid session."""
        if resp.status_code in (401, 403):
            return True
        # 3x-ui redirects to the HTML login page on session expiry
        if "text/html" in resp.headers.get("content-type", ""):
            return True
        return False

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request; re-login once on stale session."""
        await self.ensure_logged_in()
        url = f"{self._base}{path}"
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise XuiUnavailableError(
                f"Cannot reach 3x-ui at {url}: {exc}"
            ) from exc

        if self._needs_relogin(resp):
            self._logged_in = False
            await self.login()
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                raise XuiUnavailableError(
                    f"Cannot reach 3x-ui at {url}: {exc}"
                ) from exc

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise XuiError(f"3x-ui HTTP error on {path}: {exc}") from exc

        data = resp.json()
        # Some endpoints omit "success"; treat missing key as success=True
        if "success" in data and not data["success"]:
            raise XuiError(f"3x-ui API error on {path}: {data.get('msg', data)}")
        return data

    # ── Response parsing helpers ───────────────────────────────────────────────

    @staticmethod
    def _parse_inbound(obj: dict) -> dict:
        """Parse JSON-string fields (settings, streamSettings) into real dicts."""
        for field in ("settings", "streamSettings", "sniffing"):
            val = obj.get(field)
            if isinstance(val, str):
                try:
                    obj[field] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    pass  # leave as-is if not valid JSON
        return obj

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_inbound(self, inbound_id: int) -> dict:
        """Return the inbound dict with settings/streamSettings already parsed."""
        data = await self._request("GET", f"/panel/api/inbounds/get/{inbound_id}")
        return self._parse_inbound(data["obj"])

    async def get_client_by_email(self, email: str) -> dict | None:
        """Search settings.clients[] in the inbound; return matching client or None."""
        inbound = await self.get_inbound(self._inbound_id)
        clients: list[dict] = inbound.get("settings", {}).get("clients", [])
        for client in clients:
            if client.get("email") == email:
                return client
        return None

    async def get_client_traffic(self, email: str) -> dict | None:
        """Return traffic stats for a client (up/down bytes, enable, expiryTime).

        Returns None if the client has no stats record yet.
        """
        data = await self._request(
            "GET", f"/panel/api/inbounds/getClientTraffics/{email}"
        )
        obj = data.get("obj")
        # API returns null / empty obj when the email is unknown
        if not obj:
            return None
        return obj

    async def add_client(self, inbound_id: int, client_data: dict) -> dict:
        """Add a new client to the inbound.

        client_data keys (all required by 3x-ui):
            id (UUID str), email, flow, expiryTime (Unix ms, 0=never),
            enable (bool), limitIp (int, 0=unlimited), totalGB (int, 0=unlimited),
            tgId (str, can be ""), subId (16-char random), reset (int, 0).
        """
        body = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_data]}),
        }
        return await self._request("POST", "/panel/api/inbounds/addClient", json=body)

    async def update_client(
        self, inbound_id: int, client_uuid: str, client_data: dict
    ) -> dict:
        """Update an existing client (full object replacement — pass all fields).

        Fetch the current client via get_client_by_email first, then apply
        changes and pass the merged dict here.
        """
        body = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_data]}),
        }
        return await self._request(
            "POST",
            f"/panel/api/inbounds/updateClient/{client_uuid}",
            json=body,
        )

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        """Delete a client from the inbound."""
        await self._request(
            "POST",
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
        )

    async def ping(self) -> bool:
        """Try to reach 3x-ui; return True on success (used by health check)."""
        try:
            await self.get_inbound(self._inbound_id)
            return True
        except (XuiError, XuiUnavailableError):
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client (call from lifespan shutdown)."""
        await self._client.aclose()
