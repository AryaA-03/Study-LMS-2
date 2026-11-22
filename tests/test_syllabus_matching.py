"""Unit and API test suite for Syllabus Alignment & Auto-Selection Engine."""

import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations
from backend.scheduler.engine import generate_schedule

def test_syllabus_matching_and_apply_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "syllabus_test.db"
        apply_migrations(tmp_db_path)

        conn = init_connection(tmp_db_path)
        cid = "course-syllabus-test"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy)
            VALUES (?, 'TOC University Course', 'Learn TOC', '2026-12-31', 60, 1.0, '[]', 0, 'paced');
            """,
            (cid,)
        )
        sid = "source-syllabus-test"
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
            ("l3", "Deterministic Finite Automata (DFA)", 500, 2, "core"),
            ("l4", "Non-Deterministic Finite Automata (NFA)", 600, 3, "deep_dive"),
            ("l5", "Regular Languages Theory", 450, 4, "core"),
            ("l6", "Pumping Lemma for Regular Sets", 550, 5, "core"),
            ("l7", "Turing Machine Definition and Design", 800, 6, "deep_dive"),
            ("l8", "Halting Problem and Undecidability", 900, 7, "deep_dive"),
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

        # 1. Match syllabus containing ONLY Unit 1 & Unit 2 (DFA, NFA, Regular Languages, Pumping Lemma)
        # Note: Turing Machine and Halting Problem are deliberately omitted!
        pasted_syllabus = """
        Unit 1: Finite Automata
        Introduction to Theory of Computation, Finite State Machine, Deterministic Finite Automata (DFA), Non-Deterministic Finite Automata (NFA).

        Unit 2: Regular Sets
        Regular Languages Theory, Pumping Lemma for Regular Sets.
        """

        match_resp = client.post(
            f"/api/courses/{cid}/syllabus/match",
            json={"syllabus_text": pasted_syllabus, "strictness": "balanced"}
        )
        assert match_resp.status_code == 200, match_resp.text
        match_data = match_resp.json()

        assert match_data["total_lessons"] == 8
        # l1, l2, l3, l4, l5, l6 should be matched (6 lessons)
        # l7 (Turing Machine) and l8 (Halting Problem) should be UNMATCHED
        lesson_map = {l["id"]: l for l in match_data["lessons"]}

        assert lesson_map["l1"]["is_matched"] is True
        assert lesson_map["l2"]["is_matched"] is True
        assert lesson_map["l3"]["is_matched"] is True
        assert lesson_map["l4"]["is_matched"] is True
        assert lesson_map["l5"]["is_matched"] is True
        assert lesson_map["l6"]["is_matched"] is True

        assert lesson_map["l7"]["is_matched"] is False
        assert lesson_map["l8"]["is_matched"] is False

        assert match_data["matched_lessons_count"] == 6
        assert match_data["matched_percentage"] == 75.0
        # Saved minutes = 800 + 900 = 1700 sec = ~28 minutes
        assert match_data["saved_minutes"] > 20

        # Check topics returned
        assert len(match_data["topics"]) > 0

        # 2. Apply matched lessons
        matched_ids = [l["id"] for l in match_data["lessons"] if l["is_matched"]]
        apply_resp = client.post(
            f"/api/courses/{cid}/syllabus/apply",
            json={
                "syllabus_text": pasted_syllabus,
                "included_lesson_ids": matched_ids,
                "regenerate_schedule": True,
            }
        )
        assert apply_resp.status_code == 200, apply_resp.text
        apply_data = apply_resp.json()
        assert apply_data["included_count"] == 6
        assert apply_data["excluded_count"] == 2
        assert apply_data["schedule_reflowed"] is True

        # 3. Verify schedule only contains matched lessons
        sched_resp = client.get(f"/api/courses/{cid}/schedule")
        assert sched_resp.status_code == 200
        sched = sched_resp.json()
        scheduled_lesson_ids = {alloc["lesson_id"] for day in sched["days"] for alloc in day["allocations"]}

        assert {"l1", "l2", "l3", "l4", "l5", "l6"} == scheduled_lesson_ids
        assert "l7" not in scheduled_lesson_ids
        assert "l8" not in scheduled_lesson_ids

        # 4. Verify GET /api/courses/{cid}/syllabus returns the saved syllabus
        get_syl = client.get(f"/api/courses/{cid}/syllabus")
        assert get_syl.status_code == 200
        syl_data = get_syl.json()
        assert syl_data["syllabus_text"] == pasted_syllabus
        assert syl_data["syllabus_metadata"]["matched_count"] == 6

        app.dependency_overrides.pop(get_db, None)
