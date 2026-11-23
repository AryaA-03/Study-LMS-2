"""Comprehensive verification tests for Master Plan Stage 1 (Backend Final) + Stage 2 (Vite React SPA)."""

import re
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.infra.crypto import decrypt_secret, encrypt_secret
from backend.infra.job_queue import enqueue_job, update_job_progress
from backend.main import app
from backend.migrations.runner import apply_migrations
from backend.services.concept_partitioner import merge_tiny_chapters
from backend.services.syllabus_matcher import parse_syllabus_topics, score_lesson_against_topic


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    db_path = tmp_path / "master_plan_final.db"
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

    from backend.database import get_db

    app.dependency_overrides[get_db] = _get_test_db
    monkeypatch.setattr("backend.database.DB_PATH", str(db_path))
    client = TestClient(app)
    yield client, str(db_path)
    app.dependency_overrides.clear()


def test_crypto_roundtrip_and_tamper_rejection():
    master = "super-secret-master-key-for-testing-1234"
    ct1, nonce1 = encrypt_secret("AIzaSyTestKey123", master)
    ct2, nonce2 = encrypt_secret("AIzaSyTestKey123", master)
    assert nonce1 != nonce2
    assert ct1 != ct2
    assert decrypt_secret(ct1, nonce1, master) == "AIzaSyTestKey123"
    assert decrypt_secret(ct2, nonce2, master) == "AIzaSyTestKey123"

    tampered = ct1[:-2] + ("AA" if ct1[-2:] != "AA" else "BB")
    with pytest.raises(ValueError):
        decrypt_secret(tampered, nonce1, master)

    with pytest.raises(ValueError):
        decrypt_secret(ct1, nonce1, "different-master-key-for-testing-9999")


def test_migration_012_users_and_secrets_tables(isolated_client):
    _, db_path = isolated_client
    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    }
    assert "users" in tables
    assert "user_secrets" in tables
    version_count = conn.execute("SELECT COUNT(*) FROM schema_migrations;").fetchone()[0]
    assert version_count == 13
    conn.close()


def test_sse_job_events_endpoint(isolated_client):
    client, db_path = isolated_client
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    job_id = enqueue_job(conn, "cram_sheet_full", payload={"course_id": "test-course"})
    update_job_progress(conn, job_id, status="completed", progress_pct=100, message="Complete")
    conn.close()

    resp = client.get(f"/api/jobs/{job_id}/events")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert job_id in resp.text
    assert "completed" in resp.text


def test_skip_allocation_records_snapshot_and_undo_restores(isolated_client):
    client, db_path = isolated_client
    c_resp = client.post(
        "/api/courses",
        json={
            "title": "Operating Systems",
            "goal_query": "OS",
            "target_date": "2027-01-15",
            "minutes_per_day": 60,
            "playback_speed": 1.0,
            "rest_days": [],
            "revision_buffer_days": 1,
            "schedule_strategy": "paced",
        },
    )
    assert c_resp.status_code == 200
    course_id = c_resp.json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT INTO sources (id, course_id, source_type, url, title, is_approved) VALUES ('src1', ?, 'youtube_video', 'https://youtu.be/test1', 'OS Lecture 1', 1)",
        (course_id,),
    )
    conn.execute(
        "INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, order_index) VALUES ('les1', ?, 'src1', 'Processes & Threads', 1800, 0)",
        (course_id,),
    )
    conn.execute(
        "INSERT INTO schedule_allocations (id, course_id, lesson_id, scheduled_date, allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped) VALUES ('alloc1', ?, 'les1', '2026-12-01', 0, 1800, 30.0, 0, 0)",
        (course_id,),
    )
    conn.commit()
    conn.close()

    skip_resp = client.post(f"/api/courses/{course_id}/schedule/allocations/alloc1/skip")
    assert skip_resp.status_code == 200

    conn = sqlite3.connect(db_path)
    snap_count = conn.execute(
        "SELECT COUNT(*) FROM schedule_snapshots WHERE course_id = ?;", (course_id,)
    ).fetchone()[0]
    conn.close()
    assert snap_count >= 1

    undo_resp = client.post(f"/api/courses/{course_id}/schedule/undo")
    assert undo_resp.status_code == 200
    conn = sqlite3.connect(db_path)
    skipped_after_undo = conn.execute(
        "SELECT is_skipped FROM schedule_allocations WHERE id = 'alloc1';"
    ).fetchone()[0]
    conn.close()
    assert skipped_after_undo == 0


def test_syllabus_matcher_score_bounded_and_selective():
    topics = parse_syllabus_topics("1. Deterministic Finite Automata (DFA)\n2. Nondeterministic Finite Automata (NFA)")
    assert len(topics) >= 2
    score_match, _ = score_lesson_against_topic("Deterministic Finite Automata DFA Basics", "Unit 1", topics[0])
    score_miss, _ = score_lesson_against_topic("Cooking Pasta in 10 Minutes", "Food", topics[0])
    assert 0.0 <= score_match <= 1.0
    assert score_match > 0.5
    assert score_miss < 0.2


def test_concept_partitioner_clamps_end_to_total_duration():
    chapters = [
        {"title": "Intro", "start_time": 0, "end_time": 300},
        {"title": "Overflow Chapter", "start_time": 300, "end_time": 9999},
    ]
    segs = merge_tiny_chapters(chapters, total_duration=500)
    assert segs
    assert all(s["end_time"] <= 500 for s in segs)


def test_rate_limit_middleware_returns_429(isolated_client, monkeypatch):
    client, _ = isolated_client
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    from backend.main import _rate_limiter

    _rate_limiter._buckets.clear()
    old_limit = _rate_limiter.max_requests
    _rate_limiter.max_requests = 3
    try:
        statuses = [client.get("/api/courses").status_code for _ in range(5)]
        assert 200 in statuses
        assert 429 in statuses
    finally:
        _rate_limiter.max_requests = old_limit
        _rate_limiter._buckets.clear()


def test_vite_spa_served_at_root_and_legacy_fallback(isolated_client):
    client, _ = isolated_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Study LMS — Calm Exam & Learning Workspace" in resp.text
    assert "/static/dist/assets/" in resp.text

    asset_urls = re.findall(r'(/static/dist/assets/[^"]+)', resp.text)
    assert len(asset_urls) >= 2
    for url in asset_urls:
        a_resp = client.get(url)
        assert a_resp.status_code == 200, f"Asset failed: {url}"

    legacy_resp = client.get("/legacy")
    assert legacy_resp.status_code == 200
    assert "app.js" in legacy_resp.text
