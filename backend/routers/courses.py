"""Course and source management router."""

import uuid
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.database import get_db
from backend.models.schemas import (
    CourseCreateRequest,
    CourseUpdateRequest,
    CourseResponse,
    SourceImportRequest,
    SourceApprovalRequest,
    SourceResponse,
    LessonResponse,
    CandidateDiscoveryResponse,
    LessonFilterRequest,
)
from backend.services.youtube import (
    discover_candidates,
    extract_metadata,
    split_video_into_lessons,
)
from backend.scheduler.engine import calculate_effective_minutes, get_study_dates, is_rest_day, default_clock

logger = logging.getLogger("learn_lms.courses")
router = APIRouter(prefix="/api/courses", tags=["courses"])

@router.post("", response_model=CourseResponse)
def create_course(
    req: CourseCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course_id = str(uuid.uuid4())
    rest_days_json = json.dumps(req.rest_days)
    strategy = req.schedule_strategy or "paced"
    logger.info(f"[Courses] Creating new course '{req.title}' (Strategy: {strategy}, Target: {req.target_date})")

    db.execute(
        """
        INSERT INTO courses (
            id, title, goal_query, source_preferences, target_date,
            minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            course_id,
            req.title,
            req.goal_query,
            req.source_preferences or "",
            req.target_date,
            req.minutes_per_day,
            req.playback_speed,
            rest_days_json,
            req.revision_buffer_days,
            strategy,
        ),
    )
    return get_course(course_id, db)

@router.get("", response_model=List[CourseResponse])
def list_courses(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM courses ORDER BY created_at DESC;").fetchall()
    results = []
    for row in rows:
        results.append(compute_course_stats(row, db))
    return results

@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    return compute_course_stats(row, db)

def compute_course_stats(course_row: sqlite3.Row, db: sqlite3.Connection) -> CourseResponse:
    cid = course_row["id"]
    alloc_rows = db.execute(
        "SELECT * FROM schedule_allocations WHERE course_id = ?;", (cid,)
    ).fetchall()

    total_effective = 0.0
    completed_effective = 0.0
    for a in alloc_rows:
        if not a["is_skipped"]:
            total_effective += a["effective_minutes"]
            if a["is_completed"]:
                completed_effective += a["effective_minutes"]

    remaining_effective = max(0.0, total_effective - completed_effective)
    pct = round((completed_effective / total_effective * 100.0), 1) if total_effective > 0 else 0.0

    # Projected finish date from active allocations
    active_dates = [
        a["scheduled_date"] for a in alloc_rows if not a["is_skipped"]
    ]
    projected = max(active_dates) if active_dates else None

    # Check if behind schedule
    from datetime import datetime, timedelta
    is_behind = False
    if projected and course_row["target_date"]:
        try:
            proj_d = datetime.strptime(projected, "%Y-%m-%d").date()
            targ_d = datetime.strptime(course_row["target_date"], "%Y-%m-%d").date()
            eff_deadline = targ_d - timedelta(days=course_row["revision_buffer_days"])
            is_behind = proj_d > eff_deadline
        except Exception:
            pass

    # Compute effective daily target minutes
    strategy = course_row["schedule_strategy"] if "schedule_strategy" in course_row.keys() else "paced"
    daily_target = float(course_row["minutes_per_day"])
    if strategy == "paced" and course_row["target_date"]:
        try:
            today = default_clock()
            targ_d = datetime.strptime(course_row["target_date"], "%Y-%m-%d").date()
            eff_deadline = targ_d - timedelta(days=course_row["revision_buffer_days"])
            rest_days = json.loads(course_row["rest_days"])
            study_dates, _, _ = get_study_dates(today, eff_deadline, rest_days, revision_buffer_days=0)
            if len(study_dates) > 0 and remaining_effective > 0:
                daily_target = round(remaining_effective / len(study_dates), 1)
        except Exception:
            pass

    return CourseResponse(
        id=course_row["id"],
        title=course_row["title"],
        goal_query=course_row["goal_query"],
        source_preferences=course_row["source_preferences"] or "",
        target_date=course_row["target_date"],
        minutes_per_day=course_row["minutes_per_day"],
        playback_speed=course_row["playback_speed"],
        rest_days=json.loads(course_row["rest_days"]),
        revision_buffer_days=course_row["revision_buffer_days"],
        schedule_strategy=strategy,
        status=course_row["status"],
        total_effective_minutes=round(total_effective, 1),
        completed_effective_minutes=round(completed_effective, 1),
        remaining_effective_minutes=round(remaining_effective, 1),
        completion_percentage=pct,
        projected_finish_date=projected,
        is_behind_schedule=is_behind,
        effective_daily_target_minutes=daily_target,
        created_at=str(course_row["created_at"]),
    )

@router.post("/{course_id}/discover", response_model=CandidateDiscoveryResponse)
def discover_sources(
    course_id: str,
    query: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    search_query = query or course["goal_query"]
    if course["source_preferences"]:
        search_query += f" {course['source_preferences']}"

    logger.info(f"[Courses] Autonomous discovery triggered for course {course_id} (Query: '{search_query}')")

    cookie_row = db.execute("SELECT value FROM system_settings WHERE key = 'cookies_browser';").fetchone()
    cookies_browser = cookie_row["value"] if cookie_row else None

    discovery = discover_candidates(search_query, max_videos=5, max_playlists=5, cookies_browser=cookies_browser)

    # Store discovered candidates into sources table as unapproved
    for v in discovery["candidate_videos"]:
        sid = str(uuid.uuid4())
        meta_json = json.dumps(v)
        existing = db.execute(
            "SELECT id FROM sources WHERE course_id = ? AND external_id = ?;",
            (course_id, v["id"]),
        ).fetchone()
        if not existing:
            db.execute(
                """
                INSERT INTO sources (id, course_id, source_type, title, url, external_id, metadata_json, is_approved)
                VALUES (?, ?, 'youtube_video', ?, ?, ?, ?, 0);
                """,
                (sid, course_id, v["title"], v["url"], v["id"], meta_json),
            )
            v["source_id"] = sid
        else:
            v["source_id"] = existing["id"]

    for pl in discovery["candidate_playlists"]:
        sid = str(uuid.uuid4())
        meta_json = json.dumps(pl)
        existing = db.execute(
            "SELECT id FROM sources WHERE course_id = ? AND external_id = ?;",
            (course_id, pl["id"]),
        ).fetchone()
        if not existing:
            db.execute(
                """
                INSERT INTO sources (id, course_id, source_type, title, url, external_id, metadata_json, is_approved)
                VALUES (?, ?, 'youtube_playlist', ?, ?, ?, ?, 0);
                """,
                (sid, course_id, pl["title"], pl["url"], pl["id"], meta_json),
            )
            pl["source_id"] = sid
        else:
            pl["source_id"] = existing["id"]

    return CandidateDiscoveryResponse(
        candidate_videos=discovery["candidate_videos"],
        candidate_playlists=discovery["candidate_playlists"],
    )

@router.post("/{course_id}/sources/import", response_model=SourceResponse)
def import_source(
    course_id: str,
    req: SourceImportRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    logger.info(f"[Courses] Importing manual URL: {req.url} into course {course_id}")
    cookie_row = db.execute("SELECT value FROM system_settings WHERE key = 'cookies_browser';").fetchone()
    cookies_browser = cookie_row["value"] if cookie_row else None

    try:
        meta = extract_metadata(req.url, cookies_browser=cookies_browser)
    except Exception as e:
        logger.error(f"[Courses] Metadata extraction failed for {req.url}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch metadata from URL: {str(e)}")

    source_type = "youtube_playlist" if ("entries" in meta or "playlist" in req.url.lower()) else "youtube_video"
    source_id = str(uuid.uuid4())
    title = meta.get("title", "Imported Source")
    ext_id = meta.get("id")
    meta_json = json.dumps({
        "duration": meta.get("duration", 0),
        "uploader": meta.get("uploader"),
        "channel": meta.get("channel"),
        "webpage_url": meta.get("webpage_url") or req.url,
    })

    db.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, metadata_json, is_approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (source_id, course_id, source_type, title, req.url, ext_id, meta_json, 1 if req.is_approved else 0),
    )

    if req.is_approved:
        created_ids = create_lessons_from_meta(course_id, source_id, meta, db)
        logger.info(f"[Courses] Created {len(created_ids)} lessons from approved source '{title}'")

    return get_source_by_id(source_id, db)

def create_lessons_from_meta(
    course_id: str,
    source_id: str,
    meta: Dict[str, Any],
    db: sqlite3.Connection,
) -> List[str]:
    created_lesson_ids = []
    # If playlist with entries
    if "entries" in meta and meta["entries"]:
        entries = meta["entries"]
        for idx, entry in enumerate(entries):
            if not entry:
                continue
            lessons = split_video_into_lessons(entry)
            for l in lessons:
                lid = str(uuid.uuid4())
                # Auto-detect if title sounds like an example or exercise
                t_lower = l["title"].lower()
                is_example = any(kw in t_lower for kw in ["example", "problem", "question", "gate", "exercise", "practice"])
                priority = "deep-dive" if is_example else l.get("priority", "core")

                db.execute(
                    """
                    INSERT INTO lessons (
                        id, course_id, source_id, title, summary, video_id, video_url,
                        start_sec, end_sec, raw_duration_sec, priority, order_index, chapter_title, is_excluded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                    """,
                    (
                        lid,
                        course_id,
                        source_id,
                        l["title"],
                        "",
                        l.get("video_id"),
                        l.get("video_url"),
                        l["start_sec"],
                        l["end_sec"],
                        l["raw_duration_sec"],
                        priority,
                        len(created_lesson_ids),
                        l.get("chapter_title", ""),
                    ),
                )
                created_lesson_ids.append(lid)
    else:
        # Single video
        lessons = split_video_into_lessons(meta)
        for l in lessons:
            lid = str(uuid.uuid4())
            t_lower = l["title"].lower()
            is_example = any(kw in t_lower for kw in ["example", "problem", "question", "gate", "exercise", "practice"])
            priority = "deep-dive" if is_example else l.get("priority", "core")

            db.execute(
                """
                INSERT INTO lessons (
                    id, course_id, source_id, title, summary, video_id, video_url,
                    start_sec, end_sec, raw_duration_sec, priority, order_index, chapter_title, is_excluded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                """,
                (
                    lid,
                    course_id,
                    source_id,
                    l["title"],
                    "",
                    l.get("video_id"),
                    l.get("video_url"),
                    l["start_sec"],
                    l["end_sec"],
                    l["raw_duration_sec"],
                    priority,
                    len(created_lesson_ids),
                    l.get("chapter_title", ""),
                ),
            )
            created_lesson_ids.append(lid)

    return created_lesson_ids

@router.post("/{course_id}/sources/approve", response_model=List[SourceResponse])
def approve_sources(
    course_id: str,
    req: SourceApprovalRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    cookie_row = db.execute("SELECT value FROM system_settings WHERE key = 'cookies_browser';").fetchone()
    cookies_browser = cookie_row["value"] if cookie_row else None

    # Handle rejections
    for sid in req.source_ids_to_reject:
        db.execute("DELETE FROM sources WHERE id = ? AND course_id = ?;", (sid, course_id))

    approved_sources = []
    for sid in req.source_ids_to_approve:
        s_row = db.execute("SELECT * FROM sources WHERE id = ? AND course_id = ?;", (sid, course_id)).fetchone()
        if not s_row:
            continue

        db.execute("UPDATE sources SET is_approved = 1 WHERE id = ?;", (sid,))

        existing_lessons = db.execute("SELECT count(*) as c FROM lessons WHERE source_id = ?;", (sid,)).fetchone()
        if existing_lessons["c"] == 0 and s_row["url"]:
            try:
                meta = extract_metadata(s_row["url"], cookies_browser=cookies_browser)
                create_lessons_from_meta(course_id, sid, meta, db)
            except Exception as e:
                logger.error(f"[Courses] Fallback placeholder created for {s_row['url']}: {e}")
                lid = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO lessons (
                        id, course_id, source_id, title, summary, video_id, video_url,
                        start_sec, end_sec, raw_duration_sec, priority, order_index, is_excluded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 900, 900, 'core', 0, 0);
                    """,
                    (lid, course_id, sid, s_row["title"], "", s_row["external_id"], s_row["url"]),
                )

        approved_sources.append(get_source_by_id(sid, db))

    return approved_sources

@router.post("/{course_id}/lessons/filter", response_model=List[LessonResponse])
def filter_course_lessons(
    course_id: str,
    req: LessonFilterRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Smart filtering to include/exclude question & example videos or specific lessons."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # If include_examples is explicitly given
    if req.include_examples is not None:
        kw_patterns = ["%example%", "%problem%", "%question%", "%exercise%", "%practice%"]
        where_clause = " OR ".join(["LOWER(title) LIKE ?" for _ in kw_patterns])
        exclude_val = 0 if req.include_examples else 1
        db.execute(
            f"UPDATE lessons SET is_excluded = ? WHERE course_id = ? AND ({where_clause});",
            [exclude_val, course_id] + kw_patterns,
        )
        logger.info(f"[Courses] Filtered example videos in course {course_id} (include_examples={req.include_examples})")

    if req.lesson_ids_to_include:
        placeholders = ",".join("?" * len(req.lesson_ids_to_include))
        db.execute(
            f"UPDATE lessons SET is_excluded = 0 WHERE course_id = ? AND id IN ({placeholders});",
            [course_id] + req.lesson_ids_to_include,
        )

    if req.lesson_ids_to_exclude:
        placeholders = ",".join("?" * len(req.lesson_ids_to_exclude))
        db.execute(
            f"UPDATE lessons SET is_excluded = 1 WHERE course_id = ? AND id IN ({placeholders});",
            [course_id] + req.lesson_ids_to_exclude,
        )

    return list_lessons(course_id, db)

@router.post("/{course_id}/lessons/{lesson_id}/toggle-exclude", response_model=LessonResponse)
def toggle_lesson_exclusion(
    course_id: str,
    lesson_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute("SELECT * FROM lessons WHERE id = ? AND course_id = ?;", (lesson_id, course_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")

    new_val = 0 if row["is_excluded"] else 1
    db.execute("UPDATE lessons SET is_excluded = ? WHERE id = ?;", (new_val, lesson_id))
    logger.info(f"[Courses] Toggled lesson {lesson_id} exclusion: is_excluded={new_val}")

    updated = db.execute("SELECT * FROM lessons WHERE id = ?;", (lesson_id,)).fetchone()
    return LessonResponse(
        id=updated["id"],
        course_id=updated["course_id"],
        source_id=updated["source_id"],
        title=updated["title"],
        summary=updated["summary"] or "",
        video_id=updated["video_id"],
        video_url=updated["video_url"],
        start_sec=updated["start_sec"],
        end_sec=updated["end_sec"],
        raw_duration_sec=updated["raw_duration_sec"],
        priority=updated["priority"],
        order_index=updated["order_index"],
        chapter_title=updated["chapter_title"],
        is_tested_out=bool(updated["is_tested_out"]),
        is_excluded=bool(updated["is_excluded"]),
    )

@router.get("/{course_id}/sources", response_model=List[SourceResponse])
def list_sources(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM sources WHERE course_id = ? ORDER BY created_at ASC;", (course_id,)
    ).fetchall()
    return [
        SourceResponse(
            id=r["id"],
            course_id=r["course_id"],
            source_type=r["source_type"],
            title=r["title"],
            url=r["url"],
            external_id=r["external_id"],
            metadata=json.loads(r["metadata_json"] or "{}"),
            is_approved=bool(r["is_approved"]),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]

@router.get("/{course_id}/lessons", response_model=List[LessonResponse])
def list_lessons(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC;", (course_id,)
    ).fetchall()
    return [
        LessonResponse(
            id=r["id"],
            course_id=r["course_id"],
            source_id=r["source_id"],
            title=r["title"],
            summary=r["summary"] or "",
            video_id=r["video_id"],
            video_url=r["video_url"],
            start_sec=r["start_sec"],
            end_sec=r["end_sec"],
            raw_duration_sec=r["raw_duration_sec"],
            priority=r["priority"],
            order_index=r["order_index"],
            chapter_title=r["chapter_title"],
            is_tested_out=bool(r["is_tested_out"]),
            is_excluded=bool(r["is_excluded"]),
        )
        for r in rows
    ]

def get_source_by_id(source_id: str, db: sqlite3.Connection) -> SourceResponse:
    r = db.execute("SELECT * FROM sources WHERE id = ?;", (source_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceResponse(
        id=r["id"],
        course_id=r["course_id"],
        source_type=r["source_type"],
        title=r["title"],
        url=r["url"],
        external_id=r["external_id"],
        metadata=json.loads(r["metadata_json"] or "{}"),
        is_approved=bool(r["is_approved"]),
        created_at=str(r["created_at"]),
    )
