"""Screenshots API Router."""

import logging
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import sqlite3

from backend.database import get_db
from backend.models.schemas import ScreenshotResponse
from backend.services.screenshots import capture_lesson_keyframes, get_lesson_screenshots, get_screenshots_dir
from backend.config import get_settings

logger = logging.getLogger("learn_lms.api.screenshots")
router = APIRouter(tags=["screenshots"])
settings = get_settings()


@router.post("/api/lessons/{lesson_id}/screenshots", response_model=List[ScreenshotResponse])
async def capture_screenshots(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Captures opt-in keyframe screenshots for a lesson."""
    cur = db.cursor()
    cur.execute(
        """
        SELECT l.id, l.course_id, l.video_id, l.start_sec, l.end_sec, s.url
        FROM lessons l
        LEFT JOIN sources s ON l.source_id = s.id
        WHERE l.id = ?;
        """,
        (lesson_id,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[1]
    video_id = row[2] or ""
    start_sec = row[3]
    end_sec = row[4]
    video_url = row[5] or video_id

    target_video = video_id if video_id else video_url

    results = await capture_lesson_keyframes(
        db,
        course_id=course_id,
        lesson_id=lesson_id,
        video_id=target_video,
        start_sec=start_sec,
        end_sec=end_sec
    )
    return results


@router.get("/api/lessons/{lesson_id}/screenshots", response_model=List[ScreenshotResponse])
def list_screenshots(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Lists existing keyframe screenshots for a lesson."""
    return get_lesson_screenshots(db, lesson_id)


@router.get("/api/screenshots/{course_id}/{lesson_id}/{filename}")
def serve_screenshot(
    course_id: str,
    lesson_id: str,
    filename: str
):
    """Serves a stored screenshot image."""
    dir_path = get_screenshots_dir(course_id, lesson_id)
    file_path = dir_path / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot image not found")

    return FileResponse(path=file_path, media_type="image/jpeg")
