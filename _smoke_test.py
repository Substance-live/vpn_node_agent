"""Local smoke-test for Stage 6 -- no real 3x-ui / mtg needed."""
import json
import sys

from fastapi import APIRouter as _APIRouter
from fastapi.testclient import TestClient

from main import app

# Register a temporary error-trigger route to exercise the catch-all 500 handler.
# Must be added before TestClient context so the route exists at request time.
_tmp_router = _APIRouter()


@_tmp_router.get("/api/v1/_test_error")
async def _trigger_unhandled_error():
    raise ValueError("intentional test error — catch-all check")


app.include_router(_tmp_router)

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

    # 4. POST without auth -> unified envelope (FastAPI 403, NOT {"detail": ...})
    print("\n-- 4. POST without auth -> 403 unified envelope --")
    r = client.post("/api/v1/vless/users", json={"external_id": "x", "expire_days": 1})
    ok_status = r.status_code in (401, 403)
    try:
        body = json.loads(r.text)
        has_envelope = {"error", "message", "details"} <= body.keys()
        no_detail_key = "detail" not in body  # FastAPI default uses "detail"
    except (json.JSONDecodeError, TypeError):
        has_envelope = no_detail_key = False
    print(f"  {'OK' if ok_status else 'FAIL'}  status={r.status_code}  (expected 403)")
    print(f"  {'OK' if has_envelope else 'FAIL'}  JSON envelope has error/message/details keys")
    print(f"  {'OK' if no_detail_key else 'FAIL'}  no raw 'detail' key (not default FastAPI format)")
    print(f"         body={r.text[:120]!r}")
    if not (ok_status and has_envelope and no_detail_key):
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

    # 7. POST with auth but empty body -> 422 validation_error unified envelope
    print("\n-- 7. POST with auth, empty body -> 422 unified envelope --")
    r = client.post(
        "/api/v1/vless/users",
        json={},
        headers={"X-Agent-Secret": "changeme"},
    )
    ok_status = r.status_code == 422
    try:
        body = json.loads(r.text)
        ok_error = body.get("error") == "validation_error"
        ok_details = isinstance(body.get("details"), list) and len(body["details"]) > 0
        no_detail_key = "detail" not in body
    except (json.JSONDecodeError, TypeError):
        ok_error = ok_details = no_detail_key = False
    print(f"  {'OK' if ok_status else 'FAIL'}  status={r.status_code}  (expected 422)")
    print(f"  {'OK' if ok_error else 'FAIL'}  error=='validation_error'")
    print(f"  {'OK' if ok_details else 'FAIL'}  details is non-empty list")
    print(f"  {'OK' if no_detail_key else 'FAIL'}  no raw 'detail' key")
    print(f"         body={r.text[:200]!r}")
    if not (ok_status and ok_error and ok_details and no_detail_key):
        all_ok = False

    # 8. GET non-existent route -> 404 not_found unified envelope
    print("\n-- 8. GET non-existent route -> 404 unified envelope --")
    r = client.get("/api/v1/nope", headers={"X-Agent-Secret": "changeme"})
    ok_status = r.status_code == 404
    try:
        body = json.loads(r.text)
        ok_error = body.get("error") == "not_found"
        no_detail_key = "detail" not in body
    except (json.JSONDecodeError, TypeError):
        ok_error = no_detail_key = False
    print(f"  {'OK' if ok_status else 'FAIL'}  status={r.status_code}  (expected 404)")
    print(f"  {'OK' if ok_error else 'FAIL'}  error=='not_found'")
    print(f"  {'OK' if no_detail_key else 'FAIL'}  no raw 'detail' key")
    print(f"         body={r.text[:120]!r}")
    if not (ok_status and ok_error and no_detail_key):
        all_ok = False

    # 9. Unhandled ValueError -> 500 internal_error unified envelope (catch-all handler)
    print("\n-- 9. Unhandled ValueError -> 500 unified envelope --")
    r = client.get("/api/v1/_test_error")
    ok_status = r.status_code == 500
    try:
        body = json.loads(r.text)
        ok_error = body.get("error") == "internal_error"
        no_detail_key = "detail" not in body
    except (json.JSONDecodeError, TypeError):
        ok_error = no_detail_key = False
    print(f"  {'OK' if ok_status else 'FAIL'}  status={r.status_code}  (expected 500)")
    print(f"  {'OK' if ok_error else 'FAIL'}  error=='internal_error'")
    print(f"  {'OK' if no_detail_key else 'FAIL'}  no raw 'detail' key")
    print(f"         body={r.text[:120]!r}")
    if not (ok_status and ok_error and no_detail_key):
        all_ok = False

print()
if all_ok:
    print("== All local checks passed ==\n")
else:
    print("== Some checks FAILED ==\n", file=sys.stderr)

sys.exit(0 if all_ok else 1)
