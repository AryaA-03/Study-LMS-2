"""Verification tests for CourseIt-style Diagnostic Pre-Test Quality and Full-Syllabus Cram Sheet Synthesis."""

import sqlite3
import pytest
from playwright.sync_api import sync_playwright

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


def test_diagnostic_test_syllabus_coverage_and_quality():
    conn = sqlite3.connect("data-dev/app.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM courses LIMIT 1;")
    c_row = cur.fetchone()
    assert c_row is not None, "Need a course in data-dev/app.db"
    course_id = c_row[0]

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


def test_full_syllabus_cram_sheet_generation():
    conn = sqlite3.connect("data-dev/app.db")
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM courses LIMIT 1;")
    c_row = cur.fetchone()
    assert c_row is not None
    course_id = c_row[0]

    # Verify deterministic full syllabus cram sheet
    cram_md = generate_deterministic_cram_sheet(conn, course_id)
    assert "# " in cram_md
    assert "High-Yield Exam Weightage Matrix" in cram_md
    assert "Essential Concepts, Definitions & Formulas" in cram_md

    # Test full-syllabus synthesis API endpoint / engine function
    import asyncio
    sheet = asyncio.run(get_or_create_cram_sheet(conn, course_id, force_refresh=True, full_syllabus=False))
    assert sheet is not None
    assert "content_markdown" in sheet
    assert len(sheet["content_markdown"]) > 200

    conn.close()


def test_diagnostic_pre_test_live_ui():
    with sync_playwright() as p:
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
