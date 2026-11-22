"""Test suite verifying course editing, rescheduling, and replan flow."""

import os
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, date, timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import get_db
from backend.migrations.runner import apply_migrations

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Run migrations
    apply_migrations(db_path=Path(path))
    
    # Override get_db dependency in app
    def override_get_db():
        conn = sqlite3.connect(path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    yield path
    app.dependency_overrides.pop(get_db, None)
    if os.path.exists(path):
        os.unlink(path)

def test_course_update_patch_and_put(temp_db):
    client = TestClient(app)
    
    # 1. Create a course
    create_res = client.post("/api/courses", json={
        "title": "Initial Course Title",
        "goal_query": "Algorithms and Data Structures",
        "source_preferences": "YouTube, MIT OCW",
        "target_date": (date.today() + timedelta(days=30)).isoformat(),
        "minutes_per_day": 60,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    })
    assert create_res.status_code == 200, create_res.text
    course = create_res.json()
    course_id = course["id"]
    assert course["title"] == "Initial Course Title"
    assert course["minutes_per_day"] == 60

    # 2. Test PATCH /api/courses/{course_id}
    new_target_date = (date.today() + timedelta(days=20)).isoformat()
    patch_res = client.patch(f"/api/courses/{course_id}", json={
        "title": "Updated Course Title via PATCH",
        "target_date": new_target_date,
        "minutes_per_day": 90,
        "playback_speed": 1.25,
        "revision_buffer_days": 0,
        "schedule_strategy": "paced",
        "rest_days": ["Saturday", "Sunday"],
    })
    assert patch_res.status_code == 200, patch_res.text
    updated = patch_res.json()
    assert updated["title"] == "Updated Course Title via PATCH"
    assert updated["target_date"] == new_target_date
    assert updated["minutes_per_day"] == 90
    assert updated["playback_speed"] == 1.25
    assert updated["revision_buffer_days"] == 0
    assert "Saturday" in updated["rest_days"]

    # 3. Test PUT /api/courses/{course_id} (alias support)
    put_res = client.put(f"/api/courses/{course_id}", json={
        "title": "Updated Course Title via PUT",
        "minutes_per_day": 120,
    })
    assert put_res.status_code == 200, put_res.text
    put_data = put_res.json()
    assert put_data["title"] == "Updated Course Title via PUT"
    assert put_data["minutes_per_day"] == 120
    assert put_data["target_date"] == new_target_date

def test_course_replan_after_edit(temp_db):
    client = TestClient(app)
    
    # 1. Create course
    target_date = (date.today() + timedelta(days=15)).isoformat()
    create_res = client.post("/api/courses", json={
        "title": "Operating Systems",
        "goal_query": "Processes and Concurrency",
        "target_date": target_date,
        "minutes_per_day": 60,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 1,
        "schedule_strategy": "paced",
    })
    course_id = create_res.json()["id"]

    # Ingest mock source & lessons directly in DB
    conn = sqlite3.connect(temp_db)
    source_id = "src-test-1"
    conn.execute("INSERT INTO sources (id, course_id, url, title, source_type, is_approved) VALUES (?, ?, ?, ?, 'video', 1);",
                 (source_id, course_id, "https://youtube.com/watch?v=1", "OS Video"))
    for i in range(1, 6):
        lid = f"les-test-{i}"
        conn.execute("""
            INSERT INTO lessons (id, course_id, source_id, title, summary, start_sec, end_sec, raw_duration_sec, priority, order_index, is_excluded)
            VALUES (?, ?, ?, ?, ?, 0, 1800, 1800, 'core', ?, 0);
        """, (lid, course_id, source_id, f"Lesson {i}", f"Summary {i}", i))
    conn.commit()
    conn.close()

    # Initial replan to generate allocations
    replan_res1 = client.post(f"/api/courses/{course_id}/schedule/replan", json={"mode": "normal"})
    assert replan_res1.status_code == 200, replan_res1.text
    sched1 = replan_res1.json()["schedule"]
    assert len(sched1["days"]) > 0

    # 2. Reschedule with earlier deadline and higher daily spend (simulating Edit Course modal)
    earlier_target = (date.today() + timedelta(days=5)).isoformat()
    patch_res = client.patch(f"/api/courses/{course_id}", json={
        "target_date": earlier_target,
        "minutes_per_day": 120,
        "playback_speed": 1.5,
        "revision_buffer_days": 0,
        "schedule_strategy": "paced",
        "rest_days": [],
    })
    assert patch_res.status_code == 200

    # 3. Call replan endpoint with new parameters
    replan_res2 = client.post(f"/api/courses/{course_id}/schedule/replan", json={
        "mode": "normal",
        "target_date": earlier_target,
        "minutes_per_day": 120,
        "playback_speed": 1.5,
        "revision_buffer_days": 0,
        "schedule_strategy": "paced",
        "rest_days": [],
    })
    assert replan_res2.status_code == 200, replan_res2.text
    data2 = replan_res2.json()
    assert data2["success"] is True
    sched2 = data2["schedule"]
    assert sched2["target_date"] == earlier_target
    assert sched2["minutes_per_day"] == 120
    assert sched2["playback_speed"] == 1.5


def test_instant_repack_zero_llm_and_content_preservation(temp_db, monkeypatch):
    """Verifies that editing exam date (14d -> 7d -> 20d), minutes_per_day, or playback speed
    makes ZERO LLM calls, preserves notes, quizzes, and completed status, and supports 1-click Undo.
    """
    import requests
    orig_post = requests.post
    llm_call_count = [0]

    def mock_post(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if any(h in str(url) for h in ["groq.com", "googleapis.com", "openai.com"]):
            llm_call_count[0] += 1
            raise RuntimeError(f"LLM network call attempted to {url} during deterministic schedule repack!")
        return orig_post(*args, **kwargs)

    monkeypatch.setattr("requests.post", mock_post)

    client = TestClient(app)
    today = date.today()
    target_14d = (today + timedelta(days=14)).isoformat()

    # 1. Create course
    create_res = client.post("/api/courses", json={
        "title": "Automata Theory",
        "goal_query": "Pushdown Automata & Turing Machines",
        "target_date": target_14d,
        "minutes_per_day": 60,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    })
    assert create_res.status_code == 200
    course_id = create_res.json()["id"]

    # Ingest mock concept clips / lessons with note, quiz, and one completed
    conn = sqlite3.connect(temp_db)
    source_id = "src-automata"
    conn.execute(
        "INSERT INTO sources (id, course_id, url, title, source_type, is_approved) VALUES (?, ?, ?, ?, 'video', 1);",
        (source_id, course_id, "https://youtube.com/watch?v=automata", "Automata Lecture")
    )
    for i in range(1, 7):
        lid = f"clip-{i}"
        conn.execute("""
            INSERT INTO lessons (id, course_id, source_id, title, summary, start_sec, end_sec, raw_duration_sec, priority, priority_tag, order_index, is_excluded, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 720, 'core', 'core', ?, 0, 'pending');
        """, (lid, course_id, source_id, f"Concept Clip {i}", f"Summary {i}", (i-1)*720, i*720, i))
        conn.execute("""
            INSERT INTO concept_clips (id, source_id, course_id, order_index, title, start_sec, end_sec, raw_duration_sec, priority_tag, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 720, 'core', 'pending');
        """, (lid, source_id, course_id, i, f"Concept Clip {i}", (i-1)*720, i*720))

    # Add permanent study bundle for Clip 1 (Note + Quiz)
    conn.execute("""
        INSERT INTO notes (id, lesson_id, course_id, content_markdown, is_generated)
        VALUES ('note-clip-1', 'clip-1', ?, '# Concept 1 Structured Notes\n- [02:30] Definition', 1);
    """, (course_id,))
    conn.execute("""
        INSERT INTO quizzes (id, lesson_id, course_id, title, questions_json, score, passed)
        VALUES ('quiz-clip-1', 'clip-1', ?, 'Quiz Clip 1', '[]', 100, 1);
    """, (course_id,))
    conn.commit()
    conn.close()

    # Initial schedule generation
    gen_res = client.post(f"/api/courses/{course_id}/schedule/generate")
    assert gen_res.status_code == 200
    sched0 = gen_res.json()
    first_alloc_id = sched0["days"][0]["allocations"][0]["id"]

    # Mark Clip 1 as completed
    comp_res = client.post(f"/api/courses/{course_id}/schedule/allocations/{first_alloc_id}/complete")
    assert comp_res.status_code == 200

    # Verify Clip 1 completion in DB
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT status FROM lessons WHERE id = 'clip-1';").fetchone()
    assert row[0] == "completed"
    conn.close()

    # --- Replan 1: Compress from 14 days -> 7 days ---
    target_7d = (today + timedelta(days=7)).isoformat()
    replan1 = client.post(f"/api/courses/{course_id}/schedule/replan", json={
        "mode": "normal",
        "target_date": target_7d,
        "minutes_per_day": 90,
    })
    assert replan1.status_code == 200
    res1 = replan1.json()
    assert res1["success"] is True
    assert res1["schedule"]["target_date"] == target_7d
    assert "Pace:" in (res1["diff"].get("pace_change") or "")

    # --- Replan 2: Extend from 7 days -> 20 days and change playback speed to 1.5x ---
    target_20d = (today + timedelta(days=20)).isoformat()
    replan2 = client.post(f"/api/courses/{course_id}/schedule/replan", json={
        "mode": "normal",
        "target_date": target_20d,
        "playback_speed": 1.5,
        "minutes_per_day": 45,
    })
    assert replan2.status_code == 200
    res2 = replan2.json()
    assert res2["success"] is True
    assert res2["schedule"]["target_date"] == target_20d
    assert res2["schedule"]["playback_speed"] == 1.5
    assert res2["schedule"]["minutes_per_day"] == 45

    # --- Assert ZERO LLM calls made during all replan operations ---
    assert llm_call_count[0] == 0, f"Expected 0 LLM calls, but got {llm_call_count[0]}"

    # --- Assert permanent attachment: notes, quizzes, and completion state remained untouched ---
    conn = sqlite3.connect(temp_db)
    note_row = conn.execute("SELECT content_markdown FROM notes WHERE lesson_id = 'clip-1';").fetchone()
    assert note_row is not None
    assert "# Concept 1 Structured Notes" in note_row[0]

    quiz_row = conn.execute("SELECT score, passed FROM quizzes WHERE lesson_id = 'clip-1';").fetchone()
    assert quiz_row is not None
    assert quiz_row[0] == 100
    assert quiz_row[1] == 1

    lesson_status = conn.execute("SELECT status FROM lessons WHERE id = 'clip-1';").fetchone()
    assert lesson_status[0] == "completed"
    conn.close()

    # --- Test 1-click Undo ---
    undo_res = client.post(f"/api/courses/{course_id}/schedule/undo")
    assert undo_res.status_code == 200
    undone_sched = undo_res.json()
    assert undone_sched["target_date"] == target_7d
