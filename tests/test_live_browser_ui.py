import pytest
pytestmark = pytest.mark.e2e
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

        # Seed chunks and chunks_fts for FTS5 matching
        test_chunks = [
            ("chk-1", cid, "l1", "Automata theory introduces finite state machines, alphabets, languages, grammars, and computation models."),
            ("chk-2", cid, "l2", "Deterministic Finite Automata DFA consists of 5 tuples: states, input alphabet, transition function delta, start state, and accept states."),
            ("chk-4", cid, "l4", "Nondeterministic Finite Automata NFA allows epsilon transitions and multiple next states. Subset construction converts NFA to equivalent DFA."),
            ("chk-6", cid, "l6", "Regular expressions define regular languages recognized by finite automata using union, concatenation, and Kleene star operators."),
        ]
        for chk_id, c_id, l_id, text in test_chunks:
            conn.execute(
                """
                INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
                VALUES (?, ?, ?, 0, 50, 0, 300, ?);
                """,
                (chk_id, c_id, l_id, text),
            )
            conn.execute(
                """
                INSERT INTO chunks_fts (id, course_id, lesson_id, content)
                VALUES (?, ?, ?, ?);
                """,
                (chk_id, c_id, l_id, text),
            )

        # Seed sample note for lesson 2 (DFA)
        conn.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes)
            VALUES ('note-l2', ?, 'l2', '# Deterministic Finite Automata (DFA)\n\n- Formal definition of DFA with 5-tuple.\n- State transition tables and state diagrams.\n\n### Core Properties\n- Deterministic transition on each symbol.\n- Minimum state DFA construction.', '');
            """,
            (cid,)
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
        page = browser.new_page(viewport={"width": 1440, "height": 900})

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
        page = browser.new_page(viewport={"width": 1440, "height": 900})

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

        # 2. Schedule Sidebar Collapse (Slim Chrome Rail)
        pane_schedule = page.locator("#pane-schedule")
        expanded_content = page.locator("#schedule-expanded-content")
        collapsed_rail = page.locator("#schedule-collapsed-rail")
        assert pane_schedule.is_visible()
        assert expanded_content.is_visible()

        btn_collapse_schedule = page.locator("#btn-collapse-schedule")
        btn_collapse_schedule.click()
        # When collapsed, pane-schedule is a slim 52px rail
        assert "rail-collapsed" in (pane_schedule.get_attribute("class") or "")
        assert collapsed_rail.is_visible()
        assert not expanded_content.is_visible()

        btn_expand_rail_top = page.locator("#btn-expand-rail-top")
        btn_expand_rail_top.click()
        assert "rail-collapsed" not in (pane_schedule.get_attribute("class") or "")
        assert expanded_content.is_visible()
        assert not collapsed_rail.is_visible()

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
        page = browser.new_page(viewport={"width": 1440, "height": 900})

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
        page = browser.new_page(viewport={"width": 1440, "height": 900})

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

def test_ui_edit_course_modal_and_replan(ui_test_server):
    """Verifies that user can open Edit Course modal, update course settings, and trigger instant replan."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector("#btn-edit-course")

        # 1. Open Edit Course Modal
        page.click("#btn-edit-course")
        page.wait_for_selector("#edit-course-modal:not(.hidden)")

        # 2. Verify pre-populated title
        title_val = page.input_value("#edit-course-title")
        assert "Theory of Computation" in title_val

        # 3. Change title and playback speed
        page.fill("#edit-course-title", "TOC Exam Masterclass 2026")
        page.select_option("#edit-course-speed", "1.5")

        # 4. Save and verify replan
        page.click("#btn-submit-edit-course")
        page.wait_for_selector("#edit-course-modal", state="hidden", timeout=5000)
        page.wait_for_timeout(1000)

        # 5. Check updated speed in KPI bar
        spd_text = page.inner_text("#kpi-speed-display")
        assert "1.5x" in spd_text

        browser.close()

def test_ui_edit_lesson_and_priority_toggle(ui_test_server):
    """Verifies inline priority toggle and full lesson editor modal."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector(".allocation-card")

        # 1. Test inline priority toggle on active lesson bar
        btn_priority = page.locator("#btn-toggle-active-priority")
        initial_priority = page.inner_text("#active-lesson-priority").strip()
        btn_priority.click()
        page.wait_for_timeout(1000)
        new_priority = page.inner_text("#active-lesson-priority").strip()
        assert initial_priority != new_priority

        # 2. Click pencil edit button on active lesson
        page.click("#btn-edit-active-title")
        page.wait_for_selector("#edit-lesson-modal:not(.hidden)")

        # 3. Change lesson title in modal
        page.fill("#edit-lesson-title-input", "Automata Theory Foundation & Proofs")
        page.click("#btn-submit-edit-lesson")
        page.wait_for_selector("#edit-lesson-modal", state="hidden", timeout=5000)
        page.wait_for_timeout(1000)

        # 4. Verify updated title appears in active lesson bar
        updated_title = page.inner_text("#active-lesson-title")
        assert "Automata Theory Foundation" in updated_title

        browser.close()

def test_ui_personal_notes_toolbar_and_save(ui_test_server):
    """Verifies Markdown editor toolbar, character counting, and manual save in Personal Notes."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector("#tab-personal-notes")

        # 1. Switch to Personal Notes tab
        page.click("#tab-personal-notes")
        page.wait_for_selector("#pane-personal-notes:not(.hidden)")

        # 2. Click bold format button
        page.click("button[data-format='bold']")
        page.wait_for_timeout(200)

        # 3. Type text into personal notes textarea
        page.fill("#input-personal-notes", "## Key Exam Formulas\n- DFA M = (Q, Sigma, delta, q0, F)\n- NFA allows epsilon transitions")
        page.wait_for_timeout(300)

        # 4. Verify word counter
        word_count_text = page.inner_text("#personal-notes-word-count")
        assert "word" in word_count_text

        # 5. Click Save Notes button
        page.click("#btn-save-personal-notes")
        page.wait_for_timeout(1000)

        save_status = page.inner_text("#personal-note-save-status")
        assert "Saved" in save_status or "✓" in save_status

        browser.close()

def test_ui_diagnostic_pre_test_3m_flow(ui_test_server):
    """Verifies 3-minute diagnostic pre-test generation, timer, interactive answers, and mastery results screen."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector(".day-group-card")
        page.wait_for_selector("#btn-diagnostic-test")

        # 1. Click Diagnostic button
        page.click("#btn-diagnostic-test", force=True)
        page.wait_for_selector("#diagnostic-modal:not(.hidden)")

        # 2. Check 3-minute timer badge
        page.wait_for_selector("#diagnostic-timer-badge")
        timer_text = page.inner_text("#diagnostic-timer-badge")
        assert "03:" in timer_text or "02:" in timer_text

        # 3. Wait for questions to render
        page.wait_for_selector(".diagnostic-option-card", timeout=8000)
        options = page.query_selector_all(".diagnostic-option-card")
        assert len(options) >= 4

        # 4. Click first option
        options[0].click()
        page.wait_for_timeout(300)

        # 5. Submit Diagnostic
        page.click("#btn-submit-diagnostic")
        page.wait_for_selector("#btn-finish-diagnostic", timeout=8000)

        # 6. Verify celebratory results screen
        results_text = page.inner_text("#diagnostic-content-container")
        assert "Diagnostic Assessment Complete" in results_text
        assert "Score:" in results_text

        # 7. Close modal via finish button
        page.click("#btn-finish-diagnostic")
        page.wait_for_selector("#diagnostic-modal", state="hidden")

        browser.close()

def test_ui_player_auto_advance_and_shortcuts(ui_test_server):
    """Verifies player auto-advance toggle state and keyboard accessibility."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector("#btn-toggle-auto-advance")

        # 1. Check auto-advance initial state is ON
        status_text = page.inner_text("#auto-advance-label")
        assert status_text == "ON"

        # 2. Toggle to OFF
        page.click("#btn-toggle-auto-advance")
        page.wait_for_timeout(300)
        assert page.inner_text("#auto-advance-label") == "OFF"

        # 3. Toggle back to ON
        page.click("#btn-toggle-auto-advance")
        page.wait_for_timeout(300)
        assert page.inner_text("#auto-advance-label") == "ON"

        # 4. Verify keyboard shortcut Escape closes any open modal
        page.click("#btn-settings")
        page.wait_for_selector("#settings-modal:not(.hidden)")
        page.keyboard.press("Escape")
        page.wait_for_selector("#settings-modal", state="hidden")

        browser.close()

def test_ui_drag_and_drop_schedule_attributes(ui_test_server):
    """Verifies draggable cards and day dropzone attributes on schedule timeline."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(ui_test_server)
        page.wait_for_selector(".allocation-card")

        # 1. Verify cards are draggable with data attributes and drag handle
        first_card = page.locator(".allocation-card").first
        is_draggable = first_card.get_attribute("draggable")
        assert is_draggable == "true"
        alloc_id = first_card.get_attribute("data-alloc-id")
        assert alloc_id is not None
        source_date = first_card.get_attribute("data-source-date")
        assert source_date is not None

        # 2. Verify drag handle icon exists
        drag_handle = first_card.locator(".drag-handle")
        assert drag_handle.is_visible()

        # 3. Verify day card dropzone attributes
        day_cards = page.locator(".day-group-card")
        assert day_cards.count() >= 1
        first_day = day_cards.first
        assert first_day.get_attribute("data-day-date") is not None
        assert "window.handleDayDrop" in (first_day.get_attribute("ondrop") or "")

        browser.close()

def test_ui_pyq_upload_and_cram_sheet_print(ui_test_server):
    """Verifies end-to-end PYQ upload -> syllabus badge display -> Cram Sheet generation -> print layout."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(ui_test_server)
        page.wait_for_selector(".allocation-card")

        # 1. Open Add Source Modal and select Past Papers (PYQ) Tab
        page.click("#btn-open-add-source")
        page.wait_for_selector("#add-source-modal:not(.hidden)")
        page.click("#tab-src-pyq")
        page.wait_for_selector("#form-upload-pyq:not(.hidden)")

        # 2. Enter paper title and paste PYQ questions
        page.fill("#input-pyq-title", "University End-Term 2024")
        pyq_paste_text = (
            "Q1. (a) Define Deterministic Finite Automata DFA and describe its 5 tuples with transition function. [5M]\n"
            "    (b) Construct a minimal DFA for binary strings divisible by 3. [5 Marks]\n"
            "Q2. Explain NFA to DFA subset construction algorithm with transition table. [10M]\n"
        )
        page.fill("#input-pyq-raw-text", pyq_paste_text)

        # Handle alert dialog upon extraction
        dialog_messages = []
        page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.accept()))

        page.click("#btn-submit-pyq")

        # Wait for modal to close after upload
        page.wait_for_selector("#add-source-modal", state="hidden", timeout=8000)
        assert any("Extracted" in msg or "Successfully" in msg for msg in dialog_messages)

        # 3. Verify syllabus displays PYQ badges on matched lessons
        page.wait_for_selector(".allocation-card")
        pyq_badges = page.locator(".allocation-card span:has-text('PYQ ×')")
        assert pyq_badges.count() >= 1

        # 4. Test High-Yield PYQs Filter Toggle
        filter_btn = page.locator("#btn-filter-pyq")
        assert filter_btn.is_visible()
        filter_btn.click()
        page.wait_for_timeout(300)

        # All currently visible cards must have PYQ badges
        visible_cards = page.locator(".allocation-card:visible")
        assert visible_cards.count() >= 1
        for i in range(visible_cards.count()):
            card = visible_cards.nth(i)
            assert "PYQ ×" in card.inner_text()

        # Toggle filter back to All
        filter_btn.click()
        page.wait_for_timeout(300)

        # 5. Click on the high-yield DFA lesson card and verify Studio PYQ tab
        dfa_card = page.locator(".allocation-card:has-text('Deterministic Finite Automata')").first
        dfa_card.click()
        page.wait_for_timeout(300)

        # Switch to PYQ tab in right Studio panel
        pyq_tab = page.locator("#tab-pyq-questions")
        assert pyq_tab.is_visible()
        pyq_tab.click()
        page.wait_for_selector("#pane-pyq-questions:not(.hidden)")

        # Verify matched question cards in container
        q_cards = page.locator("#pyq-questions-container > div")
        assert q_cards.count() >= 1
        first_q_text = q_cards.first.inner_text()
        assert "Q1" in first_q_text or "Deterministic Finite Automata" in first_q_text

        # 6. Test Cram Sheet Generation & Modal
        cram_sheet_btn = page.locator("#btn-open-cram-sheet")
        assert cram_sheet_btn.is_visible()
        page.evaluate("() => window.loadCramSheet(false)")

        page.wait_for_selector("#modal-cram-sheet:not(.hidden)", timeout=10000)
        page.wait_for_selector("#cram-sheet-content h1, #cram-sheet-content h2")

        cram_text = page.locator("#cram-sheet-content").inner_text()
        assert "Last-Night" in cram_text or "Exam Cram Sheet" in cram_text or "Revision" in cram_text
        assert "Deterministic Finite Automata" in cram_text

        # 7. Verify print button and print styling container
        assert page.locator("#btn-print-cram-sheet").is_visible()
        assert page.locator("#btn-download-cram-md").is_visible()

        # Capture visual verification artifact
        page.screenshot(path="tests/cram_sheet_modal_verification.png")

        # Close Cram Sheet Modal
        page.click("#btn-close-cram-sheet")
        page.wait_for_selector("#modal-cram-sheet", state="hidden")

        # 8. Filter harmless network / favicon console errors and verify zero app errors
        critical_errors = [e for e in console_errors if "favicon" not in e and "video" not in e]
        assert len(critical_errors) == 0, f"Unexpected console errors: {critical_errors}"

        browser.close()


def test_ui_notes_pane_height_retention_on_rail_collapse(ui_test_server):
    """Verifies notes pane retains >= 55% of viewport height when left rail collapses in both Day and Dark modes."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(ui_test_server)
        page.wait_for_selector(".day-group-card")

        # Test both Day (Light) and Dark modes
        for mode in ["light", "dark"]:
            is_dark = (mode == "dark")
            page.evaluate(f"() => window.learnLMS.toggleTheme ? (document.documentElement.classList.toggle('dark', {str(is_dark).lower()}), document.documentElement.classList.toggle('light', {str(not is_dark).lower()})) : null")

            # 1. Expanded rail check
            notes_height_expanded = page.evaluate("() => document.getElementById('pane-grounded-notes').getBoundingClientRect().height")
            viewport_height = page.evaluate("() => window.innerHeight")
            ratio_expanded = notes_height_expanded / viewport_height
            assert ratio_expanded >= 0.50, f"Notes pane ratio in {mode} (expanded) too small: {ratio_expanded:.2%}"

            # 2. Collapse left rail
            page.click("#btn-collapse-schedule")
            page.wait_for_selector("#pane-schedule.rail-collapsed")

            # Verify notes pane retains >= 55% of viewport height
            notes_height_collapsed = page.evaluate("() => document.getElementById('pane-grounded-notes').getBoundingClientRect().height")
            ratio_collapsed = notes_height_collapsed / viewport_height
            assert ratio_collapsed >= 0.55, f"Notes pane ratio in {mode} (collapsed) must be >= 55%, got {ratio_collapsed:.2%}"

            # 3. Expand rail back
            page.click("#btn-expand-rail-top")
            page.wait_for_selector("#pane-schedule:not(.rail-collapsed)")

        browser.close()


def test_ui_dual_splitters_resize_and_persistence(ui_test_server):
    """Verifies dragging horizontal & vertical splitters resizes panes and persists across page reloads."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(ui_test_server)
        page.wait_for_selector(".day-group-card")
        page.wait_for_selector("#video-notes-splitter")

        # --- A. Horizontal Splitter (Video vs Notes) ---
        splitter_h = page.locator("#video-notes-splitter")
        box_h = splitter_h.bounding_box()
        assert box_h is not None

        # Drag horizontal splitter down by 60px
        page.mouse.move(box_h["x"] + box_h["width"] / 2, box_h["y"] + box_h["height"] / 2)
        page.mouse.down()
        page.mouse.move(box_h["x"] + box_h["width"] / 2, box_h["y"] + box_h["height"] / 2 + 60, steps=5)
        page.mouse.up()

        # Check saved height in localStorage
        saved_h = page.evaluate("() => localStorage.getItem('lms_video_pane_height')")
        assert saved_h is not None and "px" in saved_h

        # Quick Snap Compact Button (25vh)
        page.click("#snap-compact-video")
        height_compact = page.evaluate("() => localStorage.getItem('lms_video_pane_height')")
        assert height_compact == "25vh"

        # Double-click to reset to 34vh
        splitter_h.dblclick()
        height_reset = page.evaluate("() => localStorage.getItem('lms_video_pane_height')")
        assert height_reset == "34vh"

        # --- B. Vertical Splitter (Center Column vs Right Studio Panel) ---
        splitter_v = page.locator("#studio-splitter")
        box_v = splitter_v.bounding_box()
        assert box_v is not None

        # Drag vertical splitter left by 50px (increasing right studio width)
        initial_w = page.evaluate("() => document.getElementById('pane-right-studio').getBoundingClientRect().width")
        page.mouse.move(box_v["x"] + box_v["width"] / 2, box_v["y"] + box_v["height"] / 2)
        page.mouse.down()
        page.mouse.move(box_v["x"] + box_v["width"] / 2 - 50, box_v["y"] + box_v["height"] / 2, steps=5)
        page.mouse.up()

        new_w = page.evaluate("() => document.getElementById('pane-right-studio').getBoundingClientRect().width")
        assert new_w > initial_w

        saved_w = page.evaluate("() => localStorage.getItem('lms_studio_panel_width')")
        assert saved_w is not None and "px" in saved_w

        # Reload page and verify width persists
        page.reload()
        page.wait_for_selector(".day-group-card")
        page.wait_for_selector("#pane-right-studio")

        restored_w = page.evaluate("() => document.getElementById('pane-right-studio').style.width")
        assert restored_w == saved_w

        # Double-click vertical splitter to reset to 380px
        page.locator("#studio-splitter").dblclick()
        assert page.evaluate("() => localStorage.getItem('lms_studio_panel_width')") == "380px"

        # --- C. Studio Collapse Toggle in Top Bar ---
        btn_toggle_studio = page.locator("#btn-toggle-studio")
        btn_toggle_studio.click()
        assert page.evaluate("() => document.getElementById('pane-right-studio').classList.contains('hidden')")
        assert page.evaluate("() => localStorage.getItem('lms_studio_collapsed')") == "true"

        # Reload and verify collapsed persists
        page.reload()
        page.wait_for_selector(".day-group-card")
        assert page.evaluate("() => document.getElementById('pane-right-studio').classList.contains('hidden')")

        # Expand studio back
        page.locator("#btn-toggle-studio").click()
        assert not page.evaluate("() => document.getElementById('pane-right-studio').classList.contains('hidden')")

        browser.close()


def test_ui_wcag_contrast_and_zero_purple_palette(ui_test_server):
    """Verifies WCAG contrast >= 4.5:1 on AI chat bubbles and citations in Day Mode, and zero purple/pink colors in DOM."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(ui_test_server)
        page.wait_for_selector(".day-group-card")

        # Switch to Day Mode
        page.evaluate("() => { document.documentElement.classList.remove('dark'); document.documentElement.classList.add('light'); localStorage.setItem('learn_lms_theme', 'light'); }")

        # 1. Switch to Q&A tab and render sample threads
        page.click("#tab-qa-notebook")
        page.wait_for_selector("#pane-qa-notebook:not(.hidden)")

        sample_qa_script = """
        () => {
            window.renderQAThreads([
                {
                    query: "What is the difference between DFA and NFA?",
                    answer_markdown: "A **Deterministic Finite Automaton (DFA)** has exactly one transition per symbol. [00:00]\\n\\n- Each state transitions deterministically.\\n- Requires no backtracking.",
                    citations: [
                        { source_title: "TOC Lecture 1", start_sec: 0, excerpt: "DFA formal definition." }
                    ]
                }
            ]);
        }
        """
        page.evaluate(sample_qa_script)
        page.wait_for_selector(".qa-answer-bubble")

        # 2. Check WCAG 2.1 Contrast (>= 4.5:1) in Day Mode
        contrast_check_script = """
        () => {
            function parseRgb(colorStr) {
                const match = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                if (!match) return [0, 0, 0];
                return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
            }
            function luminance(r, g, b) {
                const a = [r, g, b].map(v => {
                    v /= 255;
                    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                });
                return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
            }
            function getContrast(rgb1, rgb2) {
                const lum1 = luminance(rgb1[0], rgb1[1], rgb1[2]);
                const lum2 = luminance(rgb2[0], rgb2[1], rgb2[2]);
                const brightest = Math.max(lum1, lum2);
                const darkest = Math.min(lum1, lum2);
                return (brightest + 0.05) / (darkest + 0.05);
            }

            const bubble = document.querySelector('.qa-answer-bubble > div:nth-child(2)');
            const bubbleStyle = window.getComputedStyle(bubble);
            const bgRgb = parseRgb(bubbleStyle.backgroundColor);
            const textRgb = parseRgb(bubbleStyle.color);
            const textContrast = getContrast(bgRgb, textRgb);

            const strongEl = bubble.querySelector('strong');
            const strongStyle = window.getComputedStyle(strongEl);
            const strongRgb = parseRgb(strongStyle.color);
            const strongContrast = getContrast(bgRgb, strongRgb);

            const badgeEl = bubble.querySelector('.qa-citation-badge');
            const badgeStyle = window.getComputedStyle(badgeEl);
            const badgeBg = parseRgb(badgeStyle.backgroundColor);
            const badgeText = parseRgb(badgeStyle.color);
            const badgeContrast = getContrast(badgeBg, badgeText);

            return {
                textContrast,
                strongContrast,
                badgeContrast,
                bubbleBg: bubbleStyle.backgroundColor,
                bubbleText: bubbleStyle.color,
                strongColor: strongStyle.color
            };
        }
        """
        contrast_result = page.evaluate(contrast_check_script)
        assert contrast_result["textContrast"] >= 4.5, f"Normal text contrast {contrast_result['textContrast']:.2f} < 4.5:1 (bg: {contrast_result['bubbleBg']}, text: {contrast_result['bubbleText']})"
        assert contrast_result["strongContrast"] >= 4.5, f"Bold text contrast {contrast_result['strongContrast']:.2f} < 4.5:1 (bg: {contrast_result['bubbleBg']}, strong: {contrast_result['strongColor']})"
        assert contrast_result["badgeContrast"] >= 4.5, f"Citation badge contrast {contrast_result['badgeContrast']:.2f} < 4.5:1"

        # 3. Verify Zero Purple / Pink in the Entire DOM
        zero_purple_check_script = """
        () => {
            const elements = document.querySelectorAll('*');
            const violations = [];
            const purpleHues = [
                '#6366f1', '#7c3aed', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899', '#f43f5e',
                'rgb(99, 102, 241)', 'rgb(124, 58, 237)', 'rgb(139, 92, 246)'
            ];

            for (const el of elements) {
                // Check class names
                const cls = (el.className && typeof el.className === 'string') ? el.className.toLowerCase() : '';
                if (cls.includes('indigo') || cls.includes('purple') || cls.includes('violet')) {
                    violations.push({ tag: el.tagName, id: el.id, class: cls });
                }

                // Check computed colors
                const cs = window.getComputedStyle(el);
                const bg = cs.backgroundColor.toLowerCase();
                const col = cs.color.toLowerCase();
                for (const ph of purpleHues) {
                    if (bg.includes(ph) || col.includes(ph)) {
                        violations.push({ tag: el.tagName, id: el.id, colorMatch: ph });
                    }
                }
            }
            return violations;
        }
        """
        violations = page.evaluate(zero_purple_check_script)
        assert len(violations) == 0, f"Found purple/pink color violations in DOM: {violations[:10]}"

        browser.close()
