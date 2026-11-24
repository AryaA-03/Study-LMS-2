"""Screenshots API Router."""

import logging
import mimetypes
from pathlib import Path
from typing import List, Dict, Any
from backend.deps import get_current_user, require_course_owner, require_lesson_owner
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import sqlite3

from backend.database import get_db
from backend.models.schemas import ScreenshotResponse
from backend.services.screenshots import capture_lesson_keyframes, get_lesson_screenshots, get_screenshots_dir
from backend.config import get_settings

logger = logging.getLogger("learn_lms.api.screenshots")
router = APIRouter(tags=["screenshots"], dependencies=[Depends(get_current_user)])
settings = get_settings()


@router.post("/api/lessons/{lesson_id}/screenshots", response_model=List[ScreenshotResponse], dependencies=[Depends(require_lesson_owner)])
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
    start_sec = int(row[3] or 0)
    end_sec = int(row[4] or 0)
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


@router.get("/api/lessons/{lesson_id}/screenshots", response_model=List[ScreenshotResponse], dependencies=[Depends(require_lesson_owner)])
def list_screenshots(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Lists existing keyframe screenshots for a lesson."""
    return get_lesson_screenshots(db, lesson_id)


@router.get("/api/screenshots/{course_id}/{lesson_id}/{filename}", dependencies=[Depends(require_course_owner)])
def serve_screenshot(
    course_id: str,
    lesson_id: str,
    filename: str
):
    """Serves a stored screenshot image with strict path containment."""
    import re
    from backend.config import DATA_DIR

    safe_id = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    safe_file = re.compile(r"^[a-zA-Z0-9._-]{1,128}\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
    if not (safe_id.match(course_id) and safe_id.match(lesson_id) and safe_file.match(filename)):
        raise HTTPException(status_code=400, detail="Invalid screenshot identifier")

    base_dir = (DATA_DIR / "screenshots").resolve()
    file_path = (base_dir / course_id / lesson_id / filename).resolve()
    if not file_path.is_relative_to(base_dir):
        raise HTTPException(status_code=403, detail="Forbidden path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot image not found")

    mime, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(path=file_path, media_type=mime or "image/jpeg")
