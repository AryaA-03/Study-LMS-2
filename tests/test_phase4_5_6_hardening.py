"""Verification tests for Phase 4 (UI/UX), Phase 5 (Resilience/Caching), and Phase 6 (Auth/Logging/Docker)."""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient

from backend.database import get_db, init_connection
from backend.infra.logging_config import redact_secrets
from backend.infra.rate_limit import SlidingWindowRateLimiter
from backend.main import app
from backend.migrations.runner import apply_migrations


def _make_hs256_jwt(payload: dict, secret: str) -> str:
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    p = _b64(json.dumps(payload).encode("utf-8"))
    sig = _b64(hmac.new(secret.encode("utf-8"), f"{h}.{p}".encode("utf-8"), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def test_secret_redaction_scrubs_all_provider_keys():
    raw = (
        "Failed calling Gemini AIzaSyD1234567890abcdefghijklmno "
        "and Groq gsk_1234567890abcdefghijklmnop "
        "and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
    )
    scrubbed = redact_secrets(raw)
    assert "AIzaSyD" not in scrubbed
    assert "gsk_123456" not in scrubbed
    assert "eyJhbGciOi" not in scrubbed
    assert "[REDACTED_GEMINI_KEY]" in scrubbed
    assert "[REDACTED_GROQ_KEY]" in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed


def test_auth_me_local_and_supabase_jwt_modes(monkeypatch):
    client = TestClient(app)

    # Local mode: zero friction
    monkeypatch.setenv("AUTH_MODE", "local")
    r_local = client.get("/api/auth/me")
    assert r_local.status_code == 200
    assert r_local.json()["id"] == "local"

    # Hosted Supabase/JWT mode: 401 without token, 200 with valid HS256 JWT
    secret = "super-secret-supabase-jwt-key"
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)

    r_unauth = client.get("/api/auth/me")
    assert r_unauth.status_code == 401

    token = _make_hs256_jwt(
        {"sub": "user_42", "email": "student@uni.edu", "role": "authenticated", "exp": time.time() + 3600},
        secret,
    )
    r_ok = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r_ok.status_code == 200
    assert r_ok.json()["id"] == "user_42"
    assert r_ok.json()["email"] == "student@uni.edu"

    # Expired token rejected
    expired = _make_hs256_jwt({"sub": "user_42", "exp": time.time() - 10}, secret)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_sliding_window_rate_limiter():
    rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    assert rl.allow("u1")[0] is True
    assert rl.allow("u1")[0] is True
    allowed, retry = rl.allow("u1")
    assert allowed is False and retry >= 1
    assert rl.allow("u2")[0] is True


def test_async_cram_sheet_job_returns_202(tmp_path):
    db_path = tmp_path / "async_cram.db"
    apply_migrations(db_path)

    def override_get_db():
        c = init_connection(db_path)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        c = client.post("/api/courses", json={"title": "CN", "goal_query": "CN", "target_date": "2026-12-30"})
        cid = c.json()["id"]
        resp = client.post(f"/api/courses/{cid}/cram-sheet/generate-full-async")
        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"].startswith("job_")
        # Verify job is queryable via /api/jobs/{job_id}
        jresp = client.get(f"/api/jobs/{body['job_id']}")
        assert jresp.status_code == 200
        assert jresp.json()["course_id"] == cid
    finally:
        app.dependency_overrides.clear()


def test_phase4_ui_cmdk_aria_and_docker_files_present():
    root = Path(__file__).resolve().parent.parent
    assert not (root / "frontend/templates/index.html").exists()
    assert not (root / "frontend/static/js/app.js").exists()
    assert (root / "Dockerfile").exists()
    assert (root / "docker-compose.yml").exists()
    assert (root / "pyproject.toml").exists()
    assert (root / ".github/workflows/ci.yml").exists()

