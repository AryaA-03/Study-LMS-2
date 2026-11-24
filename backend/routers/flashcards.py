"""FSRS Spaced Repetition Flashcards router."""

import sqlite3
import logging
from typing import List, Dict, Any, Optional
from backend.deps import get_current_user, require_course_owner
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.models.schemas import (
    FlashcardCreateRequest,
    FlashcardUpdateRequest,
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
router = APIRouter(prefix="/api/courses/{course_id}/flashcards", tags=["flashcards"], dependencies=[Depends(get_current_user), Depends(require_course_owner)])


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
    due_only: bool = False,
    limit: int = 100,
    db: sqlite3.Connection = Depends(get_db),
):
    """Retrieve all flashcards in a course (or only due cards when due_only=true)."""
    if due_only:
        return get_due_flashcards(conn=db, course_id=course_id, lesson_id=lesson_id, as_of=None, limit=limit)
    if lesson_id:
        rows = db.execute(
            "SELECT * FROM flashcards WHERE course_id = ? AND lesson_id = ? ORDER BY due_date ASC LIMIT ?;",
            (course_id, lesson_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM flashcards WHERE course_id = ? ORDER BY due_date ASC LIMIT ?;",
            (course_id, limit),
        ).fetchall()
    state_map = {0: "New", 1: "Learning", 2: "Review", 3: "Relearning"}
    result = []
    for r in rows:
        d = dict(r)
        d.setdefault("state_name", state_map.get(int(d.get("state") or 0), "New"))
        d.setdefault("interval_previews", {})
        result.append(d)
    return result


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


@router.put("/{card_id}", response_model=FlashcardResponse)
def update_flashcard(
    course_id: str,
    card_id: str,
    req: FlashcardUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    cur = db.cursor()
    cur.execute("SELECT * FROM flashcards WHERE id = ? AND course_id = ?;", (card_id, course_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Flashcard not found")

    col_names = [d[0] for d in cur.description]
    row_dict = dict(zip(col_names, row))

    updates = []
    params = []
    if req.front is not None:
        updates.append("front = ?")
        params.append(req.front)
        row_dict["front"] = req.front
    if req.back is not None:
        updates.append("back = ?")
        params.append(req.back)
        row_dict["back"] = req.back

    if updates:
        params.extend([card_id, course_id])
        cur.execute(f"UPDATE flashcards SET {', '.join(updates)} WHERE id = ? AND course_id = ?;", params)
        db.commit()

    import fsrs
    import datetime
    from datetime import timezone
    from backend.services.fsrs_engine import get_fsrs_scheduler, card_to_fsrs, preview_intervals
    scheduler = get_fsrs_scheduler()
    as_of = datetime.datetime.now(timezone.utc)
    fsrs_card = card_to_fsrs(row_dict)
    intervals = preview_intervals(fsrs_card, scheduler, as_of)
    _raw_state = int(row_dict.get("state") or 0)
    state_enum = fsrs.State(_raw_state) if _raw_state in (1, 2, 3) else fsrs.State.Learning

    return {
        "id": row_dict["id"],
        "course_id": row_dict["course_id"],
        "lesson_id": row_dict.get("lesson_id"),
        "chunk_id": row_dict.get("chunk_id"),
        "front": row_dict["front"],
        "back": row_dict["back"],
        "state": state_enum.value,
        "state_name": state_enum.name,
        "due_date": row_dict["due_date"],
        "stability": row_dict.get("stability", 0.0),
        "difficulty": row_dict.get("difficulty", 0.0),
        "reps": row_dict.get("reps", 0),
        "source_quote": row_dict.get("source_quote"),
        "intervals": intervals,
    }


@router.delete("/{card_id}")
def delete_card(
    course_id: str,
    card_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    cur = db.execute("DELETE FROM flashcards WHERE id = ? AND course_id = ?;", (card_id, course_id))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    return {"success": True, "deleted_id": card_id}


@router.post("/lessons/{lesson_id}/generate", response_model=List[FlashcardResponse])
def generate_lesson_flashcards_endpoint(
    course_id: str,
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Auto-generate concept flashcards for a specific lesson from its notes/chunks."""
    from backend.services.fsrs_engine import generate_concept_flashcards

    lesson = db.execute(
        "SELECT id, title FROM lessons WHERE id = ? AND course_id = ?;",
        (lesson_id, course_id),
    ).fetchone()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found in this course")
    cards = generate_concept_flashcards(db, course_id=course_id, lesson_id=lesson_id)
    state_map = {0: "New", 1: "Learning", 2: "Review", 3: "Relearning"}
    out = []
    for c in cards or []:
        d = dict(c)
        d.setdefault("state_name", state_map.get(int(d.get("state") or 0), "New"))
        d.setdefault("interval_previews", {})
        out.append(d)
    return out
