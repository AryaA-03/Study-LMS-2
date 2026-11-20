"""FSRS Spaced Repetition Flashcards router."""

import sqlite3
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.models.schemas import (
    FlashcardCreateRequest,
    FlashcardResponse,
    FlashcardReviewRequest,
    FlashcardReviewResponse,
    FlashcardCountsResponse,
)
from backend.services.fsrs_engine import (
    create_flashcard,
    review_flashcard,
    get_due_flashcards,
    get_flashcard_counts,
)

logger = logging.getLogger("learn_lms.flashcards_router")
router = APIRouter(prefix="/api/courses/{course_id}/flashcards", tags=["flashcards"])


@router.get("/due", response_model=List[FlashcardResponse])
def list_due_flashcards(
    course_id: str,
    lesson_id: Optional[str] = None,
    limit: int = 50,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    return get_due_flashcards(conn=db, course_id=course_id, lesson_id=lesson_id, limit=limit)


@router.get("/counts", response_model=FlashcardCountsResponse)
def get_counts(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    return get_flashcard_counts(conn=db, course_id=course_id)


@router.get("", response_model=List[FlashcardResponse])
def list_all_flashcards(
    course_id: str,
    lesson_id: Optional[str] = None,
    limit: int = 100,
    db: sqlite3.Connection = Depends(get_db),
):
    # Retrieve all flashcards (not just due)
    return get_due_flashcards(conn=db, course_id=course_id, lesson_id=lesson_id, as_of=None, limit=limit)


@router.post("", response_model=FlashcardResponse)
def add_flashcard(
    course_id: str,
    req: FlashcardCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        card = create_flashcard(
            conn=db,
            course_id=course_id,
            front=req.front,
            back=req.back,
            lesson_id=req.lesson_id,
            chunk_id=req.chunk_id,
            source_quote=req.source_quote,
        )
        return card
    except Exception as e:
        logger.error(f"Failed to create flashcard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create flashcard: {str(e)}")


@router.post("/{card_id}/review", response_model=FlashcardReviewResponse)
def review_card(
    course_id: str,
    card_id: str,
    req: FlashcardReviewRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        card_data, interval_str = review_flashcard(
            conn=db,
            card_id=card_id,
            rating=req.rating,
            exam_date=course["target_date"],
        )
        return {
            "card": card_data,
            "next_interval_str": interval_str,
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Flashcard review failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")


@router.delete("/{card_id}")
def delete_card(
    course_id: str,
    card_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute("DELETE FROM flashcards WHERE id = ? AND course_id = ?;", (card_id, course_id))
    db.commit()
    return {"success": True, "deleted_id": card_id}
