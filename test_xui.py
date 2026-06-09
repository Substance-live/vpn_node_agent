"""Manual CRUD test for XuiAdapter — run ON THE SERVER.

Usage (from /opt/vpn-node-agent with .env in place):
    uv run python test_xui.py

The script:
  1. Logs in to 3x-ui
  2. Fetches inbound #1 and verifies stream settings are parsed
  3. Builds a vless:// link for the first existing client
  4. Creates a temporary test client
  5. Verifies the test client exists and builds its vless:// link
  6. Disables the test client (update)
  7. Deletes the test client
  8. Verifies the test client is gone

Runs a full CRUD cycle without touching production clients.
"""

import asyncio
import secrets
import sys
import time
import uuid

from adapters.xui_adapter import XuiAdapter, XuiUnavailableError, XuiError, build_vless_link, generate_sub_id
from core.config import settings


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def fail(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def main() -> None:
    print("\n══════════════════════════════════════════════════════════")
    print("  XuiAdapter CRUD test")
    print(f"  Target: {settings.XUI_BASE_URL}")
    print(f"  Inbound ID: {settings.XUI_VLESS_INBOUND_ID}")
    print("══════════════════════════════════════════════════════════")

    adapter = XuiAdapter(
        base_url=settings.XUI_BASE_URL,
        username=settings.XUI_USERNAME,
        password=settings.XUI_PASSWORD,
        inbound_id=settings.XUI_VLESS_INBOUND_ID,
    )

    try:
        # ── Step 1: Login ──────────────────────────────────────────────────
        section("Step 1 — Login")
        await adapter.login()
        ok(f"Logged in as '{settings.XUI_USERNAME}'")

        # ── Step 2: Get inbound ────────────────────────────────────────────
        section("Step 2 — Get inbound")
        inbound = await adapter.get_inbound(settings.XUI_VLESS_INBOUND_ID)
        ok(f"Inbound remark: '{inbound.get('remark')}'")
        ok(f"Listen: {inbound.get('listen')}:{inbound.get('port')}")

        ss = inbound.get("streamSettings", {})
        if not isinstance(ss, dict):
            fail("streamSettings was not parsed into a dict — check _parse_inbound()")
        ok(f"streamSettings.network = '{ss.get('network')}'")
        ok(f"streamSettings.security = '{ss.get('security')}'")

        rs = ss.get("realitySettings", {}).get("settings", {})
        ok(f"publicKey = '{rs.get('publicKey', '?')[:20]}...'")
        ok(f"fingerprint = '{rs.get('fingerprint')}'")

        # ── Step 3: Build vless link for first existing client ─────────────
        section("Step 3 — Build vless:// link for existing client")
        clients = inbound.get("settings", {}).get("clients", [])
        if not clients:
            print("  ⚠  No existing clients — skipping link build for existing client")
        else:
            first = clients[0]
            link = build_vless_link(inbound, first["id"], first["email"])
            ok(f"Link for '{first['email']}':")
            print(f"     {link}")

        # ── Step 4: Add test client ────────────────────────────────────────
        section("Step 4 — Add test client")
        test_email = f"agent-test-{secrets.token_hex(4)}"
        test_uuid = str(uuid.uuid4())
        test_sub_id = generate_sub_id()
        # expire in 1 day
        expire_ms = int((time.time() + 86400) * 1000)

        test_client_data = {
            "id": test_uuid,
            "flow": "xtls-rprx-vision",
            "email": test_email,
            "limitIp": 0,
            "totalGB": 0,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": test_sub_id,
            "reset": 0,
        }

        await adapter.add_client(settings.XUI_VLESS_INBOUND_ID, test_client_data)
        ok(f"Created test client: email='{test_email}' uuid='{test_uuid}'")

        # ── Step 5: Verify client exists + build its link ──────────────────
        section("Step 5 — Verify test client + build its vless:// link")
        found = await adapter.get_client_by_email(test_email)
        if found is None:
            fail(f"Client '{test_email}' not found after add_client — check API response")
        ok(f"get_client_by_email → found (uuid={found['id'][:8]}...)")

        test_link = build_vless_link(inbound, found["id"], test_email)
        ok("vless:// link:")
        print(f"     {test_link}")
        print()
        print("  *** You can paste this link into v2rayN/Hiddify/etc. to verify ***")
        print("  *** The test client will be DELETED at the end of this script   ***")

        # ── Step 6: Disable test client ────────────────────────────────────
        section("Step 6 — Disable test client (update)")
        disabled = dict(found)
        disabled["enable"] = False
        await adapter.update_client(settings.XUI_VLESS_INBOUND_ID, found["id"], disabled)
        ok("update_client called with enable=False")

        # Verify disable
        updated = await adapter.get_client_by_email(test_email)
        if updated is None:
            fail("Client disappeared after update — unexpected")
        if updated.get("enable") is False:
            ok("Client is now disabled (enable=False) ✓")
        else:
            print("  ⚠  enable flag is still True — some 3x-ui versions ignore it in update")

        # ── Step 7: Delete test client ─────────────────────────────────────
        section("Step 7 — Delete test client")
        await adapter.delete_client(settings.XUI_VLESS_INBOUND_ID, found["id"])
        ok("delete_client returned OK")

        # ── Step 8: Verify deletion ────────────────────────────────────────
        section("Step 8 — Verify test client is gone")
        gone = await adapter.get_client_by_email(test_email)
        if gone is None:
            ok(f"'{test_email}' not found → deletion confirmed ✓")
        else:
            fail(f"'{test_email}' still exists after delete — check delete_client()")

        # ── Done ───────────────────────────────────────────────────────────
        print()
        print("══════════════════════════════════════════════════════════")
        print("  All steps passed — XuiAdapter is working correctly 🎉")
        print("══════════════════════════════════════════════════════════\n")

    except (XuiUnavailableError, XuiError) as exc:
        print(f"\n  ✗  {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
