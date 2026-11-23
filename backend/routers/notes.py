"""Notes API Router."""

import logging
from typing import Dict, Any
from backend.deps import get_current_user
from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.database import get_db
from backend.models.schemas import PersonalNotesUpdate, NoteResponse
from backend.services.notes import get_or_generate_lesson_notes, save_personal_notes

logger = logging.getLogger("learn_lms.api.notes")
router = APIRouter(prefix="/api/lessons", tags=["notes"], dependencies=[Depends(get_current_user)])


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


@router.put("/{lesson_id}/notes", response_model=NoteResponse)
def update_full_notes(
    lesson_id: str,
    payload: Dict[str, Any],
    db: sqlite3.Connection = Depends(get_db)
):
    cur = db.cursor()
    cur.execute("SELECT course_id FROM lessons WHERE id = ?;", (lesson_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[0]
    content_md = payload.get("content_markdown")
    personal_md = payload.get("personal_notes")

    cur.execute("SELECT id FROM notes WHERE lesson_id = ? ORDER BY updated_at DESC LIMIT 1;", (lesson_id,))
    existing = cur.fetchone()

    if existing:
        updates = []
        params = []
        if content_md is not None:
            updates.append("content_markdown = ?")
            params.append(content_md)
        if personal_md is not None:
            updates.append("personal_notes = ?")
            params.append(personal_md)
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(existing[0])
            cur.execute(f"UPDATE notes SET {', '.join(updates)} WHERE id = ?;", params)
            db.commit()
    else:
        import uuid
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated) VALUES (?, ?, ?, ?, ?, 0);",
            (note_id, course_id, lesson_id, content_md or "", personal_md or "")
        )
        db.commit()

    cur.execute("SELECT id, content_markdown, personal_notes, is_generated, updated_at FROM notes WHERE lesson_id = ? ORDER BY updated_at DESC LIMIT 1;", (lesson_id,))
    saved_note = cur.fetchone()
    return {
        "id": saved_note[0],
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_markdown": saved_note[1] or "",
        "personal_notes": saved_note[2] or "",
        "is_generated": saved_note[3],
        "updated_at": saved_note[4],
    }
