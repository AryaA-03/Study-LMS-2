"""Integration test for full M1 core loop:

import -> approve -> schedule -> skip -> reflow -> filter -> undo
Uses an isolated temporary database.
"""

import tempfile
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations

@pytest.fixture
def test_setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "test_loop.db"
        apply_migrations(tmp_db_path)

        def override_get_db():
            conn = init_connection(tmp_db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client, tmp_db_path
        app.dependency_overrides.clear()

def test_full_m1_core_pipeline(test_setup):
    client, tmp_db_path = test_setup

    # 1. Create a course with schedule_strategy = 'paced'
    course_payload = {
        "title": "DBMS Final Exam Prep",
        "goal_query": "Database Management Systems",
        "source_preferences": "freeCodeCamp",
        "target_date": "2026-12-15",
        "minutes_per_day": 90,
        "playback_speed": 1.5,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    }
    resp = client.post("/api/courses", json=course_payload)
    assert resp.status_code == 200
    course_data = resp.json()
    course_id = course_data["id"]
    assert course_data["title"] == "DBMS Final Exam Prep"
    assert course_data["playback_speed"] == 1.5
    assert course_data["schedule_strategy"] == "paced"

    # 2. Add manual source & lessons (mocking YouTube import)
    from backend.services.youtube import split_video_into_lessons
    mock_meta = {
        "id": "mock_dbms_vid",
        "title": "DBMS Full Course",
        "duration": 10800,  # 3 hours = 180 min
        "chapters": [
            {"title": "Relational Models", "start_time": 0, "end_time": 3600},
            {"title": "SQL & Queries Example 1", "start_time": 3600, "end_time": 7200},
            {"title": "Transactions & Concurrency", "start_time": 7200, "end_time": 10800},
        ],
    }

    # Seed source and lessons directly in the temp DB
    conn = init_connection(tmp_db_path)
    source_id = "s-mock-1"
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved)
        VALUES (?, ?, 'youtube_video', 'DBMS Full Course', 'https://youtu.be/mock_dbms_vid', 'mock_dbms_vid', 1);
        """,
        (source_id, course_id),
    )

    lessons = split_video_into_lessons(mock_meta)
    for idx, l in enumerate(lessons):
        conn.execute(
            """
            INSERT INTO lessons (
                id, course_id, source_id, title, summary, video_id, video_url,
                start_sec, end_sec, raw_duration_sec, priority, order_index, chapter_title, is_excluded
            ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 0);
            """,
            (
                f"l-{idx}",
                course_id,
                source_id,
                l["title"],
                l["video_id"],
                l["video_url"],
                l["start_sec"],
                l["end_sec"],
                l["raw_duration_sec"],
                "core" if idx != 1 else "deep-dive",
                idx,
                l["chapter_title"],
            ),
        )
    conn.commit()
    conn.close()

    # 3. Generate Schedule (Paced mode)
    resp_sched = client.post(f"/api/courses/{course_id}/schedule/generate")
    assert resp_sched.status_code == 200
    sched_data = resp_sched.json()
    assert sched_data["course_id"] == course_id
    assert len(sched_data["days"]) > 0
    assert abs(sched_data["total_effective_minutes"] - 120.0) < 0.5
    assert sched_data["remaining_effective_minutes"] > 0
    assert sched_data["projected_finish_date"] is not None
    assert sched_data["effective_daily_target_minutes"] > 0

    # 4. Smart Filtering: Exclude example videos
    filter_payload = {"include_examples": False}
    resp_filter = client.post(f"/api/courses/{course_id}/lessons/filter", json=filter_payload)
    assert resp_filter.status_code == 200
    filtered_lessons = resp_filter.json()
    # "SQL & Queries Example 1" should be marked is_excluded = True
    ex_lesson = [l for l in filtered_lessons if "Example" in l["title"]][0]
    assert ex_lesson["is_excluded"] is True

    # 5. Toggle Individual Lesson Exclusion
    resp_toggle_ex = client.post(f"/api/courses/{course_id}/lessons/{ex_lesson['id']}/toggle-exclude")
    assert resp_toggle_ex.status_code == 200
    assert resp_toggle_ex.json()["is_excluded"] is False

    # 6. Toggle Completion
    days_with_allocs = [d for d in sched_data["days"] if len(d["allocations"]) > 0]
    first_alloc = days_with_allocs[0]["allocations"][0]
    alloc_id = first_alloc["id"]

    resp_toggle = client.post(f"/api/courses/{course_id}/schedule/allocations/{alloc_id}/toggle")
    assert resp_toggle.status_code == 200
    toggled = resp_toggle.json()
    assert toggled["is_completed"] is True

    # 7. Skip an allocation and verify reflow
    second_alloc = None
    for d in days_with_allocs:
        for a in d["allocations"]:
            if a["id"] != alloc_id:
                second_alloc = a
                break
        if second_alloc:
            break

    if second_alloc:
        resp_skip = client.post(f"/api/courses/{course_id}/schedule/allocations/{second_alloc['id']}/skip")
        assert resp_skip.status_code == 200

    # 8. Replan with compress and strategy switch to 'fixed'
    replan_payload = {
        "mode": "compress",
        "schedule_strategy": "fixed",
        "minutes_per_day": 40,
        "playback_speed": 1.0,
    }
    resp_replan = client.post(f"/api/courses/{course_id}/schedule/replan", json=replan_payload)
    assert resp_replan.status_code == 200
    replan_data = resp_replan.json()
    assert replan_data["success"] is True
    assert replan_data["snapshot_id"] is not None

    # 9. Undo replan
    resp_undo = client.post(f"/api/courses/{course_id}/schedule/undo")
    assert resp_undo.status_code == 200
    undo_sched = resp_undo.json()
    assert undo_sched["course_id"] == course_id

    # Verify course settings restored to speed = 1.5 and strategy = paced
    resp_course_restored = client.get(f"/api/courses/{course_id}")
    assert resp_course_restored.json()["playback_speed"] == 1.5
    assert resp_course_restored.json()["schedule_strategy"] == "paced"


def test_source_confirmation_background_notes(test_setup):
    """Verify that confirming sources triggers pregenerate_initial_notes in background,
    generating notes for the first 3 lessons in order_index ASC without touching later lessons.
    """
    client, tmp_db_path = test_setup

    # 1. Create a course
    course_payload = {
        "title": "Machine Learning Fundamentals",
        "goal_query": "Machine Learning",
        "target_date": "2026-12-30",
        "minutes_per_day": 60,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 1,
        "schedule_strategy": "paced",
    }
    resp = client.post("/api/courses", json=course_payload)
    assert resp.status_code == 200
    course_id = resp.json()["id"]

    # 2. Insert candidate source and 5 lessons directly
    conn = init_connection(tmp_db_path)
    source_id = "s-ml-cand"
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved)
        VALUES (?, ?, 'youtube_video', 'ML Intro', 'https://youtu.be/ml_intro', 'ml_intro', 0);
        """,
        (source_id, course_id),
    )

    for i in range(5):
        lid = f"les-ml-{i}"
        conn.execute(
            """
            INSERT INTO lessons (
                id, course_id, source_id, title, summary, video_id, video_url,
                start_sec, end_sec, raw_duration_sec, priority, order_index, is_excluded
            ) VALUES (?, ?, ?, ?, '', 'ml_intro', 'https://youtu.be/ml_intro', ?, ?, 600, 'core', ?, 0);
            """,
            (lid, course_id, source_id, f"ML Lesson {i}", i * 600, (i + 1) * 600, i),
        )
        # Add a chunk for each lesson so note generation has text
        cid = f"chk-ml-{i}"
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, content, token_count, start_sec, end_sec)
            VALUES (?, ?, ?, ?, 0, ?, 20, ?, ?);
            """,
            (cid, course_id, source_id, lid, f"Key concepts of Machine Learning topic {i}", i * 600, (i + 1) * 600),
        )
    conn.commit()
    conn.close()

    # 3. Approve / Confirm the source via POST /api/courses/{course_id}/sources/confirm
    confirm_payload = {
        "source_ids_to_approve": [source_id],
        "source_ids_to_reject": [],
    }
    resp_confirm = client.post(f"/api/courses/{course_id}/sources/confirm", json=confirm_payload)
    assert resp_confirm.status_code == 200
    assert len(resp_confirm.json()) == 1

    # 4. Check that notes were pre-generated for the first 3 lessons (order_index 0, 1, 2)
    conn = init_connection(tmp_db_path)
    notes_rows = conn.execute(
        "SELECT lesson_id, is_generated, content_markdown FROM notes WHERE course_id = ? ORDER BY lesson_id;",
        (course_id,),
    ).fetchall()
    conn.close()

    generated_lesson_ids = {r["lesson_id"] for r in notes_rows if r["is_generated"] == 1 and r["content_markdown"]}
    assert "les-ml-0" in generated_lesson_ids
    assert "les-ml-1" in generated_lesson_ids
    assert "les-ml-2" in generated_lesson_ids

    # Lessons 3 and 4 should NOT have pre-generated notes
    assert "les-ml-3" not in generated_lesson_ids
    assert "les-ml-4" not in generated_lesson_ids


def test_replan_course_schedule_and_trigger_reflow(test_setup):
    """Verify replan_course_schedule helper and trigger_course_reflow after tested out lessons."""
    from backend.routers.schedule import replan_course_schedule, trigger_course_reflow
    client, tmp_db_path = test_setup

    conn = init_connection(tmp_db_path)
    course_id = "c-reflow-test"
    conn.execute(
        """
        INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy)
        VALUES (?, 'Reflow Test Course', 'Reflow', '2026-12-15', 60, 1.0, '[]', 2, 'fixed');
        """,
        (course_id,),
    )
    source_id = "s-reflow-1"
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved)
        VALUES (?, ?, 'youtube_video', 'Reflow Source', 'https://youtu.be/reflow', 'reflow', 1);
        """,
        (source_id, course_id),
    )

    for i in range(4):
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, source_id, title, summary, video_id, video_url, start_sec, end_sec, raw_duration_sec, priority, order_index, is_excluded, is_tested_out)
            VALUES (?, ?, ?, ?, '', 'reflow', 'https://youtu.be/reflow', 0, 1800, 1800, 'core', ?, 0, 0);
            """,
            (f"l-rf-{i}", course_id, source_id, f"Reflow Lesson {i}", i),
        )
    conn.commit()

    # 1. Test replan_course_schedule
    replan_res = replan_course_schedule(course_id=course_id, db=conn, mode="normal", minutes_per_day=60)
    assert replan_res.success is True
    assert replan_res.snapshot_id is not None

    allocs = conn.execute("SELECT * FROM schedule_allocations WHERE course_id = ?;", (course_id,)).fetchall()
    assert len(allocs) > 0

    # 2. Mark lesson 0 as tested out and trigger reflow
    conn.execute("UPDATE lessons SET is_tested_out = 1 WHERE id = 'l-rf-0';")
    conn.commit()

    trigger_course_reflow(course_id, conn)

    # 3. Verify lesson 0 is excluded from reflowed allocations
    reflowed_allocs = conn.execute(
        "SELECT * FROM schedule_allocations WHERE course_id = ? ORDER BY scheduled_date ASC;",
        (course_id,),
    ).fetchall()
    conn.close()

    reflowed_lesson_ids = {a["lesson_id"] for a in reflowed_allocs}
    assert "l-rf-0" not in reflowed_lesson_ids
    assert "l-rf-1" in reflowed_lesson_ids
    assert "l-rf-2" in reflowed_lesson_ids
    assert "l-rf-3" in reflowed_lesson_ids

