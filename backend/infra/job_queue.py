"""Persistent SQLite-backed background job queue with restart recovery and progress tracking."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_job(
    db_conn: sqlite3.Connection,
    job_type: str,
    course_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    owner_id: str = "local",
) -> str:
    """Create a queued job row in SQLite and return its job_id."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    db_conn.execute(
        """
        INSERT INTO jobs (id, owner_id, course_id, job_type, status, progress_pct, message, payload_json, cursor_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'queued', 0, 'Queued', ?, '{}', ?, ?);
        """,
        (job_id, owner_id, course_id, job_type, json.dumps(payload or {}), now, now),
    )
    db_conn.commit()
    return job_id


def update_job_progress(
    db_conn: sqlite3.Connection,
    job_id: str,
    status: str,
    progress_pct: int,
    message: str = "",
    cursor: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error_text: Optional[str] = None,
) -> None:
    """Persist job progress, cursor, result, or failure state."""
    db_conn.execute(
        """
        UPDATE jobs
        SET status = ?,
            progress_pct = ?,
            message = ?,
            cursor_json = COALESCE(?, cursor_json),
            result_json = COALESCE(?, result_json),
            error_text = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            status,
            max(0, min(100, int(progress_pct))),
            message,
            json.dumps(cursor) if cursor is not None else None,
            json.dumps(result) if result is not None else None,
            error_text,
            _now_iso(),
            job_id,
        ),
    )
    db_conn.commit()


def get_job(db_conn: sqlite3.Connection, job_id: str, owner_id: str = "local") -> Optional[Dict[str, Any]]:
    """Retrieve a single job status record scoped by owner_id."""
    row = db_conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND owner_id = ?;",
        (job_id, owner_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("payload_json", "cursor_json", "result_json"):
        if d.get(k):
            try:
                d[k.replace("_json", "")] = json.loads(d[k])
            except Exception:
                d[k.replace("_json", "")] = None
    return d


def list_jobs(
    db_conn: sqlite3.Connection,
    course_id: Optional[str] = None,
    owner_id: str = "local",
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """List recent jobs optionally filtered by course_id."""
    if course_id:
        rows = db_conn.execute(
            "SELECT * FROM jobs WHERE owner_id = ? AND course_id = ? ORDER BY created_at DESC LIMIT ?;",
            (owner_id, course_id, limit),
        ).fetchall()
    else:
        rows = db_conn.execute(
            "SELECT * FROM jobs WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?;",
            (owner_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def cancel_job(db_conn: sqlite3.Connection, job_id: str, owner_id: str = "local") -> bool:
    """Cancel a queued or running job."""
    cur = db_conn.execute(
        """
        UPDATE jobs
        SET status = 'cancelled', message = 'Cancelled by user', updated_at = ?
        WHERE id = ? AND owner_id = ? AND status IN ('queued', 'running');
        """,
        (_now_iso(), job_id, owner_id),
    )
    db_conn.commit()
    return cur.rowcount > 0


def recover_interrupted_jobs(db_conn: sqlite3.Connection) -> int:
    """On server startup, reset any interrupted 'running' jobs back to 'queued'."""
    cur = db_conn.execute(
        """
        UPDATE jobs
        SET status = 'queued', message = 'Recovered after restart', attempts = attempts + 1, updated_at = ?
        WHERE status = 'running';
        """,
        (_now_iso(),),
    )
    db_conn.commit()
    return cur.rowcount
