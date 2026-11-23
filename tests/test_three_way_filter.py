import pytest
pytestmark = pytest.mark.e2e
"""Playwright and API test suite for the 3-Way Lesson Filter (All vs Concepts vs Examples/Applications).

Validates:
1. 'All' mode includes all videos (both theory and practical examples/applications).
2. 'Concepts' mode includes only theory/concepts and excludes example walkthroughs, problems, and practicals.
3. 'Examples' mode includes only practical examples, problems, walkthroughs, and applications, excluding pure theory.
4. Active visual pill states toggle dynamically between [All], [Concepts], and [Examples] in the UI.
5. Schedule allocations reflow immediately to match the filtered selection.
"""

import time
import socket
import tempfile
import threading
import urllib.request
from pathlib import Path
import pytest
import uvicorn
sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations
from backend.scheduler.engine import generate_schedule

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def filter_test_server():
    """Starts an ephemeral FastAPI test server with a seeded test course with clear concepts and examples."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "filter_test.db"
        apply_migrations(tmp_db_path)

        conn = init_connection(tmp_db_path)
        cid = "filter-test-course"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy)
            VALUES (?, 'Theory of Computation Test Course', 'Learn TOC', '2026-12-31', 60, 1.0, '[]', 0, 'paced');
            """,
            (cid,)
        )
        sid = "filter-test-source"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved)
            VALUES (?, ?, 'youtube_playlist', 'TOC Playlist', 'https://youtube.com/playlist?list=test', 'test_pl', 1);
            """,
            (sid, cid)
        )

        test_lessons = [
            ("l1", cid, sid, "Introduction to Theory of Computation", 600, 0, "core"),
            ("l2", cid, sid, "Finite State Machine (Prerequisites)", 720, 1, "core"),
            ("l3", cid, sid, "Deterministic Finite Automata (Example 1)", 500, 2, "core"),
            ("l4", cid, sid, "Deterministic Finite Automata (Example 2)", 600, 3, "deep_dive"),
            ("l5", cid, sid, "Regular Languages Theory", 450, 4, "core"),
            ("l6", cid, sid, "Non-Deterministic Finite Automata (Solved Problems)", 550, 5, "deep_dive"),
        ]
        for lid, c_id, s_id, title, duration, order_idx, priority in test_lessons:
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, start_sec, end_sec, video_id, video_url, priority, order_index, is_excluded)
                VALUES (?, ?, ?, ?, ?, 0, ?, 'vid_' || ?, 'https://youtube.com/watch?v=test', ?, ?, 0);
                """,
                (lid, c_id, s_id, title, duration, duration, lid, priority, order_idx)
            )

        # Generate initial schedule
        lessons_data = [
            {
                "id": lid,
                "title": title,
                "raw_duration_sec": duration,
                "priority": priority,
                "order_index": order_idx,
                "is_excluded": False,
            }
            for lid, _, _, title, duration, order_idx, priority in test_lessons
        ]
        from datetime import date, timedelta
        sched = generate_schedule(
            course_id=cid,
            lessons=lessons_data,
            start_date=date.today(),
            target_date=date.today() + timedelta(days=10),
            minutes_per_day=60,
            playback_speed=1.0,
            rest_days=[],
            revision_buffer_days=0,
            schedule_strategy="paced",
        )
        for a in sched["allocations"]:
            conn.execute(
                """
                INSERT INTO schedule_allocations (
                    id, course_id, lesson_id, scheduled_date, split_index, split_count,
                    allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0);
                """,
                (a.id, cid, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes)
            )
        conn.commit()
        conn.close()

        def override_get_db():
            conn = init_connection(tmp_db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db

        port = find_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        base_url = f"http://127.0.0.1:{port}"
        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as resp:
                    if resp.status == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        if not started:
            raise RuntimeError(f"Failed to start UI test server on {base_url}")

        yield base_url

        server.should_exit = True
        thread.join(timeout=2)
        app.dependency_overrides.pop(get_db, None)


def test_three_way_filter_ui_flow(filter_test_server):
    """Verifies that clicking [Concepts], [Examples], and [All] updates pill highlights and reflows schedule."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(filter_test_server)
        page.wait_for_selector("#btn-filter-all")
        page.wait_for_selector(".allocation-card")

        btn_all = page.locator("#btn-filter-all")
        btn_concepts = page.locator("#btn-filter-concepts")
        btn_examples = page.locator("#btn-filter-examples")

        # 1. Initial State: 'All' button has active style
        assert "bg-accent" in (btn_all.get_attribute("class") or "")
        assert "bg-accent" not in (btn_concepts.get_attribute("class") or "")
        assert "bg-accent" not in (btn_examples.get_attribute("class") or "")

        # Verify all 6 lessons are initially present in schedule
        alloc_texts = page.locator(".allocation-card").all_inner_texts()
        combined_text = " ".join(alloc_texts)
        assert "Introduction to Theory of Computation" in combined_text
        assert "Deterministic Finite Automata (Example 1)" in combined_text
        assert "Non-Deterministic Finite Automata (Solved Problems)" in combined_text

        # 2. Click 'Concepts'
        btn_concepts.click()
        page.wait_for_timeout(1000)

        # Verify active pill styles
        assert "bg-accent" in (btn_concepts.get_attribute("class") or "")
        assert "bg-accent" not in (btn_all.get_attribute("class") or "")
        assert "bg-accent" not in (btn_examples.get_attribute("class") or "")

        # Verify schedule contains ONLY concepts/theory, NO examples
        alloc_texts = page.locator(".allocation-card").all_inner_texts()
        combined_text = " ".join(alloc_texts)
        assert "Introduction to Theory of Computation" in combined_text
        assert "Finite State Machine (Prerequisites)" in combined_text
        assert "Regular Languages Theory" in combined_text
        assert "Deterministic Finite Automata (Example 1)" not in combined_text
        assert "Deterministic Finite Automata (Example 2)" not in combined_text
        assert "Solved Problems" not in combined_text

        # 3. Click 'Examples'
        btn_examples.click()
        page.wait_for_timeout(1000)

        # Verify active pill styles
        assert "bg-accent" in (btn_examples.get_attribute("class") or "")
        assert "bg-accent" not in (btn_all.get_attribute("class") or "")
        assert "bg-accent" not in (btn_concepts.get_attribute("class") or "")

        # Verify schedule contains ONLY practical examples/applications, NO pure theory
        alloc_texts = page.locator(".allocation-card").all_inner_texts()
        combined_text = " ".join(alloc_texts)
        assert "Deterministic Finite Automata (Example 1)" in combined_text
        assert "Deterministic Finite Automata (Example 2)" in combined_text
        assert "Solved Problems" in combined_text
        assert "Introduction to Theory of Computation" not in combined_text
        assert "Finite State Machine (Prerequisites)" not in combined_text
        assert "Regular Languages Theory" not in combined_text

        # 4. Click 'All' to restore everything
        btn_all.click()
        page.wait_for_timeout(1000)

        # Verify active pill styles
        assert "bg-accent" in (btn_all.get_attribute("class") or "")
        assert "bg-accent" not in (btn_concepts.get_attribute("class") or "")
        assert "bg-accent" not in (btn_examples.get_attribute("class") or "")

        # Verify schedule contains both theory and examples
        alloc_texts = page.locator(".allocation-card").all_inner_texts()
        combined_text = " ".join(alloc_texts)
        assert "Introduction to Theory of Computation" in combined_text
        assert "Deterministic Finite Automata (Example 1)" in combined_text
        assert "Solved Problems" in combined_text

        browser.close()
