"""Unit tests for Citation Quiz & Diagnostic Pre-Test Engine."""

import sqlite3
import tempfile
from pathlib import Path
import pytest

from backend.migrations.runner import apply_migrations
from backend.services.quiz_engine import (
    create_and_store_quiz,
    grade_and_apply_mastery,
    generate_no_key_questions,
    evaluate_short_answer_with_rubric,
)
from backend.services.fsrs_engine import get_flashcard_counts


@pytest.fixture
def populated_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        p = Path(tmp.name)
        apply_migrations(p)
        conn = sqlite3.connect(p, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        conn.execute("INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day) VALUES ('c_toc', 'Theory of Computation', 'exam prep', '2026-12-20', 90)")
        conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index) VALUES ('l_dfa', 'c_toc', 'Deterministic Finite Automata', 900, 1)")
        conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec, order_index) VALUES ('l_nfa', 'c_toc', 'Non-Deterministic Finite Automata', 900, 2)")

        conn.execute(
            """
            INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, content)
            VALUES ('chk_dfa_1', 'c_toc', 'l_dfa', 0, 120, 'A Deterministic Finite Automaton consists of a 5-tuple: Q, Sigma, delta, q0, and F. For every state and input symbol, there is exactly one next state transition.')
            """
        )
        conn.execute(
            """
            INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, content)
            VALUES ('chk_nfa_1', 'c_toc', 'l_nfa', 0, 120, 'An NFA allows epsilon transitions and multiple next states for a single input symbol. Every NFA can be converted to an equivalent DFA using subset construction.')
            """
        )
        conn.commit()
        yield conn
        conn.close()


def test_grounded_mcq_generation(populated_db):
    conn = populated_db
    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_dfa", question_count=3)
    assert quiz["id"].startswith("qz_")
    assert len(quiz["questions"]) >= 1

    for q in quiz["questions"]:
        # Verify strict grounding: chunk_id present, quote present
        assert q["chunk_id"] == "chk_dfa_1"
        assert len(q["quote"]) > 0
        assert len(q["options"]) == 4
        assert 0 <= q["correct_index"] < 4
        # Verify quote appears in chunk content
        cur = conn.cursor()
        cur.execute("SELECT content FROM chunks WHERE id = ?;", (q["chunk_id"],))
        content = cur.fetchone()["content"]
        assert q["quote"] in content


def test_mastery_high_score_marks_tested_out(populated_db):
    conn = populated_db
    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_dfa", question_count=2)
    
    # Submit 100% correct answers
    answers = {q["id"]: q["correct_index"] for q in quiz["questions"]}
    result = grade_and_apply_mastery(conn, quiz["id"], user_answers=answers, time_taken_seconds=30)
    
    assert result["score"] == 100.0
    assert result["passed"] is True
    assert result["mastery_status"] == "mastered"
    assert "l_dfa" in result["tested_out_lessons"]

    # Verify database state
    cur = conn.cursor()
    cur.execute("SELECT is_tested_out FROM lessons WHERE id = 'l_dfa';")
    assert cur.fetchone()["is_tested_out"] == 1


def test_mastery_low_score_creates_targeted_flashcards(populated_db):
    conn = populated_db
    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_nfa", question_count=2)
    
    # Submit 0% correct answers (pick wrong option)
    answers = {q["id"]: (q["correct_index"] + 1) % 4 for q in quiz["questions"]}
    result = grade_and_apply_mastery(conn, quiz["id"], user_answers=answers, time_taken_seconds=45)
    
    assert result["score"] == 0.0
    assert result["passed"] is False
    assert result["mastery_status"] == "needs_review"
    assert result["flashcards_created"] >= 1

    # Verify flashcards created in DB
    fc_counts = get_flashcard_counts(conn, "c_toc")
    assert fc_counts["total"] >= 1
    assert fc_counts["due"] >= 1


def test_diagnostic_pre_test_marks_mastered_topics(populated_db):
    conn = populated_db
    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="diagnostic", question_count=4)
    assert quiz["quiz_type"] == "diagnostic"
    assert len(quiz["questions"]) >= 1

    # Answer all questions correctly
    answers = {q["id"]: q["correct_index"] for q in quiz["questions"]}
    result = grade_and_apply_mastery(conn, quiz["id"], user_answers=answers, time_taken_seconds=60)

    assert result["mastery_status"] == "diagnostic_applied"
    assert len(result["tested_out_lessons"]) >= 1


def test_create_quiz_with_llm_key_and_caching(populated_db, monkeypatch):
    import json
    from unittest.mock import AsyncMock, patch
    import httpx
    from backend.config import get_settings
    from backend.services.quiz_engine import settings

    conn = populated_db
    monkeypatch.setenv("GEMINI_API_KEY", "mock_gemini_key")

    mock_llm_response = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps({
                        "questions": [
                            {
                                "chunk_id": "chk_dfa_1",
                                "quote": "A Deterministic Finite Automaton consists of a 5-tuple: Q, Sigma, delta, q0, and F.",
                                "question": "What is the formal definition of a DFA?",
                                "options": [
                                    "A 5-tuple: Q, Sigma, delta, q0, and F",
                                    "A 3-tuple",
                                    "A 2-tuple",
                                    "An infinite state machine"
                                ],
                                "correct_index": 0,
                                "explanation": "Directly grounded in chunk chk_dfa_1."
                            },
                            {
                                "chunk_id": "chk_dfa_1",
                                "quote": "For every state and input symbol, there is exactly one next state transition.",
                                "question": "How many transitions exist for each state/symbol pair in a DFA?",
                                "options": [
                                    "Exactly one",
                                    "Zero or more",
                                    "Multiple transitions",
                                    "Epsilon transitions only"
                                ],
                                "correct_index": 0,
                                "explanation": "Directly grounded in chunk chk_dfa_1."
                            }
                        ]
                    })
                }]
            }
        }]
    }

    call_count = 0

    class MockResponse:
        status_code = 200
        def json(self):
            return mock_llm_response

    original_post = httpx.AsyncClient.post

    async def mock_post(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 1. First generation: calls LLM and populates cache
    quiz1 = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_dfa", question_count=2)
    assert len(quiz1["questions"]) == 2
    assert quiz1["questions"][0]["question"] == "What is the formal definition of a DFA?"
    assert call_count == 1

    # 2. Check llm_cache table
    cur = conn.cursor()
    cur.execute("SELECT prompt_hash, response_json, response_text FROM llm_cache;")
    rows = cur.fetchall()
    assert len(rows) >= 1

    # 3. Second generation with same chunks/parameters hits llm_cache (call_count stays 1)
    quiz2 = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_dfa", question_count=2)
    assert len(quiz2["questions"]) == 2
    assert quiz2["questions"][0]["question"] == "What is the formal definition of a DFA?"
    assert call_count == 1  # Cache hit, zero new HTTP requests!


@pytest.mark.asyncio
async def test_notes_llm_caching_and_db_conn(populated_db, monkeypatch):
    import httpx
    from backend.services.notes import (
        generate_llm_structured_notes,
        get_or_generate_lesson_notes,
        settings,
    )

    conn = populated_db
    monkeypatch.setenv("GEMINI_API_KEY", "mock_notes_key")

    mock_notes_text = "# Mock Structured Notes\n\n### [01:00] Core Concept\n- Grounded explanation. `[01:00]`"
    call_count = 0

    class MockNotesResponse:
        status_code = 200
        def json(self):
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": mock_notes_text}]
                    }
                }]
            }

    async def mock_post(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MockNotesResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    chunks = [{
        "id": "chk_dfa_1",
        "chunk_index": 0,
        "token_count": 100,
        "start_sec": 60,
        "end_sec": 120,
        "content": "A Deterministic Finite Automaton consists of a 5-tuple."
    }]

    # 1. First call: fetches from LLM and stores in llm_cache
    res1 = await generate_llm_structured_notes(
        lesson_title="DFA Lesson",
        chunks=chunks,
        db_conn=conn,
    )
    assert res1 == mock_notes_text
    assert call_count == 1

    # 2. Second call with same prompt hits llm_cache
    res2 = await generate_llm_structured_notes(
        lesson_title="DFA Lesson",
        chunks=chunks,
        db_conn=conn,
    )
    assert res2 == mock_notes_text
    assert call_count == 1  # No second HTTP call

    # 3. get_or_generate_lesson_notes passes db_conn
    notes_res = await get_or_generate_lesson_notes(
        db_conn=conn,
        course_id="c_toc",
        lesson_id="l_dfa",
        force_regenerate=True
    )
    assert notes_res["is_generated"] == 1
    assert notes_res["content_markdown"] != ""


def test_evaluate_short_answer_with_rubric_deterministic(populated_db):
    conn = populated_db
    q = {
        "id": "q_sa_test_1",
        "question": "Explain the concept, working mechanism, and practical application of DFA. (5 Marks)",
        "quote": "A Deterministic Finite Automaton consists of a 5-tuple: Q, Sigma, delta, q0, and F.",
        "sample_solution": "A DFA is a state machine consisting of 5 tuples. It transitions predictably on input symbols. For example, it is used in lexical analysis.",
        "max_marks": 5.0,
        "rubric": [
            "Definition & Conceptual Core (2.0 Marks)",
            "Technical Mechanism & Steps (2.0 Marks)",
            "Practical Example & Application (1.0 Mark)"
        ]
    }

    # Empty answer gives 0 marks
    empty_res = evaluate_short_answer_with_rubric(q, "", conn=conn)
    assert empty_res["marks_awarded"] == 0.0

    # Comprehensive answer with definition, mechanism, and example
    good_answer = (
        "A Deterministic Finite Automaton (DFA) is defined as a formal 5-tuple state machine. "
        "The working mechanism operates step by step where for every state and input symbol, "
        "the transition function computes exactly one deterministic next state. "
        "For example, DFAs are used in compiler lexical analysis and regex parsing engines."
    )
    good_res = evaluate_short_answer_with_rubric(q, good_answer, conn=conn)
    assert good_res["marks_awarded"] >= 4.0
    assert good_res["breakdown"]["definition"] >= 1.5
    assert good_res["breakdown"]["mechanism"] >= 1.5
    assert good_res["breakdown"]["example"] == 1.0


def test_mock_exam_rubric_generation_and_grading(populated_db):
    conn = populated_db
    # Generate mock exam
    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="mock_exam", question_count=4)
    assert quiz["quiz_type"] == "mock_exam"
    assert len(quiz["questions"]) >= 2

    # Check for presence of Section A (MCQ) and Section B (Short Answer with Rubric)
    has_mcq = any(q.get("question_type") == "mcq" for q in quiz["questions"])
    has_sa = any(q.get("question_type") == "short_answer" for q in quiz["questions"])
    assert has_mcq, "Mock exam should include Section A MCQs"
    assert has_sa, "Mock exam should include Section B Subjective questions"

    sa_q = next(q for q in quiz["questions"] if q.get("question_type") == "short_answer")
    assert sa_q["max_marks"] == 5.0
    assert len(sa_q["rubric"]) == 3
    assert sa_q["sample_solution"] is not None

    # Grade with both MCQ answers and Short Answers
    user_answers = {}
    short_answers = {}
    for q in quiz["questions"]:
        if q.get("question_type") == "short_answer":
            short_answers[q["id"]] = (
                "The concept is defined as a deterministic formal automaton with state transitions. "
                "The process works by reading input symbols sequentially. For example, in tokenizing programming code."
            )
        else:
            user_answers[q["id"]] = q["correct_index"]

    result = grade_and_apply_mastery(
        conn=conn,
        quiz_id=quiz["id"],
        user_answers=user_answers,
        short_answers=short_answers,
        time_taken_seconds=120,
    )

    assert result["score"] >= 70.0
    assert result["total_marks_obtained"] is not None
    assert result["total_marks_possible"] is not None
    assert result["total_marks_possible"] > 5.0
    assert len(result["short_answer_evaluations"]) >= 1
    assert result["short_answer_evaluations"][0]["question_id"] == sa_q["id"]


def test_quiz_drop_triggers_auto_replan_with_snapshot(populated_db):
    from datetime import date
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.database import get_db
    from backend.scheduler.engine import generate_schedule

    conn = populated_db
    sched = generate_schedule(
        course_id="c_toc",
        lessons=[
            {"id": "l_dfa", "priority": "core", "raw_duration_sec": 900, "is_excluded": False, "is_tested_out": False},
            {"id": "l_nfa", "priority": "core", "raw_duration_sec": 900, "is_excluded": False, "is_tested_out": False},
        ],
        start_date=date(2026, 11, 22),
        target_date=date(2026, 12, 20),
        minutes_per_day=90,
        playback_speed=1.0,
        rest_days=[],
        revision_buffer_days=2,
    )
    for a in sched["allocations"]:
        conn.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (a.id, a.course_id, a.lesson_id, a.scheduled_date, a.split_index, a.split_count,
             a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes, 0, 0),
        )
    conn.commit()

    quiz = create_and_store_quiz(conn, "c_toc", quiz_type="lesson", lesson_id="l_dfa", question_count=2)

    app.dependency_overrides[get_db] = lambda: conn
    try:
        client = TestClient(app)
        # Submit quiz with 0% score (fail < 60% -> needs_review)
        wrong_answers = {q["id"]: (q["correct_index"] + 1) % 4 for q in quiz["questions"]}
        resp = client.post(
            f"/api/courses/c_toc/quizzes/{quiz['id']}/submit",
            json={"answers": wrong_answers, "short_answers": {}, "time_taken_seconds": 15}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 0.0
        assert data["mastery_status"] == "needs_review"
        assert data["schedule_updated"] is True
        assert data["diff_summary"] is not None

        # Verify a snapshot was created in schedule_snapshots
        snapshot = conn.execute("SELECT * FROM schedule_snapshots WHERE course_id = 'c_toc' ORDER BY created_at DESC LIMIT 1;").fetchone()
        assert snapshot is not None
    finally:
        app.dependency_overrides.clear()



