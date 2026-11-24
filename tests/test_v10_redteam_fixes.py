"""Regression tests for v10 red-team security, pipeline, and contract fixes."""

import base64
import hashlib
import hmac
import inspect
import json
import time
from fastapi.testclient import TestClient

from backend.main import app, export_openapi_spec
from backend.database import get_db
from backend.migrations.runner import apply_migrations
from backend.services.study_bundle import process_remaining_concept_bundles
from backend.services.quiz_engine import create_and_store_quiz, grade_and_apply_mastery


def _make_jwt(sub: str, secret: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": f"{sub}@example.com", "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


def test_study_bundle_worker_signature_accepts_job_id():
    sig = inspect.signature(process_remaining_concept_bundles)
    assert "job_id" in sig.parameters


def test_hosted_tenant_isolation_and_local_admin_lockdown(tmp_path, monkeypatch):
    db_file = tmp_path / "tenant_test.db"
    apply_migrations(db_file)
    secret = "super-secret-jwt-key-for-testing-32bytes"
    monkeypatch.setenv("AUTH_MODE", "hosted")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)

    import sqlite3
    def _override_db():
        conn = sqlite3.connect(str(db_file), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        tok_a = _make_jwt("user_alice", secret)
        tok_b = _make_jwt("user_bob", secret)
        hdr_a = {"Authorization": f"Bearer {tok_a}"}
        hdr_b = {"Authorization": f"Bearer {tok_b}"}

        # Alice creates a course -> owner_id stamped as user_alice
        r = client.post(
            "/api/courses",
            headers=hdr_a,
            json={"title": "Alice OS Course", "goal_query": "OS", "target_date": "2026-12-15"},
        )
        assert r.status_code == 200, r.text
        cid = r.json()["id"]

        # Bob cannot read Alice's course, schedule, quizzes, or flashcards
        assert client.get(f"/api/courses/{cid}", headers=hdr_b).status_code == 404
        assert client.get(f"/api/courses/{cid}/schedule", headers=hdr_b).status_code == 404
        assert client.get(f"/api/courses/{cid}/quizzes", headers=hdr_b).status_code == 404
        assert client.get(f"/api/courses/{cid}/flashcards", headers=hdr_b).status_code == 404

        # Alice can read her own course and enqueue cram job; Bob cannot see Alice's job
        assert client.get(f"/api/courses/{cid}", headers=hdr_a).status_code == 200
        jr = client.post(f"/api/courses/{cid}/cram-sheet/generate-full-async", headers=hdr_a)
        assert jr.status_code == 202
        jid = jr.json()["job_id"]
        assert client.get(f"/api/jobs/{jid}", headers=hdr_a).status_code == 200
        assert client.get(f"/api/jobs/{jid}", headers=hdr_b).status_code == 404

        # Host-level settings mutation is blocked in hosted mode
        sr = client.post("/api/settings", headers=hdr_a, json={"minutes_per_day": 120})
        assert sr.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_lesson_chapter_title_update_and_missed_question_flashcard(tmp_path):
    db_file = tmp_path / "pipeline_test.db"
    apply_migrations(db_file)

    import sqlite3
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    def _override_db():
        try:
            yield conn
            conn.commit()
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        c = client.post(
            "/api/courses",
            json={"title": "SE Marathon", "goal_query": "SE", "target_date": "2026-12-20"},
        ).json()
        cid = c["id"]

        conn.execute(
            """
            INSERT INTO lessons (id, course_id, title, video_id, start_sec, end_sec, raw_duration_sec, priority, order_index, chapter_title)
            VALUES ('les_1', ?, 'SDLC Models', 'vid123', 0, 600, 600, 'core', 0, 'Intro');
            """,
            (cid,),
        )
        for idx, text in enumerate([
            "The Waterfall Model follows sequential phases: Requirements, Design, Implementation, Verification, and Maintenance.",
            "COCOMO estimates effort using E = a * (KLOC)^b where organic projects have a=2.4 and b=1.05.",
            "Cyclomatic Complexity V(G) = E - N + 2P measures independent paths in a control flow graph.",
            "Black-box testing uses Equivalence Partitioning and Boundary Value Analysis without inspecting source code.",
        ]):
            conn.execute(
                """
                INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
                VALUES (?, ?, 'les_1', ?, 20, ?, ?, ?);
                """,
                (f"chk_{idx}", cid, idx, idx * 120, (idx + 1) * 120, text),
            )
        conn.commit()

        # 1. Verify chapter_title persists via PATCH /lessons/{id}
        upd = client.patch(
            f"/api/courses/{cid}/lessons/les_1",
            json={"chapter_title": "Unit 1: SDLC & Process Models", "priority": "deep-dive"},
        )
        assert upd.status_code == 200
        assert upd.json()["chapter_title"] == "Unit 1: SDLC & Process Models"
        assert upd.json()["priority"] == "deep-dive"

        # 2. Verify missed quiz question generates FSRS flashcard even when score >= 60% (e.g., 75%)
        qdata = create_and_store_quiz(conn, cid, quiz_type="lesson", lesson_id="les_1", question_count=4)
        questions = qdata["questions"]
        assert len(questions) >= 2
        answers = {}
        for i, q in enumerate(questions):
            if i == 0:
                answers[q["id"]] = (q["correct_index"] + 1) % max(2, len(q["options"]))
            else:
                answers[q["id"]] = q["correct_index"]
        graded = grade_and_apply_mastery(conn, qdata["id"], answers)
        assert graded["score"] >= 50.0
        assert graded["flashcards_created"] >= 1
    finally:
        app.dependency_overrides.clear()
        conn.close()
