"""FSRS Spaced Repetition Engine.

Wraps the official 'fsrs' library (FSRS v5 algorithm) to manage spaced repetition
flashcards for courses and lessons. Supports dynamic target retention scaling
based on proximity to exam date, due-card retrieval, and interval previews.
"""

import json
import uuid
import re
import datetime
from datetime import timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

import fsrs
from backend.config import LOCAL_TZ
from backend.scheduler.engine import default_clock


def calculate_target_retention(exam_date_str: Optional[str], today: Optional[datetime.date] = None) -> float:
    """Calculates adaptive desired retention scaling higher as the exam nears."""
    if not exam_date_str:
        return 0.90
    try:
        exam_d = datetime.date.fromisoformat(exam_date_str)
        if today is None:
            today = default_clock()
        days_left = (exam_d - today).days
        if days_left <= 3:
            return 0.96
        elif days_left <= 7:
            return 0.94
        elif days_left <= 14:
            return 0.92
        else:
            return 0.90
    except Exception:
        return 0.90


def get_fsrs_scheduler(desired_retention: float = 0.90) -> fsrs.Scheduler:
    """Returns an FSRS Scheduler configured with the desired retention."""
    return fsrs.Scheduler(desired_retention=desired_retention)


def format_interval(delta: timedelta) -> str:
    """Formats a timedelta into compact human-readable interval (e.g. '1m', '10m', '1d', '24d')."""
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{int(total_seconds / 60)}m"
    elif total_seconds < 86400:
        return f"{int(total_seconds / 3600)}h"
    else:
        days = round(total_seconds / 86400.0)
        return f"{max(1, int(days))}d"


def preview_intervals(
    card: fsrs.Card,
    scheduler: fsrs.Scheduler,
    now: Optional[datetime.datetime] = None
) -> Dict[int, str]:
    """Generates preview intervals for each rating button (1=Again, 2=Hard, 3=Good, 4=Easy)."""
    if now is None:
        now = datetime.datetime.now(timezone.utc)
    res = {}
    for r in [fsrs.Rating.Again, fsrs.Rating.Hard, fsrs.Rating.Good, fsrs.Rating.Easy]:
        c_res, _ = scheduler.review_card(card, r, now)
        delta = c_res.due - now
        res[r.value] = format_interval(delta)
    return res


def card_to_fsrs(card_row: Dict[str, Any]) -> fsrs.Card:
    """Reconstructs an fsrs.Card from SQLite row data or its fsrs_data_json."""
    if card_row.get("fsrs_data_json"):
        try:
            data = json.loads(card_row["fsrs_data_json"])
            return fsrs.Card.from_dict(data)
        except Exception:
            pass

    # Fallback reconstruction
    card = fsrs.Card()
    state_val = card_row.get("state", 1)
    if state_val in (1, 2, 3):
        card.state = fsrs.State(state_val)
    card.stability = card_row.get("stability")
    card.difficulty = card_row.get("difficulty")
    if card_row.get("due_date"):
        try:
            due_dt = datetime.datetime.fromisoformat(card_row["due_date"])
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            card.due = due_dt
        except Exception:
            pass
    return card


def create_flashcard(
    conn,
    course_id: str,
    front: str,
    back: str,
    lesson_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
    source_quote: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new FSRS flashcard and stores it in SQLite."""
    card_id = f"fc_{uuid.uuid4().hex[:12]}"
    fsrs_card = fsrs.Card()
    now_utc = datetime.datetime.now(timezone.utc)
    fsrs_card.due = now_utc
    fsrs_json = json.dumps(fsrs_card.to_dict())

    conn.execute(
        """
        INSERT INTO flashcards (
            id, course_id, lesson_id, chunk_id, front, back,
            state, due_date, stability, difficulty,
            elapsed_days, scheduled_days, reps, lapses,
            fsrs_data_json, source_quote, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            card_id,
            course_id,
            lesson_id,
            chunk_id,
            front.strip(),
            back.strip(),
            fsrs_card.state.value,
            now_utc.isoformat(),
            fsrs_card.stability or 0.0,
            fsrs_card.difficulty or 0.0,
            0,
            0,
            0,
            0,
            fsrs_json,
            source_quote,
            now_utc.isoformat(),
        ),
    )
    conn.commit()

    scheduler = get_fsrs_scheduler()
    intervals = preview_intervals(fsrs_card, scheduler, now_utc)

    return {
        "id": card_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "chunk_id": chunk_id,
        "front": front.strip(),
        "back": back.strip(),
        "state": fsrs_card.state.value,
        "state_name": fsrs_card.state.name,
        "due_date": now_utc.isoformat(),
        "stability": fsrs_card.stability or 0.0,
        "difficulty": fsrs_card.difficulty or 0.0,
        "reps": 0,
        "source_quote": source_quote,
        "intervals": intervals,
    }


def review_flashcard(
    conn,
    card_id: str,
    rating: int,
    exam_date: Optional[str] = None,
    review_time: Optional[datetime.datetime] = None,
) -> Tuple[Dict[str, Any], str]:
    """Submits an FSRS rating (1=Again, 2=Hard, 3=Good, 4=Easy) and updates scheduling state."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM flashcards WHERE id = ?;", (card_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Flashcard {card_id} not found.")

    col_names = [d[0] for d in cur.description]
    card_row = dict(zip(col_names, row))

    if review_time is None:
        review_time = datetime.datetime.now(timezone.utc)
    elif review_time.tzinfo is None:
        review_time = review_time.replace(tzinfo=timezone.utc)

    # Adaptive retention based on exam date
    retention = calculate_target_retention(exam_date)
    scheduler = get_fsrs_scheduler(desired_retention=retention)

    fsrs_card = card_to_fsrs(card_row)
    fsrs_rating = fsrs.Rating(rating)

    card_after, review_log = scheduler.review_card(fsrs_card, fsrs_rating, review_time)

    # Next interval calculation
    delta = card_after.due - review_time
    interval_str = format_interval(delta)

    # Update counts
    reps = (card_row.get("reps") or 0) + 1
    lapses = (card_row.get("lapses") or 0) + (1 if fsrs_rating == fsrs.Rating.Again else 0)
    scheduled_days = max(0, int(delta.total_seconds() / 86400.0))

    updated_json = json.dumps(card_after.to_dict())

    conn.execute(
        """
        UPDATE flashcards
        SET state = ?,
            due_date = ?,
            stability = ?,
            difficulty = ?,
            elapsed_days = ?,
            scheduled_days = ?,
            reps = ?,
            lapses = ?,
            last_review = ?,
            fsrs_data_json = ?
        WHERE id = ?;
        """,
        (
            card_after.state.value,
            card_after.due.isoformat(),
            card_after.stability or 0.0,
            card_after.difficulty or 0.0,
            card_row.get("elapsed_days", 0),
            scheduled_days,
            reps,
            lapses,
            review_time.isoformat(),
            updated_json,
            card_id,
        ),
    )
    conn.commit()

    # Previews for next ratings
    intervals = preview_intervals(card_after, scheduler, review_time)

    card_data = {
        "id": card_id,
        "course_id": card_row["course_id"],
        "lesson_id": card_row.get("lesson_id"),
        "chunk_id": card_row.get("chunk_id"),
        "front": card_row["front"],
        "back": card_row["back"],
        "state": card_after.state.value,
        "state_name": card_after.state.name,
        "due_date": card_after.due.isoformat(),
        "stability": card_after.stability or 0.0,
        "difficulty": card_after.difficulty or 0.0,
        "reps": reps,
        "source_quote": card_row.get("source_quote"),
        "intervals": intervals,
    }
    return card_data, interval_str


def get_due_flashcards(
    conn,
    course_id: str,
    lesson_id: Optional[str] = None,
    as_of: Optional[datetime.datetime] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retrieves cards currently due for review, sorted by due date."""
    if as_of is None:
        as_of = datetime.datetime.now(timezone.utc)

    cur = conn.cursor()
    query = """
        SELECT * FROM flashcards
        WHERE course_id = ? AND (due_date <= ? OR reps = 0)
    """
    params: List[Any] = [course_id, as_of.isoformat()]
    if lesson_id:
        query += " AND lesson_id = ?"
        params.append(lesson_id)
    query += " ORDER BY due_date ASC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    col_names = [d[0] for d in cur.description]

    scheduler = get_fsrs_scheduler()
    results = []
    for r in rows:
        row_dict = dict(zip(col_names, r))
        fsrs_card = card_to_fsrs(row_dict)
        intervals = preview_intervals(fsrs_card, scheduler, as_of)
        state_enum = fsrs.State(row_dict.get("state", 1))
        results.append({
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
        })
    return results


def get_flashcard_counts(conn, course_id: str) -> Dict[str, int]:
    """Returns counts of total, due, new (reps=0), learning, and review cards."""
    now_iso = datetime.datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = ?;", (course_id,))
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = ? AND (due_date <= ? OR reps = 0);", (course_id, now_iso))
    due = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = ? AND reps = 0;", (course_id,))
    new_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = ? AND state = 1 AND reps > 0;", (course_id,))
    learning = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM flashcards WHERE course_id = ? AND state = 2;", (course_id,))
    review = cur.fetchone()[0]

    return {
        "total": total,
        "due": due,
        "new": new_cards,
        "learning": learning,
        "review": review,
    }


def generate_concept_flashcards(
    conn,
    course_id: str,
    lesson_id: str,
    count: int = 5,
) -> List[Dict[str, Any]]:
    """Automatically generates 4-6 concise Q&A / formula flashcards per Concept Clip.
    
    Extracts key principles, definitions, or formulas from the clip's transcript chunks,
    tags each with [MM:SS] timestamp and clip reference, and inserts them into the
    FSRS spaced-repetition queue.
    """
    cur = conn.cursor()
    # Check if flashcards already exist for this lesson/clip
    cur.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?;", (lesson_id,))
    existing_count = cur.fetchone()[0]
    if existing_count >= 4:
        cur.execute("SELECT * FROM flashcards WHERE lesson_id = ? ORDER BY created_at ASC;", (lesson_id,))
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]
        scheduler = get_fsrs_scheduler()
        now_utc = datetime.datetime.now(timezone.utc)
        results = []
        for r in rows:
            cd = dict(zip(col_names, r))
            fc = card_to_fsrs(cd)
            intervals = preview_intervals(fc, scheduler, now_utc)
            cd["intervals"] = intervals
            cd["state_name"] = fc.state.name
            results.append(cd)
        return results

    # Fetch lesson title and chunks
    cur.execute("SELECT title FROM lessons WHERE id = ?;", (lesson_id,))
    l_row = cur.fetchone()
    lesson_title = l_row[0] if l_row else "Concept"

    cur.execute(
        """
        SELECT id, chunk_index, start_sec, end_sec, content
        FROM chunks
        WHERE lesson_id = ?
        ORDER BY start_sec ASC;
        """,
        (lesson_id,)
    )
    chunks = [
        {"id": r[0], "chunk_index": r[1], "start_sec": r[2] or 0, "end_sec": r[3] or 0, "content": r[4] or ""}
        for r in cur.fetchall()
    ]

    cards_to_create = []

    if chunks:
        for c in chunks:
            s_sec = int(c["start_sec"])
            h, rem = divmod(s_sec, 3600)
            m, s = divmod(rem, 60)
            t_str = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
            content = c["content"].strip()
            sentences = [sent.strip() for sent in content.split(".") if len(sent.strip()) > 15]

            for sent in sentences:
                s_low = sent.lower()
                if any(kw in s_low for kw in ["is defined as", "means", "formula", "syntax", "tuple", "property", "theorem", "rule", "transition", "condition"]):
                    parts = re.split(r"\b(is defined as|means|is given by|refers to|is called|states that)\b", sent, maxsplit=1, flags=re.IGNORECASE)
                    if len(parts) >= 3:
                        term = parts[0].strip()
                        definition = parts[1].strip() + " " + parts[2].strip()
                        front = f"What is the definition or role of '{term}' in {lesson_title}?"
                        back = f"{term} {definition}"
                    else:
                        front = f"State the key rule/formula for {lesson_title}:"
                        back = sent

                    cards_to_create.append({
                        "front": front,
                        "back": back,
                        "chunk_id": c["id"],
                        "source_quote": f"{t_str} {sent}",
                    })
                    if len(cards_to_create) >= count:
                        break
            if len(cards_to_create) >= count:
                break

    # If fewer than 4 cards found from definitions, synthesize from remaining chunk sentences
    if len(cards_to_create) < 4 and chunks:
        for idx, c in enumerate(chunks):
            s_sec = int(c["start_sec"])
            h, rem = divmod(s_sec, 3600)
            m, s = divmod(rem, 60)
            t_str = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
            sent = c["content"].split(".")[0].strip()
            if sent and len(sent) > 15:
                cards_to_create.append({
                    "front": f"Explain the core principle discussed at {t_str} in '{lesson_title}':",
                    "back": sent,
                    "chunk_id": c["id"],
                    "source_quote": f"{t_str} {sent}",
                })
            if len(cards_to_create) >= count:
                break

    # Fallback if no chunks
    if not cards_to_create:
        cards_to_create.append({
            "front": f"What is the primary topic of '{lesson_title}'?",
            "back": f"Foundational concepts, mechanics, and properties of {lesson_title}.",
            "chunk_id": None,
            "source_quote": "[00:00] Overview",
        })

    created_cards = []
    for item in cards_to_create[:count]:
        card = create_flashcard(
            conn=conn,
            course_id=course_id,
            lesson_id=lesson_id,
            chunk_id=item["chunk_id"],
            front=item["front"],
            back=item["back"],
            source_quote=item["source_quote"],
        )
        created_cards.append(card)

    return created_cards
