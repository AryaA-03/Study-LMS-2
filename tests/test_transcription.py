"""Unit tests for Milestone 2 Transcription and Deduplication Service."""

import pytest
import sqlite3
from pathlib import Path

from backend.services.transcription import (
    parse_and_deduplicate_json3,
    parse_and_deduplicate_vtt,
    _group_words_into_chunks,
)
from backend.services.notes import (
    format_seconds_to_mm_ss,
    generate_no_key_structured_notes,
    save_personal_notes,
    get_or_generate_lesson_notes,
)
from backend.migrations.runner import apply_migrations
from backend.database import init_connection


def test_format_seconds_to_mm_ss():
    assert format_seconds_to_mm_ss(0) == "[00:00]"
    assert format_seconds_to_mm_ss(75) == "[01:15]"
    assert format_seconds_to_mm_ss(600) == "[10:00]"
    assert format_seconds_to_mm_ss(3665) == "[01:01:05]"


def test_parse_and_deduplicate_json3():
    mock_json3 = {
        "events": [
            {
                "tStartMs": 1000,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "Hello", "tOffsetMs": 0},
                    {"utf8": " world", "tOffsetMs": 500},
                    {"utf8": " this", "tOffsetMs": 1000},
                    {"utf8": " is", "tOffsetMs": 1500},
                ]
            },
            {
                "tStartMs": 3000,
                "aAppend": 1,
                "segs": [{"utf8": "\n"}]
            },
            {
                "tStartMs": 3100,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "a", "tOffsetMs": 0},
                    {"utf8": " test", "tOffsetMs": 400},
                    {"utf8": " of", "tOffsetMs": 800},
                    {"utf8": " captions", "tOffsetMs": 1200},
                ]
            }
        ]
    }

    chunks = parse_and_deduplicate_json3(mock_json3, start_sec=0, end_sec=10, target_chunk_tokens=10)
    assert len(chunks) > 0
    first_chunk = chunks[0]
    assert "Hello world this is" in first_chunk["content"]
    assert "test of captions" in first_chunk["content"]
    assert first_chunk["start_sec"] == 1
    assert first_chunk["token_count"] > 0


def test_parse_and_deduplicate_vtt_rolling():
    """Tests deduplication of rolling overlapping captions commonly returned by YouTube auto-captions."""
    mock_vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
Introduction to Theory

00:00:03.000 --> 00:00:05.500
Introduction to Theory
of Computation and Automata

00:00:05.500 --> 00:00:08.000
of Computation and Automata
Finite State Machines
"""

    chunks = parse_and_deduplicate_vtt(mock_vtt, start_sec=0, end_sec=10, target_chunk_tokens=10)
    assert len(chunks) > 0
    content = chunks[0]["content"]
    # The duplicate "Introduction to Theory" and "of Computation and Automata" lines must be deduplicated
    words = content.split()
    assert words.count("Introduction") == 1
    assert words.count("Automata") == 1


def test_generate_no_key_structured_notes():
    chunks = [
        {
            "id": "chk_001",
            "chunk_index": 0,
            "start_sec": 0,
            "end_sec": 120,
            "content": "A deterministic finite automaton consists of five tuples: states, alphabet, transition function, start state, and accept states.",
            "token_count": 25,
        },
        {
            "id": "chk_002",
            "chunk_index": 1,
            "start_sec": 120,
            "end_sec": 240,
            "content": "Transition diagrams represent state machines visually using circles for states and directed arrows for transitions.",
            "token_count": 20,
        }
    ]

    notes = generate_no_key_structured_notes("DFA Fundamentals", chunks)
    assert "# DFA Fundamentals" in notes
    assert "[00:00]" in notes
    assert "[02:00]" in notes
    assert "chk_001" not in notes
    assert "chk_002" not in notes
    assert "Timestamped Lecture Outline" in notes


@pytest.mark.asyncio
async def test_notes_persistence_and_personal_notes(tmp_path):
    db_file = tmp_path / "test_notes.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    # Seed course and lesson
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'TOC', 'TOC', '2026-12-31');")
    conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec, start_sec, end_sec) VALUES ('l1', 'c1', 'DFA Lesson', 300, 0, 300);")
    conn.execute(
        """
        INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
        VALUES ('chk_1', 'c1', 'l1', 0, 30, 0, 150, 'States and alphabets in automata theory.');
        """
    )
    conn.commit()

    # 1. Generate notes
    notes_data = await get_or_generate_lesson_notes(conn, 'c1', 'l1', force_regenerate=False)
    assert notes_data["is_generated"] == 1
    assert "States and alphabets" in notes_data["content_markdown"]

    # 2. Save personal notes
    save_personal_notes(conn, 'c1', 'l1', "Remember: Q is finite set of states.")
    
    # 3. Retrieve notes again
    notes_retrieved = await get_or_generate_lesson_notes(conn, 'c1', 'l1', force_regenerate=False)
    assert notes_retrieved["personal_notes"] == "Remember: Q is finite set of states."

    conn.close()
