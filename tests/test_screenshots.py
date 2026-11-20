"""Unit tests for Milestone 2 Screenshots Service."""

import pytest
from pathlib import Path
from backend.services.screenshots import (
    get_screenshots_dir,
    get_lesson_screenshots,
    capture_lesson_keyframes,
)
from backend.migrations.runner import apply_migrations
from backend.database import init_connection


@pytest.mark.asyncio
async def test_screenshot_dir_and_db_flow(tmp_path, monkeypatch):
    # Setup temporary db and data dir
    db_file = tmp_path / "test_shots.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    # Seed course and lesson
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c_shot', 'OS', 'OS', '2026-12-31');")
    conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec, start_sec, end_sec) VALUES ('l_shot', 'c_shot', 'Paging', 600, 0, 600);")
    conn.commit()

    # Mock extract_frame_ffmpeg and create_fallback_thumbnail to avoid external network/ffmpeg in unit tests
    def mock_extract(stream_url, ts, out_path, ffmpeg_bin="ffmpeg"):
        out_path.write_bytes(b"\xff\xd8\xff\xe0" + b"mock_jpeg_bytes" * 50)
        return True

    monkeypatch.setattr("backend.services.screenshots.extract_frame_ffmpeg", mock_extract)
    monkeypatch.setattr("backend.services.screenshots.resolve_stream_url", lambda v: "http://mock.stream")

    # Capture keyframes
    shots = await capture_lesson_keyframes(
        conn,
        course_id="c_shot",
        lesson_id="l_shot",
        video_id="mock_vid_123",
        start_sec=0,
        end_sec=600,
        timestamps=[60, 300, 500]
    )

    assert len(shots) == 3
    assert shots[0]["timestamp_sec"] == 60
    assert shots[0]["formatted_time"] == "01:00"
    assert "/api/screenshots/c_shot/l_shot/kf_60.jpg" in shots[0]["url"]

    # Verify retrieval
    retrieved = get_lesson_screenshots(conn, "l_shot")
    assert len(retrieved) == 3
    assert retrieved[1]["timestamp_sec"] == 300
    assert retrieved[1]["formatted_time"] == "05:00"

    conn.close()
