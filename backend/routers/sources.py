"""Multi-Source Management API Router (PDF & Web Ingestion)."""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import sqlite3

from backend.database import get_db
from backend.models.schemas import SourceResponse, WebSourceImportRequest
from backend.services.pdf_ingest import ingest_pdf_source
from backend.services.web_ingest import ingest_web_page

logger = logging.getLogger("learn_lms.api.sources")
router = APIRouter(prefix="/api/courses", tags=["sources"])


@router.get("/{course_id}/sources", response_model=List[SourceResponse])
def list_course_sources(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db)
):
    """Lists all approved and candidate sources for a course."""
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, course_id, source_type, title, url, external_id, metadata_json, is_approved, created_at, chunk_count
        FROM sources
        WHERE course_id = ?
        ORDER BY created_at ASC;
        """,
        (course_id,)
    )
    rows = cur.fetchall()
    sources = []
    for r in rows:
        import json
        meta = {}
        try:
            meta = json.loads(r[6]) if r[6] else {}
        except Exception:
            pass
        meta["chunk_count"] = r[9]
        sources.append({
            "id": r[0],
            "course_id": r[1],
            "source_type": r[2],
            "title": r[3],
            "url": r[4],
            "external_id": r[5],
            "metadata": meta,
            "is_approved": bool(r[7]),
            "created_at": r[8] or ""
        })
    return sources


@router.post("/{course_id}/sources/pdf")
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

    pdf_bytes = await file.read()
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


@router.post("/{course_id}/sources/web")
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
