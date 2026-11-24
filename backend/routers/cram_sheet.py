from pathlib import Path
"""Last-Night Cram Sheet API Router."""

import logging
from typing import Dict, Any, Optional
from backend.deps import CurrentUser, get_current_user, require_course_owner
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
import sqlite3

from backend.database import get_db
from backend.models.schemas import CramSheetGenerateRequest, CramSheetResponse
from backend.services.cram_sheet_engine import get_or_create_cram_sheet

logger = logging.getLogger("learn_lms.api.cram_sheet")
router = APIRouter(prefix="/api/courses", tags=["cram_sheet"], dependencies=[Depends(get_current_user)])


@router.post("/{course_id}/cram-sheet/generate", response_model=CramSheetResponse, dependencies=[Depends(require_course_owner)])
async def generate_cram_sheet(
    course_id: str,
    payload: CramSheetGenerateRequest = CramSheetGenerateRequest(),
    db: sqlite3.Connection = Depends(get_db)
):
    """Synthesizes or retrieves cached 1-2 page Last-Night Exam Cram Sheet."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    sheet = await get_or_create_cram_sheet(
        db,
        course_id=course_id,
        force_refresh=payload.force_refresh,
        full_syllabus=payload.full_syllabus,
        source_id=payload.source_id,
        chapter_title=payload.chapter_title,
    )
    return sheet


@router.post("/{course_id}/cram-sheet/generate-full", response_model=CramSheetResponse, dependencies=[Depends(require_course_owner)])
async def generate_full_cram_sheet(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Sequentially processes and synthesizes notes across all playlist/syllabus videos in batches."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    sheet = await get_or_create_cram_sheet(
        db,
        course_id=course_id,
        force_refresh=True,
        full_syllabus=True
    )
    return sheet


@router.get("/{course_id}/cram-sheet", response_model=CramSheetResponse, dependencies=[Depends(require_course_owner)])
async def get_cram_sheet(
    course_id: str,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """Retrieves the current course Cram Sheet, generating one if not yet present."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    sheet = await get_or_create_cram_sheet(
        db, course_id=course_id, force_refresh=False, source_id=source_id, chapter_title=chapter_title
    )
    return sheet


@router.get("/{course_id}/cram-sheet/download", dependencies=[Depends(require_course_owner)])
def download_cram_sheet_markdown(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Downloads the cram sheet as a standalone Markdown document."""
    cur = db.cursor()
    cur.execute("SELECT title FROM courses WHERE id = ?;", (course_id,))
    c_row = cur.fetchone()
    if not c_row:
        raise HTTPException(status_code=404, detail="Course not found")

    title = c_row[0] or "Course"
    safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in title)

    cur.execute("SELECT content_markdown FROM cram_sheets WHERE course_id = ?;", (course_id,))
    sheet_row = cur.fetchone()
    if not sheet_row or not sheet_row[0]:
        raise HTTPException(status_code=404, detail="Cram sheet has not been generated yet")

    markdown_content = sheet_row[0]
    filename = f"{safe_title}_Last_Night_Cram_Sheet.md"

    return Response(
        content=markdown_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/{course_id}/cram-sheet/generate-full-async", status_code=202, dependencies=[Depends(require_course_owner)])
async def trigger_full_syllabus_cram_sheet_async(
    course_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Non-blocking background job version of full-syllabus cram sheet synthesis (returns 202 + job_id)."""
    from backend.infra.job_queue import enqueue_job

    row = db.execute("SELECT id FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")

    job_id = enqueue_job(
        db,
        "cram_sheet_full",
        course_id=course_id,
        payload={"full_syllabus": True},
        owner_id=user.id,
    )
    return {"job_id": job_id, "status": "queued", "course_id": course_id}
