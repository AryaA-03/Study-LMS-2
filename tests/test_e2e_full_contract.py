"""Full End-to-End Frontend-Backend Contract Verification Suite.

Exercises every single API contract used by the React SPA with the exact JSON
payloads and asserts every response key the UI relies on.
"""

import io
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.database import get_db
from backend.main import app
from backend.migrations.runner import apply_migrations


@pytest.fixture
def e2e_client(tmp_path, monkeypatch):
    db_path = tmp_path / "full_contract.db"
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


def test_complete_study_workflow_contract(e2e_client):
    client, db_path = e2e_client

    # 1. Create & Edit Course
    c = client.post(
        "/api/courses",
        json={
            "title": "Software Engineering",
            "goal_query": "SE Finals",
            "target_date": "2027-01-15",
            "minutes_per_day": 90,
            "playback_speed": 1.25,
            "schedule_strategy": "paced",
            "rest_days": ["Sunday"],
            "revision_buffer_days": 2,
        },
    )
    assert c.status_code == 200
    cid = c.json()["id"]

    upd = client.patch(
        f"/api/courses/{cid}",
        json={"minutes_per_day": 60, "playback_speed": 1.5, "schedule_strategy": "fixed"},
    )
    assert upd.status_code == 200

    # 2. Manual Transcript Source -> creates lesson + chunks + notes
    mt = client.post(
        f"/api/courses/{cid}/sources/manual-transcript",
        json={
            "title": "SDLC Waterfall vs Agile",
            "transcript_text": (
                "The Software Development Life Cycle (SDLC) defines requirements, design, coding, testing, "
                "and maintenance. Waterfall is sequential with fixed requirements, whereas Agile uses iterative "
                "Scrum sprints for rapid customer feedback. Maintenance accounts for 60 percent of total cost."
            ),
            "url": "",
        },
    )
    assert mt.status_code == 200
    lid = mt.json()["lesson_id"]

    # 3. Valid PDF upload
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_r = client.post(
        f"/api/courses/{cid}/sources/pdf",
        files={"file": ("slides.pdf", buf.getvalue(), "application/pdf")},
        data={"title": "slides.pdf"},
    )
    assert pdf_r.status_code == 200

    # 4. Schedule generate, toggle, skip, undo, replan
    sched = client.post(f"/api/courses/{cid}/schedule/generate")
    assert sched.status_code == 200
    day0 = sched.json()["days"][0]
    assert "total_effective_minutes" in day0
    alloc_id = day0["allocations"][0]["id"]

    assert client.post(f"/api/courses/{cid}/schedule/allocations/{alloc_id}/toggle").status_code == 200
    assert client.post(f"/api/courses/{cid}/schedule/allocations/{alloc_id}/skip").status_code == 200
    assert client.post(f"/api/courses/{cid}/schedule/undo").status_code == 200
    assert client.post(f"/api/courses/{cid}/schedule/replan", json={"mode": "normal"}).status_code == 200

    # 5. Notes & Personal Notes
    notes = client.get(f"/api/lessons/{lid}/notes")
    assert notes.status_code == 200
    assert "content_markdown" in notes.json()
    assert "personal_notes" in notes.json()
    assert client.put(f"/api/lessons/{lid}/notes/personal", json={"personal_notes": "Key exam point"}).status_code == 200

    # 6. Ask AI
    qa = client.post(f"/api/courses/{cid}/qa", json={"query": "Compare Waterfall and Agile", "lesson_id": lid})
    assert qa.status_code == 200
    assert "answer_markdown" in qa.json()
    hist = client.get(f"/api/courses/{cid}/qa").json()
    assert len(hist) >= 1 and "query" in hist[0] and "answer_markdown" in hist[0]

    # 7. Quiz Generate + Submit + Wrong-Answer Timestamp & Missed Flashcards
    q_resp = client.post(
        f"/api/courses/{cid}/quizzes/generate",
        json={"quiz_type": "lesson", "lesson_id": lid, "question_count": 3},
    )
    assert q_resp.status_code == 200
    quiz = q_resp.json()
    assert len(quiz["questions"]) >= 1
    q0 = quiz["questions"][0]
    assert q0.get("question")
    assert "correct_index" in q0
    assert "timestamp_sec" in q0

    wrong_answers = {q["id"]: ((q.get("correct_index") or 0) + 1) % max(2, len(q.get("options") or [0, 1])) for q in quiz["questions"]}
    sub = client.post(
        f"/api/courses/{cid}/quizzes/{quiz['id']}/submit",
        json={"answers": wrong_answers, "short_answers": {}, "time_taken_seconds": 25},
    )
    assert sub.status_code == 200
    assert sub.json()["score"] == 0.0

    # 8. Flashcards Auto-Gen + Create + Edit + Review + Delete
    gen_fc = client.post(f"/api/courses/{cid}/flashcards/lessons/{lid}/generate")
    assert gen_fc.status_code == 200
    fc = client.post(f"/api/courses/{cid}/flashcards", json={"front": "SDLC?", "back": "Software Dev Life Cycle", "lesson_id": lid}).json()
    assert client.put(f"/api/courses/{cid}/flashcards/{fc['id']}", json={"front": "SDLC", "back": "Updated"}).status_code == 200
    assert client.post(f"/api/courses/{cid}/flashcards/{fc['id']}/review", json={"rating": 3}).status_code == 200
    assert client.delete(f"/api/courses/{cid}/flashcards/{fc['id']}").status_code == 200

    # 9. PYQ Upload + Summary includes `questions` list!
    assert client.post(
        f"/api/courses/{cid}/pyq/upload-text",
        json={"title": "End-Sem 2024", "raw_text": "Q1. Compare Waterfall and Agile SDLC models. [10M]"},
    ).status_code == 200
    pyq_sum = client.get(f"/api/courses/{cid}/pyq").json()
    assert "questions" in pyq_sum and len(pyq_sum["questions"]) >= 1

    # 10. Syllabus Match + Apply using `included_lesson_ids`
    sm = client.post(
        f"/api/courses/{cid}/syllabus/match",
        json={"syllabus_text": "Unit 1: SDLC Waterfall Agile", "strictness": "balanced"},
    )
    assert sm.status_code == 200
    matched_ids = [m["id"] for m in sm.json()["lessons"] if m.get("is_matched")]
    assert len(matched_ids) >= 1
    sa = client.post(
        f"/api/courses/{cid}/syllabus/apply",
        json={"syllabus_text": "Unit 1: SDLC", "included_lesson_ids": matched_ids, "strictness": "balanced", "regenerate_schedule": True},
    )
    assert sa.status_code == 200

    # 11. Cram Sheet Generate + Get + Download
    assert client.post(f"/api/courses/{cid}/cram-sheet/generate", json={"force_refresh": True}).status_code == 200
    assert client.get(f"/api/courses/{cid}/cram-sheet").status_code == 200
    assert client.get(f"/api/courses/{cid}/cram-sheet/download").status_code == 200


def test_smart_prepare_repartitions_fixed_slice_marathon_video(e2e_client):
    client, db_path = e2e_client

    c = client.post(
        "/api/courses",
        json={"title": "SE Marathon", "goal_query": "SE", "target_date": "2027-01-15", "minutes_per_day": 90},
    ).json()
    cid = c["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved) VALUES ('src1', ?, 'youtube_video', 'Complete SE One Shot', 'https://youtu.be/NlLM3sVF8wY', 'NlLM3sVF8wY', 1);",
        (cid,),
    )
    # Seed 3 fixed-slice lessons with [MM:SS - MM:SS] suffix
    for i, (s, e) in enumerate([(0, 780), (780, 1560), (1560, 2340)]):
        conn.execute(
            "INSERT INTO lessons (id, course_id, source_id, title, video_id, video_url, start_sec, end_sec, raw_duration_sec, priority, order_index) VALUES (?, ?, 'src1', ?, 'NlLM3sVF8wY', 'https://youtu.be/NlLM3sVF8wY', ?, ?, 780, 'core', ?);",
            (f"fixed_{i}", cid, f"Complete SE One Shot [{s//60:02d}:00 - {e//60:02d}:00]", s, e, i),
        )
    conn.commit()
    conn.close()

    fake_captions = [
        {"chunk_index": 0, "start_sec": 0, "end_sec": 600, "token_count": 100, "content": "Welcome to SDLC and the Waterfall Model requirements phase."},
        {"chunk_index": 1, "start_sec": 600, "end_sec": 1200, "token_count": 100, "content": "Next we cover Agile Scrum sprints and iterative delivery."},
        {"chunk_index": 2, "start_sec": 1200, "end_sec": 2340, "token_count": 100, "content": "Finally we examine Black Box Testing and Cyclomatic Complexity."},
    ]

    with patch("backend.services.smart_prepare.fetch_youtube_captions", new=AsyncMock(return_value=fake_captions)):
        res = client.post(f"/api/courses/{cid}/smart-prepare")
        assert res.status_code == 200
        data = res.json()
        assert data["repartitioned_sources"] == 1
        assert data["new_semantic_clips"] >= 1
        assert data["background_job_id"]
