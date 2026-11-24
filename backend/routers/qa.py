"""Strict Citation-Grounded Q&A Router."""

import logging
from typing import List, Dict, Any
from backend.deps import get_current_user, require_course_owner
from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.database import get_db
from backend.models.schemas import QARequest, QAResponse
from backend.services.qa_engine import answer_course_question, get_course_qa_history

logger = logging.getLogger("learn_lms.api.qa")
router = APIRouter(prefix="/api/courses", tags=["qa"], dependencies=[Depends(get_current_user)])


@router.post("/{course_id}/qa", response_model=QAResponse, dependencies=[Depends(require_course_owner)])
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


@router.get("/{course_id}/qa", dependencies=[Depends(require_course_owner)])
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

@router.delete("/{course_id}/qa/{thread_id}", dependencies=[Depends(require_course_owner)])
def delete_qa_thread(
    course_id: str,
    thread_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Delete a single Q&A history thread for this course."""
    cur = db.execute(
        "DELETE FROM qa_threads WHERE id = ? AND course_id = ?;",
        (thread_id, course_id),
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Q&A thread not found")
    return {"success": True, "deleted_thread_id": thread_id}
