"""Unit tests for Layer 1 Concept Clip Partitioning.

Verifies:
- Sequential continuity: clip[0].start_sec == 0, clip[i].end_sec == clip[i+1].start_sec, clip[-1].end_sec == total_duration.
- Zero gaps, zero overlaps across multi-hour videos.
- ~10–18 min target unit sizing.
- Long concept splitting (> 18 min) into sequential parts.
- Merging tiny (< 3 min) intro/outro micro-chapters.
- AI-Assisted Semantic sliding window mode with marathon continuity.
- Deterministic mode zero-LLM fallback.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from backend.services.concept_partitioner import (
    partition_video_deterministic,
    partition_video_semantic_ai,
    partition_video,
    merge_tiny_chapters,
    detect_priority_tag,
    format_timestamp_pill,
)
from backend.migrations.runner import apply_migrations


def test_merge_tiny_chapters():
    # Chapters with tiny 45s intro and 30s outro
    raw_chapters = [
        {"title": "Intro Teaser", "start_time": 0, "end_time": 45},
        {"title": "DFA Foundations", "start_time": 45, "end_time": 900},
        {"title": "Outro & Subscribe", "start_time": 900, "end_time": 930},
    ]
    merged = merge_tiny_chapters(raw_chapters, total_duration=930, min_sec=180)
    assert len(merged) == 1
    assert merged[0]["title"] == "DFA Foundations"
    assert merged[0]["start_time"] == 0
    assert merged[0]["end_time"] == 930


def test_deterministic_partition_with_chapters_and_long_chapter_split():
    # 2.5 hour video (9,000 sec) with 3 chapters:
    # Ch 1: 10 min (600s) -> stays 1 clip
    # Ch 2: 70 min (4,200s) -> splits into sequential ~12-14 min parts
    # Ch 3: 70 min (4,200s) -> splits into sequential ~12-14 min parts
    total_duration = 9000
    video_meta = {
        "id": "vid-marathon",
        "title": "Automata Theory Full Course",
        "duration": total_duration,
        "chapters": [
            {"title": "Introduction to Grammars", "start_time": 0, "end_time": 600},
            {"title": "Pushdown Automata Theory", "start_time": 600, "end_time": 4800},
            {"title": "Turing Machines and Decidability", "start_time": 4800, "end_time": 9000},
        ],
    }

    # Synthetic transcript chunks
    transcript_chunks = []
    for s in range(0, total_duration, 120):
        transcript_chunks.append({
            "start_sec": s,
            "end_sec": s + 120,
            "content": f"Sentence at second {s}. More discussion here.",
        })

    clips = partition_video_deterministic(video_meta, transcript_data=transcript_chunks)

    # 1. First clip starts at 0
    assert clips[0]["start_sec"] == 0

    # 2. Last clip ends at total_duration
    assert clips[-1]["end_sec"] == total_duration

    # 3. Continuous zero-gap, zero-overlap invariants
    for i in range(len(clips) - 1):
        assert clips[i]["end_sec"] == clips[i + 1]["start_sec"], f"Gap or overlap at index {i}"

    # 4. Clip count and sizing: 9000s / ~780s = ~10-12 clips
    assert len(clips) >= 8
    for c in clips:
        dur_min = c["raw_duration_sec"] / 60.0
        assert 7.0 <= dur_min <= 19.0, f"Clip '{c['title']}' duration {dur_min}m outside acceptable range"

    # 5. Check sequential part naming on long chapter
    pda_parts = [c for c in clips if "Pushdown Automata Theory" in c["title"]]
    assert len(pda_parts) >= 3
    assert "Part 1" in pda_parts[0]["title"]
    assert "Part 2" in pda_parts[1]["title"]


def test_deterministic_partition_chapterless_marathon():
    # 5-hour marathon video (18,000 sec) with NO chapters
    total_duration = 18000
    video_meta = {
        "id": "vid-marathon-no-ch",
        "title": "Discrete Math Marathon",
        "duration": total_duration,
        "chapters": [],
    }

    transcript_chunks = [
        {"start_sec": s, "end_sec": s + 60, "content": f"Topic content at {s}."}
        for s in range(0, total_duration, 60)
    ]

    clips = partition_video_deterministic(video_meta, transcript_data=transcript_chunks)

    assert clips[0]["start_sec"] == 0
    assert clips[-1]["end_sec"] == total_duration
    for i in range(len(clips) - 1):
        assert clips[i]["end_sec"] == clips[i + 1]["start_sec"]

    # 18000s / ~780s = ~23 clips
    assert 18 <= len(clips) <= 30
    for c in clips:
        dur_min = c["raw_duration_sec"] / 60.0
        assert 7.5 <= dur_min <= 18.5


def test_ai_semantic_sliding_window_mocked(monkeypatch):
    """Verifies that sliding window AI-assisted semantic partitioning processes
    a multi-hour lecture in 45-60 min windows and strictly guarantees continuity.
    """
    total_duration = 7200 # 2 hours
    video_meta = {
        "id": "vid-semantic-test",
        "title": "Algorithms Deep Dive",
        "duration": total_duration,
        "chapters": [],
    }

    transcript_chunks = [
        {"start_sec": s, "end_sec": s + 60, "content": f"Algorithm step at {s}."}
        for s in range(0, total_duration, 60)
    ]

    # Mock _call_llm_for_window
    call_counts = []
    def mock_call_llm(video_title, window_start, window_end, transcript_text, db_conn=None):
        call_counts.append((window_start, window_end))
        w_dur = window_end - window_start
        mid = window_start + (w_dur // 2)
        return [
            {
                "title": f"Concept Analysis [{window_start}s]",
                "start_sec": window_start,
                "end_sec": mid,
                "priority_tag": "core",
            },
            {
                "title": f"Worked Example Exercise [{mid}s]",
                "start_sec": mid,
                "end_sec": window_end,
                "priority_tag": "deep-dive",
            },
        ]

    monkeypatch.setattr("backend.services.concept_partitioner._call_llm_for_window", mock_call_llm)
    monkeypatch.setattr("backend.services.concept_partitioner.get_settings", lambda: type("Settings", (), {
        "GEMINI_API_KEY": "fake-key",
        "GROQ_API_KEY": None,
        "OPENROUTER_API_KEY": None,
    })())

    clips = partition_video_semantic_ai(video_meta, transcript_chunks, window_duration_sec=3000)

    assert clips is not None
    assert len(clips) >= 4
    # Check window sliding invocations
    assert len(call_counts) >= 2
    assert clips[0]["start_sec"] == 0
    assert clips[-1]["end_sec"] == total_duration

    for i in range(len(clips) - 1):
        assert clips[i]["end_sec"] == clips[i + 1]["start_sec"]

    # Verify priority tagging
    examples = [c for c in clips if "Worked Example" in c["title"]]
    assert len(examples) > 0
    assert all(e["priority_tag"] == "deep-dive" for e in examples)
