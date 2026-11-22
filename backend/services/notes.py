"""Structured Notes Generation Service.

Generates structured, grounded Markdown study notes from transcript chunks,
incorporating verbatim citations and clickable [MM:SS] player seek links.
Supports LLM enrichment (Gemini/OpenRouter/Groq) and deterministic No-Key mode.
"""

import os
import re
import uuid
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.services.llm_cache import (
    compute_sha256,
    get_cached_response,
    set_cached_response,
    ensure_llm_cache_table,
)

logger = logging.getLogger("learn_lms.notes")
settings = get_settings()


def format_seconds_to_mm_ss(seconds: Optional[int]) -> str:
    """Formats integer seconds to [MM:SS] or [HH:MM:SS]."""
    if seconds is None:
        return "[00:00]"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def generate_no_key_structured_notes(
    lesson_title: str,
    chunks: List[Dict[str, Any]],
    screenshots: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Generates structured Markdown study notes deterministically from chunks.
    
    Used when no LLM key is configured. Incorporates [MM:SS] links, keyframe
    embeds, section headings, and cited chunk IDs.
    """
    if not chunks:
        return (
            f"# {lesson_title}\n\n"
            "> [!NOTE]\n"
            "> No transcript or captions found for this lesson yet. "
            "Use the 'Transcribe / Fetch Captions' button to ingest content.\n"
        )

    lines: List[str] = []
    lines.append(f"# {lesson_title}\n")
    
    # Overview banner
    first_start = chunks[0]["start_sec"]
    last_end = chunks[-1]["end_sec"]
    lines.append(f"**Lesson Time Range**: {format_seconds_to_mm_ss(first_start)} — {format_seconds_to_mm_ss(last_end)}\n")
    lines.append(f"**Source Evidence**: Grounded across {len(chunks)} transcript sections.\n")
    lines.append("---\n")

    lines.append("## 📌 Key Takeaways & Core Concepts\n")

    # Map screenshots by timestamp for inline pairing
    shots_by_time = {}
    if screenshots:
        for s in screenshots:
            shots_by_time[s["timestamp_sec"]] = s

    for chunk in chunks:
        s_sec = chunk["start_sec"]
        e_sec = chunk["end_sec"]
        time_tag = format_seconds_to_mm_ss(s_sec)
        content = chunk["content"].strip()
        chunk_id = chunk.get("id", f"chk_{chunk.get('chunk_index', 0)}")

        # Pick first sentence or up to 100 characters as heading concept
        first_sentence = content.split(".")[0].strip()
        if len(first_sentence) > 90:
            first_sentence = first_sentence[:87] + "..."

        lines.append(f"### {time_tag} {first_sentence.title()}\n")

        # Check if an opt-in screenshot matches this chunk start
        matching_shot = next(
            (s for s in (screenshots or []) if abs(s["timestamp_sec"] - s_sec) < 15),
            None
        )
        if matching_shot:
            lines.append(f"![{matching_shot['caption']}]({matching_shot['url']})\n")

        # Body paragraphs with inline citations
        sentences = [s.strip() for s in content.split(".") if s.strip()]
        for sent in sentences[:4]:
            lines.append(f"- {sent}. `[{time_tag}]` `[ref:{chunk_id}]`")
        lines.append("")

    lines.append("---\n")
    lines.append("## 🔍 Grounding & Source Chunks\n")
    lines.append("| Timestamp | Chunk Ref | Words | Excerpt |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for chunk in chunks:
        t_str = format_seconds_to_mm_ss(chunk["start_sec"])
        excerpt = chunk["content"][:60].replace("|", "/") + "..."
        c_id = chunk.get("id", f"chk_{chunk.get('chunk_index', 0)}")
        word_count = len(chunk["content"].split())
        lines.append(f"| {t_str} | `{c_id}` | {word_count} | {excerpt} |")

    return "\n".join(lines)


async def generate_llm_structured_notes(
    lesson_title: str,
    chunks: List[Dict[str, Any]],
    gemini_key: Optional[str] = None,
    screenshots: Optional[List[Dict[str, Any]]] = None,
    db_conn: Optional[Any] = None,
) -> str:
    """Generates LLM-synthesized structured study notes grounded in transcript chunks."""
    if not chunks:
        return generate_no_key_structured_notes(lesson_title, chunks, screenshots)

    # Format transcript chunks with exact timestamps and IDs for strict grounding
    transcript_text = "\n\n".join([
        f"[START: {format_seconds_to_mm_ss(c['start_sec'])}, END: {format_seconds_to_mm_ss(c['end_sec'])}, ID: {c.get('id', c['chunk_index'])}]\n{c['content']}"
        for c in chunks
    ])

    system_instruction = (
        "You are an expert college professor and technical study assistant. "
        "Create comprehensive, crystal-clear, structured Markdown study notes for this lesson. "
        "CRITICAL RULES:\n"
        "1. Every single key point, definition, formula, or concept MUST include a clickable timestamp link in [MM:SS] format (e.g. [02:15]) pointing to the exact moment in the video.\n"
        "2. Ground all points strictly in the provided transcript text. Do not hallucinate external facts.\n"
        "3. Include:\n"
        "   - Overview & Exam Importance\n"
        "   - Detailed Breakdown with Timestamped Subheadings (### [MM:SS] Concept Name)\n"
        "   - Formulas / Code Blocks / Definitions where applicable\n"
        "   - Common Exam Pitfalls / Misconceptions\n"
        "4. Use standard GitHub Flavored Markdown with > [!NOTE] or > [!IMPORTANT] alerts.\n"
    )

    prompt_text = f"{system_instruction}\n\nLesson Title: {lesson_title}\n\nTranscript Chunks:\n{transcript_text}"
    prompt_hash = compute_sha256(prompt_text)

    # 1. Check cache first
    if db_conn is not None:
        cached_content = get_cached_response(db_conn, prompt_hash)
        if cached_content:
            logger.info("Returning cached structured notes from llm_cache")
            return cached_content

    # 2. Determine provider and model
    key = gemini_key or settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    model_used = "deterministic"
    generated_text = None

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            if key:
                model_used = "gemini-2.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_used}:generateContent?key={key}"
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": prompt_text
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 2048,
                    }
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    result = resp.json()
                    candidates = result.get("candidates", [])
                    if candidates:
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if content_parts:
                            generated_text = content_parts[0].get("text", "")
                else:
                    logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}")
            elif groq_key:
                model_used = "llama-3.3-70b-versatile"
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_used,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Lesson Title: {lesson_title}\n\nTranscript Chunks:\n{transcript_text}"}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2048,
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        generated_text = choices[0].get("message", {}).get("content", "")
                else:
                    logger.warning(f"Groq API returned status {resp.status_code}: {resp.text[:200]}")
            elif openrouter_key:
                model_used = "google/gemini-2.5-flash"
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_used,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Lesson Title: {lesson_title}\n\nTranscript Chunks:\n{transcript_text}"}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2048,
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        generated_text = choices[0].get("message", {}).get("content", "")
                else:
                    logger.warning(f"OpenRouter API returned status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"LLM notes generation request failed: {e}")

    if generated_text:
        if db_conn is not None:
            set_cached_response(db_conn, prompt_hash, model_used, generated_text)
        return generated_text

    # Fallback to deterministic generation if LLM fails or is unconfigured
    return generate_no_key_structured_notes(lesson_title, chunks, screenshots)


# ---------------------------------------------------------------------------
# High-Level Note Management (Persistence & Retrieval)
# ---------------------------------------------------------------------------

async def get_or_generate_lesson_notes(
    db_conn,
    course_id: str,
    lesson_id: str,
    force_regenerate: bool = False
) -> Dict[str, Any]:
    """Retrieves existing notes or generates new structured notes for a lesson."""
    cur = db_conn.cursor()

    # 1. Fetch lesson info
    cur.execute("SELECT id, title FROM lessons WHERE id = ?;", (lesson_id,))
    l_row = cur.fetchone()
    if not l_row:
        return {"content_markdown": "", "personal_notes": "", "is_generated": 1}
    
    lesson_title = l_row[1]

    # 2. Check if generated notes already exist in DB
    if not force_regenerate:
        cur.execute(
            """
            SELECT id, content_markdown, personal_notes, is_generated, updated_at 
            FROM notes 
            WHERE lesson_id = ? 
            ORDER BY (CASE WHEN personal_notes IS NOT NULL AND personal_notes != '' THEN 1 ELSE 0 END) DESC, updated_at DESC LIMIT 1;
            """,
            (lesson_id,)
        )
        note_row = cur.fetchone()
        if note_row and note_row[1]:
            return {
                "id": note_row[0],
                "content_markdown": note_row[1],
                "personal_notes": note_row[2] or "",
                "is_generated": note_row[3],
                "updated_at": note_row[4],
            }

    # 3. Fetch chunks for generation
    cur.execute(
        """
        SELECT id, chunk_index, token_count, start_sec, end_sec, content 
        FROM chunks 
        WHERE lesson_id = ? 
        ORDER BY start_sec ASC, chunk_index ASC;
        """,
        (lesson_id,)
    )
    chunk_rows = cur.fetchall()
    chunks = [
        {
            "id": r[0],
            "chunk_index": r[1],
            "token_count": r[2],
            "start_sec": r[3],
            "end_sec": r[4],
            "content": r[5]
        }
        for r in chunk_rows
    ]

    # Fetch screenshots for inline embed
    from backend.services.screenshots import get_lesson_screenshots
    screenshots = get_lesson_screenshots(db_conn, lesson_id)

    # 4. Generate structured notes
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if has_llm:
        markdown = await generate_llm_structured_notes(
            lesson_title=lesson_title,
            chunks=chunks,
            gemini_key=settings.GEMINI_API_KEY,
            screenshots=screenshots,
            db_conn=db_conn,
        )
    else:
        markdown = generate_no_key_structured_notes(lesson_title, chunks, screenshots)

    # 5. Persist generated notes in SQLite, preserving user's personal notes
    cur.execute("SELECT id, personal_notes FROM notes WHERE lesson_id = ? ORDER BY (CASE WHEN personal_notes IS NOT NULL AND personal_notes != '' THEN 1 ELSE 0 END) DESC, updated_at DESC LIMIT 1;", (lesson_id,))
    existing_note = cur.fetchone()
    existing_personal = existing_note[1] if existing_note else ""

    if existing_note:
        note_id = existing_note[0]
        cur.execute(
            """
            UPDATE notes 
            SET content_markdown = ?, personal_notes = ?, is_generated = 1, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?;
            """,
            (markdown, existing_personal or "", note_id)
        )
        cur.execute("DELETE FROM notes WHERE lesson_id = ? AND id != ?;", (lesson_id, note_id))
    else:
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated)
            VALUES (?, ?, ?, ?, '', 1);
            """,
            (note_id, course_id, lesson_id, markdown)
        )
    db_conn.commit()

    return {
        "id": note_id,
        "content_markdown": markdown,
        "personal_notes": existing_personal or "",
        "is_generated": 1,
    }


def save_personal_notes(
    db_conn,
    course_id: str,
    lesson_id: str,
    personal_notes_text: str
) -> bool:
    """Updates user's personal editable notes for a lesson."""
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM notes WHERE lesson_id = ? ORDER BY updated_at DESC LIMIT 1;", (lesson_id,))
    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE notes 
            SET personal_notes = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE lesson_id = ?;
            """,
            (personal_notes_text, lesson_id)
        )
        cur.execute("DELETE FROM notes WHERE lesson_id = ? AND id != ?;", (lesson_id, row[0]))
    else:
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated)
            VALUES (?, ?, ?, '', ?, 0);
            """,
            (note_id, course_id, lesson_id, personal_notes_text)
        )
    db_conn.commit()
    return True
