"""Notes API Router."""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.database import get_db
from backend.models.schemas import PersonalNotesUpdate, NoteResponse
from backend.services.notes import get_or_generate_lesson_notes, save_personal_notes

logger = logging.getLogger("learn_lms.api.notes")
router = APIRouter(prefix="/api/lessons", tags=["notes"])


@router.get("/{lesson_id}/notes", response_model=NoteResponse)
async def get_lesson_notes(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Retrieves or automatically synthesizes structured notes for a lesson."""
    cur = db.cursor()
    cur.execute("SELECT course_id FROM lessons WHERE id = ?;", (lesson_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[0]
    result = await get_or_generate_lesson_notes(db, course_id, lesson_id, force_regenerate=False)
    return {
        "id": result.get("id", ""),
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_markdown": result.get("content_markdown", ""),
        "personal_notes": result.get("personal_notes", ""),
        "is_generated": result.get("is_generated", 1),
        "updated_at": result.get("updated_at")
    }


@router.post("/{lesson_id}/notes/regenerate", response_model=NoteResponse)
async def regenerate_lesson_notes(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Forces re-synthesis of structured notes for a lesson from its chunks."""
    cur = db.cursor()
    cur.execute("SELECT course_id FROM lessons WHERE id = ?;", (lesson_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[0]
    result = await get_or_generate_lesson_notes(db, course_id, lesson_id, force_regenerate=True)
    return {
        "id": result.get("id", ""),
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_markdown": result.get("content_markdown", ""),
        "personal_notes": result.get("personal_notes", ""),
        "is_generated": result.get("is_generated", 1),
        "updated_at": result.get("updated_at")
    }


@router.put("/{lesson_id}/notes/personal")
def update_personal_notes(
    lesson_id: str,
    payload: PersonalNotesUpdate,
    db: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Saves user personal editable notes for a lesson."""
    cur = db.cursor()
    cur.execute("SELECT course_id FROM lessons WHERE id = ?;", (lesson_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[0]
    saved = save_personal_notes(db, course_id, lesson_id, payload.personal_notes)
    return {"success": saved, "lesson_id": lesson_id}
