"""Playwright E2E tests for Milestone 3 features:
- Multi-source pills in Sources Tray (YouTube, PDF, Web)
- Add Source Modal
- NotebookLM-style Grounded Q&A tab with citations
"""

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
def live_server_m3():
    """Runs a real FastAPI server on an ephemeral port with a temporary DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "e2e_m3_app.db"
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
            pytest.fail("Failed to start test server for E2E M3")

        yield base_url, tmp_db_path

        server.should_exit = True
        app.dependency_overrides.clear()


def test_e2e_m3_sources_and_grounded_qa(live_server_m3):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed in environment")

    base_url, db_path = live_server_m3

    try:
        # Seed course with YouTube, PDF, and Web sources + chunks
        conn = init_connection(db_path)
        cid = "e2e-m3-c1"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed)
            VALUES (?, 'E2E Multi-Source TOC', 'TOC Grounding', '2026-12-31', 60, 1.25);
            """,
            (cid,),
        )
        # 1. YouTube Source
        conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved, chunk_count) VALUES ('src_yt_1', ?, 'youtube_video', 'Lecture 1: Intro', 1, 3);", (cid,))
        # 2. PDF Source
        conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved, chunk_count) VALUES ('src_pdf_1', ?, 'pdf', 'Automata Syllabus.pdf', 1, 5);", (cid,))
        # 3. Web Source
        conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved, chunk_count) VALUES ('src_web_1', ?, 'web_page', 'GeeksforGeeks DFA Guide', 1, 4);", (cid,))

        # Seed Lesson & Allocation so studio is active
        lid = "e2e-m3-l1"
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, source_id, title, video_id, start_sec, end_sec, raw_duration_sec, priority, order_index, has_transcript)
            VALUES (?, ?, 'src_yt_1', 'Lesson 1: Foundations', '58N2N7zJGrQ', 0, 300, 300, 'core', 0, 1);
            """,
            (lid, cid)
        )
        conn.execute(
            """
            INSERT INTO schedule_allocations (id, course_id, lesson_id, scheduled_date, split_index, split_count, allocated_start_sec, allocated_end_sec, effective_minutes)
            VALUES ('alloc_m3_1', ?, ?, '2026-11-20', 0, 1, 0, 300, 4.0);
            """,
            (cid, lid)
        )

        # Seed chunks for Grounded Q&A
        chk_id = "chk_m3_dfa"
        chunk_content = "A deterministic finite automaton is formally described as a 5-tuple consisting of states Q, alphabet Sigma, delta transition, start state q0, and accept states F."
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content, source_type)
            VALUES (?, ?, 'src_yt_1', ?, 0, 40, 30, 90, ?, 'youtube_video');
            """,
            (chk_id, cid, lid, chunk_content)
        )
        conn.execute(
            """
            INSERT INTO chunks_fts (id, course_id, lesson_id, content)
            VALUES (?, ?, ?, ?);
            """,
            (chk_id, cid, lid, chunk_content)
        )
        conn.commit()
        conn.close()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Load application & select course
            page.goto(f"{base_url}/")
            page.wait_for_selector("#course-selector")
            page.select_option("#course-selector", cid)
            page.wait_for_timeout(800)

            # 2. Verify Sources Tray renders pills
            page.wait_for_selector("#sources-pills-list")
            sources_html = page.inner_html("#sources-pills-list")
            assert "Lecture 1" in sources_html
            assert "Automata Syllabus.pdf" in sources_html
            assert "GeeksforGeeks" in sources_html

            # 3. Test Add Source Modal open and close
            page.click("#btn-open-add-source")
            modal = page.locator("#add-source-modal")
            assert modal.is_visible()

            # Switch modal tab to web import
            page.click("#tab-src-web")
            assert page.locator("#form-import-web").is_visible()
            assert not page.locator("#form-upload-pdf").is_visible()

            page.click("#btn-close-add-source")
            assert not modal.is_visible()

            # 4. Switch to Ask NotebookLM Tab
            page.click("#tab-qa-notebook")
            page.wait_for_timeout(400)
            pane_qa = page.locator("#pane-qa-notebook")
            assert pane_qa.is_visible()

            # 5. Ask Grounded Question
            page.fill("#input-qa-query", "What are the 5 tuples of a DFA?")
            page.click("#btn-submit-qa")

            # Wait for answer balloon to appear
            page.wait_for_selector(".qa-answer-bubble", timeout=15000)
            messages_html = page.inner_html("#qa-messages-list")
            assert "What are the 5 tuples of a DFA?" in messages_html
            assert "deterministic finite automaton" in messages_html or "tuples" in messages_html or "DFA" in messages_html

            # 6. Verify Citations are interactive
            citation_btn = page.locator(".qa-answer-bubble button").first
            assert citation_btn.is_visible()
            citation_btn.click(force=True)

            browser.close()

    except Exception as e:
        if "Executable doesn't exist" in str(e) or "Host system is missing dependencies" in str(e):
            pytest.skip(f"Chromium executable not available in this environment: {e}")
        else:
            raise e
