import asyncio
import os
os.environ["DATA_DIR"] = "data-dev"

from backend.database import init_connection
from backend.services.transcription import ingest_lesson_transcript
from backend.services.screenshots import capture_lesson_keyframes
from backend.services.notes import get_or_generate_lesson_notes

conn = init_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT l.id, l.course_id, l.source_id, l.video_id, l.start_sec, l.end_sec, l.title
    FROM lessons l
    JOIN courses c ON l.course_id = c.id
    WHERE c.title LIKE '%DBMS%'
    ORDER BY l.order_index ASC LIMIT 2
""")
lessons = cursor.fetchall()

async def main():
    for l in lessons:
        lid, cid, sid, vid, s_sec, e_sec, title = l
        print(f"\nProcessing lesson: {title} ({vid})")
        # 1. Ingest transcript chunks
        ok, t_type, chunks = await ingest_lesson_transcript(conn, cid, sid, lid, vid, s_sec, e_sec)
        print(f"Transcript: ok={ok}, type={t_type}, chunks={chunks}")
        
        # 2. Extract keyframe screenshots
        shots = await capture_lesson_keyframes(conn, cid, lid, vid, s_sec, e_sec)
        print(f"Screenshots captured: {len(shots)}")
        for s in shots:
            print(f"  - [{s['formatted_time']}] {s['url']} -> {s['caption']}")
        
        # 3. Generate structured Markdown notes with embedded screenshots & clickable timestamps
        notes = await get_or_generate_lesson_notes(conn, cid, lid, force_regenerate=True)
        md = notes.get("content_markdown", "")
        print(f"Notes generated ({len(md)} chars). First 300 chars:")
        print(md[:300])

if __name__ == "__main__":
    asyncio.run(main())
