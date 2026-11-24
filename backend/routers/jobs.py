from pathlib import Path
"""Background Jobs API Router for non-blocking progress tracking and cancellation."""

import sqlite3
from typing import Optional
import asyncio
import json
from backend.deps import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.database import get_db
from backend.infra.job_queue import cancel_job, get_job, list_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.get("")
def get_jobs_list(
    course_id: Optional[str] = None,
    limit: int = 25,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """List recent background jobs, optionally filtered by course_id."""
    return {"jobs": list_jobs(db, course_id=course_id, owner_id=user.id, limit=min(max(1, limit), 100))}


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Get status, progress percentage, and result of a specific background job."""
    job = get_job(db, job_id, owner_id=user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel")
def cancel_background_job(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Cancel a queued or running background job."""
    cancelled = cancel_job(db, job_id, owner_id=user.id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Active job not found or already finished")
    return {"success": True, "job_id": job_id, "status": "cancelled"}


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Server-Sent Events (SSE) stream for live background job progress until terminal status or disconnect."""
    initial = get_job(db, job_id, owner_id=user.id)
    if not initial:
        raise HTTPException(status_code=404, detail="Job not found")

    db_file_row = db.execute("PRAGMA database_list;").fetchone()
    db_file = Path(db_file_row[2]) if (db_file_row and db_file_row[2]) else None

    async def _event_gen():
        from backend.database import get_db_context
        ticks = 0
        while True:
            if await request.is_disconnected():
                break
            ctx = get_db_context(db_file) if db_file else get_db_context()
            with ctx as conn:
                current = get_job(conn, job_id, owner_id=user.id)
            if not current:
                break
            yield f"data: {json.dumps(current, default=str)}\n\n"
            if current.get("status") in ("completed", "failed", "cancelled"):
                break
            ticks += 1
            if ticks % 15 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(_event_gen(), media_type="text/event-stream")
