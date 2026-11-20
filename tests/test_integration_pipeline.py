"""Integration test for full M1 core loop:

import -> approve -> schedule -> skip -> reflow -> undo
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
        # Run migrations
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

    # 1. Create a course
    course_payload = {
        "title": "DBMS Final Exam Prep",
        "goal_query": "Database Management Systems",
        "source_preferences": "freeCodeCamp",
        "target_date": "2026-12-15",
        "minutes_per_day": 90,
        "playback_speed": 1.5,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
    }
    resp = client.post("/api/courses", json=course_payload)
    assert resp.status_code == 200
    course_data = resp.json()
    course_id = course_data["id"]
    assert course_data["title"] == "DBMS Final Exam Prep"
    assert course_data["playback_speed"] == 1.5

    # 2. Add manual source & lessons (mocking YouTube import)
    from backend.services.youtube import split_video_into_lessons
    mock_meta = {
        "id": "mock_dbms_vid",
        "title": "DBMS Full Course",
        "duration": 10800,  # 3 hours = 180 min
        "chapters": [
            {"title": "Relational Models", "start_time": 0, "end_time": 3600},
            {"title": "SQL & Queries", "start_time": 3600, "end_time": 7200},
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
                start_sec, end_sec, raw_duration_sec, priority, order_index, chapter_title
            ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?);
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
                "core" if idx < 2 else "deep-dive",
                idx,
                l["chapter_title"],
            ),
        )
    conn.commit()
    conn.close()

    # 3. Generate Schedule
    resp_sched = client.post(f"/api/courses/{course_id}/schedule/generate")
    assert resp_sched.status_code == 200
    sched_data = resp_sched.json()
    assert sched_data["course_id"] == course_id
    assert len(sched_data["days"]) > 0
    # Total raw = 180 min; at 1.5x speed -> 120 effective minutes
    assert abs(sched_data["total_effective_minutes"] - 120.0) < 0.5
    assert sched_data["remaining_effective_minutes"] > 0
    assert sched_data["projected_finish_date"] is not None

    # Get first day with allocations
    days_with_allocs = [d for d in sched_data["days"] if len(d["allocations"]) > 0]
    assert len(days_with_allocs) > 0
    first_alloc = days_with_allocs[0]["allocations"][0]
    alloc_id = first_alloc["id"]

    # 4. Toggle completion
    resp_toggle = client.post(f"/api/courses/{course_id}/schedule/allocations/{alloc_id}/toggle")
    assert resp_toggle.status_code == 200
    toggled = resp_toggle.json()
    assert toggled["is_completed"] is True

    # Check updated stats
    resp_course = client.get(f"/api/courses/{course_id}")
    course_stats = resp_course.json()
    assert course_stats["completed_effective_minutes"] > 0
    assert course_stats["completion_percentage"] > 0

    # 5. Skip an allocation and verify reflow
    # Find second allocation
    second_alloc = None
    for d in days_with_allocs:
        for a in d["allocations"]:
            if a["id"] != alloc_id:
                second_alloc = a
                break
        if second_alloc:
            break

    assert second_alloc is not None
    resp_skip = client.post(f"/api/courses/{course_id}/schedule/allocations/{second_alloc['id']}/skip")
    assert resp_skip.status_code == 200

    # 6. Replan with compress
    replan_payload = {
        "mode": "compress",
        "minutes_per_day": 40,
        "playback_speed": 1.0,
    }
    resp_replan = client.post(f"/api/courses/{course_id}/schedule/replan", json=replan_payload)
    assert resp_replan.status_code == 200
    replan_data = resp_replan.json()
    assert replan_data["success"] is True
    assert replan_data["snapshot_id"] is not None
    assert "diff" in replan_data

    # 7. Undo replan
    resp_undo = client.post(f"/api/courses/{course_id}/schedule/undo")
    assert resp_undo.status_code == 200
    undo_sched = resp_undo.json()
    assert undo_sched["course_id"] == course_id

    # Verify course settings restored to speed = 1.5
    resp_course_restored = client.get(f"/api/courses/{course_id}")
    assert resp_course_restored.json()["playback_speed"] == 1.5
