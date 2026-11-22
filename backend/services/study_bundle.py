"""Automatic Per-Concept Study Bundle Service (Layer 1 Study Package).

Generates complete, self-contained study bundles per Concept Clip:
1. Standalone GeeksforGeeks-Style Notes (structured from transcript slice alone).
2. Per-Concept Quiz ("Miss One -> Replay the Moment") with exact [MM:SS] timestamp links.
3. Auto-Generated FSRS Spaced Repetition Flashcards (4-6 cards tagged with clip + timestamp).
4. Progressive Background Queue: Immediately generates Clips 1-3, silently queues remaining
   in background, resumable and SQLite cached by SHA-256 content hash.
"""

import sys
import logging
import sqlite3
import asyncio
from typing import Dict, Any, List, Optional
import contextlib

from backend.database import get_db, get_db_context
from backend.services.transcription import ingest_lesson_transcript
from backend.services.notes import get_or_generate_lesson_notes
from backend.services.quiz_engine import create_and_store_quiz
from backend.services.fsrs_engine import generate_concept_flashcards

logger = logging.getLogger("learn_lms.study_bundle")


@contextlib.contextmanager
def _get_bundle_db(db: Optional[sqlite3.Connection] = None):
    """Context manager providing an active SQLite connection for background tasks."""
    if db is not None:
        yield db
        return

    main_mod = sys.modules.get("backend.main")
    app = getattr(main_mod, "app", None) if main_mod else None
    if app and get_db in getattr(app, "dependency_overrides", {}):
        override_fn = app.dependency_overrides[get_db]
        gen = override_fn()
        conn = next(gen)
        try:
            yield conn
        finally:
            try:
                next(gen)
            except StopIteration:
                pass
    else:
        with get_db_context() as conn:
            yield conn


async def generate_single_concept_bundle(
    conn: sqlite3.Connection,
    course_id: str,
    lesson_id: str,
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """Generates complete study bundle (Notes + Quiz + Flashcards) for a single Concept Clip."""
    cur = conn.cursor()

    # 1. Fetch lesson metadata
    cur.execute(
        """
        SELECT id, course_id, source_id, title, video_id, video_url, start_sec, end_sec
        FROM lessons
        WHERE id = ?;
        """,
        (lesson_id,)
    )
    l_row = cur.fetchone()
    if not l_row:
        logger.warning(f"[StudyBundle] Lesson {lesson_id} not found.")
        return {"notes": None, "quiz": None, "flashcards": []}

    source_id = l_row[2] or ""
    title = l_row[3]
    video_id = l_row[4] or ""
    video_url = l_row[5] or ""
    start_sec = int(l_row[6] or 0)
    end_sec = int(l_row[7] or 0)
    target_video = video_id if video_id else video_url

    # 2. Check and ingest transcript chunks if missing
    cur.execute("SELECT COUNT(*) FROM chunks WHERE lesson_id = ?;", (lesson_id,))
    c_count = cur.fetchone()[0]
    if c_count == 0 and target_video:
        try:
            logger.info(f"[StudyBundle] Fetching transcript chunks for clip {lesson_id} ({title})")
            await ingest_lesson_transcript(
                conn,
                course_id=course_id,
                source_id=source_id,
                lesson_id=lesson_id,
                video_id_or_url=target_video,
                start_sec=start_sec,
                end_sec=end_sec,
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"[StudyBundle] Transcript ingestion failed for {lesson_id}: {e}")

    # 3. Generate Standalone GeeksforGeeks-Style Notes
    notes_res = None
    try:
        notes_res = await get_or_generate_lesson_notes(conn, course_id, lesson_id, force_regenerate=force_regenerate)
        conn.commit()
    except Exception as e:
        logger.warning(f"[StudyBundle] Notes generation failed for {lesson_id}: {e}")

    # 4. Generate Per-Concept Quiz ("Miss One -> Replay the Moment")
    quiz_res = None
    try:
        cur.execute("SELECT id FROM quizzes WHERE lesson_id = ? AND quiz_type = 'lesson';", (lesson_id,))
        q_row = cur.fetchone()
        if not q_row or force_regenerate:
            quiz_res = create_and_store_quiz(conn, course_id, quiz_type="lesson", lesson_id=lesson_id, question_count=4)
            conn.commit()
    except Exception as e:
        logger.warning(f"[StudyBundle] Quiz generation failed for {lesson_id}: {e}")

    # 5. Generate Auto-Generated FSRS Flashcards
    flashcards_res = []
    try:
        cur.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?;", (lesson_id,))
        fc_count = cur.fetchone()[0]
        if fc_count < 4 or force_regenerate:
            flashcards_res = generate_concept_flashcards(conn, course_id, lesson_id, count=5)
            conn.commit()
    except Exception as e:
        logger.warning(f"[StudyBundle] Flashcards generation failed for {lesson_id}: {e}")

    logger.info(f"[StudyBundle] Completed bundle for Concept Clip {lesson_id} ({title})")
    return {
        "notes": notes_res,
        "quiz": quiz_res,
        "flashcards": flashcards_res,
    }


async def generate_initial_concept_bundles(
    course_id: str,
    db: Optional[sqlite3.Connection] = None,
    count: int = 3,
) -> None:
    """Immediately generates study bundles for Clips 1..3 so user can start studying within seconds."""
    logger.info(f"[StudyBundle] Immediately preparing first {count} Concept Clips for course {course_id}")
    try:
        with _get_bundle_db(db) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, title, order_index
                FROM lessons
                WHERE course_id = ?
                ORDER BY order_index ASC
                LIMIT ?;
                """,
                (course_id, count)
            )
            clips = cur.fetchall()

            for c in clips:
                cid = c[0]
                ctitle = c[1]
                logger.info(f"[StudyBundle] Pre-warming initial bundle for clip {cid} ({ctitle})")
                await generate_single_concept_bundle(conn, course_id, cid, force_regenerate=False)

        # Enqueue remaining clips in background
        asyncio.create_task(process_remaining_concept_bundles(course_id, db))
    except Exception as e:
        logger.error(f"[StudyBundle] Initial concept bundle generation error: {e}", exc_info=True)


async def process_remaining_concept_bundles(
    course_id: str,
    db: Optional[sqlite3.Connection] = None,
) -> None:
    """Silently processes remaining Concept Clips in a resumable background queue.
    
    Cached in SQLite by SHA-256 content hash so resumption is instantaneous if interrupted.
    """
    logger.info(f"[StudyBundle] Starting background processing of remaining concept clips for course {course_id}")
    try:
        with _get_bundle_db(db) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, title, order_index
                FROM lessons
                WHERE course_id = ?
                ORDER BY order_index ASC;
                """,
                (course_id,)
            )
            all_clips = cur.fetchall()

            for c in all_clips:
                cid = c[0]
                ctitle = c[1]
                # Check if this clip already has notes, quiz, and flashcards
                cur.execute(
                    "SELECT (SELECT COUNT(*) FROM notes WHERE lesson_id = ? AND is_generated = 1), "
                    "(SELECT COUNT(*) FROM quizzes WHERE lesson_id = ? AND quiz_type = 'lesson'), "
                    "(SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?);",
                    (cid, cid, cid)
                )
                counts = cur.fetchone()
                has_notes = counts[0] > 0
                has_quiz = counts[1] > 0
                has_flashcards = counts[2] >= 4

                if has_notes and has_quiz and has_flashcards:
                    continue  # Already generated, move to next clip

                logger.info(f"[StudyBundle] Background processing clip {cid} ({ctitle})")
                await generate_single_concept_bundle(conn, course_id, cid, force_regenerate=False)
                # Yield control briefly so we don't hog the event loop
                await asyncio.sleep(0.05)

        logger.info(f"[StudyBundle] Finished background concept bundle processing for course {course_id}")
    except Exception as e:
        logger.error(f"[StudyBundle] Background bundle processing failed for {course_id}: {e}", exc_info=True)
