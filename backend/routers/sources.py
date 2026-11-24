"""Multi-Source Management API Router (PDF & Web Ingestion)."""

import logging
from typing import Dict, Any, Optional
from backend.deps import get_current_user, require_course_owner
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import sqlite3

from backend.database import get_db
from backend.models.schemas import WebSourceImportRequest
from backend.services.pdf_ingest import ingest_pdf_source
from backend.services.web_ingest import ingest_web_page

logger = logging.getLogger("learn_lms.api.sources")
router = APIRouter(prefix="/api/courses", tags=["sources"], dependencies=[Depends(get_current_user)])


@router.post("/{course_id}/sources/pdf", dependencies=[Depends(require_course_owner)])
async def upload_pdf_source(
    course_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: sqlite3.Connection = Depends(get_db)
):
    """Uploads and ingests a local PDF document into course chunks & FTS5."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    pdf_bytes = await file.read(25 * 1024 * 1024 + 1)
    if len(pdf_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded PDF exceeds 25 MB limit.")
    if pdf_bytes and not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF document.")
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded PDF file is empty")

    doc_title = title or file.filename or "Uploaded PDF Document"
    source_id, chunk_count = await ingest_pdf_source(
        db,
        course_id=course_id,
        title=doc_title,
        pdf_bytes=pdf_bytes,
        original_filename=file.filename or "document.pdf"
    )

    return {
        "success": True,
        "source_id": source_id,
        "title": doc_title,
        "source_type": "pdf",
        "chunk_count": chunk_count
    }


@router.post("/{course_id}/sources/web", dependencies=[Depends(require_course_owner)])
async def import_web_source(
    course_id: str,
    payload: WebSourceImportRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """Politely imports a single web article URL into course chunks & FTS5."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    success, source_id, title, chunk_count = await ingest_web_page(
        db,
        course_id=course_id,
        url=payload.url,
        custom_title=payload.title
    )

    if not success:
        raise HTTPException(status_code=400, detail=title)

    return {
        "success": True,
        "source_id": source_id,
        "title": title,
        "source_type": "web_page",
        "chunk_count": chunk_count
    }
