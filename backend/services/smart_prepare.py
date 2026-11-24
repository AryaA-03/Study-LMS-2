"""Smart Subtitle-First Semantic Partitioning & Auto-Build Service.

Upgrades any long marathon video (including already-imported courses that were
split into fixed `[MM:SS - MM:SS]` or `— Part N` slices) by:
  1. Fetching full-video subtitles once (captions-first with en/en-IN/hi support + disk cache).
  2. Running async subtitle-driven semantic topic partitioning (`partition_video_async`)
     so each ~10-15 min clip has a real topic title and clean module grouping (`chapter_title`).
  3. Preserving completed/skipped progress by >= 60% time-range overlap (zero duplicate clips!).
  4. Clustering multi-video playlists into structured Topic Groups (`cluster_course_topics`).
  5. Deterministically regenerating the schedule and enqueueing background study bundles via `JobWorker`.
"""

import logging
import re
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.infra.job_queue import enqueue_job, update_job_progress
from backend.services.concept_partitioner import partition_video_async
from backend.services.topic_grouper import cluster_course_topics
from backend.services.transcription import fetch_youtube_captions

logger = logging.getLogger("learn_lms.smart_prepare")

_FIXED_SLICE_RE = re.compile(
    r"(?:\[\d{1,2}:\d{2}(?::\d{2})?\s*[-–—]\s*\d{1,2}:\d{2}(?::\d{2})?\]|(?:[-–—]\s*|\(\s*)Part\s+\d+\)?)\s*$",
    re.IGNORECASE,
)


def is_placeholder_lesson_title(title: str) -> bool:
    """Return True if a lesson title is still a fixed-slice or Part-N placeholder."""
    return bool(_FIXED_SLICE_RE.search((title or "").strip()))


def course_needs_semantic_repartition(db: sqlite3.Connection, course_id: str) -> List[str]:
    """Return source_ids of long single videos currently stuck in placeholder slices."""
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
        fixed_hits = sum(1 for i in items if is_placeholder_lesson_title(i["title"] or ""))
        if fixed_hits >= max(2, len(items) // 2):
            candidates.append(sid)
    return candidates


def _overlap_ratio(start_a: int, end_a: int, start_b: int, end_b: int) -> float:
    dur_a = max(1, end_a - start_a)
    ov = max(0, min(end_a, end_b) - max(start_a, start_b))
    return ov / dur_a


async def smart_prepare_course(
    db: sqlite3.Connection,
    course_id: str,
    force_repartition: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Upgrade placeholder-slice long videos using subtitles, preserve completion by overlap, repack schedule, and enqueue bundles."""
    course = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not course:
        raise ValueError("Course not found")

    repartitioned_sources = 0
    new_topics_count = 0

    target_sids = course_needs_semantic_repartition(db, course_id)
    if force_repartition:
        all_vid_sources = db.execute(
            "SELECT id FROM sources WHERE course_id = ? AND source_type = 'youtube_video';",
            (course_id,),
        ).fetchall()
        for s in all_vid_sources:
            if s["id"] not in target_sids:
                target_sids.append(s["id"])

    total_targets = max(1, len(target_sids))
    for s_idx, sid in enumerate(target_sids, start=1):
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

        if job_id:
            update_job_progress(db, job_id, "running", 20 + int((s_idx / total_targets) * 30), f"Fetching subtitles ({s_idx}/{total_targets})...")

        transcript_chunks = await fetch_youtube_captions(vid_id or vid_url, start_sec=0, end_sec=total_dur + 600)
        if not transcript_chunks:
            logger.info(f"[SmartPrepare] No captions available for {vid_id or vid_url}; skipping repartition.")
            continue

        if job_id:
            update_job_progress(db, job_id, "running", 50 + int((s_idx / total_targets) * 25), "Analyzing topic boundaries from subtitles...")

        video_meta = {
            "id": vid_id,
            "source_id": sid,
            "title": src["title"] or "Lecture",
            "url": vid_url,
            "duration": total_dur,
        }
        clips = await partition_video_async(video_meta, transcript_data=transcript_chunks, mode="auto", db_conn=db)
        if not clips:
            continue

        # Snapshot completed/skipped time ranges & personal notes across ALL old lessons of this source
        old_rows = db.execute(
            """
            SELECT l.id, l.start_sec, l.end_sec, l.status, l.completed_at, l.skipped_at, n.personal_notes
            FROM lessons l
            LEFT JOIN notes n ON n.lesson_id = l.id
            WHERE l.source_id = ? AND l.course_id = ?;
            """,
            (sid, course_id),
        ).fetchall()

        completed_ranges: List[Tuple[int, int, Optional[str]]] = []
        skipped_ranges: List[Tuple[int, int, Optional[str]]] = []
        personal_notes_ranges: List[Tuple[int, int, str]] = []
        old_ids: List[str] = []
        for r in old_rows:
            old_ids.append(r["id"])
            rs = int(r["start_sec"] or 0)
            re_ = int(r["end_sec"] or rs + 600)
            if r["status"] == "completed":
                completed_ranges.append((rs, re_, r["completed_at"]))
            elif r["status"] == "skipped":
                skipped_ranges.append((rs, re_, r["skipped_at"]))
            if r["personal_notes"]:
                personal_notes_ranges.append((rs, re_, r["personal_notes"]))

        # Cleanly replace ALL old clips for this source in one transaction (eliminating duplicate overlapping clips!)
        if old_ids:
            ph = ",".join(["?"] * len(old_ids))
            db.execute(f"DELETE FROM chunks WHERE lesson_id IN ({ph});", old_ids)
            db.execute(f"DELETE FROM schedule_allocations WHERE lesson_id IN ({ph});", old_ids)
            db.execute(f"DELETE FROM lessons WHERE id IN ({ph});", old_ids)

        for idx, clip in enumerate(clips):
            lid = clip.get("id") or str(uuid.uuid4())
            prio = clip.get("priority_tag") or clip.get("priority") or "core"
            c_start = int(clip.get("start_sec", 0))
            c_end = int(clip.get("end_sec", c_start + 600))
            c_dur = max(60, c_end - c_start)
            c_title = clip["title"]
            # Use semantic module_title/chapter_title; never duplicate title verbatim
            mod_title = (clip.get("module_title") or clip.get("chapter_title") or "").strip()
            if mod_title.lower() == c_title.lower():
                mod_title = ""

            # Restore completed/skipped status if >= 60% time overlap with a prior completed/skipped clip
            restored_status = "not_started"
            restored_completed_at = None
            restored_skipped_at = None
            for cs, ce, cat in completed_ranges:
                if _overlap_ratio(c_start, c_end, cs, ce) >= 0.60:
                    restored_status = "completed"
                    restored_completed_at = cat
                    break
            if restored_status == "not_started":
                for ss, se, sat in skipped_ranges:
                    if _overlap_ratio(c_start, c_end, ss, se) >= 0.60:
                        restored_status = "skipped"
                        restored_skipped_at = sat
                        break

            db.execute(
                """
                INSERT INTO lessons (
                    id, course_id, source_id, title, summary, video_id, video_url,
                    start_sec, end_sec, raw_duration_sec, priority, priority_tag,
                    status, completed_at, skipped_at, order_index, chapter_title,
                    is_excluded, has_transcript, transcription_status
                ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, 'completed');
                """,
                (
                    lid, course_id, sid, c_title, vid_id, vid_url,
                    c_start, c_end, c_dur, prio, prio,
                    restored_status, restored_completed_at, restored_skipped_at, idx, mod_title,
                ),
            )

            # Restore personal notes if overlapping
            matched_pnotes = [pn for ps, pe, pn in personal_notes_ranges if _overlap_ratio(c_start, c_end, ps, pe) >= 0.5]
            if matched_pnotes:
                db.execute(
                    """
                    INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated, generation_mode)
                    VALUES (?, ?, ?, '', ?, 0, 'deterministic');
                    """,
                    (str(uuid.uuid4()), course_id, lid, "\n\n".join(matched_pnotes)),
                )

            # Store sliced transcript chunks directly for each new semantic clip
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

    # 4. Enqueue background study-bundle generation if not already queued
    existing_job = db.execute(
        "SELECT id FROM jobs WHERE course_id = ? AND job_type = 'study_bundle_remaining' AND status IN ('queued', 'running') LIMIT 1;",
        (course_id,),
    ).fetchone()
    if existing_job:
        bundle_job_id = existing_job["id"]
    else:
        bundle_job_id = enqueue_job(db, "study_bundle_remaining", course_id=course_id, payload={"course_id": course_id})

    return {
        "course_id": course_id,
        "repartitioned_sources": repartitioned_sources,
        "new_semantic_clips": new_topics_count,
        "topics_clustered": cluster_res.get("topics_created", 0) if isinstance(cluster_res, dict) else 0,
        "background_job_id": bundle_job_id,
    }
