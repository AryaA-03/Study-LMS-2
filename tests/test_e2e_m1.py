"""Playwright E2E tests for M1 golden path.

Runs against an ephemeral database and server instance.
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
def live_server():
    """Runs a real FastAPI server on an ephemeral port with a temporary DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "e2e_app.db"
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

        # Wait for server to start
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
            pytest.skip("Local test server could not be bound (sandboxed/restricted networking environment)")

        yield base_url, tmp_db_path

        server.should_exit = True
        app.dependency_overrides.clear()

def test_e2e_m1_golden_path(live_server):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed in environment")

    base_url, db_path = live_server

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Navigate to home
            page.goto(f"{base_url}/")
            assert "Learn LMS" in page.title()

            # 2. Verify creator view is displayed when no courses exist
            creator_view = page.locator("#creator-view")
            assert creator_view.is_visible()

            # 3. Fill course creation form
            page.fill("#input-course-title", "E2E Distributed Systems")
            page.fill("#input-goal-query", "Distributed Consensus & Raft")
            page.fill("#input-minutes-day", "60")
            page.select_option("#input-playback-speed", "1.5")

            # 4. Open Settings modal to verify storage guard & yt-dlp version
            page.click("#btn-settings")
            settings_modal = page.locator("#settings-modal")
            assert settings_modal.is_visible()
            ytdlp_text = page.inner_text("#settings-ytdlp-version")
            assert len(ytdlp_text) > 2

            # Close settings
            page.click("#btn-close-settings")
            assert not settings_modal.is_visible()

            # 5. Direct URL / Mock seed check
            # Seed a course and lessons directly into DB to test workspace UI
            conn = init_connection(db_path)
            cid = "e2e-course-1"
            conn.execute(
                """
                INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed)
                VALUES (?, 'E2E Seeded Course', 'Distributed Systems', '2026-12-31', 60, 1.5);
                """,
                (cid,),
            )
            sid = "e2e-source-1"
            conn.execute(
                """
                INSERT INTO sources (id, course_id, source_type, title, is_approved)
                VALUES (?, ?, 'youtube_video', 'Consensus Lectures', 1);
                """,
                (sid, cid),
            )
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, start_sec, end_sec, raw_duration_sec, priority, order_index)
                VALUES ('e2e-l1', ?, ?, 'Lesson 1: Raft Basics', 0, 3600, 3600, 'core', 0);
                """,
                (cid, sid),
            )
            conn.commit()
            conn.close()

            # Reload page and verify course selector loads and workspace appears
            page.goto(f"{base_url}/")
            page.wait_for_selector("#course-selector")

            # Select the seeded course
            page.select_option("#course-selector", cid)
            page.wait_for_timeout(500)

            # Workspace view should be visible
            workspace_view = page.locator("#workspace-view")
            assert workspace_view.is_visible()

            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "Host system is missing dependencies" in str(e):
            pytest.skip(f"Chromium executable not available in this environment: {e}")
        else:
            raise e
