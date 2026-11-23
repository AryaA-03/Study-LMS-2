"""Tests verifying Phase 2 & Phase 3 upgrades + the 2 live Playwright bug fixes."""

import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

from backend.database import get_db, init_connection
from backend.infra.job_queue import cancel_job, enqueue_job, get_job, recover_interrupted_jobs, update_job_progress
from backend.infra.text_utils import chunk_text, format_timestamp, parse_llm_json
from backend.main import app
from backend.migrations.runner import apply_migrations
from backend.services.llm_cache import get_cached_response, prune_expired_cache, set_cached_response
from backend.services.notes import generate_no_key_structured_notes
from backend.services.quiz_engine import grade_and_apply_mastery


def test_live_bug_1_no_undeclared_inputCourseTitle_in_app_js():
    js = (Path(__file__).resolve().parent.parent / "frontend/static/js/app.js").read_text(encoding="utf-8")
    assert "inputCourseTitle." not in js
    assert "inputGoalQuery." not in js


def test_live_bug_2_quiz_submit_with_synthetic_chunk_id_no_fk_crash(tmp_path):
    """Submitting a failed quiz whose questions reference a synthetic chunk_id ('chunk-0')
    must NOT throw SQLite FOREIGN KEY constraint failed, and must deduplicate flashcards on re-submit."""
    db_path = tmp_path / "quiz_fk.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)

    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'TOC', 'TOC', '2026-12-30');")
    conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index) VALUES ('l1', 'c1', 'DFA', 600, 0);")
    import json
    questions = [
        {
            "id": "q1",
            "chunk_id": "chunk-0",  # Synthetic ID not in chunks table!
            "lesson_id": "l1",
            "quote": "DFA has 5 tuples.",
            "question": "How many tuples define a DFA?",
            "options": ["3", "4", "5", "6"],
            "correct_index": 2,
            "explanation": "A DFA is a 5-tuple.",
        }
    ]
    conn.execute(
        "INSERT INTO quizzes (id, course_id, lesson_id, quiz_type, title, questions_json) VALUES ('qz1', 'c1', 'l1', 'lesson', 'DFA Quiz', ?);",
        (json.dumps(questions),),
    )
    conn.commit()

    # Submit wrong answer (0% < 60%) -> previously crashed with FOREIGN KEY constraint failed
    res1 = grade_and_apply_mastery(conn, "qz1", user_answers={"q1": 0})
    assert res1["score"] == 0.0
    cards_after_first = conn.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = 'c1';").fetchone()[0]
    assert cards_after_first == 1

    # Re-submit -> must NOT create duplicate flashcard
    grade_and_apply_mastery(conn, "qz1", user_answers={"q1": 0})
    cards_after_second = conn.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = 'c1';").fetchone()[0]
    assert cards_after_second == 1
    conn.close()


def test_notes_embeds_captured_screenshots():
    chunks = [{"id": "chk_1", "start_sec": 0, "end_sec": 60, "content": "DFA has 5 tuples."}]
    screenshots = [{"timestamp_sec": 15, "formatted_time": "[00:15]", "caption": "DFA Diagram", "url": "/api/screenshots/c1/l1/f1.jpg"}]
    md = generate_no_key_structured_notes("DFA", chunks, screenshots=screenshots)
    assert "## Captured Slides & Keyframes" in md
    assert "![DFA Diagram](/api/screenshots/c1/l1/f1.jpg)" in md
    assert "## Grounding & Source Chunks" in md


def test_text_utils_timestamps_and_fenced_json():
    assert format_timestamp(65) == "[01:05]"
    assert format_timestamp(5400) == "[01:30:00]"
    parsed = parse_llm_json('Here is the JSON:\n```json\n{"ok": true, "items": [1, 2]}\n```')
    assert parsed == {"ok": True, "items": [1, 2]}
    ch = chunk_text("word " * 400, target_words=100, overlap_words=20)
    assert len(ch) >= 4


def test_job_queue_lifecycle_and_recovery(tmp_path):
    db_path = tmp_path / "jobs.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    jid = enqueue_job(conn, "cram_sheet_full", course_id="c1", payload={"full": True})
    update_job_progress(conn, jid, "running", 40, "Transcribing 4/10")
    job = get_job(conn, jid)
    assert job["status"] == "running" and job["progress_pct"] == 40
    recovered = recover_interrupted_jobs(conn)
    assert recovered == 1
    assert get_job(conn, jid)["status"] == "queued"
    assert cancel_job(conn, jid) is True
    assert get_job(conn, jid)["status"] == "cancelled"
    conn.close()


def test_llm_cache_ttl_and_single_column_write(tmp_path):
    db_path = tmp_path / "cache.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    set_cached_response(conn, "h1", "gemini-2.5-flash", '{"a": 1}', ttl_days=30)
    assert get_cached_response(conn, "h1") == '{"a": 1}'
    # Expire it manually and verify pruning
    conn.execute("UPDATE llm_cache SET expires_at = '2020-01-01T00:00:00+00:00' WHERE prompt_hash = 'h1';")
    conn.commit()
    assert get_cached_response(conn, "h1") is None
    set_cached_response(conn, "h2", "gemini-2.5-flash", '{"b": 2}', ttl_days=-1)
    assert prune_expired_cache(conn) >= 1
    conn.close()


def test_course_and_source_delete_endpoints_and_flashcard_full_deck(tmp_path):
    db_path = tmp_path / "crud.db"
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
        r = client.post("/api/courses", json={"title": "OS", "goal_query": "OS", "target_date": "2026-12-30"})
        assert r.status_code == 200
        cid = r.json()["id"]

        # Seed a non-due future flashcard and verify GET /flashcards returns it (due_only=False)
        conn = init_connection(db_path)
        conn.execute(
            "INSERT INTO flashcards (id, course_id, front, back, due_date, reps) VALUES ('fc1', ?, 'Q', 'A', '2099-01-01T00:00:00+00:00', 3);",
            (cid,),
        )
        conn.execute(
            "INSERT INTO sources (id, course_id, source_type, title, is_approved) VALUES ('src1', ?, 'web', 'Wiki', 1);",
            (cid,),
        )
        conn.commit()
        conn.close()

        all_cards = client.get(f"/api/courses/{cid}/flashcards")
        assert all_cards.status_code == 200 and len(all_cards.json()) == 1
        due_cards = client.get(f"/api/courses/{cid}/flashcards?due_only=true")
        assert due_cards.status_code == 200 and len(due_cards.json()) == 0

        # Delete source & delete course
        ds = client.delete(f"/api/courses/{cid}/sources/src1")
        assert ds.status_code == 200
        dc = client.delete(f"/api/courses/{cid}")
        assert dc.status_code == 200
        assert client.get(f"/api/courses/{cid}").status_code == 404

        # Jobs endpoint works
        jl = client.get("/api/jobs")
        assert jl.status_code == 200 and "jobs" in jl.json()
    finally:
        app.dependency_overrides.clear()
