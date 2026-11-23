"""Regression tests for all verified security, stability, and architecture audit fixes."""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.infra.crypto import decrypt_secret, encrypt_secret
from backend.infra.rate_limit import SlidingWindowRateLimiter
from backend.main import app, export_openapi_spec
from backend.migrations.runner import apply_migrations


def _make_hs256_jwt(payload: dict, secret: str, alg: str = "HS256") -> str:
    def _b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    h = _b64({"alg": alg, "typ": "JWT"})
    p = _b64(payload)
    sig = hmac.new(secret.encode("utf-8"), f"{h}.{p}".encode("ascii"), hashlib.sha256).digest()
    s = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{h}.{p}.{s}"


@pytest.fixture
def hardened_client(tmp_path, monkeypatch):
    db_path = tmp_path / "hardened_audit.db"
    apply_migrations(str(db_path))

    def _get_test_db():
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _get_test_db
    monkeypatch.setattr("backend.database.DB_PATH", str(db_path))
    client = TestClient(app)
    yield client, str(db_path)
    app.dependency_overrides.clear()


def test_aes256_gcm_hkdf_crypto_roundtrip_and_tamper():
    master = "production-grade-master-secret-key-2026"
    ct1, n1 = encrypt_secret("sk-live-secret-1", master)
    ct2, n2 = encrypt_secret("sk-live-secret-1", master)
    assert ct1 != ct2
    assert n1 != n2
    assert decrypt_secret(ct1, n1, master) == "sk-live-secret-1"
    with pytest.raises(ValueError):
        decrypt_secret(ct1, n1, "wrong-master-secret-key-0000")


def test_hosted_auth_enforcement_and_jwt_hardening(hardened_client, monkeypatch):
    client, _ = hardened_client
    secret = "super-secret-jwt-signing-key-2026"
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)

    # 1. Anonymous requests must be rejected with 401 across routers
    assert client.get("/api/courses").status_code == 401
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/auth/me").status_code == 401

    # 2. Host-level admin endpoints must return 403/401 in hosted mode
    assert client.post("/api/settings/update-ytdlp").status_code in (401, 403)

    # 3. alg:none and missing-exp tokens must be rejected
    none_tok = _make_hs256_jwt({"sub": "u1", "exp": time.time() + 300}, secret, alg="none")
    assert client.get("/api/courses", headers={"Authorization": f"Bearer {none_tok}"}).status_code == 401

    no_exp_tok = _make_hs256_jwt({"sub": "u1"}, secret)
    assert client.get("/api/courses", headers={"Authorization": f"Bearer {no_exp_tok}"}).status_code == 401

    # 4. Valid HS256 JWT with exp + sub succeeds
    valid_tok = _make_hs256_jwt({"sub": "user-alpha", "email": "a@example.com", "exp": time.time() + 300}, secret)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid_tok}"})
    assert r.status_code == 200
    assert r.json()["id"] == "user-alpha"
    assert client.get("/api/courses", headers={"Authorization": f"Bearer {valid_tok}"}).status_code == 200
    # Even with a valid JWT, host-level admin endpoints remain 403 in hosted mode
    assert client.post("/api/settings/update-ytdlp", headers={"Authorization": f"Bearer {valid_tok}"}).status_code == 403


def test_ssrf_openrouter_and_no_gemini_query_key(hardened_client):
    client, _ = hardened_client
    r = client.post("/api/settings", json={"openrouter_base_url": "http://127.0.0.1:9999/steal"})
    assert r.status_code == 400
    r2 = client.post("/api/settings", json={"openrouter_base_url": "http://169.254.169.254/latest/meta-data"})
    assert r2.status_code == 400

    settings_src = Path("backend/routers/settings.py").read_text(encoding="utf-8")
    assert 'params={"key":' not in settings_src


def test_flashcard_state0_edit_and_delete_404(hardened_client):
    client, _ = hardened_client
    c = client.post(
        "/api/courses",
        json={"title": "DBMS", "goal_query": "DBMS", "target_date": "2027-01-01", "minutes_per_day": 60},
    ).json()
    cid = c["id"]

    card = client.post(f"/api/courses/{cid}/flashcards", json={"front": "What is ACID?", "back": "Atomicity..."}).json()
    upd = client.put(
        f"/api/courses/{cid}/flashcards/{card['id']}",
        json={"front": "What is ACID in DBMS?", "back": "Atomicity, Consistency, Isolation, Durability"},
    )
    assert upd.status_code == 200
    assert "intervals" in upd.json()

    missing_del = client.delete(f"/api/courses/{cid}/flashcards/nonexistent-card-id")
    assert missing_del.status_code == 404


def test_pdf_magic_byte_validation(hardened_client):
    client, _ = hardened_client
    c = client.post(
        "/api/courses",
        json={"title": "OS", "goal_query": "OS", "target_date": "2027-01-01", "minutes_per_day": 60},
    ).json()
    cid = c["id"]

    r = client.post(
        f"/api/courses/{cid}/sources/pdf",
        files={"file": ("fake.pdf", b"NOT A REAL PDF FILE", "application/pdf")},
    )
    assert r.status_code == 400


def test_migration_013_fts5_insert_trigger_and_qa_columns(hardened_client):
    _, db_path = hardened_client
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    # Verify qa_threads has lesson_id and scope
    qa_cols = {r[1] for r in conn.execute("PRAGMA table_info(qa_threads)").fetchall()}
    assert "lesson_id" in qa_cols
    assert "scope" in qa_cols

    # Verify inserting into chunks automatically syncs chunks_fts via trg_chunks_insert_fts
    conn.execute(
        "INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day) VALUES ('c1', 'TOC', 'TOC', '2027-01-01', 60);"
    )
    conn.execute(
        "INSERT INTO sources (id, course_id, source_type, title, url, is_approved) VALUES ('s1', 'c1', 'youtube_video', 'V1', 'https://youtu.be/x', 1);"
    )
    conn.execute(
        "INSERT INTO chunks (id, course_id, source_id, chunk_index, start_sec, end_sec, content, token_count) VALUES ('ch1', 'c1', 's1', 0, 0, 60, 'Pushdown automata use a LIFO stack', 6);"
    )
    conn.commit()
    hits = conn.execute("SELECT id FROM chunks_fts WHERE chunks_fts MATCH 'Pushdown';").fetchall()
    conn.close()
    assert len(hits) == 1
    assert hits[0][0] == "ch1"


def test_csp_header_and_openapi_includes_auth_me(hardened_client):
    client, _ = hardened_client
    r = client.get("/healthz")
    assert r.status_code == 200
    assert "Content-Security-Policy" in r.headers
    spec = export_openapi_spec(Path("/tmp/test_openapi_audit.json"))
    assert "/api/auth/me" in spec["paths"]


def test_rate_limiter_evicts_stale_keys():
    rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=0.05, max_keys=10)
    for i in range(15):
        rl.allow(f"ip-{i}")
    assert len(rl._buckets) <= 10
    time.sleep(0.08)
    rl._prune_stale_locked(time.monotonic() - 0.05)
    assert len(rl._buckets) == 0
