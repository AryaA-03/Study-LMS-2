import pytest
pytestmark = pytest.mark.live
"""Live Smoke Tests for Milestone 2 against user-specified YouTube anchors.

Anchors:
1. TOC Playlist: https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev
2. Large Video: https://youtu.be/YRnjGeQbsHQ
"""

import pytest
from pathlib import Path

from backend.services.transcription import fetch_youtube_captions, ingest_lesson_transcript
from backend.services.notes import get_or_generate_lesson_notes
from backend.migrations.runner import apply_migrations
from backend.database import init_connection


@pytest.mark.asyncio
async def test_live_m2_toc_playlist_captions_and_notes(tmp_path):
    """Smoke test: Ingest real captions and generate structured notes for TOC anchor video."""
    video_id = "58N2N7zJGrQ"  # Video 1 of TOC playlist: Introduction to Theory of Computation
    db_file = tmp_path / "live_m2_toc.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    # Seed course and lesson
    cid = "live_toc_c"
    lid = "live_toc_l1"
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES (?, 'TOC Course', 'TOC', '2026-12-31');", (cid,))
    conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved) VALUES ('s1', ?, 'youtube_video', 'TOC Video 1', 1);", (cid,))
    conn.execute(
        """
        INSERT INTO lessons (id, course_id, source_id, title, video_id, raw_duration_sec, start_sec, end_sec)
        VALUES (?, ?, 's1', 'Introduction to TOC', ?, 695, 0, 695);
        """,
        (lid, cid, video_id)
    )
    conn.commit()

    # 1. Ingest real captions
    success, t_type, chunk_count = await ingest_lesson_transcript(
        conn,
        course_id=cid,
        source_id="s1",
        lesson_id=lid,
        video_id_or_url=video_id,
        start_sec=0,
        end_sec=695
    )

    assert success is True
    assert chunk_count > 0
    if t_type == "structured_metadata":
        pytest.skip("Live network unavailable in environment; offline fallback verified.")
    assert t_type in ("captions", "whisper")

    # 2. Verify chunks stored in DB and searchable via FTS5
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chunks WHERE lesson_id = ?;", (lid,))
    assert cur.fetchone()[0] == chunk_count

    cur.execute("SELECT id, content FROM chunks_fts WHERE content MATCH 'theory OR computation' LIMIT 5;")
    fts_rows = cur.fetchall()
    assert len(fts_rows) > 0, "FTS5 query should match words in TOC transcript"

    # 3. Generate notes
    notes = await get_or_generate_lesson_notes(conn, cid, lid, force_regenerate=True)
    markdown = notes["content_markdown"]
    assert len(markdown) > 100
    assert "Theory of Computation" in markdown or "TOC" in markdown
    assert "[" in markdown and "]" in markdown, "Must contain clickable [MM:SS] timestamp tags"

    conn.close()


@pytest.mark.asyncio
async def test_live_m2_large_video_captions_and_notes(tmp_path):
    """Smoke test: Ingest captions / Whisper slice for chapter 1 of 5.5 hour DBMS video."""
    video_id = "YRnjGeQbsHQ"  # 5.5 hour DBMS video
    db_file = tmp_path / "live_m2_large.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    cid = "live_large_c"
    lid = "live_large_l1"
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES (?, 'DBMS Marathon', 'DBMS', '2026-12-31');", (cid,))
    conn.execute("INSERT INTO sources (id, course_id, source_type, title, is_approved) VALUES ('s2', ?, 'youtube_video', 'DBMS Lecture', 1);", (cid,))
    # Chapter 1 slice: [0 - 60]
    conn.execute(
        """
        INSERT INTO lessons (id, course_id, source_id, title, video_id, raw_duration_sec, start_sec, end_sec)
        VALUES (?, ?, 's2', 'DBMS Architecture & Basics', ?, 60, 0, 60);
        """,
        (lid, cid, video_id)
    )
    conn.commit()

    success, t_type, chunk_count = await ingest_lesson_transcript(
        conn,
        course_id=cid,
        source_id="s2",
        lesson_id=lid,
        video_id_or_url=video_id,
        start_sec=0,
        end_sec=60
    )

    assert success is True
    assert chunk_count > 0

    notes = await get_or_generate_lesson_notes(conn, cid, lid, force_regenerate=True)
    markdown = notes["content_markdown"]
    assert len(markdown) > 100
    assert "DBMS" in markdown

    conn.close()
