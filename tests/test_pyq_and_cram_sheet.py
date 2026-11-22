"""Unit and integration tests for University PYQ matching and Last-Night Cram Sheet synthesis."""

import tempfile
import sqlite3
from pathlib import Path
import pytest

from backend.migrations.runner import apply_migrations
from backend.database import init_connection
from backend.services.pyq_engine import (
    parse_pyq_questions,
    ingest_pyq_source,
    get_course_pyq_summary,
    get_lesson_pyq_questions,
)
from backend.services.cram_sheet_engine import (
    compute_course_notes_hash,
    generate_deterministic_cram_sheet,
    get_or_create_cram_sheet,
)


def test_pyq_question_splitting():
    """Validates regex splitting across diverse university question paper styles."""
    sample_paper = """
    CENTRAL UNIVERSITY SEMESTER EXAMINATION
    Subject: Database Management Systems
    Time: 3 Hours                            Maximum Marks: 100
    Instructions: Answer any five full questions.

    Q1. (a) Explain the Three-Schema Architecture of DBMS with a neat diagram. [5M]
        (b) What are the disadvantages of file-processing systems over DBMS? [5 Marks]
    
    Q2. What is an Entity-Relationship (ER) model? Explain primary key, candidate key, and foreign key with examples. [10M]
    
    Q3. (a) Define Boyce-Codd Normal Form (BCNF). How does BCNF differ from 3NF? (6 marks)
        (b) Explain 2-Phase Locking (2PL) protocol for concurrency control in transactions. [6]
    
    4. Consider the relational schema R(A, B, C, D). Find candidate keys. (8 marks)
    """

    questions = parse_pyq_questions(sample_paper)
    assert len(questions) >= 5

    # Check Q1(a)
    q1a = next(q for q in questions if "Three-Schema" in q["question_text"])
    assert q1a["question_number"] in ["Q1(a)", "Q1"]
    assert q1a["marks"] == 5

    # Check Q2
    q2 = next(q for q in questions if "Entity-Relationship" in q["question_text"])
    assert q2["question_number"] == "Q2"
    assert q2["marks"] == 10

    # Check Q3(a) and Q3(b)
    q3b = next(q for q in questions if "2-Phase Locking" in q["question_text"])
    assert "2PL" in q3b["question_text"]
    assert q3b["marks"] == 6


@pytest.mark.asyncio
async def test_pyq_fts5_matching_and_lesson_badges():
    """Tests FTS5 BM25 matching of PYQs to course lessons and aggregate hit counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_pyq.db"
        apply_migrations(db_path)
        conn = init_connection(db_path)

        cid = "course-pyq-test"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day)
            VALUES (?, 'Database Engineering', 'DBMS end-term', '2026-12-25', 60);
            """,
            (cid,)
        )
        sid = "source-pyq-test"
        conn.execute(
            """
            INSERT INTO sources (id, course_id, source_type, title, is_approved)
            VALUES (?, ?, 'youtube_playlist', 'DBMS Lectures', 1);
            """,
            (sid, cid)
        )

        # 3 Lessons
        lessons = [
            ("l1", "DBMS Architecture & File Systems", 1800, 1),
            ("l2", "Entity-Relationship Model & Keys", 2400, 2),
            ("l3", "Concurrency Control & 2-Phase Locking", 2400, 3),
        ]
        for lid, title, dur, idx in lessons:
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, start_sec, end_sec, raw_duration_sec, order_index)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?);
                """,
                (lid, cid, sid, title, dur, dur, idx)
            )

        # Populate chunks and chunks_fts
        chunks = [
            ("c1", cid, "l1", "The Three-Schema architecture of a database system defines internal conceptual and external schemas to achieve physical and logical data independence."),
            ("c2", cid, "l2", "In an Entity-Relationship ER model, entities represent real-world objects. A primary key uniquely identifies each entity tuple. Candidate keys are minimal superkeys."),
            ("c3", cid, "l3", "Concurrency control ensures transaction isolation. The 2-Phase Locking 2PL protocol requires transactions to acquire all locks in a growing phase before releasing any in a shrinking phase."),
        ]
        for cid_item, course_id, lesson_id, content in chunks:
            conn.execute(
                """
                INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
                VALUES (?, ?, ?, 0, 50, 0, 300, ?);
                """,
                (cid_item, course_id, lesson_id, content)
            )
            conn.execute(
                """
                INSERT INTO chunks_fts (id, course_id, lesson_id, content)
                VALUES (?, ?, ?, ?);
                """,
                (cid_item, course_id, lesson_id, content)
            )
        conn.commit()

        # Ingest past paper with 3 questions matching each lesson
        pyq_raw = """
        Q1. (a) What is Three-Schema Architecture in database management? [5M]
        Q2. Explain Entity-Relationship ER diagram constructs and primary key attributes. [10M]
        Q3. Describe 2-Phase Locking 2PL protocol for concurrency control in transactions. [8M]
        """

        result = ingest_pyq_source(
            conn,
            course_id=cid,
            title="University Exam 2024",
            raw_text=pyq_raw,
            filename="dbms_2024.pdf"
        )

        assert result["questions_count"] == 3
        assert result["matched_count"] == 3

        # Verify lesson 2 matched Q2
        l2_row = conn.execute("SELECT pyq_hit_count, pyq_total_marks FROM lessons WHERE id = 'l2';").fetchone()
        assert l2_row[0] == 1
        assert l2_row[1] == 10

        # Verify lesson 3 matched Q3
        l3_row = conn.execute("SELECT pyq_hit_count, pyq_total_marks FROM lessons WHERE id = 'l3';").fetchone()
        assert l3_row[0] == 1
        assert l3_row[1] == 8

        # Verify summary query
        summary = get_course_pyq_summary(conn, cid)
        assert summary["total_questions"] == 3
        assert summary["matched_questions"] == 3
        assert len(summary["high_yield_lessons"]) == 3

        # Verify specific lesson PYQs
        l2_pyqs = get_lesson_pyq_questions(conn, cid, "l2")
        assert len(l2_pyqs) == 1
        assert "Entity-Relationship" in l2_pyqs[0]["question_text"]
        assert l2_pyqs[0]["marks"] == 10

        conn.close()


@pytest.mark.asyncio
async def test_cram_sheet_generation_and_sha256_cache():
    """Tests Last-Night Cram Sheet synthesis, deterministic no-key assembly, and SHA-256 cache hits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cram.db"
        apply_migrations(db_path)
        conn = init_connection(db_path)

        cid = "course-cram-test"
        conn.execute(
            """
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day)
            VALUES (?, 'Theory of Computation', 'Automata Finals', '2026-12-22', 45);
            """,
            (cid,)
        )

        # Insert lessons and notes
        conn.execute(
            """
            INSERT INTO lessons (id, course_id, title, start_sec, end_sec, raw_duration_sec, order_index, pyq_hit_count, pyq_total_marks)
            VALUES ('l1', ?, 'Deterministic Finite Automata (DFA)', 0, 1800, 1800, 1, 2, 16);
            """,
            (cid,)
        )
        dfa_notes = """# Deterministic Finite Automata (DFA)

- **Deterministic Finite Automata (DFA)**: A 5-tuple (Q, Sigma, delta, q0, F) where delta is a deterministic transition function.
- **Dead State**: A reject state from which no accepting state can be reached.

| Feature | DFA | NFA |
| :--- | :--- | :--- |
| Transitions per symbol | Exactly 1 | 0, 1, or more |
| Epsilon transitions | Not Allowed | Allowed |
"""
        conn.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, is_generated)
            VALUES ('n1', ?, 'l1', ?, 1);
            """,
            (cid, dfa_notes)
        )

        # Insert a PYQ question
        conn.execute(
            """
            INSERT INTO pyq_questions (id, course_id, question_number, question_text, marks, matched_lesson_id)
            VALUES ('q1', ?, 'Q1(a)', 'Define DFA. Differentiate between DFA and NFA with transition diagrams.', 10, 'l1');
            """,
            (cid,)
        )
        conn.commit()

        # Step 1: Initial Generation (Fresh, not cached)
        sheet1 = await get_or_create_cram_sheet(conn, cid, force_refresh=False)
        assert sheet1["cached"] is False
        assert "Theory of Computation — Last-Night Exam Cram Sheet" in sheet1["content_markdown"]
        assert "High-Yield Exam Weightage Matrix" in sheet1["content_markdown"]
        assert "DFA" in sheet1["content_markdown"]
        assert "Define DFA. Differentiate between DFA and NFA" in sheet1["content_markdown"]

        initial_hash = sheet1["notes_hash"]
        assert len(initial_hash) == 64  # SHA-256

        # Step 2: Instant Cache Hit on second request
        sheet2 = await get_or_create_cram_sheet(conn, cid, force_refresh=False)
        assert sheet2["cached"] is True
        assert sheet2["notes_hash"] == initial_hash
        assert sheet2["content_markdown"] == sheet1["content_markdown"]

        # Step 3: Modifying underlying notes invalidates cache
        conn.execute(
            """
            UPDATE notes SET content_markdown = content_markdown || '\n- **Pumping Lemma**: Used to prove that a language is non-regular.'
            WHERE id = 'n1';
            """
        )
        conn.commit()

        new_hash = compute_course_notes_hash(conn, cid)
        assert new_hash != initial_hash

        # Step 4: Next request detects hash change and regenerates
        sheet3 = await get_or_create_cram_sheet(conn, cid, force_refresh=False)
        assert sheet3["cached"] is False
        assert sheet3["notes_hash"] == new_hash
        assert "Pumping Lemma" in sheet3["content_markdown"]

        conn.close()
