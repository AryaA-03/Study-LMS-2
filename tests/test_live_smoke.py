"""Live smoke test for YouTube metadata extraction and discovery."""

import pytest
from backend.services.youtube import discover_candidates, extract_metadata, split_video_into_lessons

def test_live_youtube_discovery():
    """Live smoke test discovering candidate videos without API key."""
    # Discover candidates for a short query
    res = discover_candidates("python fast tutorial", max_videos=2, max_playlists=1)
    # If network is offline or throttled by sandbox, verify clean error handling without crash
    if res.get("error"):
        pytest.skip(f"Live network fetch skipped or restricted: {res.get('error')}")

    assert isinstance(res["candidate_videos"], list)
    assert isinstance(res["candidate_playlists"], list)
    if len(res["candidate_videos"]) > 0:
        first = res["candidate_videos"][0]
        assert "id" in first
        assert "title" in first
        assert "url" in first

def test_live_youtube_metadata_and_splitting():
    """Live smoke test extracting metadata for a short public video (zero download)."""
    # Short 10-second test video: https://www.youtube.com/watch?v=jNQXAC9IVRw (Me at the zoo)
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    try:
        meta = extract_metadata(url)
    except Exception as e:
        pytest.skip(f"Live YouTube metadata fetch restricted or timed out: {e}")

    assert meta is not None
    assert meta.get("id") == "jNQXAC9IVRw"
    assert "duration" in meta

    lessons = split_video_into_lessons(meta)
    assert len(lessons) >= 1
    assert lessons[0]["video_id"] == "jNQXAC9IVRw"
    assert lessons[0]["raw_duration_sec"] > 0
