"""Live smoke test for user-specified YouTube anchors:

1. TOC Playlist: https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev
2. Large Single Lecture: https://youtu.be/YRnjGeQbsHQ
"""

import pytest
import yt_dlp
from backend.services.youtube import discover_candidates, extract_metadata, split_video_into_lessons

# User test anchors
TOC_PLAYLIST_URL = "https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev"
LARGE_VIDEO_URL = "https://youtu.be/YRnjGeQbsHQ"

def test_live_user_toc_playlist():
    """Live smoke test on Neso Academy TOC playlist (zero video download)."""
    opts = {"quiet": True, "extract_flat": "in_playlist", "skip_download": True, "socket_timeout": 15}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(TOC_PLAYLIST_URL, download=False)
    except Exception as e:
        pytest.skip(f"Live YouTube TOC playlist fetch restricted or throttled: {e}")

    assert meta is not None
    assert "Theory of Computation" in meta.get("title", "")
    entries = meta.get("entries", [])
    assert len(entries) >= 50, f"Expected 50+ TOC videos, found {len(entries)}"

    # Check sample video
    first = entries[0]
    assert first is not None
    assert "id" in first
    assert "title" in first

def test_live_user_large_video():
    """Live smoke test on single large lecture video (https://youtu.be/YRnjGeQbsHQ)."""
    try:
        meta = extract_metadata(LARGE_VIDEO_URL)
        if not meta or not meta.get("duration"):
            pytest.skip("Live YouTube large video fetch offline or throttled.")
    except Exception as e:
        pytest.skip(f"Live YouTube large video fetch restricted or throttled: {e}")

    assert meta is not None
    # 20,010 seconds = ~5.5 hours
    duration = meta.get("duration", 0)
    assert duration > 10000, f"Expected marathon lecture > 10,000s, got {duration}"

    # Verify chapters
    chapters = meta.get("chapters", [])
    assert len(chapters) >= 5, f"Expected 5+ chapters in marathon lecture, found {len(chapters)}"

    lessons = split_video_into_lessons(meta)
    assert len(lessons) == len(chapters), f"Expected 1 chapter = 1 lesson ({len(chapters)}), got {len(lessons)}"
    assert lessons[0]["video_id"] is not None
    assert lessons[0]["raw_duration_sec"] > 0

def test_live_youtube_discovery():
    """Live smoke test discovering candidate videos without API key."""
    res = discover_candidates("python fast tutorial", max_videos=2, max_playlists=1)
    if res.get("error"):
        pytest.skip(f"Live network fetch skipped: {res.get('error')}")

    assert isinstance(res["candidate_videos"], list)
    assert isinstance(res["candidate_playlists"], list)
