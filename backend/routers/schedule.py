"""Schedule generation, reflow, replanning, diffing, and undo router."""

import uuid
import json
import sqlite3
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from backend.database import get_db
from backend.models.schemas import (
    ScheduleResponse,
    DayScheduleResponse,
    AllocationResponse,
    ReplanRequest,
    ReplanResponse,
    DiffSummary,
)
from backend.scheduler.engine import (
    generate_schedule,
    reflow_overdue_and_remaining,
    compress_schedule,
    compute_schedule_diff,
    ScheduleAllocation,
    is_rest_day,
    get_study_dates,
    default_clock,
)

logger = logging.getLogger("learn_lms.schedule")
router = APIRouter(prefix="/api/courses/{course_id}/schedule", tags=["schedule"])

@router.post("/generate", response_model=ScheduleResponse)
def generate_course_schedule(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    lessons = db.execute(
        """
        SELECT l.* FROM lessons l
        JOIN sources s ON l.source_id = s.id
        WHERE l.course_id = ? AND s.is_approved = 1 AND l.is_excluded = 0
        ORDER BY l.order_index ASC;
        """,
        (course_id,),
    ).fetchall()

    if not lessons:
        lessons = db.execute(
            "SELECT * FROM lessons WHERE course_id = ? AND is_excluded = 0 ORDER BY order_index ASC;",
            (course_id,),
        ).fetchall()

    if not lessons:
        raise HTTPException(status_code=400, detail="No active approved lessons found to schedule. Check source approvals or lesson filters.")

    lesson_dicts = [dict(l) for l in lessons]
    rest_days = json.loads(course["rest_days"])
    target_d = datetime.strptime(course["target_date"], "%Y-%m-%d").date()
    today = default_clock()
    strategy = course["schedule_strategy"] if "schedule_strategy" in course.keys() else "paced"

    logger.info(f"[Schedule] Generating schedule for course '{course['title']}' | Strategy: {strategy} | Target: {course['target_date']}")

    sched_result = generate_schedule(
        course_id=course_id,
        lessons=lesson_dicts,
        start_date=today,
        target_date=target_d,
        minutes_per_day=course["minutes_per_day"],
        playback_speed=course["playback_speed"],
        rest_days=rest_days,
        revision_buffer_days=course["revision_buffer_days"],
        schedule_strategy=strategy,
    )

    # Save initial snapshot if existing allocations were present
    existing_allocs = db.execute(
        "SELECT * FROM schedule_allocations WHERE course_id = ?;", (course_id,)
    ).fetchall()
    if existing_allocs:
        save_snapshot(
            course_id=course_id,
            reason="regenerate",
            allocations=[dict(a) for a in existing_allocs],
            course_row=course,
            diff_summary={"action": "initial_generation"},
            db=db,
        )

    # Replace allocations in DB
    db.execute("DELETE FROM schedule_allocations WHERE course_id = ?;", (course_id,))
    for a in sched_result["allocations"]:
        db.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                a.id,
                course_id,
                a.lesson_id,
                a.scheduled_date,
                a.split_index,
                a.split_count,
                a.allocated_start_sec,
                a.allocated_end_sec,
                a.effective_minutes,
                1 if a.is_completed else 0,
                1 if a.is_skipped else 0,
            ),
        )

    return get_course_schedule(course_id, db)

@router.get("", response_model=ScheduleResponse)
def get_course_schedule(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    rows = db.execute(
        """
        SELECT sa.*, l.title as lesson_title, l.video_id, l.video_url, l.priority
        FROM schedule_allocations sa
        JOIN lessons l ON sa.lesson_id = l.id
        WHERE sa.course_id = ?
        ORDER BY sa.scheduled_date ASC, sa.split_index ASC, sa.allocated_start_sec ASC;
        """,
        (course_id,),
    ).fetchall()

    rest_days = json.loads(course["rest_days"])
    target_d = datetime.strptime(course["target_date"], "%Y-%m-%d").date()
    rev_buffer = course["revision_buffer_days"]
    strategy = course["schedule_strategy"] if "schedule_strategy" in course.keys() else "paced"

    from collections import defaultdict
    allocs_by_date = defaultdict(list)
    total_effective = 0.0
    completed_effective = 0.0
    dates_seen = set()

    for r in rows:
        alloc_dto = AllocationResponse(
            id=r["id"],
            course_id=r["course_id"],
            lesson_id=r["lesson_id"],
            lesson_title=r["lesson_title"],
            video_id=r["video_id"],
            video_url=r["video_url"],
            scheduled_date=r["scheduled_date"],
            split_index=r["split_index"],
            split_count=r["split_count"],
            allocated_start_sec=r["allocated_start_sec"],
            allocated_end_sec=r["allocated_end_sec"],
            raw_minutes=round((r["allocated_end_sec"] - r["allocated_start_sec"]) / 60.0, 2),
            effective_minutes=round(r["effective_minutes"], 2),
            is_completed=bool(r["is_completed"]),
            is_skipped=bool(r["is_skipped"]),
            priority=r["priority"],
        )
        allocs_by_date[r["scheduled_date"]].append(alloc_dto)
        dates_seen.add(r["scheduled_date"])
        if not r["is_skipped"]:
            total_effective += r["effective_minutes"]
            if r["is_completed"]:
                completed_effective += r["effective_minutes"]

    today = default_clock()
    min_date = today
    if dates_seen:
        earliest_alloc = min(datetime.strptime(d, "%Y-%m-%d").date() for d in dates_seen)
        min_date = min(today, earliest_alloc)

    max_date = target_d
    if dates_seen:
        latest_alloc = max(datetime.strptime(d, "%Y-%m-%d").date() for d in dates_seen)
        max_date = max(target_d, latest_alloc)

    revision_dates_set = set()
    if rev_buffer > 0:
        for i in range(rev_buffer):
            rev_d = target_d - timedelta(days=i)
            revision_dates_set.add(rev_d.strftime("%Y-%m-%d"))

    days: List[DayScheduleResponse] = []
    curr = min_date
    while curr <= max_date:
        d_str = curr.strftime("%Y-%m-%d")
        day_allocs = allocs_by_date.get(d_str, [])
        is_rest = is_rest_day(curr, rest_days)
        is_rev = d_str in revision_dates_set
        day_eff = sum(a.effective_minutes for a in day_allocs if not a.is_skipped)

        days.append(
            DayScheduleResponse(
                date=d_str,
                day_name=curr.strftime("%A"),
                is_rest_day=is_rest,
                is_revision_day=is_rev,
                total_effective_minutes=round(day_eff, 1),
                allocations=day_allocs,
            )
        )
        curr += timedelta(days=1)

    projected = max(dates_seen) if dates_seen else None
    remaining_eff = max(0.0, total_effective - completed_effective)

    is_behind = False
    if projected:
        try:
            proj_d = datetime.strptime(projected, "%Y-%m-%d").date()
            eff_deadline = target_d - timedelta(days=rev_buffer)
            is_behind = proj_d > eff_deadline
        except Exception:
            pass

    # Compute daily target minutes
    daily_target = float(course["minutes_per_day"])
    if strategy == "paced":
        try:
            eff_deadline = target_d - timedelta(days=rev_buffer)
            study_dates, _, _ = get_study_dates(today, eff_deadline, rest_days, revision_buffer_days=0)
            if len(study_dates) > 0 and remaining_eff > 0:
                daily_target = round(remaining_eff / len(study_dates), 1)
        except Exception:
            pass

    return ScheduleResponse(
        course_id=course_id,
        days=days,
        total_effective_minutes=round(total_effective, 1),
        completed_effective_minutes=round(completed_effective, 1),
        remaining_effective_minutes=round(remaining_eff, 1),
        projected_finish_date=projected,
        target_date=course["target_date"],
        is_behind_schedule=is_behind,
        revision_buffer_days=rev_buffer,
        schedule_strategy=strategy,
        effective_daily_target_minutes=daily_target,
    )

@router.post("/allocations/{allocation_id}/toggle", response_model=AllocationResponse)
def toggle_allocation(
    course_id: str,
    allocation_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        """
        SELECT sa.*, l.title as lesson_title, l.video_id, l.video_url, l.priority
        FROM schedule_allocations sa
        JOIN lessons l ON sa.lesson_id = l.id
        WHERE sa.id = ? AND sa.course_id = ?;
        """,
        (allocation_id, course_id),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Allocation not found")

    new_completed = 0 if row["is_completed"] else 1
    completed_at = datetime.now().isoformat() if new_completed else None

    db.execute(
        "UPDATE schedule_allocations SET is_completed = ?, completed_at = ? WHERE id = ?;",
        (new_completed, completed_at, allocation_id),
    )
    logger.info(f"[Schedule] Toggled allocation {allocation_id} completion: {bool(new_completed)}")

    updated = db.execute(
        """
        SELECT sa.*, l.title as lesson_title, l.video_id, l.video_url, l.priority
        FROM schedule_allocations sa
        JOIN lessons l ON sa.lesson_id = l.id
        WHERE sa.id = ?;
        """,
        (allocation_id,),
    ).fetchone()

    return AllocationResponse(
        id=updated["id"],
        course_id=updated["course_id"],
        lesson_id=updated["lesson_id"],
        lesson_title=updated["lesson_title"],
        video_id=updated["video_id"],
        video_url=updated["video_url"],
        scheduled_date=updated["scheduled_date"],
        split_index=updated["split_index"],
        split_count=updated["split_count"],
        allocated_start_sec=updated["allocated_start_sec"],
        allocated_end_sec=updated["allocated_end_sec"],
        raw_minutes=round((updated["allocated_end_sec"] - updated["allocated_start_sec"]) / 60.0, 2),
        effective_minutes=round(updated["effective_minutes"], 2),
        is_completed=bool(updated["is_completed"]),
        is_skipped=bool(updated["is_skipped"]),
        priority=updated["priority"],
    )

@router.post("/allocations/{allocation_id}/skip", response_model=ScheduleResponse)
def skip_allocation(
    course_id: str,
    allocation_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    target_alloc = db.execute(
        "SELECT * FROM schedule_allocations WHERE id = ? AND course_id = ?;",
        (allocation_id, course_id),
    ).fetchone()
    if not target_alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")

    logger.info(f"[Schedule] Skipped allocation {allocation_id} - triggering automatic reflow")
    db.execute(
        "UPDATE schedule_allocations SET is_skipped = 1, skipped_at = ? WHERE id = ?;",
        (datetime.now().isoformat(), allocation_id),
    )

    replan_req = ReplanRequest(mode="normal")
    replan_schedule(course_id, replan_req, db)
    return get_course_schedule(course_id, db)

@router.post("/replan", response_model=ReplanResponse)
def replan_schedule(
    course_id: str,
    req: ReplanRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    old_alloc_rows = db.execute(
        """
        SELECT sa.*, l.title as lesson_title, l.video_id, l.video_url, l.priority
        FROM schedule_allocations sa
        JOIN lessons l ON sa.lesson_id = l.id
        WHERE sa.course_id = ?
        ORDER BY sa.scheduled_date ASC;
        """,
        (course_id,),
    ).fetchall()

    old_allocs = [
        ScheduleAllocation.from_dict({
            **dict(r),
            "effective_minutes": r["effective_minutes"],
        })
        for r in old_alloc_rows
    ]

    # Apply updated course parameters
    minutes_per_day = req.minutes_per_day or course["minutes_per_day"]
    playback_speed = req.playback_speed or course["playback_speed"]
    rest_days = req.rest_days if req.rest_days is not None else json.loads(course["rest_days"])
    target_date_str = req.target_date or course["target_date"]
    rev_buffer = req.revision_buffer_days if req.revision_buffer_days is not None else course["revision_buffer_days"]
    strategy = req.schedule_strategy or (course["schedule_strategy"] if "schedule_strategy" in course.keys() else "paced")

    target_d = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    today = default_clock()

    logger.info(f"[Schedule] Replanning course {course_id} | Mode: {req.mode} | Strategy: {strategy} | Speed: {playback_speed}x")

    # Fetch lessons (excluding is_excluded)
    lessons_rows = db.execute(
        """
        SELECT l.* FROM lessons l
        JOIN sources s ON l.source_id = s.id
        WHERE l.course_id = ? AND s.is_approved = 1 AND l.is_excluded = 0
        ORDER BY l.order_index ASC;
        """,
        (course_id,),
    ).fetchall()
    lessons = [dict(l) for l in lessons_rows]

    dropped_count = 0
    deficit_minutes = 0.0
    deficit_message = None

    if req.mode == "compress":
        sched_res, dropped_count, deficit_minutes, deficit_message = compress_schedule(
            course_id=course_id,
            lessons=lessons,
            start_date=today,
            target_date=target_d,
            minutes_per_day=minutes_per_day,
            playback_speed=playback_speed,
            rest_days=rest_days,
            revision_buffer_days=rev_buffer,
        )
    elif req.mode == "extend":
        sched_res = reflow_overdue_and_remaining(
            course_id=course_id,
            allocations=old_allocs,
            lessons=lessons,
            target_date=target_d + timedelta(days=365),
            minutes_per_day=minutes_per_day,
            playback_speed=playback_speed,
            rest_days=rest_days,
            revision_buffer_days=rev_buffer,
            schedule_strategy=strategy,
        )
        if sched_res["projected_finish_date"]:
            new_proj = datetime.strptime(sched_res["projected_finish_date"], "%Y-%m-%d").date()
            new_target = new_proj + timedelta(days=rev_buffer)
            target_date_str = new_target.strftime("%Y-%m-%d")
            sched_res["target_date"] = target_date_str
            sched_res["is_behind_schedule"] = False
    else:
        sched_res = reflow_overdue_and_remaining(
            course_id=course_id,
            allocations=old_allocs,
            lessons=lessons,
            target_date=target_d,
            minutes_per_day=minutes_per_day,
            playback_speed=playback_speed,
            rest_days=rest_days,
            revision_buffer_days=rev_buffer,
            schedule_strategy=strategy,
        )

    # Compute diff between old and new
    old_dates = [a.scheduled_date for a in old_allocs if not a.is_skipped]
    old_proj = max(old_dates) if old_dates else None
    new_allocs = sched_res["allocations"]
    new_proj = sched_res["projected_finish_date"]

    diff = compute_schedule_diff(
        old_allocations=old_allocs,
        new_allocations=new_allocs,
        old_target_date=course["target_date"],
        new_target_date=target_date_str,
        old_projected=old_proj,
        new_projected=new_proj,
        dropped_count=dropped_count,
        deficit_minutes=deficit_minutes,
        deficit_message=deficit_message,
    )

    snapshot_id = save_snapshot(
        course_id=course_id,
        reason=f"replan_{req.mode}",
        allocations=[a.to_dict() for a in old_allocs],
        course_row=course,
        diff_summary=diff,
        db=db,
    )

    # Update course settings
    db.execute(
        """
        UPDATE courses SET
            minutes_per_day = ?,
            playback_speed = ?,
            rest_days = ?,
            target_date = ?,
            revision_buffer_days = ?,
            schedule_strategy = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """,
        (minutes_per_day, playback_speed, json.dumps(rest_days), target_date_str, rev_buffer, strategy, course_id),
    )

    # Overwrite allocations with new plan
    db.execute("DELETE FROM schedule_allocations WHERE course_id = ?;", (course_id,))
    for a in new_allocs:
        db.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                a.id,
                course_id,
                a.lesson_id,
                a.scheduled_date,
                a.split_index,
                a.split_count,
                a.allocated_start_sec,
                a.allocated_end_sec,
                a.effective_minutes,
                1 if a.is_completed else 0,
                1 if a.is_skipped else 0,
            ),
        )

    updated_sched = get_course_schedule(course_id, db)
    return ReplanResponse(
        success=True,
        snapshot_id=snapshot_id,
        diff=DiffSummary(**diff),
        schedule=updated_sched,
    )

@router.post("/undo", response_model=ScheduleResponse)
def undo_last_replan(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Restores the most recent schedule snapshot in one click."""
    snapshot = db.execute(
        "SELECT * FROM schedule_snapshots WHERE course_id = ? ORDER BY created_at DESC LIMIT 1;",
        (course_id,),
    ).fetchone()

    if not snapshot:
        raise HTTPException(status_code=400, detail="No previous schedule snapshot to undo.")

    state = json.loads(snapshot["snapshot_state_json"])
    course_state = state.get("course", {})
    allocations_state = state.get("allocations", [])

    if course_state:
        db.execute(
            """
            UPDATE courses SET
                minutes_per_day = ?,
                playback_speed = ?,
                rest_days = ?,
                target_date = ?,
                revision_buffer_days = ?,
                schedule_strategy = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (
                course_state.get("minutes_per_day"),
                course_state.get("playback_speed"),
                json.dumps(course_state.get("rest_days")),
                course_state.get("target_date"),
                course_state.get("revision_buffer_days"),
                course_state.get("schedule_strategy", "paced"),
                course_id,
            ),
        )

    db.execute("DELETE FROM schedule_allocations WHERE course_id = ?;", (course_id,))
    for a in allocations_state:
        db.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                a["id"],
                course_id,
                a["lesson_id"],
                a["scheduled_date"],
                a.get("split_index", 0),
                a.get("split_count", 1),
                a["allocated_start_sec"],
                a["allocated_end_sec"],
                a["effective_minutes"],
                1 if a.get("is_completed") else 0,
                1 if a.get("is_skipped") else 0,
            ),
        )

    db.execute("DELETE FROM schedule_snapshots WHERE id = ?;", (snapshot["id"],))
    logger.info(f"[Schedule] Restored snapshot {snapshot['id']} for course {course_id}")

    return get_course_schedule(course_id, db)

def save_snapshot(
    course_id: str,
    reason: str,
    allocations: List[Dict[str, Any]],
    course_row: sqlite3.Row,
    diff_summary: Dict[str, Any],
    db: sqlite3.Connection,
) -> str:
    snapshot_id = str(uuid.uuid4())
    strategy = course_row["schedule_strategy"] if "schedule_strategy" in course_row.keys() else "paced"
    snapshot_payload = {
        "course": {
            "minutes_per_day": course_row["minutes_per_day"],
            "playback_speed": course_row["playback_speed"],
            "rest_days": json.loads(course_row["rest_days"]),
            "target_date": course_row["target_date"],
            "revision_buffer_days": course_row["revision_buffer_days"],
            "schedule_strategy": strategy,
        },
        "allocations": allocations,
    }

    db.execute(
        """
        INSERT INTO schedule_snapshots (id, course_id, reason, diff_summary_json, snapshot_state_json)
        VALUES (?, ?, ?, ?, ?);
        """,
        (snapshot_id, course_id, reason, json.dumps(diff_summary), json.dumps(snapshot_payload)),
    )
    return snapshot_id
