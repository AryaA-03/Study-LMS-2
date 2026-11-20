"""Playwright E2E tests for Milestone 2 features:
- Grounded Study Notes with clickable [MM:SS] player seek links
- Personal editable notes with auto-save
- NotebookLM-style tabs switching
- Keyframes UI
"""

import os
import time
import socket
import tempfile
import threading
from pathlib import Path
import pytest
import uvicorn

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def live_server_m2():
    """Runs a real FastAPI server on an ephemeral port with a temporary DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "e2e_m2_app.db"
        apply_migrations(tmp_db_path)

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
            pytest.fail("Failed to start test server for E2E M2")

        yield base_url, tmp_db_path

        server.should_exit = True
        app.dependency_overrides.clear()


def test_e2e_m2_notes_and_tabs(live_server_m2):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed in environment")

    base_url, db_path = live_server_m2

    try:
        # Seed course, lesson, allocation, chunks, and notes into ephemeral DB
        conn = init_connection(db_path)
        cid = "e2e-m2-c1"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed)
            VALUES (?, 'E2E Automata Theory', 'TOC DFA', '2026-12-31', 60, 1.25);
            """,
            (cid,),
        )
        sid = "e2e-m2-s1"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, is_approved)
            VALUES (?, ?, 'youtube_video', 'TOC Lecture 1', 1);
            """,
            (sid, cid),
        )
        lid = "e2e-m2-l1"
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, source_id, title, video_id, start_sec, end_sec, raw_duration_sec, priority, order_index, has_transcript, transcript_type)
            VALUES (?, ?, ?, 'DFA Formal Definition', '58N2N7zJGrQ', 0, 300, 300, 'core', 0, 1, 'captions');
            """,
            (lid, cid, sid),
        )
        conn.execute(
            """
            INSERT INTO schedule_allocations (id, course_id, lesson_id, scheduled_date, split_index, split_count, allocated_start_sec, allocated_end_sec, effective_minutes)
            VALUES ('alloc_1', ?, ?, '2026-11-20', 0, 1, 0, 300, 4.0);
            """,
            (cid, lid)
        )
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
            VALUES ('chk_e2e_1', ?, ?, ?, 0, 50, 0, 120, 'A deterministic finite automaton consists of five tuples: states, alphabet, transition function, start state, and accept states.');
            """,
            (cid, sid, lid)
        )
        conn.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated)
            VALUES ('note_e2e_1', ?, ?, '# DFA Formal Definition\n\n### [00:00] Five Tuples\n- A deterministic finite automaton has states, alphabet, and transitions. `[00:00]` `[ref:chk_e2e_1]`', 'My TOC review note', 1);
            """,
            (cid, lid)
        )
        conn.commit()
        conn.close()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Load application and select seeded course
            page.goto(f"{base_url}/")
            page.wait_for_selector("#course-selector")
            page.select_option("#course-selector", cid)
            page.wait_for_timeout(800)

            # 2. Verify workspace is visible
            workspace_view = page.locator("#workspace-view")
            assert workspace_view.is_visible()

            # 3. Verify Active Lesson and Grounded Notes
            page.wait_for_selector("#active-lesson-title")
            title_text = page.inner_text("#active-lesson-title")
            assert "DFA" in title_text

            page.wait_for_selector("#notes-content")
            notes_html = page.inner_html("#notes-content")
            assert "Five Tuples" in notes_html
            assert "00:00" in notes_html

            # 4. Verify Clickable Timestamp Button Exists
            timestamp_btn = page.locator("#notes-content button").first
            assert timestamp_btn.is_visible()
            timestamp_btn.click()

            # 5. Test NotebookLM-style Personal Notes Tab
            page.click("#tab-personal-notes")
            page.wait_for_timeout(300)

            pane_personal = page.locator("#pane-personal-notes")
            assert pane_personal.is_visible()

            # Check pre-seeded personal note value
            notes_input = page.locator("#input-personal-notes")
            assert notes_input.input_value() == "My TOC review note"

            # Edit personal note and test auto-save
            notes_input.fill("Updated exam formula: M = (Q, Sigma, delta, q0, F)")
            page.wait_for_timeout(1200)  # Wait for 800ms debounce save

            save_status = page.inner_text("#personal-note-save-status")
            assert "Saved" in save_status

            # 6. Switch back to Grounded Notes
            page.click("#tab-grounded-notes")
            page.wait_for_timeout(300)
            pane_grounded = page.locator("#pane-grounded-notes")
            assert pane_grounded.is_visible()

            browser.close()

    except Exception as e:
        if "Executable doesn't exist" in str(e) or "Host system is missing dependencies" in str(e):
            pytest.skip(f"Chromium executable not available in this environment: {e}")
        else:
            raise e
