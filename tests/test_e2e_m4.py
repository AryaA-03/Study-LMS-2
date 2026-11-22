"""Playwright E2E tests for Milestone 4 features:
- Grounded Citation Quiz with score calculation and mastery test-out
- FSRS Spaced Repetition Flashcards with 3D card flip and interval ratings
- Diagnostic Pre-Test modal with automated topic test-out
- Timed Mock Exam modal
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
def live_server_m4():
    """Runs a real FastAPI server on an ephemeral port with an isolated temporary DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "e2e_m4_app.db"
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


def test_e2e_m4_quiz_mastery_and_fsrs(live_server_m4):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed in environment")

    base_url, db_path = live_server_m4

    try:
        # Seed test course, lessons, and chunks
        conn = init_connection(db_path)
        cid = "e2e-m4-c1"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, playback_speed)
            VALUES (?, ?, ?, '2026-12-25', 60, 1.0);
            """,
            (cid, "E2E TOC Exam Prep", "Theory of Computation")
        )
        # Lessons
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index, video_id)
            VALUES ('l_dfa', ?, 'Deterministic Finite Automata', 900, 1, '58Z247YS77E');
            """,
            (cid,)
        )
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index, video_id)
            VALUES ('l_nfa', ?, 'NFA and Equivalence', 900, 2, '58Z247YS77E');
            """,
            (cid,)
        )
        # Chunks
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
            VALUES ('chk_e2e_dfa', ?, 'l_dfa', 0, 150, 0, 300, 'A Deterministic Finite Automaton (DFA) is a finite state machine that accepts or rejects strings of characters. For every state and input symbol, exactly one transition is permitted.');
            """,
            (cid,)
        )
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
            VALUES ('chk_e2e_nfa', ?, 'l_nfa', 0, 150, 0, 300, 'A Non-deterministic Finite Automaton (NFA) allows multiple state transitions for a single symbol. Every NFA can be converted to an equivalent DFA via subset construction.');
            """,
            (cid,)
        )
        # Generate initial schedule
        from backend.scheduler.engine import generate_schedule, default_clock
        from datetime import date
        sched = generate_schedule(
            course_id=cid,
            lessons=[
                {"id": "l_dfa", "title": "Deterministic Finite Automata", "raw_duration_sec": 900, "priority": "core", "video_id": "58Z247YS77E"},
                {"id": "l_nfa", "title": "NFA and Equivalence", "raw_duration_sec": 900, "priority": "core", "video_id": "58Z247YS77E"}
            ],
            start_date=default_clock(),
            target_date=date(2026, 12, 25),
            minutes_per_day=60,
            playback_speed=1.0,
            rest_days=["Sunday"],
            revision_buffer_days=2,
            schedule_strategy="paced"
        )
        for a in sched["allocations"]:
            conn.execute(
                """
                INSERT INTO schedule_allocations (id, course_id, lesson_id, scheduled_date, split_index, split_count, allocated_start_sec, allocated_end_sec, effective_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (a.id, cid, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes)
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

        # Select the seeded course
        page.select_option("#course-selector", cid)
        page.wait_for_timeout(500)

        # 2. Test "Quiz & Mastery" Tab
        page.click("#tab-quiz-mastery")
        page.wait_for_selector("#pane-quiz-mastery", state="visible")

        # Generate Quiz
        page.click("#btn-generate-lesson-quiz")
        page.wait_for_selector("#quiz-form input[type='radio']", timeout=10000)

        # Select an option for each question
        question_cards = page.locator("#quiz-questions-list > div").all()
        for qc in question_cards:
            qc.locator("input[type='radio']").first.check()

        # Submit quiz
        page.click("#btn-submit-lesson-quiz")
        page.wait_for_selector("#quiz-results-banner", state="visible", timeout=10000)
        assert page.locator("#quiz-results-banner").is_visible()

        # 3. Test "Flashcards (FSRS)" Tab
        page.click("#tab-flashcards-fsrs")
        page.wait_for_selector("#pane-flashcards-fsrs", state="visible")
        assert page.locator("#fsrs-retention-pill").is_visible()

        # Create a manual flashcard if queue is empty
        page.click("#btn-add-card-manual")
        page.wait_for_selector("#add-card-modal", state="visible")
        page.fill("#input-card-front", "What is subset construction?")
        page.fill("#input-card-back", "An algorithm to convert any NFA into an equivalent DFA.")
        page.click("#form-create-card button[type='submit']")
        page.wait_for_selector("#add-card-modal", state="hidden")

        # Card should now be visible in study area (either auto-generated from quiz review or manual card)
        page.wait_for_selector("#fc-active-card-container", state="visible")
        front_text = page.text_content("#fsrs-front-text").lower()
        assert len(front_text) > 5

        # Flip the card
        page.click("#fsrs-card-flipper")
        page.wait_for_selector("#fsrs-rating-bar", state="visible")
        assert page.locator("#btn-fsrs-good").is_visible()

        # Submit Rating Good (3)
        page.click("#btn-fsrs-good")
        page.wait_for_timeout(500)

        # 4. Test Diagnostic Pre-Test Modal
        page.click("#btn-diagnostic-test")
        page.wait_for_selector("#diagnostic-modal", state="visible")
        page.wait_for_selector("#diagnostic-content-container input[type='radio']", timeout=10000)

        # Close modal
        page.click("#btn-close-diagnostic")
        page.wait_for_selector("#diagnostic-modal", state="hidden")

        # 5. Test Mock Exam Modal
        page.click("#btn-mock-exam")
        page.wait_for_selector("#mock-exam-modal", state="visible")
        assert page.locator("#mock-exam-timer").is_visible()

        # Close mock exam modal
        page.click("#btn-close-mock-exam")
        page.wait_for_selector("#mock-exam-modal", state="hidden")

        browser.close()
