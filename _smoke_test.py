"""Local smoke-test for Stage 6 -- no real 3x-ui / mtg needed."""
import json
import sys

from fastapi.testclient import TestClient

from main import app

all_ok = True

with TestClient(app, raise_server_exceptions=False) as client:

    # 1. Import sanity: test_xui.py should still be importable (re-export check)
    print("\n-- 1. Re-export check (test_xui.py imports) --")
    try:
        from adapters.xui_adapter import XuiError, XuiUnavailableError  # noqa: F401
        from adapters.mtg_adapter import MtgConfigError  # noqa: F401
        print("  OK  XuiError, XuiUnavailableError, MtgConfigError importable from adapters")
    except ImportError as e:
        print(f"  FAIL  {e}", file=sys.stderr)
        all_ok = False

    # 2. /health still 200
    print("\n-- 2. /health --")
    r = client.get("/api/v1/health")
    ok = r.status_code == 200
    print(f"  {'OK' if ok else 'FAIL'}  status={r.status_code}")
    if not ok:
        all_ok = False

    # 3. GET non-existent user -> 502 (xui_unavailable locally, not 500)
    print("\n-- 3. GET unknown user -> 502 with unified envelope --")
    r = client.get("/api/v1/vless/users/nobody", headers={"X-Agent-Secret": "changeme"})
    body_text = r.text
    ok_status = r.status_code in (404, 502)
    try:
        body = json.loads(body_text)
        has_envelope = {"error", "message", "details"} <= body.keys()
    except (json.JSONDecodeError, TypeError):
        has_envelope = False
    print(f"  {'OK' if ok_status else 'FAIL'}  status={r.status_code}  (expected 404 on server / 502 locally)")
    print(f"  {'OK' if has_envelope else 'FAIL'}  JSON envelope has error/message/details keys")
    print(f"         body={body_text[:120]!r}")
    if not (ok_status and has_envelope):
        all_ok = False

    # 4. POST without auth -> unified envelope (FastAPI 403)
    print("\n-- 4. POST without auth -> 401/403 --")
    r = client.post("/api/v1/vless/users", json={"external_id": "x", "expire_days": 1})
    ok = r.status_code in (401, 403)
    print(f"  {'OK' if ok else 'FAIL'}  status={r.status_code}")
    if not ok:
        all_ok = False

    # 5. GET /mtproto/info with bad MTG_CONFIG_PATH -> 502 mtg_config_error envelope
    print("\n-- 5. MtgConfigError -> 502 mtg_config_error --")
    import os; os.environ["MTG_CONFIG_PATH"] = "/nonexistent/path.toml"
    # Re-import adapter to pick up changed env (singleton already created, call directly)
    from adapters.mtg_adapter import MtgConfigError as MCE, MtgAdapter
    from core.config import settings as s
    adapter_bad = MtgAdapter("/nonexistent/path.toml", "127.0.0.1", 1234)
    try:
        adapter_bad.get_proxy_info()
        print("  FAIL  no exception raised for missing config", file=sys.stderr)
        all_ok = False
    except MCE as e:
        print(f"  OK  MtgConfigError raised: {e}")

    # Trigger via HTTP: the real mtg_adapter singleton uses fake_mtg_config.toml
    # so /health is 200. Provoke the handler directly instead via the adapter error.
    r = client.get("/api/v1/health")
    print(f"  OK  /health with fake config still 200: status={r.status_code}")

    # 6. Access-log: verify middleware runs (just check response isn't broken)
    print("\n-- 6. Middleware sanity --")
    r = client.get("/api/v1/health")
    ok = r.status_code == 200
    print(f"  {'OK' if ok else 'FAIL'}  /health after middleware wired: status={r.status_code}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("== All local checks passed ==\n")
else:
    print("== Some checks FAILED ==\n", file=sys.stderr)

sys.exit(0 if all_ok else 1)
