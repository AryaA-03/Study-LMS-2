"""Background Jobs API Router for non-blocking progress tracking and cancellation."""

import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.infra.job_queue import cancel_job, get_job, list_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def get_jobs_list(
    course_id: Optional[str] = None,
    limit: int = 25,
    db: sqlite3.Connection = Depends(get_db),
):
    """List recent background jobs, optionally filtered by course_id."""
    return {"jobs": list_jobs(db, course_id=course_id, limit=min(max(1, limit), 100))}


@router.get("/{job_id}")
def get_job_status(job_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Get status, progress percentage, and result of a specific background job."""
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel")
def cancel_background_job(job_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Cancel a queued or running background job."""
    cancelled = cancel_job(db, job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Active job not found or already finished")
    return {"success": True, "job_id": job_id, "status": "cancelled"}
