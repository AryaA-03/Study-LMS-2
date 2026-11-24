"""Smart Subtitle-First Semantic Partitioning & Auto-Build Service.

Upgrades any long marathon video (including already-imported courses that were
split into fixed `[MM:SS - MM:SS]` slices) by:
  1. Fetching full-video subtitles once (captions-first with en/en-IN/hi support + disk cache).
  2. Running subtitle-driven semantic topic partitioning (`partition_video(..., transcript_data=...)`)
     so each ~10-15 min clip has a real topic title and boundary from the transcript.
  3. Clustering playlist videos into structured Topic Groups (`cluster_course_topics`).
  4. Deterministically regenerating the schedule (preserving completed lessons).
  5. Enqueueing background auto-generation of Notes, Quizzes, and FSRS Flashcards via `JobWorker`.
"""

import logging
import re
import sqlite3
import uuid
from typing import Any, Dict, List

from backend.infra.job_queue import enqueue_job
from backend.services.concept_partitioner import partition_video
from backend.services.topic_grouper import cluster_course_topics
from backend.services.transcription import fetch_youtube_captions

logger = logging.getLogger("learn_lms.smart_prepare")

_FIXED_SLICE_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\s*[-–—]\s*\d{1,2}:\d{2}(?::\d{2})?\]\s*$")


def course_needs_semantic_repartition(db: sqlite3.Connection, course_id: str) -> List[str]:
    """Return source_ids of long single videos currently stuck in fixed [MM:SS - MM:SS] slices."""
    rows = db.execute(
        """
        SELECT source_id, title, video_id, start_sec, end_sec, is_excluded, status
        FROM lessons
        WHERE course_id = ? AND source_id IS NOT NULL
        ORDER BY order_index ASC;
        """,
        (course_id,),
    ).fetchall()

    by_source: Dict[str, List[sqlite3.Row]] = {}
    for r in rows:
        by_source.setdefault(r["source_id"], []).append(r)

    candidates: List[str] = []
    for sid, items in by_source.items():
        if len(items) < 2:
            continue
        unique_vids = {i["video_id"] for i in items if i["video_id"]}
        if len(unique_vids) != 1:
            continue
        fixed_hits = sum(1 for i in items if _FIXED_SLICE_RE.search(i["title"] or ""))
        if fixed_hits >= max(2, len(items) // 2):
            candidates.append(sid)
    return candidates


async def smart_prepare_course(db: sqlite3.Connection, course_id: str, force_repartition: bool = False) -> Dict[str, Any]:
    """Upgrade fixed-slice long videos using subtitles, cluster playlist topics, repack schedule, and enqueue background bundles."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise ValueError("Course not found")

    repartitioned_sources = 0
    new_topics_count = 0

    # 1. Identify single-video sources that have fixed [MM:SS - MM:SS] slices
    target_sids = course_needs_semantic_repartition(db, course_id)
    if force_repartition:
        all_vid_sources = db.execute(
            "SELECT id FROM sources WHERE course_id = ? AND source_type = 'youtube_video';",
            (course_id,),
        ).fetchall()
        for s in all_vid_sources:
            if s["id"] not in target_sids:
                target_sids.append(s["id"])

    for sid in target_sids:
        src = db.execute("SELECT * FROM sources WHERE id = ? AND course_id = ?;", (sid, course_id)).fetchone()
        if not src:
            continue
        first_les = db.execute(
            "SELECT video_id, video_url, MAX(end_sec) as max_end FROM lessons WHERE source_id = ? AND course_id = ?;",
            (sid, course_id),
        ).fetchone()
        vid_id = (first_les["video_id"] if first_les else None) or src["external_id"] or ""
        vid_url = (first_les["video_url"] if first_les else None) or src["url"] or ""
        total_dur = int((first_les["max_end"] if first_les and first_les["max_end"] else 0) or 3600)

        if not (vid_id or vid_url):
            continue

        # Fetch full-video subtitles once
        transcript_chunks = await fetch_youtube_captions(vid_id or vid_url, start_sec=0, end_sec=total_dur + 600)
        if not transcript_chunks:
            logger.info(f"[SmartPrepare] No captions available for {vid_id or vid_url}; skipping repartition.")
            continue

        video_meta = {
            "id": vid_id,
            "source_id": sid,
            "title": src["title"] or "Lecture",
            "url": vid_url,
            "duration": total_dur,
        }
        clips = partition_video(video_meta, transcript_data=transcript_chunks, mode="auto", db_conn=db)
        if not clips:
            continue

        # Replace old fixed-slice uncompleted lessons for this source with semantic topic clips
        old_rows = db.execute(
            "SELECT id FROM lessons WHERE source_id = ? AND course_id = ? AND COALESCE(status, 'not_started') != 'completed';",
            (sid, course_id),
        ).fetchall()
        old_ids = [r["id"] for r in old_rows]
        if old_ids:
            ph = ",".join(["?"] * len(old_ids))
            db.execute(f"DELETE FROM chunks WHERE lesson_id IN ({ph});", old_ids)
            db.execute(
                f"DELETE FROM schedule_allocations WHERE lesson_id IN ({ph}) AND COALESCE(is_completed, 0) = 0;",
                old_ids,
            )
            db.execute(f"DELETE FROM concept_clips WHERE id IN ({ph});", old_ids)
            db.execute(f"DELETE FROM lessons WHERE id IN ({ph});", old_ids)

        for idx, clip in enumerate(clips):
            lid = clip.get("id") or str(uuid.uuid4())
            prio = clip.get("priority_tag") or clip.get("priority") or "core"
            c_start = int(clip.get("start_sec", 0))
            c_end = int(clip.get("end_sec", c_start + 600))
            c_dur = max(60, c_end - c_start)
            db.execute(
                """
                INSERT INTO lessons (
                    id, course_id, source_id, title, summary, video_id, video_url,
                    start_sec, end_sec, raw_duration_sec, priority, priority_tag,
                    status, order_index, chapter_title, is_excluded, has_transcript, transcription_status
                ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, 'not_started', ?, ?, 0, 1, 'completed');
                """,
                (
                    lid, course_id, sid, clip["title"], vid_id, vid_url,
                    c_start, c_end, c_dur, prio, prio, idx, clip.get("chapter_title") or src["title"] or "",
                ),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO concept_clips (
                    id, course_id, source_id, order_index, title, start_sec, end_sec, raw_duration_sec, priority_tag, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started');
                """,
                (lid, course_id, sid, idx, clip["title"], c_start, c_end, c_dur, prio),
            )
            # Store sliced transcript chunks directly for each new semantic clip so Notes/Quiz/Cards are instant!
            clip_chunks = [
                ch for ch in transcript_chunks
                if int(ch.get("start_sec", 0)) >= c_start and int(ch.get("start_sec", 0)) < c_end
            ]
            for c_idx, ch in enumerate(clip_chunks):
                ch_id = f"chk_{uuid.uuid4().hex[:10]}"
                db.execute(
                    """
                    INSERT INTO chunks (id, course_id, source_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ch_id, course_id, sid, lid, c_idx,
                        int(ch.get("token_count") or len((ch.get("content") or "").split())),
                        int(ch.get("start_sec", c_start)),
                        int(ch.get("end_sec", c_end)),
                        ch.get("content", ""),
                    ),
                )
        db.commit()
        repartitioned_sources += 1
        new_topics_count += len(clips)

    # 2. Cluster playlist videos into structured topics only when course has multiple distinct videos
    distinct_vids_row = db.execute(
        "SELECT COUNT(DISTINCT video_id) FROM lessons WHERE course_id = ? AND video_id IS NOT NULL AND video_id != '';",
        (course_id,),
    ).fetchone()
    distinct_vids = distinct_vids_row[0] if distinct_vids_row else 0
    if distinct_vids > 1:
        cluster_res = cluster_course_topics(db, course_id)
    else:
        cluster_res = {"clusters_created": 0, "skipped": "single_video_semantic_chapters"}

    # 3. Regenerate schedule deterministically if repartitioned
    if repartitioned_sources > 0:
        from backend.routers.schedule import generate_course_schedule
        try:
            generate_course_schedule(course_id, db)
        except Exception as se:
            logger.warning(f"[SmartPrepare] Schedule regenerate note: {se}")

    # 4. Enqueue background study-bundle generation (notes + quizzes + FSRS flashcards) if not already queued
    existing_job = db.execute(
        "SELECT id FROM jobs WHERE course_id = ? AND job_type = 'study_bundle_remaining' AND status IN ('queued', 'running') LIMIT 1;",
        (course_id,),
    ).fetchone()
    if existing_job:
        job_id = existing_job["id"]
    else:
        job_id = enqueue_job(db, "study_bundle_remaining", course_id=course_id, payload={"course_id": course_id})

    return {
        "course_id": course_id,
        "repartitioned_sources": repartitioned_sources,
        "new_semantic_clips": new_topics_count,
        "topics_clustered": cluster_res.get("topics_created", 0),
        "background_job_id": job_id,
    }
