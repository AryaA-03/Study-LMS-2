"""Tests for Playlist Topic Grouping & Overhauled High-Yield Cram Sheet."""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.migrations.runner import apply_migrations
from backend.services.cram_sheet_engine import generate_deterministic_cram_sheet
from backend.services.topic_grouper import (
    classify_lesson_role,
    group_playlist_lessons,
    normalize_topic_stem,
)


def test_topic_grouper_clusters_parts_and_examples():
    lessons = [
        {"id": "1", "title": "Deterministic Finite Automata (Part 1) | Neso Academy"},
        {"id": "2", "title": "Deterministic Finite Automata (Part 2) | Neso Academy"},
        {"id": "3", "title": "Deterministic Finite Automata Example 1"},
        {"id": "4", "title": "Example 2"},
        {"id": "5", "title": "Pushdown Automata (Introduction)"},
        {"id": "6", "title": "Pushdown Automata Part 2"},
    ]
    grouped = group_playlist_lessons(lessons)
    assert len(grouped) == 6
    # First 4 videos belong to the same DFA topic group
    dfa_topics = {g["chapter_title"] for g in grouped[:4]}
    assert len(dfa_topics) == 1
    # Last 2 belong to Pushdown Automata topic group
    pda_topics = {g["chapter_title"] for g in grouped[4:]}
    assert len(pda_topics) == 1
    assert dfa_topics != pda_topics

    # Role classification for Lesson Rail Filters
    assert classify_lesson_role("Deterministic Finite Automata (Part 1)") == "concept"
    assert classify_lesson_role("Deterministic Finite Automata Example 1") == "example"
    assert classify_lesson_role("Solved GATE 2023 Problem on PDA") == "example"
    assert "Neso" not in normalize_topic_stem("DFA Part 1 | Neso Academy")


def test_cluster_endpoint_and_zero_boilerplate_cram_sheet(tmp_path, monkeypatch):
    db_path = tmp_path / "topic_cram_v2.db"
    apply_migrations(str(db_path))

    def _get_test_db():
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _get_test_db
    monkeypatch.setattr("backend.database.DB_PATH", str(db_path))
    client = TestClient(app)

    try:
        c_resp = client.post(
            "/api/courses",
            json={
                "title": "Theory of Computation",
                "goal_query": "TOC",
                "target_date": "2027-02-01",
                "minutes_per_day": 60,
                "playback_speed": 1.25,
                "rest_days": [],
                "revision_buffer_days": 2,
                "schedule_strategy": "paced",
            },
        )
        assert c_resp.status_code == 200
        cid = c_resp.json()["id"]

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT INTO sources (id, course_id, source_type, title, url, is_approved) VALUES ('s1', ?, 'youtube_playlist', 'TOC Playlist', 'https://youtube.com/playlist?list=test', 1)",
            (cid,),
        )
        conn.execute(
            "INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, start_sec, order_index) VALUES ('l1', ?, 's1', 'Pushdown Automata Part 1', 600, 0, 0)",
            (cid,),
        )
        conn.execute(
            "INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, start_sec, order_index) VALUES ('l2', ?, 's1', 'Pushdown Automata Example 1', 480, 120, 1)",
            (cid,),
        )
        conn.execute(
            "INSERT INTO lessons (id, course_id, source_id, title, raw_duration_sec, start_sec, order_index) VALUES ('l3', ?, 's1', 'Turing Machine Basics', 720, 0, 2)",
            (cid,),
        )
        # Real structured note on l1 with formula + comparison table
        conn.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown) VALUES (
                'n1', ?, 'l1',
                '# Pushdown Automata\n- **PDA**: A finite automaton augmented with an unbounded LIFO stack to recognize Context-Free Languages [00:45].\n- Transition function: $\\delta: Q \\times (\\Sigma \\cup \\{\\varepsilon\\}) \\times \\Gamma \\to P(Q \\times \\Gamma^*)$ [02:10]\n\n| Model | Memory | Language Class |\n| --- | --- | --- |\n| FSM | None | Regular |\n| PDA | 1 Stack | Context-Free |\n'
            );
            """,
            (cid,),
        )
        # Real transcript chunk on l2 (no note yet -> Cram Sheet should extract real transcript highlight!)
        conn.execute(
            "INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, start_sec, end_sec, content, token_count) VALUES ('c1', ?, 's1', 'l2', 0, 125, 180, 'The key theorem for palindrome acceptance is that a deterministic PDA requires a center marker whereas a nondeterministic PDA guesses the midpoint.', 25)",
            (cid,),
        )
        conn.commit()
        conn.close()

        # 1. Test /topics/cluster endpoint
        cl_resp = client.post(f"/api/courses/{cid}/topics/cluster")
        assert cl_resp.status_code == 200
        cl_data = cl_resp.json()
        assert cl_data["lessons_updated"] == 3
        assert cl_data["topics_created"] == 2

        # 2. Test Overhauled Cram Sheet (zero boilerplate, real formula, table, transcript highlight)
        conn = sqlite3.connect(str(db_path))
        md = generate_deterministic_cram_sheet(conn, cid)
        conn.close()

        assert "Foundational mathematical model" not in md
        assert "Master formal notations" not in md
        assert "Pushdown Automata" in md
        assert "LIFO stack" in md
        assert "\\delta" in md
        assert "| Model | Memory | Language Class |" in md
        assert "palindrome acceptance" in md
        assert "Lessons Pending Notes Synthesis" in md  # transparent disclosure for l3
        assert "Turing Machine Basics" in md
    finally:
        app.dependency_overrides.clear()
