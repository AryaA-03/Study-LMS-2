"""Strict Citation-Grounded Q&A Router."""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.database import get_db
from backend.models.schemas import QARequest, QAResponse
from backend.services.qa_engine import answer_course_question, get_course_qa_history

logger = logging.getLogger("learn_lms.api.qa")
router = APIRouter(prefix="/api/courses", tags=["qa"])


@router.post("/{course_id}/qa", response_model=QAResponse)
async def ask_question(
    course_id: str,
    req: QARequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """Answers a question strictly grounded in course evidence chunks."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    result = await answer_course_question(db, course_id, req.query, lesson_id=req.lesson_id)
    return result


@router.get("/{course_id}/qa")
def get_qa_history(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Retrieves previous grounded Q&A threads for this course."""
    cur = db.cursor()
    cur.execute("SELECT id FROM courses WHERE id = ?;", (course_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Course not found")

    return get_course_qa_history(db, course_id)
