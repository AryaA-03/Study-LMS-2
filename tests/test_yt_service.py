"""Unit tests for YouTube service and lesson splitting logic."""

from backend.services.youtube import (
    format_duration,
    split_video_into_lessons,
    get_ytdlp_version,
)

def test_format_duration():
    assert format_duration(0) == "00:00"
    assert format_duration(45) == "00:45"
    assert format_duration(125) == "02:05"
    assert format_duration(3665) == "01:01:05"

def test_split_video_with_chapters():
    video_meta = {
        "id": "vid123",
        "title": "Database Systems Lecture",
        "webpage_url": "https://www.youtube.com/watch?v=vid123",
        "duration": 3600,
        "chapters": [
            {"title": "Introduction & ACID", "start_time": 0, "end_time": 1200},
            {"title": "Relational Algebra", "start_time": 1200, "end_time": 2400},
            {"title": "Normalization (1NF-BCNF)", "start_time": 2400, "end_time": 3600},
        ],
    }

    lessons = split_video_into_lessons(video_meta)
    assert len(lessons) == 3
    assert lessons[0]["chapter_title"] == "Introduction & ACID"
    assert lessons[0]["start_sec"] == 0
    assert lessons[0]["end_sec"] == 1200
    assert lessons[0]["raw_duration_sec"] == 1200
    assert lessons[0]["video_id"] == "vid123"

    assert lessons[1]["chapter_title"] == "Relational Algebra"
    assert lessons[1]["start_sec"] == 1200
    assert lessons[1]["end_sec"] == 2400

    assert lessons[2]["chapter_title"] == "Normalization (1NF-BCNF)"
    assert lessons[2]["start_sec"] == 2400
    assert lessons[2]["end_sec"] == 3600

def test_split_video_without_chapters_deterministic():
    # 50 minute video (3000 seconds) without chapters
    # 15 min chunks = 900 sec
    # Chunk 1: 0 - 900 (15 min)
    # Chunk 2: 900 - 1800 (15 min)
    # Chunk 3: 1800 - 2700 (15 min)
    # Remaining 300 sec (5 min) is exactly 5 min, so gets its own chunk or merges if < 5 min
    video_meta = {
        "id": "vid456",
        "title": "Crash Course",
        "webpage_url": "https://www.youtube.com/watch?v=vid456",
        "duration": 3000,
        "chapters": None,
    }

    lessons = split_video_into_lessons(video_meta, default_chunk_min=15)
    assert len(lessons) == 4
    assert lessons[0]["start_sec"] == 0
    assert lessons[0]["end_sec"] == 900
    assert lessons[0]["raw_duration_sec"] == 900
    assert "[00:00 - 15:00]" in lessons[0]["title"]

    assert lessons[1]["start_sec"] == 900
    assert lessons[1]["end_sec"] == 1800

    assert lessons[2]["start_sec"] == 1800
    assert lessons[2]["end_sec"] == 2700

    assert lessons[3]["start_sec"] == 2700
    assert lessons[3]["end_sec"] == 3000

def test_split_video_merges_small_remainder():
    # 32 minute video (1920 sec)
    # Chunk 1: 0 - 900 (15 min)
    # Next start: 900. 900 + 900 = 1800. Remainder = 1920 - 1800 = 120 sec (< 300 sec / 5 min)
    # It should merge remainder into Chunk 2 (900 - 1920)
    video_meta = {
        "id": "vid789",
        "title": "Short Tutorial",
        "duration": 1920,
        "chapters": [],
    }
    lessons = split_video_into_lessons(video_meta, default_chunk_min=15)
    assert len(lessons) == 2
    assert lessons[0]["start_sec"] == 0
    assert lessons[0]["end_sec"] == 900
    assert lessons[1]["start_sec"] == 900
    assert lessons[1]["end_sec"] == 1920
    assert lessons[1]["raw_duration_sec"] == 1020

def test_ytdlp_version_installed():
    ver = get_ytdlp_version()
    assert ver != "unknown"
    assert len(ver) > 4

def test_sub_3_minute_chapter_merging():
    """Verifies that chapters shorter than 3 minutes (180s) merge with adjacent chapters."""
    video_meta = {
        "id": "vid_short_chapters",
        "title": "TOC Course Lecture",
        "webpage_url": "https://www.youtube.com/watch?v=vid_short_chapters",
        "duration": 3600,
        "chapters": [
            {"title": "Intro Bumper", "start_time": 0, "end_time": 42},          # 42s (< 180s) -> merge into next
            {"title": "Finite State Machine", "start_time": 42, "end_time": 600}, # 558s
            {"title": "Micro Break", "start_time": 600, "end_time": 640},        # 40s (< 180s) -> merge into next
            {"title": "Deterministic Automata", "start_time": 640, "end_time": 1800},
            {"title": "Outro Clip", "start_time": 1800, "end_time": 1830},       # 30s (< 180s, trailing) -> merge into previous
        ],
    }

    lessons = split_video_into_lessons(video_meta, min_chapter_sec=180)
    # The 5 chapters should collapse into 2 robust lessons >= 180s each:
    # Lesson 0: 0 to 600 ("Finite State Machine", 600s)
    # Lesson 1: 600 to 1830 ("Deterministic Automata", 1230s)
    assert len(lessons) == 2
    assert lessons[0]["start_sec"] == 0
    assert lessons[0]["end_sec"] == 600
    assert lessons[0]["raw_duration_sec"] == 600
    assert lessons[0]["chapter_title"] == "Finite State Machine"

    assert lessons[1]["start_sec"] == 600
    assert lessons[1]["end_sec"] == 1830
    assert lessons[1]["raw_duration_sec"] == 1230
    assert lessons[1]["chapter_title"] == "Deterministic Automata"
