"""Verification tests for CourseIt-style Diagnostic Pre-Test Quality and Full-Syllabus Cram Sheet Synthesis."""

import sqlite3
import pytest
from pathlib import Path
from backend.migrations.runner import apply_migrations
from backend.database import init_connection

from backend.services.quiz_engine import (
    create_and_store_quiz,
    grade_and_apply_mastery,
    extract_key_sentences,
    VIDEO_NOISE_PATTERN
)
from backend.services.cram_sheet_engine import (
    get_or_create_cram_sheet,
    synthesize_full_syllabus_cram_sheet,
    generate_deterministic_cram_sheet
)


def test_video_noise_filtering_and_sentence_extraction():
    noisy_text = (
        "hello everyone welcome to the first lecture in the course. "
        "A Pushdown Automaton is a finite state machine augmented with an auxiliary stack memory. "
        "Deterministic finite automata have exactly one transition per input symbol. "
        "thank you for [Music] watching [Music] and see you in the next one! "
        "don't forget to like and subscribe to the channel. "
        "Context-free grammars generate languages recognized by pushdown automata."
    )
    extracted = extract_key_sentences(noisy_text)
    
    # Verify no noise in extracted sentences
    for s in extracted:
        assert not VIDEO_NOISE_PATTERN.search(s), f"Noise found in extracted sentence: {s}"
        assert "watching" not in s.lower() or "see you" not in s.lower()
        assert "subscribe" not in s.lower()
        assert "hello everyone" not in s.lower()

    # Verify substantive sentences are kept
    assert any("Pushdown Automaton" in s for s in extracted)
    assert any("Deterministic finite automata" in s for s in extracted)



def _create_seeded_course_db(tmp_path: Path):
    db_path = tmp_path / "cram_diag_test.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    cid = "c_toc_diag"
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day) VALUES (?, 'Theory of Computation', 'TOC', '2026-12-30', 60);", (cid,))
    conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved) VALUES ('s1', ?, 'youtube_playlist', 'TOC Lectures', 1);", (cid,))
    topics = [
        ("l1", "Deterministic Finite Automata (DFA)", "A Deterministic Finite Automaton consists of five tuples Q, Sigma, delta, q0, and F."),
        ("l2", "Non-Deterministic Finite Automata (NFA)", "A Non-Deterministic Finite Automaton allows epsilon transitions and multiple next states."),
        ("l3", "Regular Expressions and Languages", "Regular expressions define regular languages using union, concatenation, and Kleene star."),
        ("l4", "Context-Free Grammars (CFG)", "Context-free grammars generate context-free languages recognized by pushdown automata."),
        ("l5", "Turing Machines and Decidability", "A Turing Machine has an infinite tape and models any computable algorithm."),
    ]
    for idx, (lid, title, content) in enumerate(topics):
        conn.execute("INSERT INTO lessons (id, course_id, source_id, title, start_sec, end_sec, raw_duration_sec, order_index) VALUES (?, ?, 's1', ?, 0, 600, 600, ?);", (lid, cid, title, idx))
        conn.execute("INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content) VALUES (?, ?, 's1', ?, 0, 40, 0, 600, ?);", (f"chk_{lid}", cid, lid, content))
    conn.execute("INSERT INTO notes (id, course_id, lesson_id, content_markdown) VALUES ('n1', ?, 'l1', '# DFA\n\n## Key Definitions\n- **DFA**: Deterministic Finite Automaton with 5 tuples.\n');", (cid,))
    conn.commit()
    return conn, cid

def test_diagnostic_test_syllabus_coverage_and_quality(tmp_path):
    conn, course_id = _create_seeded_course_db(tmp_path)

    quiz = create_and_store_quiz(conn, course_id=course_id, quiz_type="diagnostic", question_count=5)
    questions = quiz.get("questions", [])
    assert len(questions) >= 3, "Diagnostic test should generate multiple questions across topics"

    for i, q in enumerate(questions):
        # 1. Topic name must be informative, not generic
        assert q.get("topic_name"), f"Question {i} missing topic_name"
        assert len(q["topic_name"]) > 3, f"Topic name too short: {q['topic_name']}"

        # 2. Must not contain outro or music garbage
        q_text = q.get("question", "")
        assert "watching and see you" not in q_text.lower()
        assert "[music]" not in q_text.lower()
        assert "subscribe" not in q_text.lower()

        # 3. Distractors must not contain raw slice noise
        for opt in q.get("options", []):
            assert not opt.startswith("It is entirely unrelated to watching")
            assert "[music]" not in opt.lower()
            assert len(opt) > 5

        # 4. Correct index is valid
        assert 0 <= q.get("correct_index", -1) < 4

    # Test submission and test-out mechanism
    user_answers = {q["id"]: q["correct_index"] for q in questions[:2]}
    res = grade_and_apply_mastery(conn, quiz["id"], user_answers=user_answers)
    assert len(res.get("tested_out_lessons", [])) >= 1, "Correct answers should test out lessons"

    conn.close()


def test_full_syllabus_cram_sheet_generation(tmp_path):
    conn, course_id = _create_seeded_course_db(tmp_path)

    # Verify deterministic full syllabus cram sheet
    cram_md = generate_deterministic_cram_sheet(conn, course_id)
    assert "# " in cram_md
    assert "High-Yield Exam Weightage Matrix" in cram_md
    assert ("Master Formula" in cram_md or "Rapid Recall Sheet" in cram_md)

    # Test full-syllabus synthesis API endpoint / engine function
    import asyncio
    sheet = asyncio.run(get_or_create_cram_sheet(conn, course_id, force_refresh=True, full_syllabus=False))
    assert sheet is not None
    assert "content_markdown" in sheet
    assert len(sheet["content_markdown"]) > 200

    conn.close()


@pytest.mark.e2e
def test_diagnostic_pre_test_live_ui():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector(".day-group-card", timeout=15000)

        # 1. Open Diagnostic Pre-Test Modal
        page.click("#btn-diagnostic-test")
        page.wait_for_selector("#diagnostic-modal:not(.hidden)", timeout=5000)

        # 2. Verify Diagnostic Questions rendered with Topic Badges
        page.wait_for_selector(".diagnostic-option-card", timeout=10000)
        badge_texts = page.locator("#diagnostic-content-container span:has-text('Topic')").all_inner_texts()
        assert len(badge_texts) >= 3, f"Expected multiple topic badges, got: {badge_texts}"
        for b in badge_texts:
            assert "watching" not in b.lower()

        # 3. Verify question text does not have video noise
        first_q = page.locator("#diagnostic-content-container span.font-bold").first.inner_text()
        assert "watching and see you" not in first_q.lower()
        assert "[music]" not in first_q.lower()

        # 4. Select options and submit
        page.locator(".diagnostic-option-card").first.click()
        page.click("#btn-submit-diagnostic")

        # 5. Verify celebratory results screen appears
        page.wait_for_selector("#btn-finish-diagnostic", timeout=10000)
        result_text = page.locator("#diagnostic-content-container").inner_text()
        assert "Diagnostic Placement Complete" in result_text or "Diagnostic Assessment Complete" in result_text
        assert "Tested Out" in result_text

        # 6. Click Return to Updated Schedule
        page.click("#btn-finish-diagnostic")
        assert page.is_hidden("#diagnostic-modal")

        # 7. Open Cram Sheet and verify Full Syllabus button exists
        page.click("#btn-open-cram-sheet")
        page.wait_for_selector("#modal-cram-sheet:not(.hidden)", timeout=5000)
        assert page.is_visible("#btn-full-cram-sheet")
        assert page.is_visible("#btn-print-cram-sheet")
        assert page.is_visible("#btn-download-cram-md")
        page.click("#btn-close-cram-sheet")

        assert len(console_errors) == 0, f"Found console errors: {console_errors}"
        browser.close()
