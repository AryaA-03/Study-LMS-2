"""CourseIt-Style Auto-Generated Study Bundle Pipeline.

Pre-generates standalone GeeksforGeeks-style notes, quizzes ("Miss One -> Replay the Moment"),
and FSRS flashcards for Concept Clips.
- Immediately generates Clips 1..3 so the student can start studying within seconds.
- Enqueues remaining clips via persistent BackgroundJobWorker (short DB transactions; never holds SQLite locks across async LLM calls).
"""

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.database import get_db_context
from backend.services.transcription import ingest_lesson_transcript
from backend.services.notes import get_or_generate_lesson_notes
from backend.services.quiz_engine import create_and_store_quiz
from backend.services.fsrs_engine import generate_concept_flashcards

logger = logging.getLogger("learn_lms.study_bundle")


@contextmanager
def _get_bundle_db(db: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None):
    if db is not None:
        yield db
    elif db_path is not None:
        with get_db_context(db_path) as conn:
            yield conn
    else:
        with get_db_context() as conn:
            yield conn


async def generate_single_concept_bundle(
    conn: Optional[sqlite3.Connection],
    course_id: str,
    lesson_id: str,
    force_regenerate: bool = False,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generates notes, quiz, and FSRS flashcards for a single Concept Clip with short-lived DB transactions."""
    # 1. Short read: fetch lesson metadata & chunk count
    with _get_bundle_db(conn, db_path) as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, course_id, source_id, title, video_id, video_url, start_sec, end_sec
            FROM lessons
            WHERE id = ?;
            """,
            (lesson_id,),
        )
        l_row = cur.fetchone()
        if not l_row:
            logger.warning(f"[StudyBundle] Lesson {lesson_id} not found.")
            return {"notes": None, "quiz": None, "flashcards": []}
        source_id = l_row[2] or None
        title = l_row[3]
        video_id = l_row[4] or ""
        video_url = l_row[5] or ""
        start_sec = int(l_row[6] or 0)
        end_sec = int(l_row[7]) if l_row[7] else None
        target_video = video_id if video_id else video_url
        c_count = cur.execute("SELECT COUNT(*) FROM chunks WHERE lesson_id = ?;", (lesson_id,)).fetchone()[0]

    # 2. Ingest transcript chunks if missing
    if c_count == 0 and target_video:
        try:
            logger.info(f"[StudyBundle] Fetching transcript chunks for clip {lesson_id} ({title})")
            with _get_bundle_db(conn, db_path) as db:
                await ingest_lesson_transcript(
                    db,
                    course_id=course_id,
                    source_id=source_id,
                    lesson_id=lesson_id,
                    video_id_or_url=target_video,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )
                db.commit()
        except Exception as e:
            logger.warning(f"[StudyBundle] Transcript ingestion failed for {lesson_id}: {e}")

    # 3. Generate Standalone GeeksforGeeks-Style Notes
    notes_res = None
    try:
        with _get_bundle_db(conn, db_path) as db:
            notes_res = await get_or_generate_lesson_notes(db, course_id, lesson_id, force_regenerate=force_regenerate)
            db.commit()
    except Exception as e:
        logger.warning(f"[StudyBundle] Notes generation failed for {lesson_id}: {e}")

    # 4. Generate Per-Concept Quiz (run sync quiz generator off event loop when using fresh DB)
    quiz_res = None
    try:
        def _gen_quiz():
            with _get_bundle_db(conn, db_path) as db:
                q_row = db.execute("SELECT id FROM quizzes WHERE lesson_id = ? AND quiz_type = 'lesson';", (lesson_id,)).fetchone()
                if not q_row or force_regenerate:
                    res = create_and_store_quiz(db, course_id, quiz_type="lesson", lesson_id=lesson_id, question_count=4)
                    db.commit()
                    return res
                return None
        quiz_res = _gen_quiz() if conn is not None else await asyncio.to_thread(_gen_quiz)
    except Exception as e:
        logger.warning(f"[StudyBundle] Quiz generation failed for {lesson_id}: {e}")

    # 5. Generate Auto-Generated FSRS Flashcards
    flashcards_res: List[Dict[str, Any]] = []
    try:
        def _gen_cards():
            with _get_bundle_db(conn, db_path) as db:
                fc_count = db.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?;", (lesson_id,)).fetchone()[0]
                if fc_count < 4 or force_regenerate:
                    res = generate_concept_flashcards(db, course_id, lesson_id, count=5)
                    db.commit()
                    return res
                return []
        flashcards_res = _gen_cards() if conn is not None else await asyncio.to_thread(_gen_cards)
    except Exception as e:
        logger.warning(f"[StudyBundle] Flashcards generation failed for {lesson_id}: {e}")

    logger.info(f"[StudyBundle] Completed bundle for Concept Clip {lesson_id} ({title})")
    return {"notes": notes_res, "quiz": quiz_res, "flashcards": flashcards_res}


async def generate_initial_concept_bundles(
    course_id: str,
    db: Optional[sqlite3.Connection] = None,
    count: int = 3,
    db_path: Optional[Path] = None,
) -> None:
    """Immediately generates study bundles for Clips 1..3 so user can start studying within seconds."""
    logger.info(f"[StudyBundle] Immediately preparing first {count} Concept Clips for course {course_id}")
    try:
        with _get_bundle_db(db, db_path) as conn:
            clips = conn.execute(
                """
                SELECT id, title, order_index
                FROM lessons
                WHERE course_id = ? AND COALESCE(is_excluded, 0) = 0
                ORDER BY order_index ASC
                LIMIT ?;
                """,
                (course_id, count),
            ).fetchall()

        for c in clips:
            cid, ctitle = c[0], c[1]
            logger.info(f"[StudyBundle] Pre-warming initial bundle for clip {cid} ({ctitle})")
            await generate_single_concept_bundle(db, course_id, cid, force_regenerate=False, db_path=db_path)

        with _get_bundle_db(db, db_path) as qconn:
            from backend.infra.job_queue import enqueue_job
            existing = qconn.execute(
                "SELECT id FROM jobs WHERE course_id = ? AND job_type = 'study_bundle_remaining' AND status IN ('queued', 'running') LIMIT 1;",
                (course_id,),
            ).fetchone()
            if not existing:
                enqueue_job(qconn, "study_bundle_remaining", course_id=course_id, payload={"course_id": course_id})
    except Exception as e:
        logger.error(f"[StudyBundle] Initial concept bundle generation error: {e}", exc_info=True)


async def process_remaining_concept_bundles(
    course_id: str,
    db: Optional[sqlite3.Connection] = None,
    job_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Silently processes remaining Concept Clips in a resumable background queue without holding SQLite locks."""
    from backend.infra.job_queue import update_job_progress

    logger.info(f"[StudyBundle] Starting background processing of remaining concept clips for course {course_id}")
    try:
        with _get_bundle_db(db, db_path) as conn:
            all_clips = conn.execute(
                """
                SELECT id, title, order_index
                FROM lessons
                WHERE course_id = ? AND COALESCE(is_excluded, 0) = 0
                ORDER BY order_index ASC;
                """,
                (course_id,),
            ).fetchall()

        total = max(1, len(all_clips))
        for idx, c in enumerate(all_clips, start=1):
            cid, ctitle = c[0], c[1]
            # Short check for cancellation + existing bundle completeness
            with _get_bundle_db(db, db_path) as conn:
                if job_id:
                    jrow = conn.execute("SELECT status FROM jobs WHERE id = ?;", (job_id,)).fetchone()
                    if jrow and jrow[0] == "cancelled":
                        logger.info(f"[StudyBundle] Job {job_id} cancelled; stopping background loop.")
                        break
                counts = conn.execute(
                    "SELECT (SELECT COUNT(*) FROM notes WHERE lesson_id = ? AND is_generated = 1 AND COALESCE(generation_mode, 'deterministic') = 'llm'), "
                    "(SELECT COUNT(*) FROM quizzes WHERE lesson_id = ? AND quiz_type = 'lesson'), "
                    "(SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?);",
                    (cid, cid, cid),
                ).fetchone()
                if counts[0] > 0 and counts[1] > 0 and counts[2] >= 4:
                    continue
                if job_id:
                    pct = min(95, 15 + int((idx / total) * 80))
                    update_job_progress(conn, job_id, "running", pct, f"Preparing clip {idx}/{total}: {ctitle[:50]}")

            await generate_single_concept_bundle(db, course_id, cid, force_regenerate=False, db_path=db_path)
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"[StudyBundle] Background concept bundle processing error: {e}", exc_info=True)
