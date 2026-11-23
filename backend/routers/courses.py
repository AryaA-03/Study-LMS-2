from backend.infra.net_guard import validate_youtube_url_or_id
"""Course and source management router."""

import uuid
import json
import sqlite3
import logging
import contextlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, BackgroundTasks
from backend.database import get_db, get_db_context
from backend.models.schemas import (
    CourseCreateRequest,
    CourseUpdateRequest,
    CourseResponse,
    SourceImportRequest,
    SourceApprovalRequest,
    SourceResponse,
    LessonResponse,
    LessonUpdateRequest,
    CandidateDiscoveryResponse,
    LessonFilterRequest,
    ManualTranscriptRequest,
    SyllabusMatchRequest,
    SyllabusMatchResponse,
    SyllabusApplyRequest,
    SyllabusApplyResponse,
    SyllabusInfoResponse,
)
from backend.services.youtube import (
    discover_candidates,
    extract_metadata,
    split_video_into_lessons,
)
from backend.services.concept_partitioner import partition_video
from backend.services.study_bundle import generate_initial_concept_bundles
from backend.scheduler.engine import calculate_effective_minutes, get_study_dates, is_rest_day, default_clock, generate_schedule
from backend.services.notes import get_or_generate_lesson_notes
from backend.services.syllabus_matcher import match_syllabus_to_course

logger = logging.getLogger("learn_lms.courses")
router = APIRouter(prefix="/api/courses", tags=["courses"])

@contextlib.contextmanager
def _get_background_db(db: Optional[sqlite3.Connection] = None):
    """Context manager providing an active SQLite connection for background tasks.
    
    Uses dependency_overrides if set (for tests), otherwise opens a fresh
    connection via get_db_context.
    """
    if db is not None:
        yield db
        return

    import sys
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

async def pregenerate_initial_notes(course_id: str, db: Optional[sqlite3.Connection] = None) -> None:
    """Pre-generates structured notes for the first 3 lessons in order (by order_index ASC)
    of that course, skipping lessons that already have generated notes.
    """
    logger.info(f"[Courses] Background note pre-warming triggered for course {course_id}")
    try:
        with _get_background_db(db) as conn:
            rows = conn.execute(
                """
                SELECT id, title FROM lessons
                WHERE course_id = ?
                ORDER BY order_index ASC
                LIMIT 3;
                """,
                (course_id,),
            ).fetchall()

            for r in rows:
                lesson_id = r["id"]
                lesson_title = r["title"]
                try:
                    existing_note = conn.execute(
                        """
                        SELECT id FROM notes
                        WHERE lesson_id = ? AND is_generated = 1 AND content_markdown IS NOT NULL AND content_markdown != '';
                        """,
                        (lesson_id,),
                    ).fetchone()

                    if not existing_note:
                        logger.info(f"[Courses] Pre-generating initial notes for lesson {lesson_id} ({lesson_title})")
                        await get_or_generate_lesson_notes(conn, course_id, lesson_id, force_regenerate=False)
                    else:
                        logger.info(f"[Courses] Notes already exist for lesson {lesson_id}, skipping pre-generation")
                except Exception as inner_e:
                    logger.warning(f"[Courses] Could not pre-generate notes for lesson {lesson_id}: {inner_e}")
    except Exception as e:
        logger.error(f"[Courses] Background note pregeneration failed for course {course_id}: {e}", exc_info=True)


@router.post("", response_model=CourseResponse)
def create_course(
    req: CourseCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course_id = str(uuid.uuid4())
    rest_days_json = json.dumps(req.rest_days)
    strategy = req.schedule_strategy or "paced"
    logger.info(f"[Courses] Creating new course '{req.title}' (Strategy: {strategy}, Target: {req.target_date})")

    preferred_mins = req.preferred_daily_minutes or req.minutes_per_day or 60
    db.execute(
        """
        INSERT INTO courses (
            id, title, goal_query, source_preferences, target_date,
            minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy,
            num_study_days, preferred_daily_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
            req.num_study_days,
            preferred_mins,
        ),
    )
    return get_course(course_id, db)

@router.get("", response_model=List[CourseResponse])
def list_courses(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM courses ORDER BY created_at DESC;").fetchall()
    if not rows:
        return []

    # Batch query schedule allocations for all courses to avoid N+1 queries
    course_ids = [r["id"] for r in rows]
    allocs_by_course: Dict[str, List[sqlite3.Row]] = {cid: [] for cid in course_ids}
    batch_size = 500
    for i in range(0, len(course_ids), batch_size):
        batch = course_ids[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        alloc_batch = db.execute(
            f"SELECT * FROM schedule_allocations WHERE course_id IN ({placeholders});",
            batch,
        ).fetchall()
        for a in alloc_batch:
            allocs_by_course[a["course_id"]].append(a)

    results = []
    for row in rows:
        cid = row["id"]
        results.append(compute_course_stats(row, db, alloc_rows=allocs_by_course.get(cid, [])))
    return results

get_all_courses = list_courses  # backward-compat alias for tests that import this directly

@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    return compute_course_stats(row, db)

@router.patch("/{course_id}", response_model=CourseResponse)
@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: str,
    req: CourseUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    updates = []
    params = []
    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title)
    if req.target_date is not None:
        updates.append("target_date = ?")
        params.append(req.target_date)
    if req.minutes_per_day is not None:
        updates.append("minutes_per_day = ?")
        params.append(req.minutes_per_day)
    if req.playback_speed is not None:
        updates.append("playback_speed = ?")
        params.append(req.playback_speed)
    if req.rest_days is not None:
        updates.append("rest_days = ?")
        params.append(json.dumps(req.rest_days))
    if req.revision_buffer_days is not None:
        updates.append("revision_buffer_days = ?")
        params.append(req.revision_buffer_days)
    if req.schedule_strategy is not None:
        updates.append("schedule_strategy = ?")
        params.append(req.schedule_strategy)
    if req.num_study_days is not None:
        updates.append("num_study_days = ?")
        params.append(req.num_study_days)
    if req.preferred_daily_minutes is not None:
        updates.append("preferred_daily_minutes = ?")
        params.append(req.preferred_daily_minutes)

    if updates:
        params.append(course_id)
        db.execute(f"UPDATE courses SET {', '.join(updates)} WHERE id = ?;", params)
        db.commit()

    return get_course(course_id, db)

def compute_course_stats(
    course_row: sqlite3.Row,
    db: sqlite3.Connection,
    alloc_rows: Optional[List[sqlite3.Row]] = None,
) -> CourseResponse:
    cid = course_row["id"]
    if alloc_rows is None:
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
        num_study_days=course_row["num_study_days"] if "num_study_days" in course_row.keys() else None,
        preferred_daily_minutes=course_row["preferred_daily_minutes"] if "preferred_daily_minutes" in course_row.keys() else 60,
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
    background_tasks: BackgroundTasks,
    db: sqlite3.Connection = Depends(get_db),
):
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    logger.info(f"[Courses] Importing manual URL: {req.url} into course {course_id}")
    cookie_row = db.execute("SELECT value FROM system_settings WHERE key = 'cookies_browser';").fetchone()
    cookies_browser = cookie_row["value"] if cookie_row else None

    try:
        validate_youtube_url_or_id(req.url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        meta = extract_metadata(req.url, cookies_browser=cookies_browser)
        if not meta or not meta.get("id"):
            raise ValueError("Could not extract video or playlist information. URL may be unavailable, private, or invalid.")
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
        background_tasks.add_task(pregenerate_initial_notes, course_id)

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
            entry_copy = dict(entry)
            entry_copy["source_id"] = source_id
            clips = partition_video(entry_copy, transcript_data=None, mode="auto", db_conn=db)
            for l in clips:
                lid = l.get("id") or str(uuid.uuid4())
                priority_tag = l.get("priority_tag") or l.get("priority", "core")

                db.execute(
                    """
                    INSERT INTO lessons (
                        id, course_id, source_id, title, summary, video_id, video_url,
                        start_sec, end_sec, raw_duration_sec, priority, priority_tag, status, order_index, chapter_title, is_excluded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started', ?, ?, 0);
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
                        priority_tag,
                        priority_tag,
                        len(created_lesson_ids),
                        l.get("chapter_title", ""),
                    ),
                )
                db.execute(
                    """
                    INSERT OR REPLACE INTO concept_clips (
                        id, course_id, source_id, order_index, title, start_sec, end_sec, raw_duration_sec, priority_tag, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started');
                    """,
                    (
                        lid,
                        course_id,
                        source_id,
                        len(created_lesson_ids),
                        l["title"],
                        l["start_sec"],
                        l["end_sec"],
                        l["raw_duration_sec"],
                        priority_tag,
                    ),
                )
                created_lesson_ids.append(lid)
    else:
        # Single video
        meta_copy = dict(meta)
        meta_copy["source_id"] = source_id
        clips = partition_video(meta_copy, transcript_data=None, mode="auto", db_conn=db)
        for l in clips:
            lid = l.get("id") or str(uuid.uuid4())
            priority_tag = l.get("priority_tag") or l.get("priority", "core")

            db.execute(
                """
                INSERT INTO lessons (
                    id, course_id, source_id, title, summary, video_id, video_url,
                    start_sec, end_sec, raw_duration_sec, priority, priority_tag, status, order_index, chapter_title, is_excluded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started', ?, ?, 0);
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
                    priority_tag,
                    priority_tag,
                    len(created_lesson_ids),
                    l.get("chapter_title", ""),
                ),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO concept_clips (
                    id, course_id, source_id, order_index, title, start_sec, end_sec, raw_duration_sec, priority_tag, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started');
                """,
                (
                    lid,
                    course_id,
                    source_id,
                    len(created_lesson_ids),
                    l["title"],
                    l["start_sec"],
                    l["end_sec"],
                    l["raw_duration_sec"],
                    priority_tag,
                ),
            )
            created_lesson_ids.append(lid)

    return created_lesson_ids

@router.post("/{course_id}/sources/approve", response_model=List[SourceResponse])
@router.post("/{course_id}/sources/confirm", response_model=List[SourceResponse])
def approve_sources(
    course_id: str,
    req: SourceApprovalRequest,
    background_tasks: BackgroundTasks,
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
    db.commit()

    approved_sources = []
    for sid in req.source_ids_to_approve:
        s_row = db.execute("SELECT * FROM sources WHERE id = ? AND course_id = ?;", (sid, course_id)).fetchone()
        if not s_row:
            continue

        db.execute("UPDATE sources SET is_approved = 1 WHERE id = ?;", (sid,))
        db.commit()

        existing_lessons = db.execute("SELECT count(*) as c FROM lessons WHERE source_id = ?;", (sid,)).fetchone()
        if existing_lessons["c"] == 0 and s_row["url"]:
            try:
                meta = extract_metadata(s_row["url"], cookies_browser=cookies_browser)
                create_lessons_from_meta(course_id, sid, meta, db)
                db.commit()
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
                db.commit()

        approved_sources.append(get_source_by_id(sid, db))

    if req.source_ids_to_approve:
        background_tasks.add_task(generate_initial_concept_bundles, course_id)

    return approved_sources


@router.post("/{course_id}/lessons/filter", response_model=List[LessonResponse])
def filter_course_lessons(
    course_id: str,
    req: LessonFilterRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Smart filtering to include/exclude question & example videos, concepts, or specific lessons."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    kw_patterns = [
        "%example%", "%examples%",
        "%problem%", "%problems%",
        "%question%", "%questions%",
        "%exercise%", "%exercises%",
        "%practice%",
        "%project%", "%projects%",
        "%practical%", "%practicals%",
        "%application%", "%applications%",
        "%code%", "%coding%", "%implementation%",
        "%lab%", "%hands-on%", "%walkthrough%",
        "%solved%", "%solution%", "%solutions%",
        "%numerical%", "%numericals%",
        "%pyq%", "%gate%",
        "%demo%", "%demonstration%",
        "%assignment%",
    ]
    where_clause = " OR ".join(["LOWER(title) LIKE ?" for _ in kw_patterns])

    mode = req.filter_mode
    if mode is None and req.include_examples is not None:
        mode = "all" if req.include_examples is True else "concepts"

    if mode == "all":
        db.execute(
            "UPDATE lessons SET is_excluded = 0 WHERE course_id = ?;",
            (course_id,)
        )
        logger.info(f"[Courses] Filtered course {course_id} to 'all' (every video included)")
    elif mode == "concepts":
        c_concepts = db.execute(
            f"SELECT COUNT(*) FROM lessons WHERE course_id = ? AND NOT ({where_clause});",
            [course_id] + kw_patterns,
        ).fetchone()[0]
        if c_concepts == 0:
            raise HTTPException(status_code=400, detail="No theory or concept lessons found in this course.")
        # Include pure concepts/theory, exclude examples/applications
        db.execute(
            f"UPDATE lessons SET is_excluded = 0 WHERE course_id = ? AND NOT ({where_clause});",
            [course_id] + kw_patterns,
        )
        db.execute(
            f"UPDATE lessons SET is_excluded = 1 WHERE course_id = ? AND ({where_clause});",
            [course_id] + kw_patterns,
        )
        logger.info(f"[Courses] Filtered course {course_id} to 'concepts' only (examples/applications excluded)")
    elif mode == "examples":
        c_examples = db.execute(
            f"SELECT COUNT(*) FROM lessons WHERE course_id = ? AND ({where_clause});",
            [course_id] + kw_patterns,
        ).fetchone()[0]
        if c_examples == 0:
            raise HTTPException(status_code=400, detail="No practical examples or application lessons found in this course.")
        # Include examples/applications, exclude pure concepts/theory
        db.execute(
            f"UPDATE lessons SET is_excluded = 0 WHERE course_id = ? AND ({where_clause});",
            [course_id] + kw_patterns,
        )
        db.execute(
            f"UPDATE lessons SET is_excluded = 1 WHERE course_id = ? AND NOT ({where_clause});",
            [course_id] + kw_patterns,
        )
        logger.info(f"[Courses] Filtered course {course_id} to 'examples' only (theory/concepts excluded)")

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

# --- Syllabus Alignment Endpoints ---
@router.post("/{course_id}/syllabus/match", response_model=SyllabusMatchResponse)
def match_course_syllabus(
    course_id: str,
    req: SyllabusMatchRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Parses pasted syllabus text and automatically identifies matching course videos."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        match_data = match_syllabus_to_course(
            course_id=course_id,
            syllabus_text=req.syllabus_text,
            strictness=req.strictness or "balanced",
            db=db,
        )
        return SyllabusMatchResponse(**match_data)
    except Exception as e:
        logger.error(f"[Courses] Syllabus matching error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{course_id}/syllabus/apply", response_model=SyllabusApplyResponse)
def apply_syllabus_alignment(
    course_id: str,
    req: SyllabusApplyRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Applies the selected syllabus-matched lessons, excluding out-of-syllabus videos and reflowing schedule."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if not req.included_lesson_ids:
        raise HTTPException(status_code=400, detail="Cannot apply empty selection. At least 1 matching video must be selected.")

    # 1. Update lesson exclusion states
    placeholders = ",".join(["?"] * len(req.included_lesson_ids))
    db.execute(
        f"UPDATE lessons SET is_excluded = 0 WHERE course_id = ? AND id IN ({placeholders});",
        [course_id] + req.included_lesson_ids,
    )
    db.execute(
        f"UPDATE lessons SET is_excluded = 1 WHERE course_id = ? AND id NOT IN ({placeholders});",
        [course_id] + req.included_lesson_ids,
    )

    # 2. Persist syllabus text and alignment metadata
    meta = json.dumps({
        "matched_count": len(req.included_lesson_ids),
        "strictness": req.strictness,
        "applied_at": datetime.now().isoformat(),
    })
    try:
        db.execute(
            "UPDATE courses SET syllabus_text = ?, syllabus_metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
            (req.syllabus_text, meta, course_id),
        )
    except Exception as e:
        logger.warning(f"[Courses] Could not save syllabus text to course row: {e}")

    # 3. Auto-regenerate schedule
    schedule_reflowed = False
    if req.regenerate_schedule:
        try:
            active_lessons = db.execute(
                "SELECT * FROM lessons WHERE course_id = ? AND is_excluded = 0 ORDER BY order_index ASC;",
                (course_id,),
            ).fetchall()
            if active_lessons:
                lesson_dicts = [dict(l) for l in active_lessons]
                rest_days = json.loads(course["rest_days"]) if course["rest_days"] else []
                target_d = datetime.strptime(course["target_date"], "%Y-%m-%d").date()
                today = default_clock()
                strategy = course["schedule_strategy"] if "schedule_strategy" in course.keys() else "paced"

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
                db.execute("DELETE FROM schedule_allocations WHERE course_id = ?;", (course_id,))
                for a in sched_result["allocations"]:
                    db.execute(
                        """
                        INSERT INTO schedule_allocations (
                            id, course_id, lesson_id, scheduled_date, split_index, split_count,
                            allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0);
                        """,
                        (a.id, course_id, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes)
                    )
                schedule_reflowed = True
        except Exception as e:
            logger.warning(f"[Courses] Could not regenerate schedule during syllabus apply: {e}")

    inc_count = db.execute("SELECT COUNT(*) FROM lessons WHERE course_id = ? AND is_excluded = 0;", (course_id,)).fetchone()[0]
    exc_count = db.execute("SELECT COUNT(*) FROM lessons WHERE course_id = ? AND is_excluded = 1;", (course_id,)).fetchone()[0]

    return SyllabusApplyResponse(
        course_id=course_id,
        included_count=inc_count,
        excluded_count=exc_count,
        schedule_reflowed=schedule_reflowed,
        message=f"Syllabus successfully applied! {inc_count} videos matched & scheduled ({exc_count} out-of-syllabus videos excluded)."
    )

@router.get("/{course_id}/syllabus", response_model=SyllabusInfoResponse)
def get_course_syllabus(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Retrieves previously saved syllabus text and metadata for a course."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    meta = None
    if "syllabus_metadata" in course.keys() and course["syllabus_metadata"]:
        try:
            meta = json.loads(course["syllabus_metadata"])
        except Exception:
            pass

    return SyllabusInfoResponse(
        course_id=course_id,
        syllabus_text=course["syllabus_text"] if "syllabus_text" in course.keys() else None,
        syllabus_metadata=meta,
    )

@router.patch("/{course_id}/lessons/{lesson_id}", response_model=LessonResponse)
@router.put("/{course_id}/lessons/{lesson_id}", response_model=LessonResponse)
def update_lesson(
    course_id: str,
    lesson_id: str,
    req: LessonUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    lesson = db.execute(
        "SELECT * FROM lessons WHERE id = ? AND course_id = ?;", (lesson_id, course_id)
    ).fetchone()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    updates = []
    params = []
    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title)
    if req.summary is not None:
        updates.append("summary = ?")
        params.append(req.summary)
    if req.priority is not None:
        updates.append("priority = ?")
        params.append(req.priority)

    if updates:
        params.extend([lesson_id, course_id])
        db.execute(
            f"UPDATE lessons SET {', '.join(updates)} WHERE id = ? AND course_id = ?;",
            params,
        )
        db.commit()

    updated = db.execute(
        "SELECT * FROM lessons WHERE id = ? AND course_id = ?;", (lesson_id, course_id)
    ).fetchone()
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

@router.put("/{course_id}/lessons/{lesson_id}/notes")
def update_course_lesson_notes(
    course_id: str,
    lesson_id: str,
    payload: Dict[str, Any],
    db: sqlite3.Connection = Depends(get_db),
):
    """Updates user personal notes or full notes for a lesson under a course."""
    from backend.services.notes import save_personal_notes
    lesson = db.execute(
        "SELECT id FROM lessons WHERE id = ? AND course_id = ?;", (lesson_id, course_id)
    ).fetchone()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found in course")

    personal_text = payload.get("personal_notes")
    if personal_text is None:
        personal_text = payload.get("content_markdown") or payload.get("notes") or ""

    saved = save_personal_notes(db, course_id, lesson_id, personal_text)
    return {"success": saved, "course_id": course_id, "lesson_id": lesson_id}

@router.get("/{course_id}/sources", response_model=List[SourceResponse])
def list_sources(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM sources WHERE course_id = ? ORDER BY created_at ASC;", (course_id,)
    ).fetchall()
    res = []
    for r in rows:
        meta = json.loads(r["metadata_json"] or "{}")
        if "chunk_count" in r.keys() and r["chunk_count"] is not None:
            meta["chunk_count"] = r["chunk_count"]
        res.append(
            SourceResponse(
                id=r["id"],
                course_id=r["course_id"],
                source_type=r["source_type"],
                title=r["title"],
                url=r["url"],
                external_id=r["external_id"],
                metadata=meta,
                is_approved=bool(r["is_approved"]),
                created_at=str(r["created_at"]),
            )
        )
    return res

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
    meta = json.loads(r["metadata_json"] or "{}")
    if "chunk_count" in r.keys() and r["chunk_count"] is not None:
        meta["chunk_count"] = r["chunk_count"]
    return SourceResponse(
        id=r["id"],
        course_id=r["course_id"],
        source_type=r["source_type"],
        title=r["title"],
        url=r["url"],
        external_id=r["external_id"],
        metadata=meta,
        is_approved=bool(r["is_approved"]),
        created_at=str(r["created_at"]),
    )


@router.get("/{course_id}/export")
def export_course_bundle(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Exports full course study bundle (metadata, lessons, notes, flashcards, quizzes) as JSON."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    sources = [dict(r) for r in db.execute("SELECT * FROM sources WHERE course_id = ?;", (course_id,)).fetchall()]
    lessons = [dict(r) for r in db.execute("SELECT * FROM lessons WHERE course_id = ?;", (course_id,)).fetchall()]
    allocations = [dict(r) for r in db.execute("SELECT * FROM schedule_allocations WHERE course_id = ?;", (course_id,)).fetchall()]
    notes = [dict(r) for r in db.execute("SELECT * FROM notes WHERE course_id = ?;", (course_id,)).fetchall()]
    flashcards = [dict(r) for r in db.execute("SELECT * FROM flashcards WHERE course_id = ?;", (course_id,)).fetchall()]
    quizzes = [dict(r) for r in db.execute("SELECT * FROM quizzes WHERE course_id = ?;", (course_id,)).fetchall()]

    bundle = {
        "version": "1.0",
        "exported_at": default_clock().isoformat(),
        "course": dict(course),
        "sources": sources,
        "lessons": lessons,
        "schedule_allocations": allocations,
        "notes": notes,
        "flashcards": flashcards,
        "quizzes": quizzes,
    }
    return bundle


@router.get("/{course_id}/export-markdown")
def export_course_markdown(
    course_id: str,
    db: sqlite3.Connection = Depends(get_db),
):
    """Exports complete Subject Markdown Bundle containing all formatted notes, citations, and study state."""
    import re
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    lessons = [dict(r) for r in db.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC;", (course_id,)).fetchall()]
    notes = {r["lesson_id"]: dict(r) for r in db.execute("SELECT * FROM notes WHERE course_id = ?;", (course_id,)).fetchall()}
    sources = [dict(r) for r in db.execute("SELECT * FROM sources WHERE course_id = ?;", (course_id,)).fetchall()]

    md_lines = []
    md_lines.append(f"# {course['title']} • Subject Study Bundle")
    md_lines.append(f"\n> **Goal**: {course['goal_query']}  ")
    md_lines.append(f"> **Target Date**: {course['target_date']} | **Pacing**: {course['schedule_strategy']} | **Daily Budget**: {course['minutes_per_day']}m @ {course['playback_speed']}x\n")
    md_lines.append("## Table of Contents")
    for i, les in enumerate(lessons, 1):
        md_lines.append(f"{i}. [{les['title']}](#lesson-{les['id']})")

    md_lines.append("\n---\n")
    md_lines.append("## Course Sources")
    for s in sources:
        md_lines.append(f"- **{s['title']}** ({s['source_type']}) - {s.get('url') or 'Local / Attached'}")

    md_lines.append("\n---\n")
    md_lines.append("## Detailed Lesson Notes & Citations\n")
    for i, les in enumerate(lessons, 1):
        md_lines.append(f"### <a id='lesson-{les['id']}'></a>{i}. {les['title']}")
        raw_min = round(les['raw_duration_sec'] / 60, 1)
        md_lines.append(f"- **Duration**: ~{raw_min} min | **Priority**: `{les['priority']}`")
        if les.get('video_url'):
            md_lines.append(f"- **Stream Link**: [{les['video_url']}]({les['video_url']})")

        les_note = notes.get(les["id"])
        if les_note and les_note.get("content_markdown"):
            md_lines.append("\n#### Grounded Structured Notes & Timestamps")
            md_lines.append(les_note["content_markdown"])
        if les_note and les_note.get("personal_notes"):
            md_lines.append("\n#### Personal Notes")
            md_lines.append(les_note["personal_notes"])
        md_lines.append("\n---\n")

    md_content = "\n".join(md_lines)
    clean_title = re.sub(r"[^a-zA-Z0-9_-]", "_", course['title'])
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{clean_title}_notes_bundle.md"'}
    )


@router.post("/{course_id}/sources/manual-transcript")
def import_manual_transcript(
    course_id: str,
    req: ManualTranscriptRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Fallback manual transcript paste or local file import when YouTube URL is unavailable."""
    from datetime import datetime
    from backend.config import get_now
    from backend.scheduler.engine import generate_schedule

    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    source_id = str(uuid.uuid4())
    title = req.title or "Manual Source Material"
    db.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, metadata_json, is_approved)
        VALUES (?, ?, 'manual_text', ?, '', ?, 1);
        """,
        (source_id, course_id, title, json.dumps({"raw_chars": len(req.transcript_text)})),
    )

    lesson_id = str(uuid.uuid4())
    raw_dur = req.raw_duration_sec or max(600, len(req.transcript_text.split()) * 3)
    db.execute(
        """
        INSERT INTO lessons (id, course_id, source_id, title, summary, video_id, video_url, start_sec, end_sec, raw_duration_sec, priority, order_index)
        VALUES (?, ?, ?, ?, ?, '', '', 0, ?, ?, ?, (SELECT COALESCE(MAX(order_index) + 1, 0) FROM lessons WHERE course_id = ?));
        """,
        (lesson_id, course_id, source_id, title, f"Manual Transcript ({len(req.transcript_text)} chars)", raw_dur, raw_dur, req.priority, course_id),
    )

    # Chunk into FTS5 chunks
    from backend.services.qa_engine import chunk_text
    chunks = chunk_text(req.transcript_text, chunk_size=400, overlap=50)
    for idx, c in enumerate(chunks):
        cid = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (cid, course_id, source_id, lesson_id, idx, c, len(c.split())),
        )
        db.execute("INSERT INTO chunks_fts (id, course_id, lesson_id, content) VALUES (?, ?, ?, ?);", (cid, course_id, lesson_id, c))

    # Save note
    note_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO notes (id, course_id, lesson_id, content_markdown, is_generated)
        VALUES (?, ?, ?, ?, 1);
        """,
        (note_id, course_id, lesson_id, f"## {title}\n\n{req.transcript_text[:1200]}...\n\n_Manual Transcript Ingested Successfully._"),
    )

    # Reflow schedule
    rows = db.execute("SELECT * FROM lessons WHERE course_id = ? AND is_excluded = 0 ORDER BY order_index ASC;", (course_id,)).fetchall()
    lessons_list = [dict(r) for r in rows]
    sched = generate_schedule(
        course_id=course_id,
        lessons=lessons_list,
        start_date=get_now().date(),
        target_date=datetime.strptime(course["target_date"], "%Y-%m-%d").date(),
        minutes_per_day=course["minutes_per_day"],
        playback_speed=course["playback_speed"],
        rest_days=json.loads(course["rest_days"]),
        revision_buffer_days=course["revision_buffer_days"],
        schedule_strategy=course["schedule_strategy"],
    )
    db.execute("DELETE FROM schedule_allocations WHERE course_id = ?;", (course_id,))
    for a in sched["allocations"]:
        db.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0);
            """,
            (a.id, course_id, a.lesson_id, a.scheduled_date, a.split_index, a.split_count, a.allocated_start_sec, a.allocated_end_sec, a.effective_minutes),
        )
    db.commit()

    return {"success": True, "source_id": source_id, "lesson_id": lesson_id, "message": "Manual transcript ingested and schedule regenerated."}


@router.get("/{course_id}/sources/discover-web")
def discover_web_candidates(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Suggests curated web documentation and guides for the course topic with an approval step."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    query = f"{course['title']} {course['goal_query'] or ''}".lower()

    if "dbms" in query or "database" in query:
        candidates = [
            {"id": "web-dbms-1", "title": "GeeksforGeeks DBMS Complete Guide & Architecture", "url": "https://www.geeksforgeeks.org/introduction-of-dbms-database-management-system-set-1/", "site": "GeeksforGeeks", "summary": "Relational models, ACID properties, ER diagrams, normalization (1NF-BCNF)."},
            {"id": "web-dbms-2", "title": "Wikipedia: Database Management System Overview", "url": "https://en.wikipedia.org/wiki/Database", "site": "Wikipedia", "summary": "Formal definitions, transaction management, indexing, and SQL standards."},
            {"id": "web-dbms-3", "title": "PostgreSQL Official Documentation: Concurrency & Transactions", "url": "https://www.postgresql.org/docs/current/mvcc.html", "site": "PostgreSQL", "summary": "Transaction isolation, Multi-Version Concurrency Control (MVCC), and locking."},
        ]
    elif "toc" in query or "automata" in query or "computation" in query:
        candidates = [
            {"id": "web-toc-1", "title": "GeeksforGeeks Theory of Computation Guide", "url": "https://www.geeksforgeeks.org/theory-of-computation-automata-tutorials/", "site": "GeeksforGeeks", "summary": "DFA, NFA, Regular Expressions, Pumping Lemma, Turing Machines."},
            {"id": "web-toc-2", "title": "Wikipedia: Deterministic Finite Automaton", "url": "https://en.wikipedia.org/wiki/Deterministic_finite_automaton", "site": "Wikipedia", "summary": "Formal definition 5-tuple (Q, Sigma, delta, q0, F) and minimization."},
        ]
    else:
        candidates = [
            {"id": "web-gen-1", "title": f"Wikipedia: {course['title']}", "url": f"https://en.wikipedia.org/wiki/{course['title'].replace(' ', '_')}", "site": "Wikipedia", "summary": "Foundational overview, definitions, principles, and references."},
            {"id": "web-gen-2", "title": f"Study Notes Guide: {course['title']}", "url": f"https://www.geeksforgeeks.org/{course['title'].lower().replace(' ', '-')}/", "site": "GeeksforGeeks", "summary": "Exam-focused summary sheets and worked examples."},
        ]
    return {"candidates": candidates}



@router.delete("/{course_id}")
def delete_course(course_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Delete a course, cascading all DB child records and cleaning disk uploads/screenshots."""
    import shutil
    from backend.config import DATA_DIR

    row = db.execute("SELECT id FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    db.execute("DELETE FROM courses WHERE id = ?;", (course_id,))
    db.commit()
    for folder_name in ("uploads", "screenshots"):
        target = (DATA_DIR / folder_name / course_id).resolve()
        base = (DATA_DIR / folder_name).resolve()
        if target.is_relative_to(base) and target.exists():
            shutil.rmtree(target, ignore_errors=True)
    return {"success": True, "deleted_course_id": course_id}


@router.delete("/{course_id}/sources/{source_id}")
def delete_course_source(course_id: str, source_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Delete a single source from a course, cascading its lessons and chunks."""
    row = db.execute(
        "SELECT id FROM sources WHERE id = ? AND course_id = ?;",
        (source_id, course_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found in this course")
    db.execute("DELETE FROM sources WHERE id = ? AND course_id = ?;", (source_id, course_id))
    db.commit()
    return {"success": True, "deleted_source_id": source_id}
