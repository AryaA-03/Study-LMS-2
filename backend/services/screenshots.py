"""Opt-In Keyframe Screenshots Service.

Extracts low-res (~40 KB, 480p) keyframe frames at topic/chunk transitions
using ffmpeg on fresh re-resolved YouTube streams, with thumbnail fallback.
"""

import os
import uuid
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

import yt_dlp

from backend.config import get_settings

logger = logging.getLogger("learn_lms.screenshots")
settings = get_settings()


def get_screenshots_dir(course_id: str, lesson_id: str) -> Path:
    """Returns and creates the screenshot directory for a lesson."""
    dir_path = settings.DATA_DIR / "screenshots" / course_id / lesson_id
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def resolve_stream_url(video_url_or_id: str) -> Optional[str]:
    """Re-resolves a fresh direct stream URL using yt-dlp."""
    video_url = video_url_or_id
    if not video_url.startswith("http"):
        video_url = f"https://www.youtube.com/watch?v={video_url_or_id}"

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get("url")
    except Exception as e:
        logger.warning(f"Failed to resolve fresh stream URL for {video_url}: {e}")
        return None


def extract_frame_ffmpeg(
    stream_url: str,
    timestamp_sec: int,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg"
) -> bool:
    """Extracts a single 480p JPEG frame at timestamp_sec via ffmpeg."""
    cmd = [
        ffmpeg_bin,
        "-protocol_whitelist", "https,tls,tcp", "-ss", str(timestamp_sec),
        "-i", stream_url,
        "-frames:v", "1",
        "-vf", "scale=480:-1",
        "-q:v", "3",
        "-y",
        str(output_path),
    ]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=12,
            check=False
        )
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 500:
            return True
        logger.warning(f"ffmpeg frame extraction exited with code {res.returncode}")
        return False
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg frame extraction timed out at {timestamp_sec}s")
        return False
    except Exception as e:
        logger.warning(f"ffmpeg frame extraction failed: {e}")
        return False


def create_fallback_thumbnail(video_id: str, output_path: Path) -> bool:
    """Fetches high-quality YouTube thumbnail as a fallback keyframe."""
    import httpx
    thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(thumb_url)
            if resp.status_code == 200:
                output_path.write_bytes(resp.content)
                return True
    except Exception as e:
        logger.warning(f"Thumbnail fallback failed: {e}")
    return False


async def capture_lesson_keyframes(
    db_conn,
    course_id: str,
    lesson_id: str,
    video_id: str,
    start_sec: int,
    end_sec: int,
    timestamps: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Captures 3-5 opt-in keyframes for a lesson and stores metadata in SQLite."""
    screenshots_dir = get_screenshots_dir(course_id, lesson_id)

    # 1. Determine target timestamps
    if not timestamps:
        # Check if chunks exist to align with topic transitions
        cur = db_conn.cursor()
        cur.execute(
            "SELECT start_sec FROM chunks WHERE lesson_id = ? ORDER BY start_sec ASC LIMIT 4;",
            (lesson_id,)
        )
        chunk_starts = [row[0] for row in cur.fetchall()]
        if chunk_starts:
            timestamps = chunk_starts
        else:
            # Evenly space 3 keyframes
            duration = max(60, end_sec - start_sec)
            timestamps = [
                start_sec + int(duration * 0.15),
                start_sec + int(duration * 0.50),
                start_sec + int(duration * 0.85),
            ]

    # Find ffmpeg binary (.venv/bin/ffmpeg or system ffmpeg)
    venv_ffmpeg = settings.PROJECT_ROOT / ".venv" / "bin" / "ffmpeg"
    ffmpeg_bin = str(venv_ffmpeg) if venv_ffmpeg.exists() else "ffmpeg"

    # 2. Resolve fresh stream URL
    stream_url = resolve_stream_url(video_id)

    results: List[Dict[str, Any]] = []

    for ts in timestamps:
        file_name = f"kf_{ts}.jpg"
        file_path = screenshots_dir / file_name

        captured = False
        if stream_url:
            captured = extract_frame_ffmpeg(stream_url, ts, file_path, ffmpeg_bin=ffmpeg_bin)

        if not captured:
            # Fallback to thumbnail
            captured = create_fallback_thumbnail(video_id, file_path)

        if captured:
            # Relative web URL for serving
            relative_url = f"/api/screenshots/{course_id}/{lesson_id}/{file_name}"
            m, s = divmod(ts, 60)
            caption = f"Keyframe at {m:02d}:{s:02d}"

            # Persist in DB idempotently (prevent duplicate records for same timestamp)
            cur = db_conn.cursor()
            cur.execute(
                "SELECT id FROM screenshots WHERE lesson_id = ? AND timestamp_sec = ?;",
                (lesson_id, ts)
            )
            existing_shot = cur.fetchone()
            if existing_shot:
                shot_id = existing_shot[0]
                db_conn.execute(
                    """
                    UPDATE screenshots
                    SET file_path = ?, caption = ?
                    WHERE id = ?;
                    """,
                    (str(file_path), caption, shot_id)
                )
            else:
                shot_id = f"kf_{uuid.uuid4().hex[:10]}"
                db_conn.execute(
                    """
                    INSERT INTO screenshots (id, course_id, lesson_id, timestamp_sec, file_path, caption)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (shot_id, course_id, lesson_id, ts, str(file_path), caption)
                )
            results.append({
                "id": shot_id,
                "timestamp_sec": ts,
                "formatted_time": f"{m:02d}:{s:02d}",
                "url": relative_url,
                "caption": caption
            })

    db_conn.commit()
    logger.info(f"Captured {len(results)} keyframe screenshots for lesson {lesson_id}")
    return results


def get_lesson_screenshots(db_conn, lesson_id: str) -> List[Dict[str, Any]]:
    """Retrieves all captured screenshots for a lesson."""
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT id, course_id, timestamp_sec, file_path, caption 
        FROM screenshots 
        WHERE lesson_id = ? 
        ORDER BY timestamp_sec ASC;
        """,
        (lesson_id,)
    )
    rows = cur.fetchall()
    shots = []
    for r in rows:
        ts = r[2]
        m, s = divmod(ts, 60)
        file_name = Path(r[3]).name
        course_id = r[1]
        shots.append({
            "id": r[0],
            "timestamp_sec": ts,
            "formatted_time": f"{m:02d}:{s:02d}",
            "url": f"/api/screenshots/{course_id}/{lesson_id}/{file_name}",
            "caption": r[4] or f"Keyframe at {m:02d}:{s:02d}"
        })
    return shots
