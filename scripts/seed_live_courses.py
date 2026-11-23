import os
import sys
import uuid
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Ensure backend can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["DATA_DIR"] = "data-dev"

from backend.database import init_connection
from backend.migrations.runner import apply_migrations
from backend.services.youtube import extract_metadata
from backend.routers.courses import create_lessons_from_meta
from backend.scheduler.engine import generate_schedule, default_clock

def seed_courses():
    db_path = Path("data-dev/app.db")
    apply_migrations(db_path)
    conn = init_connection(db_path)

    print("Checking existing courses in data-dev/app.db...")
    existing = conn.execute("SELECT id, title FROM courses").fetchall()
    print("Existing courses:", [dict(e) for e in existing])

    # 1. Seed DBMS Marathon Lecture
    dbms_url = "https://youtu.be/YRnjGeQbsHQ"
    print(f"\n1. Ingesting DBMS Marathon Anchor: {dbms_url}")
    target_date_dbms = (datetime.now() + timedelta(days=21)).strftime("%Y-%m-%d")
    
    dbms_course_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO courses (
            id, title, goal_query, source_preferences, target_date,
            minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            dbms_course_id,
            "Complete DBMS Marathon • One Shot Semester Prep",
            "DBMS end-term in 2 weeks, I know basics, 90 min/day",
            "Exam oriented, one-shot with chapters",
            target_date_dbms,
            90,
            1.25,
            json.dumps(["Sunday"]),
            2,
            "paced"
        )
    )
    
    print("Extracting metadata for DBMS video...")
    meta_dbms = extract_metadata(dbms_url)
    source_id_dbms = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, metadata_json, is_approved)
        VALUES (?, ?, 'youtube_video', ?, ?, ?, ?, 1);
        """,
        (
            source_id_dbms,
            dbms_course_id,
            meta_dbms.get("title", "Complete DBMS Data Base Management System in one shot"),
            dbms_url,
            meta_dbms.get("id"),
            json.dumps({
                "duration": meta_dbms.get("duration", 0),
                "uploader": meta_dbms.get("uploader"),
                "channel": meta_dbms.get("channel"),
                "webpage_url": dbms_url,
            })
        )
    )
    
    lesson_ids_dbms = create_lessons_from_meta(dbms_course_id, source_id_dbms, meta_dbms, conn)
    print(f"Created {len(lesson_ids_dbms)} lesson chapters for DBMS.")
    
    # Generate schedule
    lessons_dbms = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC", (dbms_course_id,)).fetchall()
    sched_dbms = generate_schedule(
        course_id=dbms_course_id,
        lessons=[dict(l) for l in lessons_dbms],
        start_date=default_clock(),
        target_date=datetime.strptime(target_date_dbms, "%Y-%m-%d").date(),
        minutes_per_day=90,
        playback_speed=1.25,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="paced"
    )
    # Save allocations
    for a in sched_dbms["allocations"]:
        conn.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                a.id,
                dbms_course_id,
                a.lesson_id,
                a.scheduled_date,
                a.split_index,
                a.split_count,
                a.allocated_start_sec,
                a.allocated_end_sec,
                a.effective_minutes,
                1 if a.is_completed else 0,
                1 if a.is_skipped else 0
            )
        )
    conn.commit()
    print("DBMS schedule allocations generated successfully.")

    # 2. Seed TOC Playlist
    toc_url = "https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev&si=rlyiJ9fIMBnIWFnj"
    print(f"\n2. Ingesting TOC Playlist Anchor: {toc_url}")
    target_date_toc = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
    
    toc_course_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO courses (
            id, title, goal_query, source_preferences, target_date,
            minutes_per_day, playback_speed, rest_days, revision_buffer_days, schedule_strategy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            toc_course_id,
            "Theory of Computation • Neso Academy Complete Playlist",
            "Theory of Computation comprehensive semester exam preparation",
            "Complete playlist, GATE and semester syllabus",
            target_date_toc,
            90,
            1.25,
            json.dumps(["Sunday"]),
            2,
            "paced"
        )
    )
    
    print("Extracting metadata for TOC playlist...")
    meta_toc = extract_metadata(toc_url)
    source_id_toc = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, external_id, metadata_json, is_approved)
        VALUES (?, ?, 'youtube_playlist', ?, ?, ?, ?, 1);
        """,
        (
            source_id_toc,
            toc_course_id,
            meta_toc.get("title", "Theory of Computation - Neso Academy"),
            toc_url,
            meta_toc.get("id"),
            json.dumps({
                "duration": meta_toc.get("duration", 0),
                "uploader": meta_toc.get("uploader"),
                "channel": meta_toc.get("channel"),
                "webpage_url": toc_url,
            })
        )
    )
    
    lesson_ids_toc = create_lessons_from_meta(toc_course_id, source_id_toc, meta_toc, conn)
    print(f"Created {len(lesson_ids_toc)} lessons for TOC playlist.")
    
    # Generate schedule
    lessons_toc = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC", (toc_course_id,)).fetchall()
    sched_toc = generate_schedule(
        course_id=toc_course_id,
        lessons=[dict(l) for l in lessons_toc],
        start_date=default_clock(),
        target_date=datetime.strptime(target_date_toc, "%Y-%m-%d").date(),
        minutes_per_day=90,
        playback_speed=1.25,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="paced"
    )
    # Save allocations
    for a in sched_toc["allocations"]:
        conn.execute(
            """
            INSERT INTO schedule_allocations (
                id, course_id, lesson_id, scheduled_date, split_index, split_count,
                allocated_start_sec, allocated_end_sec, effective_minutes, is_completed, is_skipped
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                a.id,
                toc_course_id,
                a.lesson_id,
                a.scheduled_date,
                a.split_index,
                a.split_count,
                a.allocated_start_sec,
                a.allocated_end_sec,
                a.effective_minutes,
                1 if a.is_completed else 0,
                1 if a.is_skipped else 0
            )
        )
    conn.commit()
    print("TOC schedule allocations generated successfully.")

    courses = conn.execute("SELECT id, title, created_at FROM courses").fetchall()
    print("\nSUCCESS! Saved courses in data-dev/app.db:")
    for c in courses:
        print(" ->", dict(c))

if __name__ == "__main__":
    seed_courses()
