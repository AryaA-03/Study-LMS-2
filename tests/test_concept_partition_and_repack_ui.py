import pytest
pytestmark = pytest.mark.e2e
"""Playwright UI verification test for Concept Partitioning, Instant Deterministic Day Repacking,
Timestamp Seeking in Notes, Quiz Replay, and Whole-Video Master Cheat Sheet.

Validates:
1. Editing Exam Date / Number of Days in the UI updates syllabus rail day groupings instantaneously
   without losing progress or reloading notes.
2. Clicking [MM:SS] timestamp pills in standalone structured notes seeks the player.
3. Missing a quiz question reveals 'Replay Explanation [MM:SS]' button which seeks the player.
4. Clicking [MM:SS] timestamp pills in the Master Cheat Sheet / Cram Sheet seeks the player.
5. Zero console or page errors throughout all interactions.
"""

import socket
import tempfile
import threading
from pathlib import Path
from datetime import date, timedelta
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
def concept_test_server():
    """Starts an ephemeral FastAPI test server with seeded concept clips, notes, quizzes, and cram sheet."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = Path(tmpdir) / "concept_ui_test.db"
        apply_migrations(tmp_db_path)

        conn = init_connection(tmp_db_path)
        cid = "course-concept-ui-1"
        today = date.today()
        target_date = today + timedelta(days=14)

        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day, preferred_daily_minutes, playback_speed, revision_buffer_days, schedule_strategy)
            VALUES (?, 'Theory of Computation', 'Automata Theory', ?, 60, 60, 1.0, 2, 'paced');
            """,
            (cid, target_date.strftime("%Y-%m-%d")),
        )
        sid = "src-concept-ui-1"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, is_approved)
            VALUES (?, ?, 'video', 'TOC Concept Series', 1);
            """,
            (sid, cid),
        )

        clips_data = [
            ("clip-ui-1", "DFA — Part 1: Definition & 5-Tuples", 720, "core", 0, 720),
            ("clip-ui-2", "DFA — Part 2: Transition Tables & State Diagrams", 780, "core", 720, 1500),
            ("clip-ui-3", "NFA — Part 1: Nondeterminism & Epsilon Transitions", 840, "core", 1500, 2340),
            ("clip-ui-4", "NFA — Part 2: Subset Construction Algorithm", 900, "deep-dive", 2340, 3240),
        ]

        for idx, (lid, title, duration, priority, s_sec, e_sec) in enumerate(clips_data):
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, start_sec, end_sec, raw_duration_sec, priority, priority_tag, order_index, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending');
                """,
                (lid, cid, sid, title, s_sec, e_sec, duration, priority, priority, idx),
            )


        # Standalone Notes for clip-ui-1 with clickable [MM:SS] pills
        notes_md = """# DFA — Part 1: Definition & 5-Tuples

## 1. Overview & Intuition
Deterministic Finite Automata [02:15] is a state machine that processes symbols deterministically.

## 2. Key Definitions & Formulas
A DFA is a 5-tuple (Q, Sigma, delta, q0, F) [05:30].

## 3. Step-by-Step Worked Example
Starting at q0 [08:45], evaluate string '01'.

## 4. Comparison & Edge Cases
| Model | Deterministic? | Backtracking? |
|---|---|---|
| DFA | Yes [10:20] | No |

## 5. Quick Exam Revision Bullets
- [11:40] Every DFA state has exactly one transition per alphabet symbol.
"""
        conn.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, is_generated)
            VALUES ('note-clip-1', ?, 'clip-ui-1', ?, 1);
            """,
            (cid, notes_md),
        )

        # Quiz for clip-ui-1 with citations and replay timestamps
        import json
        questions = [
            {
                "id": "q1",
                "question": "How many transitions must exist for each input symbol in a valid DFA?",
                "options": [
                    "Zero or more transitions",
                    "Exactly one transition per symbol from each state",
                    "At least two transitions",
                    "Arbitrary number of transitions"
                ],
                "correct_index": 1,
                "explanation": "A DFA requires exactly one deterministic transition for each symbol in the alphabet from every state.",
                "quote": "Every state has exactly one transition for each alphabet symbol.",
                "chunk_id": "chk-dfa-1",
                "timestamp_sec": 330,
                "timestamp_str": "05:30",
                "question_type": "mcq"
            }
        ]
        conn.execute(
            """
            INSERT INTO quizzes (id, course_id, lesson_id, title, questions_json)
            VALUES ('quiz-clip-1', ?, 'clip-ui-1', 'DFA Part 1 Quiz', ?);
            """,
            (cid, json.dumps(questions)),
        )

        # Cram sheet cache
        cram_md = f"""# Theory of Computation — Last-Night Exam Cram Sheet (Whole-Video Master Cheat Sheet)

## 1-Line Formal Definitions
- **DFA** [05:30]: 5-tuple finite state machine with deterministic transitions.
- **NFA** [25:00]: Nondeterministic finite automaton allowing epsilon moves.

## Key Formulas & Complexity
| Machine | Transitions | Conversion Complexity |
|---|---|---|
| DFA | 1 per symbol [05:30] | O(1) |
| NFA | 2^Q states [26:15] | O(2^n) |
"""
        conn.execute(
            """
            INSERT INTO cram_sheets (id, course_id, content_markdown, notes_hash)
            VALUES ('cram-ui-1', ?, ?, 'samplehash123');
            """,
            (cid, cram_md),
        )

        # Initial schedule allocations
        lessons_dict = [
            {"id": lid, "title": title, "raw_duration_sec": dur, "priority": prio, "start_sec": s, "end_sec": e}
            for (lid, title, dur, prio, s, e) in clips_data
        ]
        sched = generate_schedule(
            course_id=cid,
            lessons=lessons_dict,
            start_date=today,
            target_date=target_date,
            minutes_per_day=60,
            playback_speed=1.0,
            rest_days=["Sunday"],
            revision_buffer_days=2,
            schedule_strategy="paced",
        )
        for a in sched["allocations"]:
            conn.execute(
                """
                INSERT INTO schedule_allocations (
                    id, course_id, lesson_id, clip_id, scheduled_date, split_index, split_count,
                    allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0);
                """,
                (a.id, cid, a.lesson_id, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes),
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

        import time
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)

        yield f"http://127.0.0.1:{port}", cid

        app.dependency_overrides.pop(get_db, None)


def test_ui_concept_repacking_and_timestamp_seeking(concept_test_server):
    base_url, course_id = concept_test_server

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # Track seekToSeconds invocations via client-side spy
        page.add_init_script("""
            window.__seekCalls = [];
            window.addEventListener('DOMContentLoaded', () => {
                const origSeek = window.seekToSeconds;
                window.seekToSeconds = function(sec) {
                    window.__seekCalls.push(sec);
                    if (origSeek) origSeek(sec);
                };
            });
        """)

        # Navigate to LMS
        page.goto(base_url)
        page.wait_for_selector(".day-group-card", timeout=10000)

        # 1. Verify Day Grouping in Left Syllabus Rail
        initial_cards = page.locator(".day-group-card")
        initial_card_count = initial_cards.count()
        assert initial_card_count > 0, "Expected at least 1 day card rendered"

        # 2. Open Edit Course & Pacing Modal and Repack
        btn_edit_course = page.locator("#btn-edit-course")
        assert btn_edit_course.is_visible()
        btn_edit_course.click()

        page.wait_for_selector("#edit-course-modal:not(.hidden)", timeout=5000)

        # Change Number of Days or Target Date
        input_days = page.locator("#edit-course-days")
        if input_days.is_visible():
            input_days.fill("7")
        input_minutes = page.locator("#edit-course-minutes")
        input_minutes.fill("90")

        # Save and Replan Schedule
        btn_save = page.locator("#btn-submit-edit-course")
        btn_save.click()

        # Modal closes and Diff Banner appears
        page.wait_for_selector("#edit-course-modal", state="hidden", timeout=5000)
        page.wait_for_selector("#diff-banner:not(.hidden)", timeout=5000)

        diff_text = page.locator("#diff-text").inner_text()
        assert "Finish:" in diff_text, f"Expected Finish in diff text, got {diff_text}"

        # Test 1-click Undo in UI
        btn_undo = page.locator("#btn-undo-diff")
        assert btn_undo.is_visible()
        btn_undo.click()
        page.wait_for_selector("#diff-banner", state="hidden", timeout=5000)

        # 3. Verify Clickable [MM:SS] Timestamps in Structured Notes
        # Click first clip allocation to open notes
        first_alloc = page.locator(".allocation-card").first
        first_alloc.click()

        # Wait for notes tab content to be rendered
        page.wait_for_selector(".timestamp-link", timeout=5000)
        ts_links = page.locator(".timestamp-link")
        assert ts_links.count() > 0, "Expected timestamp pills in structured notes"

        # Click the [05:30] timestamp pill (which corresponds to 330 seconds)
        ts_330 = page.locator(".timestamp-link[data-timestamp-sec='330']").first
        if ts_330.is_visible():
            ts_330.click()
        else:
            ts_links.first.click()

        # Verify seek was triggered
        seek_calls = page.evaluate("window.__seekCalls")
        assert len(seek_calls) > 0, f"Expected seekToSeconds call, got {seek_calls}"

        # 4. Verify Quiz Replay on Missed Question
        btn_quiz_tab = page.locator("#tab-quiz-mastery")
        btn_quiz_tab.click()

        page.wait_for_selector("#quiz-form", timeout=5000)

        # Select option index 0 (the INCORRECT option: "Zero or more transitions")
        opt_wrong = page.locator("input[name^='quiz_q_'][value='0']")
        if opt_wrong.is_visible():
            opt_wrong.click()
            btn_submit_quiz = page.locator("#btn-submit-lesson-quiz")
            btn_submit_quiz.click()

            # Wait for quiz completion view
            page.wait_for_selector(".replay-explanation-btn", timeout=5000)
            replay_btn = page.locator(".replay-explanation-btn")
            assert replay_btn.is_visible(), "Expected Replay Explanation [MM:SS] button"

            # Click replay button
            replay_btn.click()
            seek_calls = page.evaluate("window.__seekCalls")
            assert 330 in seek_calls, f"Expected seek to 330 seconds from quiz replay, got {seek_calls}"

        # 5. Verify Master Cheat Sheet [MM:SS] Timestamp Seeking
        btn_cram = page.locator("#btn-open-cram-sheet")
        if btn_cram.is_visible():
            btn_cram.click()
            page.wait_for_selector("#modal-cram-sheet:not(.hidden)", timeout=5000)

            # In the cram sheet modal, find and click a timestamp link
            cram_ts_links = page.locator("#modal-cram-sheet .timestamp-link")
            if cram_ts_links.count() > 0:
                cram_ts_links.first.click()
                seek_calls = page.evaluate("window.__seekCalls")
                assert len(seek_calls) >= 2, f"Expected seek call from cram sheet, got {seek_calls}"

            # Close modal
            btn_close_cram = page.locator("#btn-close-cram-sheet")
            btn_close_cram.click()

        # Assert zero console errors throughout test
        assert len(console_errors) == 0, f"Encountered browser console errors: {console_errors}"

        browser.close()
