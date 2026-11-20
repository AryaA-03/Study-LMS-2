"""Unit tests for Milestone 3 Grounded Q&A Engine."""

import pytest
from pathlib import Path

from backend.services.qa_engine import (
    search_chunks_fts,
    format_no_key_answer,
    answer_course_question,
    get_course_qa_history,
)
from backend.migrations.runner import apply_migrations
from backend.database import init_connection


@pytest.mark.asyncio
async def test_qa_fts_and_grounding(tmp_path):
    db_file = tmp_path / "test_qa_db.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    cid = "course_qa_test"
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES (?, 'TOC Course', 'TOC', '2026-12-31');", (cid,))

    # Seed 3 multi-source chunks: YouTube, PDF, Web
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, is_approved)
        VALUES ('src_yt', ?, 'youtube_video', 'Lecture 1: Finite Automata', 1);
        """,
        (cid,)
    )
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, is_approved)
        VALUES ('src_pdf', ?, 'pdf', 'Hopcroft & Ullman Textbook Chapter 2', 1);
        """,
        (cid,)
    )
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, is_approved)
        VALUES ('src_web', ?, 'web_page', 'Wikipedia: State Transitions in Automata', 1);
        """,
        (cid,)
    )

    conn.execute(
        """
        INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, start_sec, end_sec, content, source_type)
        VALUES ('chk_1', ?, 'src_yt', 0, 40, 60, 180, 'A deterministic finite automaton consists of five tuples: states Q, alphabet Sigma, delta, q0, and accept states F.', 'youtube_video');
        """,
        (cid,)
    )
    conn.execute(
        """
        INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, content, source_type)
        VALUES ('chk_2', ?, 'src_pdf', 0, 50, '[Page 45] Pumping Lemma for regular languages states that for any regular language L, there exists a pumping length p.', 'pdf');
        """,
        (cid,)
    )
    conn.execute(
        """
        INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, content, source_type)
        VALUES ('chk_3', ?, 'src_web', 0, 45, 'Non-deterministic finite automata (NFA) can have epsilon transitions and multiple next states for a single symbol.', 'web_page');
        """,
        (cid,)
    )

    conn.execute("INSERT INTO chunks_fts (id, course_id, lesson_id, content) VALUES ('chk_1', ?, NULL, 'A deterministic finite automaton consists of five tuples: states Q, alphabet Sigma, delta, q0, and accept states F.');", (cid,))
    conn.execute("INSERT INTO chunks_fts (id, course_id, lesson_id, content) VALUES ('chk_2', ?, NULL, '[Page 45] Pumping Lemma for regular languages states that for any regular language L, there exists a pumping length p.');", (cid,))
    conn.execute("INSERT INTO chunks_fts (id, course_id, lesson_id, content) VALUES ('chk_3', ?, NULL, 'Non-deterministic finite automata (NFA) can have epsilon transitions and multiple next states for a single symbol.');", (cid,))
    conn.commit()

    # 1. Test FTS5 BM25 search
    hits = search_chunks_fts(conn, cid, "five tuples deterministic finite automaton")
    assert len(hits) >= 1
    assert hits[0]["id"] == "chk_1"
    assert hits[0]["source_type"] == "youtube_video"
    assert hits[0]["start_sec"] == 60

    # 2. Test No-Key Grounded Answer Generation
    answer, citations = format_no_key_answer("What are the 5 tuples?", hits)
    assert "Lecture 1: Finite Automata" in answer
    assert "[ref:chk_1]" in answer
    assert "[01:00]" in answer
    assert len(citations) >= 1
    assert citations[0]["chunk_id"] == "chk_1"

    # 3. Test Negative / Insufficient Evidence Case
    empty_answer, empty_cits = format_no_key_answer("What is quantum entanglement?", [])
    assert "sufficient evidence" in empty_answer.lower()
    assert len(empty_cits) == 0

    # 4. Test High-Level Orchestrator & Persistence
    qa_result = await answer_course_question(conn, cid, "Pumping Lemma explanation")
    assert "Pumping Lemma" in qa_result["answer_markdown"] or "Hopcroft" in qa_result["answer_markdown"]
    assert qa_result["id"].startswith("qa_")

    # 5. Retrieve History
    history = get_course_qa_history(conn, cid)
    assert len(history) == 1
    assert history[0]["query"] == "Pumping Lemma explanation"

    conn.close()
