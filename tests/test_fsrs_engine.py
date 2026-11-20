"""Unit tests for FSRS Spaced Repetition Engine."""

import sqlite3
import datetime
from datetime import timezone, timedelta
from pathlib import Path
import tempfile
import pytest

from backend.migrations.runner import apply_migrations
from backend.services.fsrs_engine import (
    create_flashcard,
    review_flashcard,
    get_due_flashcards,
    get_flashcard_counts,
    calculate_target_retention,
    format_interval,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        p = Path(tmp.name)
        apply_migrations(p)
        conn = sqlite3.connect(p)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day) VALUES ('c_test', 'TOC', 'prep', '2026-12-15', 60)")
        conn.commit()
        yield conn
        conn.close()


def test_target_retention_scaling():
    today = datetime.date(2026, 12, 1)
    
    # 14+ days away -> standard 0.90
    assert calculate_target_retention("2026-12-25", today=today) == 0.90
    
    # 8-14 days away -> 0.92
    assert calculate_target_retention("2026-12-12", today=today) == 0.92
    
    # 4-7 days away -> 0.94
    assert calculate_target_retention("2026-12-06", today=today) == 0.94
    
    # <=3 days away -> 0.96 (high crunch retention)
    assert calculate_target_retention("2026-12-03", today=today) == 0.96


def test_format_interval():
    assert format_interval(timedelta(seconds=45)) == "45s"
    assert format_interval(timedelta(minutes=10)) == "10m"
    assert format_interval(timedelta(hours=4)) == "4h"
    assert format_interval(timedelta(days=7)) == "7d"


def test_fsrs_card_lifecycle(temp_db):
    conn = temp_db
    course_id = "c_test"

    # 1. Create Flashcard
    card = create_flashcard(
        conn=conn,
        course_id=course_id,
        front="What is a Regular Language?",
        back="A language recognized by a finite automaton.",
        source_quote="A regular language is a language that can be expressed with a regular expression or recognized by a DFA.",
    )
    assert card["id"].startswith("fc_")
    assert card["reps"] == 0
    assert card["intervals"][1] != ""  # Again
    assert card["intervals"][3] != ""  # Good

    # 2. Check counts
    counts = get_flashcard_counts(conn, course_id)
    assert counts["total"] == 1
    assert counts["due"] == 1
    assert counts["new"] == 1

    # 3. Review Card with Rating.Good (3)
    now = datetime.datetime.now(timezone.utc)
    card_after, interval_str = review_flashcard(conn, card["id"], rating=3, exam_date="2026-12-15", review_time=now)
    assert card_after["reps"] == 1
    assert card_after["state_name"] == "Learning"
    assert "m" in interval_str or "d" in interval_str

    # 4. Review again after due interval with Rating.Easy (4)
    future = now + timedelta(days=1)
    card_after_easy, interval_str_easy = review_flashcard(conn, card["id"], rating=4, exam_date="2026-12-15", review_time=future)
    assert card_after_easy["reps"] == 2
    assert card_after_easy["state_name"] == "Review"
    assert card_after_easy["stability"] > card_after["stability"]


def test_fsrs_card_lapse_on_again(temp_db):
    conn = temp_db
    course_id = "c_test"

    card = create_flashcard(
        conn=conn,
        course_id=course_id,
        front="What is Pumping Lemma?",
        back="A property of all regular languages used to prove non-regularity.",
    )

    now = datetime.datetime.now(timezone.utc)
    # Review with Again (1)
    card_after, interval_str = review_flashcard(conn, card["id"], rating=1, exam_date="2026-12-15", review_time=now)
    assert card_after["reps"] == 1
    assert interval_str == "1m"
