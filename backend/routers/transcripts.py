"""Transcripts and Captions API Router."""

import logging
from typing import Dict, Any, List
from backend.deps import get_current_user
from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.database import get_db
from backend.services.transcription import ingest_lesson_transcript

logger = logging.getLogger("learn_lms.api.transcripts")
router = APIRouter(prefix="/api/lessons", tags=["transcripts"], dependencies=[Depends(get_current_user)])


@router.post("/{lesson_id}/transcribe")
async def transcribe_lesson(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Ingests captions or runs lazy Whisper fallback for a single lesson."""
    cur = db.cursor()
    cur.execute(
        """
        SELECT l.id, l.course_id, l.source_id, l.video_id, l.start_sec, l.end_sec, s.url
        FROM lessons l
        LEFT JOIN sources s ON l.source_id = s.id
        WHERE l.id = ?;
        """,
        (lesson_id,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    course_id = row[1]
    source_id = row[2] or ""
    video_id = str(row[3] or "").strip()
    start_sec = int(row[4] or 0)
    end_sec = row[5]
    video_url = row[6] or video_id

    # If video_url is a playlist or not single video, fallback to video_id
    target_video = video_id if video_id else video_url

    success, transcript_type, chunk_count = await ingest_lesson_transcript(
        db,
        course_id=course_id,
        source_id=source_id,
        lesson_id=lesson_id,
        video_id_or_url=target_video,
        start_sec=start_sec,
        end_sec=end_sec
    )

    return {
        "success": success,
        "lesson_id": lesson_id,
        "transcript_type": transcript_type,
        "chunk_count": chunk_count
    }


@router.get("/{lesson_id}/chunks")
def get_lesson_chunks(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Retrieves all indexed transcript chunks for a lesson."""
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, chunk_index, token_count, start_sec, end_sec, content
        FROM chunks
        WHERE lesson_id = ?
        ORDER BY start_sec ASC, chunk_index ASC;
        """,
        (lesson_id,)
    )
    rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "chunk_index": r[1],
            "token_count": r[2],
            "start_sec": r[3],
            "end_sec": r[4],
            "content": r[5]
        }
        for r in rows
    ]


@router.get("/{lesson_id}/status")
def get_lesson_transcript_status(
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db)
) -> Dict[str, Any]:
    """Returns the current transcription and caption status for a lesson."""
    cur = db.cursor()
    cur.execute(
        """
        SELECT has_transcript, transcript_type, transcription_status
        FROM lessons
        WHERE id = ?;
        """,
        (lesson_id,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    return {
        "lesson_id": lesson_id,
        "has_transcript": bool(row[0]),
        "transcript_type": row[1] or "",
        "transcription_status": row[2] or "pending"
    }
