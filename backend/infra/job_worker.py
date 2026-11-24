"""Single-process async SQLite background job worker.

Polls the persistent `jobs` table for `queued` jobs (including jobs recovered after
a crash/restart by `recover_interrupted_jobs`), claims them atomically, checks for
cancellation between steps, and never holds a SQLite write lock across long awaits.
"""

import asyncio
import json
import logging
import sqlite3
from typing import Any, Dict, Optional

from backend.database import get_db_context
from backend.infra.job_queue import get_job, update_job_progress

logger = logging.getLogger("learn_lms.job_worker")


def _claim_next_queued_job() -> Optional[Dict[str, Any]]:
    """Atomically claim the oldest queued job with attempts < 3."""
    with get_db_context() as conn:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'queued' AND attempts < 3
            ORDER BY created_at ASC
            LIMIT 1;
            """
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = 'running', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'queued';
            """,
            (job_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return dict(row)


def is_job_cancelled(job_id: str) -> bool:
    """Short-lived check to honor mid-execution cancellation."""
    with get_db_context() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id = ?;", (job_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")


async def _execute_job(job: Dict[str, Any]) -> None:
    job_id = job["id"]
    job_type = job["job_type"]
    course_id = job.get("course_id") or ""
    payload = {}
    try:
        payload = json.loads(job.get("payload_json") or "{}")
    except Exception:
        payload = {}

    if not course_id:
        course_id = str(payload.get("course_id") or "")

    logger.info(f"[JobWorker] Claimed job {job_id} ({job_type}) for course {course_id}")

    try:
        if job_type == "cram_sheet_full":
            from backend.services.cram_sheet_engine import synthesize_full_syllabus_cram_sheet

            with get_db_context() as conn:
                update_job_progress(conn, job_id, "running", 10, "Synthesizing full-syllabus cram sheet...")

            if is_job_cancelled(job_id):
                return

            # Run synthesis with fresh connection inside executor/async context
            with get_db_context() as conn:
                result = await synthesize_full_syllabus_cram_sheet(conn, course_id)

            if is_job_cancelled(job_id):
                return

            with get_db_context() as conn:
                update_job_progress(
                    conn,
                    job_id,
                    "completed",
                    100,
                    "Full-syllabus Cram Sheet complete",
                    result={"cram_sheet_id": result.get("id"), "is_generated_by_llm": result.get("is_generated_by_llm")},
                )

        elif job_type == "smart_prepare":
            from backend.services.smart_prepare import smart_prepare_course

            with get_db_context() as conn:
                update_job_progress(conn, job_id, "running", 15, "Extracting subtitles and splitting into semantic topics...")

            if is_job_cancelled(job_id):
                return

            force_rep = bool(payload.get("force_repartition", False))
            with get_db_context() as conn:
                sp_res = await smart_prepare_course(conn, course_id, force_repartition=force_rep, job_id=job_id)

            if is_job_cancelled(job_id):
                return

            with get_db_context() as conn:
                update_job_progress(
                    conn,
                    job_id,
                    "completed",
                    100,
                    f"Smart topic split complete ({sp_res.get('new_semantic_clips', 0)} topics)",
                    result=sp_res,
                )

        elif job_type == "study_bundle_remaining":
            from backend.services.study_bundle import process_remaining_concept_bundles

            with get_db_context() as conn:
                update_job_progress(conn, job_id, "running", 15, "Building background study bundles...")

            if is_job_cancelled(job_id):
                return

            await process_remaining_concept_bundles(course_id, job_id=job_id)

            if is_job_cancelled(job_id):
                return

            with get_db_context() as conn:
                update_job_progress(conn, job_id, "completed", 100, "Background study bundles complete")

        else:
            with get_db_context() as conn:
                update_job_progress(
                    conn,
                    job_id,
                    "failed",
                    0,
                    f"Unknown job type: {job_type}",
                    error_text=f"Unsupported job_type={job_type}",
                )
    except Exception as exc:
        logger.error(f"[JobWorker] Job {job_id} failed: {exc}", exc_info=True)
        try:
            with get_db_context() as conn:
                update_job_progress(conn, job_id, "failed", 0, "Job failed", error_text=str(exc))
        except Exception:
            pass


class BackgroundJobWorker:
    """Lifecycle-managed async polling loop for SQLite jobs."""

    def __init__(self, poll_interval: float = 1.5):
        self.poll_interval = poll_interval
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._loop(), name="study-lms-job-worker")

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._stop_event and not self._stop_event.is_set():
            try:
                job = await asyncio.to_thread(_claim_next_queued_job)
                if job:
                    await _execute_job(job)
                    continue
            except sqlite3.OperationalError:
                # DB may not be migrated yet in unit tests
                pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"[JobWorker] Poll iteration error: {exc}")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue


job_worker = BackgroundJobWorker()
