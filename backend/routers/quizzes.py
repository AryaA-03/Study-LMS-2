"""Quizzes and Diagnostic Tests router."""

import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.models.schemas import (
    QuizGenerateRequest,
    QuizResponse,
    QuizQuestion,
    QuizSubmitRequest,
    QuizSubmitResponse,
)
from backend.services.quiz_engine import create_and_store_quiz, grade_and_apply_mastery
from backend.routers.schedule import trigger_course_reflow

logger = logging.getLogger("learn_lms.quizzes_router")
router = APIRouter(prefix="/api/courses/{course_id}/quizzes", tags=["quizzes"])


@router.post("/generate", response_model=QuizResponse)
def generate_quiz(
    course_id: str,
    req: QuizGenerateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        quiz_data = create_and_store_quiz(
            conn=db,
            course_id=course_id,
            quiz_type=req.quiz_type,
            lesson_id=req.lesson_id,
            question_count=req.question_count,
            custom_title=req.title,
        )
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")

    return quiz_data


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz(
    course_id: str,
    quiz_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    cur = db.execute("SELECT * FROM quizzes WHERE id = ? AND course_id = ?;", (quiz_id, course_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = json.loads(row["questions_json"])
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "lesson_id": row["lesson_id"],
        "quiz_type": row["quiz_type"],
        "title": row["title"],
        "questions": questions,
        "score": row["score"],
        "passed": bool(row["passed"]),
        "time_taken_seconds": row["time_taken_seconds"] if "time_taken_seconds" in row.keys() else None,
        "created_at": row["created_at"],
    }


@router.post("/{quiz_id}/submit", response_model=QuizSubmitResponse)
def submit_quiz(
    course_id: str,
    quiz_id: str,
    req: QuizSubmitRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        result = grade_and_apply_mastery(
            conn=db,
            quiz_id=quiz_id,
            user_answers=req.answers,
            short_answers=req.short_answers,
            time_taken_seconds=req.time_taken_seconds,
        )

        schedule_updated = False
        diff_summary = None

        # Feature 2: Automated Replanning on Quiz Drops ("Plan updated — Undo" banner)
        # If any lesson was tested out (score >= 80% or diagnostic) OR score dropped < 60% (needs review)
        if result.get("tested_out_lessons") or result.get("mastery_status") == "needs_review":
            try:
                from backend.routers.schedule import replan_course_schedule
                from backend.models.schemas import ReplanRequest
                replan_res = replan_course_schedule(
                    course_id=course_id,
                    req=ReplanRequest(mode="normal"),
                    db=db,
                )
                schedule_updated = True
                diff_summary = replan_res.diff.model_dump()
                logger.info(f"[Mastery Reflow] Auto-replanned schedule with snapshot for course {course_id}.")
            except Exception as e:
                logger.warning(f"Failed to auto-replan schedule after quiz trigger: {e}")
                # Fallback to direct reflow if replan fails
                if result.get("tested_out_lessons"):
                    trigger_course_reflow(course_id, db)

        result["schedule_updated"] = schedule_updated
        result["diff_summary"] = diff_summary

        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Quiz submission failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to grade quiz: {str(e)}")


@router.get("", response_model=List[QuizResponse])
def list_quizzes(
    course_id: str,
    quiz_type: Optional[str] = None,
    lesson_id: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
):
    query = "SELECT * FROM quizzes WHERE course_id = ?"
    params: List[Any] = [course_id]
    if quiz_type:
        query += " AND quiz_type = ?"
        params.append(quiz_type)
    if lesson_id:
        query += " AND lesson_id = ?"
        params.append(lesson_id)
    query += " ORDER BY created_at DESC LIMIT 50;"

    rows = db.execute(query, params).fetchall()
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "course_id": r["course_id"],
            "lesson_id": r["lesson_id"],
            "quiz_type": r["quiz_type"],
            "title": r["title"],
            "questions": json.loads(r["questions_json"]),
            "score": r["score"],
            "passed": bool(r["passed"]),
            "time_taken_seconds": r["time_taken_seconds"] if "time_taken_seconds" in r.keys() else None,
            "created_at": r["created_at"],
        })
    return results
