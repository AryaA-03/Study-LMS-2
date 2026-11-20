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
)
from backend.services.fsrs_engine import get_flashcard_counts


@pytest.fixture
def populated_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        p = Path(tmp.name)
        apply_migrations(p)
        conn = sqlite3.connect(p)
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
