"""PYQ (Previous Year Question Paper) Weightage & Auto-Tagging Router."""

import asyncio
import sqlite3
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body

from backend.database import get_db
from backend.deps import get_current_user, require_course_owner
from backend.models.schemas import PYQUploadResponse
from backend.services.pyq_engine import (
    extract_text_from_pdf,
    ingest_pyq_source,
    get_course_pyq_summary,
    get_lesson_pyq_questions,
    update_course_pyq_aggregates,
    rematch_course_pyqs,
)

logger = logging.getLogger("learn_lms.pyq_router")
router = APIRouter(prefix="/api/courses", tags=["pyq"], dependencies=[Depends(get_current_user)])

MAX_PYQ_BYTES = 25 * 1024 * 1024  # 25 MB upload cap


@router.post("/{course_id}/pyq/upload-file", response_model=PYQUploadResponse, dependencies=[Depends(require_course_owner)])
async def upload_pyq_file(
    course_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: sqlite3.Connection = Depends(get_db),
):
    """Uploads and ingests a past exam paper (PDF or text file), matching against course lessons."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    # Streaming read capped at 25 MB to prevent memory DoS
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_PYQ_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded paper exceeds the 25 MB limit.")
        chunks.append(chunk)
    content_bytes = b"".join(chunks)
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "paper.pdf"
    doc_title = title or filename.rsplit(".", 1)[0]

    # Validate magic bytes for PDFs and extract off the event loop
    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_magic = content_bytes[:5] == b"%PDF-"
    if is_pdf_name and not is_pdf_magic:
        raise HTTPException(status_code=400, detail="Invalid PDF file (missing %PDF- header).")

    if is_pdf_name or is_pdf_magic:
        try:
            raw_text = await asyncio.to_thread(extract_text_from_pdf, content_bytes)
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

    result = await asyncio.to_thread(
        ingest_pyq_source,
        db,
        course_id=course_id,
        title=doc_title,
        raw_text=raw_text,
        filename=filename,
    )
    return PYQUploadResponse(**result)


@router.post("/{course_id}/pyq/upload-text", response_model=PYQUploadResponse, dependencies=[Depends(require_course_owner)])
async def upload_pyq_text(
    course_id: str,
    title: str = Body(..., embed=True),
    raw_text: str = Body(..., embed=True),
    db: sqlite3.Connection = Depends(get_db),
):
    """Ingests pasted past exam paper questions and matches them against course lessons."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Text content cannot be empty")

    result = await asyncio.to_thread(
        ingest_pyq_source,
        db,
        course_id=course_id,
        title=title.strip() or "Pasted Exam Paper",
        raw_text=raw_text,
    )
    return PYQUploadResponse(**result)


@router.get("/{course_id}/pyq", dependencies=[Depends(require_course_owner)])
def list_course_pyq(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Returns summary of uploaded past papers, questions, and per-lesson PYQ weightage."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    return get_course_pyq_summary(db, course_id)


@router.get("/{course_id}/lessons/{lesson_id}/pyq", dependencies=[Depends(require_course_owner)])
def list_lesson_pyq(
    course_id: str,
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Retrieves all past paper questions matched to a specific lesson."""
    return get_lesson_pyq_questions(db, course_id, lesson_id)


@router.post("/{course_id}/pyq/rematch", dependencies=[Depends(require_course_owner)])
def rematch_course_pyq_weights(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Re-matches all uploaded past paper questions against current course lessons (useful after repartitioning)."""
    res = rematch_course_pyqs(db, course_id)
    return {"success": True, **res}


@router.delete("/{course_id}/pyq/papers/{paper_id}", dependencies=[Depends(require_course_owner)])
def delete_pyq_paper(
    course_id: str,
    paper_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Deletes a past paper and its questions, recalculating lesson hit counts."""
    cur = db.execute("DELETE FROM pyq_papers WHERE id = ? AND course_id = ?;", (paper_id, course_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Past paper not found")
    db.execute("DELETE FROM pyq_questions WHERE paper_id = ? AND course_id = ?;", (paper_id, course_id))
    update_course_pyq_aggregates(db, course_id)
    db.commit()
    return {"success": True, "message": "Past paper deleted and lesson weights updated"}
