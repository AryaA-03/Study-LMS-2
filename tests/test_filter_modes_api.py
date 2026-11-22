"""Direct in-memory ASGI test for Lesson Filtering (All vs Concepts vs Examples).

Runs without external sockets or network access using FastAPI TestClient.
Tests:
1. filter_mode = "concepts" includes theory and excludes examples.
2. filter_mode = "examples" includes examples and excludes theory.
3. filter_mode = "all" includes both.
4. Schedule generation succeeds with each mode.
"""

import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations
from backend.scheduler.engine import generate_schedule

def test_filter_modes_and_schedule_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "filter_asgi_test.db"
        apply_migrations(tmp_db_path)

        conn = init_connection(tmp_db_path)
        cid = "test-course-filter-123"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy)
            VALUES (?, 'Theory of Computation Test Course', 'Learn TOC', '2026-12-31', 60, 1.0, '[]', 0, 'paced');
            """,
            (cid,)
        )
        sid = "test-source-filter-123"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved)
            VALUES (?, ?, 'youtube_playlist', 'TOC Playlist', 'https://youtube.com/playlist?list=test', 'test_pl', 1);
            """,
            (sid, cid)
        )

        test_lessons = [
            ("l1", "Introduction to Theory of Computation", 600, 0, "core"),
            ("l2", "Finite State Machine (Prerequisites)", 720, 1, "core"),
            ("l3", "Deterministic Finite Automata (Example 1)", 500, 2, "core"),
            ("l4", "Deterministic Finite Automata (Example 2)", 600, 3, "deep_dive"),
            ("l5", "Regular Languages Theory", 450, 4, "core"),
            ("l6", "Non-Deterministic Finite Automata (Solved Problems)", 550, 5, "deep_dive"),
        ]
        for lid, title, duration, order_idx, priority in test_lessons:
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, start_sec, end_sec, video_id, video_url, priority, order_index, is_excluded)
                VALUES (?, ?, ?, ?, ?, 0, ?, 'vid_' || ?, 'https://youtube.com/watch?v=test', ?, ?, 0);
                """,
                (lid, cid, sid, title, duration, duration, lid, priority, order_idx)
            )

        conn.commit()
        conn.close()

        def override_get_db():
            c = init_connection(tmp_db_path)
            try:
                yield c
                c.commit()
            finally:
                c.close()

        app.dependency_overrides[get_db] = override_get_db

        client = TestClient(app)

        # 1. Test 'concepts' mode
        resp_concepts = client.post(f"/api/courses/{cid}/lessons/filter", json={"filter_mode": "concepts"})
        assert resp_concepts.status_code == 200, resp_concepts.text
        lessons_concepts = resp_concepts.json()
        assert len(lessons_concepts) == 6

        # Check exclusion flags
        excluded_dict = {l["title"]: l["is_excluded"] for l in lessons_concepts}
        # Concepts should be INCLUDED (is_excluded == False)
        assert excluded_dict["Introduction to Theory of Computation"] is False
        assert excluded_dict["Finite State Machine (Prerequisites)"] is False
        assert excluded_dict["Regular Languages Theory"] is False
        # Examples should be EXCLUDED (is_excluded == True)
        assert excluded_dict["Deterministic Finite Automata (Example 1)"] is True
        assert excluded_dict["Deterministic Finite Automata (Example 2)"] is True
        assert excluded_dict["Non-Deterministic Finite Automata (Solved Problems)"] is True

        # Generate schedule with concepts filter active
        sched_res = client.post(f"/api/courses/{cid}/schedule/generate")
        assert sched_res.status_code == 200, sched_res.text
        sched = client.get(f"/api/courses/{cid}/schedule").json()
        sched_lesson_ids = {alloc["lesson_id"] for day in sched["days"] for alloc in day["allocations"]}
        assert "l1" in sched_lesson_ids
        assert "l2" in sched_lesson_ids
        assert "l5" in sched_lesson_ids
        assert "l3" not in sched_lesson_ids
        assert "l4" not in sched_lesson_ids
        assert "l6" not in sched_lesson_ids

        # 2. Test 'examples' mode
        resp_examples = client.post(f"/api/courses/{cid}/lessons/filter", json={"filter_mode": "examples"})
        assert resp_examples.status_code == 200, resp_examples.text
        lessons_examples = resp_examples.json()
        assert len(lessons_examples) == 6

        excluded_dict = {l["title"]: l["is_excluded"] for l in lessons_examples}
        # Examples should be INCLUDED (is_excluded == False)
        assert excluded_dict["Deterministic Finite Automata (Example 1)"] is False
        assert excluded_dict["Deterministic Finite Automata (Example 2)"] is False
        assert excluded_dict["Non-Deterministic Finite Automata (Solved Problems)"] is False
        # Concepts should be EXCLUDED (is_excluded == True)
        assert excluded_dict["Introduction to Theory of Computation"] is True
        assert excluded_dict["Finite State Machine (Prerequisites)"] is True
        assert excluded_dict["Regular Languages Theory"] is True

        # Generate schedule with examples filter active
        sched_res = client.post(f"/api/courses/{cid}/schedule/generate")
        assert sched_res.status_code == 200, sched_res.text
        sched = client.get(f"/api/courses/{cid}/schedule").json()
        sched_lesson_ids = {alloc["lesson_id"] for day in sched["days"] for alloc in day["allocations"]}
        assert "l3" in sched_lesson_ids
        assert "l4" in sched_lesson_ids
        assert "l6" in sched_lesson_ids
        assert "l1" not in sched_lesson_ids
        assert "l2" not in sched_lesson_ids
        assert "l5" not in sched_lesson_ids

        # 3. Test 'all' mode
        resp_all = client.post(f"/api/courses/{cid}/lessons/filter", json={"filter_mode": "all"})
        assert resp_all.status_code == 200, resp_all.text
        lessons_all = resp_all.json()
        assert len(lessons_all) == 6

        excluded_dict = {l["title"]: l["is_excluded"] for l in lessons_all}
        # All should be INCLUDED
        for t, is_exc in excluded_dict.items():
            assert is_exc is False, f"Expected {t} to be included in 'all' mode"

        # Generate schedule with all filter active
        sched_res = client.post(f"/api/courses/{cid}/schedule/generate")
        assert sched_res.status_code == 200, sched_res.text
        sched = client.get(f"/api/courses/{cid}/schedule").json()
        sched_lesson_ids = {alloc["lesson_id"] for day in sched["days"] for alloc in day["allocations"]}
        assert {"l1", "l2", "l3", "l4", "l5", "l6"}.issubset(sched_lesson_ids)

        app.dependency_overrides.pop(get_db, None)
