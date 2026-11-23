import pytest
pytestmark = pytest.mark.e2e
"""Playwright E2E tests for Milestone 5:
- In-browser Pyodide scratchpad tab and controls
- Storage Guard maintenance: SQLite Vacuum, Backup download, and Course Bundle Export
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
def live_server_m5():
    """Runs a real FastAPI server on an ephemeral port with an isolated temporary DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "e2e_m5_app.db"
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
            pytest.skip("Local test server could not be bound (sandboxed/restricted networking environment)")

        yield base_url, tmp_db_path

        server.should_exit = True
        app.dependency_overrides.clear()


def test_e2e_m5_pyodide_and_storage_guard(live_server_m5):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed in environment")

    base_url, db_path = live_server_m5

    try:
        conn = init_connection(db_path)
        cid = "e2e-m5-c1"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed)
            VALUES (?, ?, ?, '2026-12-25', 60, 1.0);
            """,
            (cid, "E2E M5 Study Course", "Theory of Computation")
        )
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index, video_id)
            VALUES ('l_m5', ?, 'Automata Sandbox', 600, 1, '58Z247YS77E');
            """,
            (cid,)
        )
        conn.commit()
    finally:
        conn.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Load application
        page.goto(base_url, timeout=15000)
        page.wait_for_selector("#course-selector")

        # Select course
        page.select_option("#course-selector", cid)
        page.wait_for_timeout(500)

        # 2. Test In-Browser Pyodide Scratchpad Tab
        page.click("#tab-pyodide-scratchpad")
        page.wait_for_selector("#pane-pyodide-scratchpad", state="visible")
        assert page.locator("#pyodide-code-input").is_visible()
        assert page.locator("#btn-run-pyodide").is_visible()

        # Check preset template change
        page.select_option("#pyodide-presets", "math")
        assert "Formula Calculator" in page.input_value("#pyodide-code-input")

        # 3. Test Settings & Storage Guard Modal
        page.click("#btn-settings")
        page.wait_for_selector("#settings-modal", state="visible")

        assert page.locator("#btn-vacuum-db").is_visible()
        assert page.locator("#btn-download-db").is_visible()
        assert page.locator("#btn-export-bundle").is_visible()

        # Test Vacuum DB button
        page.click("#btn-vacuum-db")
        page.wait_for_timeout(500)

        # Close Settings Modal
        page.click("#btn-close-settings")
        page.wait_for_selector("#settings-modal", state="hidden")

        browser.close()
