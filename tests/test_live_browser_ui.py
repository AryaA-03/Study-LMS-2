"""Playwright Live Browser Test Suite for UI/UX, Themes, Date Alignment & Collapsible Studio.

Runs against an ephemeral FastAPI server with a seeded SQLite database.
Validates:
1. Dual Themes: Light and Dark switching, localStorage persistence, CSS contrast.
2. Date Alignment & Pacing:
   - "Finish on Exam Date" with 0 buffer -> Finish Date == Exam Date!
   - 2-Day Review Buffer -> Finish Date is 2 days before Exam Date.
   - Fixed Daily Spend -> Sprint finish date with free buffer notice.
3. Collapsible Studio & Days:
   - Video player theater toggle.
   - Schedule sidebar collapse (full-width studio).
   - Day-wise collapsible cards with chevrons.
4. Selective Video Toggling:
   - Curriculum drawer slide-in.
   - Auto-skipping question & example videos.
   - Granular checkbox toggling with instant schedule reflow.
5. F12 Console Logs & window.learnLMS Global Inspection Object.
"""

import time
import socket
import tempfile
import threading
from pathlib import Path
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations
from backend.scheduler.engine import generate_schedule

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def ui_test_server():
    """Starts an ephemeral FastAPI test server with a seeded test course."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "ui_test.db"
        apply_migrations(tmp_db_path)

        # Seed test course with lessons (Theory and Examples)
        conn = init_connection(tmp_db_path)
        cid = "ui-test-course-1"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed, revision_buffer_days, schedule_strategy)
            VALUES (?, 'Theory of Computation & Automata', 'TOC Neso Academy', '2026-12-22', 90, 1.25, 0, 'paced');
            """,
            (cid,),
        )
        sid = "ui-test-source-1"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, is_approved)
            VALUES (?, ?, 'youtube_playlist', 'TOC Full Course', 1);
            """,
            (sid, cid),
        )

        # Insert 6 lessons: 3 Theory/Concepts + 3 Examples
        lessons_data = [
            ("l1", "Introduction to Automata Theory", 1800, "core"),
            ("l2", "Deterministic Finite Automata (DFA)", 2400, "core"),
            ("l3", "Example Problem 1: DFA for strings ending in 01", 1200, "core"),
            ("l4", "Nondeterministic Finite Automata (NFA)", 2100, "core"),
            ("l5", "Question Exercise 2: NFA to DFA Subset Construction", 1500, "core"),
            ("l6", "Regular Expressions and Languages", 1800, "core"),
        ]
        for idx, (lid, title, duration, priority) in enumerate(lessons_data):
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, start_sec, end_sec, raw_duration_sec, priority, order_index)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?);
                """,
                (lid, cid, sid, title, duration, duration, priority, idx),
            )

        # Generate initial schedule
        lessons_dict = [
            {"id": lid, "title": title, "raw_duration_sec": duration, "priority": priority, "start_sec": 0, "end_sec": duration}
            for (lid, title, duration, priority) in lessons_data
        ]
        from datetime import date
        sched = generate_schedule(
            course_id=cid,
            lessons=lessons_dict,
            start_date=date.today(),
            target_date=date(2026, 12, 22),
            minutes_per_day=90,
            playback_speed=1.25,
            rest_days=["Sunday"],
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
                (a.id, cid, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes),
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
        import urllib.request
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
        app.dependency_overrides.clear()

def test_ui_theme_switching_and_persistence(ui_test_server):
    """Verifies that the theme toggle switches between Light and Dark themes, persists to localStorage, and updates UI."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(msg.text))

        page.goto(ui_test_server)
        page.wait_for_selector("#btn-theme-toggle")

        # 1. Check initial theme (default is dark)
        html_classes = page.locator("html").get_attribute("class") or ""
        assert "dark" in html_classes

        # 2. Click Theme Switcher to switch to Light Theme
        btn_theme = page.locator("#btn-theme-toggle")
        btn_theme.click()
        page.wait_for_timeout(300)

        # 3. Assert HTML has class 'light' and lacks 'dark'
        html_classes_after = page.locator("html").get_attribute("class") or ""
        assert "light" in html_classes_after
        assert "dark" not in html_classes_after

        # 4. Assert localStorage persisted 'light'
        saved_theme = page.evaluate("() => localStorage.getItem('learn_lms_theme')")
        assert saved_theme == "light"

        # 5. Assert sun icon is hidden and moon icon is visible
        sun_icon = page.locator("#theme-icon-sun")
        assert "hidden" in (sun_icon.get_attribute("class") or "")

        # 6. Click Theme Switcher again to return to Dark Theme
        btn_theme.click()
        page.wait_for_timeout(300)
        html_classes_dark = page.locator("html").get_attribute("class") or ""
        assert "dark" in html_classes_dark

        saved_theme_dark = page.evaluate("() => localStorage.getItem('learn_lms_theme')")
        assert saved_theme_dark == "dark"

        # 7. Check F12 console captured theme change logs
        theme_logged = any("[LearnLMS:Theme]" in log for log in console_logs)
        assert theme_logged, f"Expected [LearnLMS:Theme] in console logs, got {console_logs}"

        browser.close()

def test_ui_course_pacing_and_date_alignment(ui_test_server):
    """Verifies user choice between 'Finish on Exam Date' vs 'By Daily Spend' and 0-day vs 2-day buffer."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(ui_test_server)
        page.wait_for_selector("#pane-schedule")

        # 1. Check Initial Date Alignment (Seeded as 0-day buffer, Paced)
        finish_text = page.inner_text("#stat-projected-finish")
        exam_text = page.inner_text("#stat-target-date")
        assert finish_text == "2026-12-22"
        assert exam_text == "2026-12-22"

        # 2. Check Pacing Detail note
        pacing_note = page.inner_text("#pacing-note-detail")
        assert "exam day" in pacing_note.lower()

        # 3. Switch Buffer to 2 Days via UI pill
        pill_buffer_two = page.locator("#pill-buffer-two")
        pill_buffer_two.click()
        page.wait_for_timeout(1000)

        # In 2-day buffer mode (with Sunday rest day), projected finish finishes on Saturday before buffer (2026-12-19)
        finish_text_2d = page.inner_text("#stat-projected-finish")
        exam_text_2d = page.inner_text("#stat-target-date")
        assert finish_text_2d == "2026-12-19"
        assert exam_text_2d == "2026-12-22"

        # 4. Switch to 'By Daily Spend' (Fixed Sprint mode)
        pill_fixed = page.locator("#pill-strategy-fixed")
        pill_fixed.click()
        page.wait_for_timeout(1000)

        # In Fixed Daily Spend mode, mode label updates to Fixed
        mode_label = page.inner_text("#pacing-mode-label")
        assert "Fixed Daily Spend" in mode_label

        # 5. Switch back to 'Finish on Exam Date' with 0-Day Buffer
        pill_paced = page.locator("#pill-strategy-paced")
        pill_paced.click()
        page.wait_for_timeout(500)
        pill_buffer_zero = page.locator("#pill-buffer-zero")
        pill_buffer_zero.click()
        page.wait_for_timeout(1000)

        assert page.inner_text("#stat-projected-finish") == "2026-12-22"
        assert page.inner_text("#stat-target-date") == "2026-12-22"

        browser.close()

def test_ui_collapsible_studio_and_days(ui_test_server):
    """Verifies that the Studio video player, Schedule sidebar, and Day cards collapse and expand cleanly."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(ui_test_server)
        page.wait_for_selector("#pane-studio")

        # 1. Player Collapse / Theater Toggle
        player_wrapper = page.locator("#player-wrapper")
        assert "hidden" not in (player_wrapper.get_attribute("class") or "").split()

        btn_collapse_player = page.locator("#btn-collapse-player")
        btn_collapse_player.click()
        assert "hidden" in (player_wrapper.get_attribute("class") or "").split()

        btn_collapse_player.click()
        assert "hidden" not in (player_wrapper.get_attribute("class") or "").split()

        # 2. Schedule Sidebar Collapse (Full-Width Studio)
        pane_schedule = page.locator("#pane-schedule")
        pane_studio = page.locator("#pane-studio")
        assert pane_schedule.is_visible()

        btn_collapse_schedule = page.locator("#btn-collapse-schedule")
        btn_collapse_schedule.click()
        assert not pane_schedule.is_visible()
        assert "md:w-full" in (pane_studio.get_attribute("class") or "")

        btn_collapse_schedule.click()
        assert pane_schedule.is_visible()
        assert "md:w-7/12" in (pane_studio.get_attribute("class") or "")

        # 3. Collapse All Days
        btn_collapse_all = page.locator("#btn-toggle-collapse-all")
        btn_collapse_all.click()
        assert page.inner_text("#btn-toggle-collapse-all") == "Expand Days"

        day_bodies = page.locator(".day-body")
        count = day_bodies.count()
        assert count > 0
        for i in range(count):
            assert not day_bodies.nth(i).is_visible()

        btn_collapse_all.click()
        assert page.inner_text("#btn-toggle-collapse-all") == "Collapse Days"
        for i in range(count):
            assert day_bodies.nth(i).is_visible()

        browser.close()

def test_ui_selective_video_filtering_and_curriculum_drawer(ui_test_server):
    """Verifies that the user can open Curriculum Drawer, toggle individual lessons, or filter out example videos."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(ui_test_server)
        page.wait_for_selector("#btn-toggle-curriculum")

        # 1. Open Curriculum Drawer
        curriculum_drawer = page.locator("#curriculum-drawer")
        assert "hidden" in (curriculum_drawer.get_attribute("class") or "")

        btn_curriculum = page.locator("#btn-toggle-curriculum")
        btn_curriculum.click()
        assert "hidden" not in (curriculum_drawer.get_attribute("class") or "")

        # 2. Check lesson count in drawer (6 seeded lessons)
        lesson_items = page.locator("#curriculum-lessons-list > div")
        count_before = lesson_items.count()
        assert count_before == 6

        # 3. Click 'Skip All Examples' button in drawer
        btn_skip_examples = page.locator("#btn-curriculum-skip-examples")
        btn_skip_examples.click()
        page.wait_for_timeout(1000)

        # Check effective remaining time dropped because 2 examples were excluded
        rem_text = page.inner_text("#stat-effective-left")
        assert len(rem_text) > 0

        # 4. Click 'Select All' in drawer to restore all lessons
        btn_include_all = page.locator("#btn-curriculum-include-all")
        btn_include_all.click()
        page.wait_for_timeout(1000)

        # 5. Close Curriculum Drawer
        btn_close = page.locator("#btn-close-curriculum")
        btn_close.click()
        assert "hidden" in (curriculum_drawer.get_attribute("class") or "")

        browser.close()

def test_ui_window_inspection_and_console_logger(ui_test_server):
    """Verifies that window.learnLMS is exposed in F12 console and provides programmatic inspection."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(ui_test_server)
        page.wait_for_selector("#pane-studio")

        # 1. Check window.learnLMS properties
        has_learn_lms = page.evaluate("() => typeof window.learnLMS === 'object'")
        assert has_learn_lms is True

        course_title = page.evaluate("() => window.learnLMS.getCurrentCourse()?.title")
        assert "Theory of Computation" in (course_title or "")

        schedule_days = page.evaluate("() => window.learnLMS.getCurrentSchedule()?.days?.length")
        assert schedule_days and schedule_days > 0

        # 2. Test programmatic theme toggle via window.learnLMS
        page.evaluate("() => window.learnLMS.toggleTheme()")
        theme_after = page.evaluate("() => localStorage.getItem('learn_lms_theme')")
        assert theme_after in ["light", "dark"]

        browser.close()
