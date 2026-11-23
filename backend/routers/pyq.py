"""University PYQ (Previous Year Questions) Management API Router."""

import logging
from typing import Dict, Any, Optional, List
from backend.deps import get_current_user
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
import sqlite3

from backend.database import get_db
from backend.models.schemas import PYQUploadResponse, PYQUploadTextRequest
from backend.services.pyq_engine import (
    extract_text_from_pdf,
    ingest_pyq_source,
    get_course_pyq_summary,
    get_lesson_pyq_questions,
    update_course_pyq_aggregates,
)

logger = logging.getLogger("learn_lms.api.pyq")
router = APIRouter(prefix="/api/courses", tags=["pyq"], dependencies=[Depends(get_current_user)])


@router.post("/{course_id}/pyq/upload-file", response_model=PYQUploadResponse)
async def upload_pyq_file(
    course_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """Uploads and ingests a past exam paper (PDF or text file), matching against course lessons."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    content_bytes = await file.read()
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "paper.pdf"
    doc_title = title or filename.rsplit(".", 1)[0]

    # Extract text based on file extension / content
    if filename.lower().endswith(".pdf") or content_bytes[:4] == b"%PDF":
        try:
            raw_text = extract_text_from_pdf(content_bytes)
        except Exception as e:
            logger.error(f"Failed to parse PYQ PDF: {e}")
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {str(e)}")
    else:
        try:
            raw_text = content_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not decode text file: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in uploaded paper")

    result = ingest_pyq_source(
        db,
        course_id=course_id,
        title=doc_title,
        raw_text=raw_text,
        filename=filename
    )
    return result


@router.post("/{course_id}/pyq/upload-text", response_model=PYQUploadResponse)
def upload_pyq_text(
    course_id: str,
    payload: PYQUploadTextRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """Ingests pasted past exam questions text, splitting and matching against course lessons."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    result = ingest_pyq_source(
        db,
        course_id=course_id,
        title=payload.title,
        raw_text=payload.raw_text,
        filename="pasted_text"
    )
    return result


@router.get("/{course_id}/pyq")
def get_pyq_summary(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Retrieves all past papers and high-yield topic stats for a course."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    return get_course_pyq_summary(db, course_id)


@router.get("/{course_id}/lessons/{lesson_id}/pyq")
def get_lesson_pyqs(
    course_id: str,
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Retrieves all past paper questions matched to a specific lesson."""
    return get_lesson_pyq_questions(db, course_id, lesson_id)


@router.delete("/{course_id}/pyq/papers/{paper_id}")
def delete_pyq_paper(
    course_id: str,
    paper_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Deletes a past paper and its questions, recalculating lesson hit counts."""
    db.execute("DELETE FROM pyq_papers WHERE id = ? AND course_id = ?;", (paper_id, course_id))
    db.execute("DELETE FROM pyq_questions WHERE paper_id = ? AND course_id = ?;", (paper_id, course_id))
    update_course_pyq_aggregates(db, course_id)
    return {"success": True, "message": "Past paper deleted and lesson weights updated"}
