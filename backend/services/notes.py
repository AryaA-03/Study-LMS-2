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
    """Generates standalone GeeksforGeeks-style Markdown study notes deterministically from chunks.
    
    Structure:
    1. Overview & Intuition
    2. Key Definitions, Syntax & Formulas
    3. Step-by-Step Worked Example
    4. Comparison / Complexity / Edge Cases Table
    5. Quick Exam Revision Bullets
    
    Embeds clickable [MM:SS] timestamp pills on every section/concept so the user
    can learn from notes alone or jump straight into the video player.
    """
    if not chunks:
        return (
            f"# {lesson_title}\n\n"
            "> [!NOTE]\n"
            "> No transcript or captions found for this concept clip yet. "
            "Use the 'Transcribe / Fetch Captions' button to ingest content.\n"
        )

    lines: List[str] = []
    lines.append(f"# {lesson_title}\n")
    
    first_start = chunks[0]["start_sec"]
    last_end = chunks[-1]["end_sec"]
    time_badge = f"{format_seconds_to_mm_ss(first_start)} — {format_seconds_to_mm_ss(last_end)}"
    lines.append(f"> [!NOTE]\n> **Concept Clip Time Range**: {time_badge} • Grounded strictly across {len(chunks)} transcript sections.\n")
    lines.append("---\n")

    # 1. Overview & Intuition
    lines.append("## 1. Overview & Intuition\n")
    first_content = chunks[0]["content"].strip()
    first_pill = format_seconds_to_mm_ss(chunks[0]["start_sec"])
    overview_sentences = [s.strip() for s in first_content.split(".") if len(s.strip()) > 15]
    if overview_sentences:
        lines.append(f"{first_pill} **Core Motivation**: {overview_sentences[0]}.")
        if len(overview_sentences) > 1:
            lines.append(f"\n{overview_sentences[1]}.")
    else:
        lines.append(f"{first_pill} This concept clip explores foundational theory, mechanics, and applications of `{lesson_title}`.")
    lines.append("\n---\n")

    # 2. Key Definitions, Syntax & Formulas
    lines.append("## 2. Key Definitions, Syntax & Formulas\n")
    def_bullets = []
    for c in chunks:
        c_pill = format_seconds_to_mm_ss(c["start_sec"])
        c_text = c["content"].strip()
        sentences = [s.strip() for s in c_text.split(".") if s.strip()]
        for s in sentences:
            if any(kw in s.lower() for kw in ["is defined", "means", "formula", "syntax", "called", "known as", "rule", "property", "theorem"]):
                def_bullets.append(f"- **Key Principle** {c_pill}: {s}.")
                if len(def_bullets) >= 5:
                    break
        if len(def_bullets) >= 5:
            break

    if not def_bullets:
        for c in chunks[:3]:
            c_pill = format_seconds_to_mm_ss(c["start_sec"])
            first_s = c["content"].split(".")[0].strip()
            def_bullets.append(f"- **Formal Point** {c_pill}: {first_s}.")

    for b in def_bullets:
        lines.append(b)
    lines.append("\n---\n")

    # 3. Step-by-Step Worked Example
    lines.append("## 3. Step-by-Step Worked Example\n")
    mid_chunk = chunks[len(chunks) // 2]
    mid_pill = format_seconds_to_mm_ss(mid_chunk["start_sec"])
    example_sentences = [s.strip() for s in mid_chunk["content"].split(".") if len(s.strip()) > 10]
    lines.append(f"Walkthrough demonstrating how the rules of `{lesson_title}` execute in practice:")
    lines.append(f"1. **Step 1: Setup & Inputs** {mid_pill}: Initialize base states, alphabet symbols, or data parameters as discussed in the lecture.")
    if example_sentences:
        lines.append(f"2. **Step 2: Transition & Computation** {mid_pill}: {example_sentences[0]}.")
        if len(example_sentences) > 1:
            lines.append(f"3. **Step 3: State Verification** {mid_pill}: {example_sentences[1]}.")
    else:
        lines.append(f"2. **Step 2: Transition & Computation** {mid_pill}: Process the input sequence deterministically through valid states.")
        lines.append(f"3. **Step 3: Result & Verification** {mid_pill}: Verify termination and validate acceptance criteria.")
    lines.append("\n---\n")

    # 4. Comparison / Complexity / Edge Cases Table
    lines.append("## 4. Comparison / Complexity / Edge Cases Table\n")
    lines.append("| Concept / Aspect | Property / Behavior | Edge Case / Pitfall | Timestamp |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for idx, c in enumerate(chunks[:4]):
        c_pill = format_seconds_to_mm_ss(c["start_sec"])
        word = c["content"].split()[0].title() if c["content"].split() else f"Phase {idx+1}"
        short_summary = (c["content"][:45] + "...").replace("|", "/")
        lines.append(f"| Aspect {idx+1} ({word}) | {short_summary} | Watch for empty strings / boundaries | {c_pill} |")
    lines.append("\n---\n")

    # 5. Quick Exam Revision Bullets
    lines.append("## 5. Quick Exam Revision Bullets\n")
    for idx, c in enumerate(chunks[-3:]):
        c_pill = format_seconds_to_mm_ss(c["start_sec"])
        s_part = c["content"].split(".")[0].strip()
        lines.append(f"- ⚡ **High-Yield Point {idx+1}** {c_pill}: {s_part}.")

    chunk_ids = [str(c["id"]) for c in chunks if c.get("id")]
    if screenshots:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Captured Slides & Keyframes")
        lines.append("")
        for sc in screenshots[:6]:
            sc_pill = sc.get("formatted_time") or format_seconds_to_mm_ss(sc.get("timestamp_sec") or 0)
            sc_cap = sc.get("caption") or f"Slide at {sc_pill}"
            sc_url = sc.get("url") or ""
            if sc_url:
                lines.append(f"![{sc_cap}]({sc_url})")
                lines.append(f"*{sc_pill} — {sc_cap}*")
                lines.append("")

    if chunk_ids:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Grounding & Source Chunks")
        lines.append("")
        lines.append("- Sources: " + ", ".join(chunk_ids[:10]))

    return "\n".join(lines)


async def generate_llm_structured_notes(
    lesson_title: str,
    chunks: List[Dict[str, Any]],
    gemini_key: Optional[str] = None,
    screenshots: Optional[List[Dict[str, Any]]] = None,
    db_conn: Optional[Any] = None,
    bypass_cache: bool = False,
) -> str:
    """Generates LLM-synthesized standalone GeeksforGeeks-style Markdown study notes grounded in transcript chunks."""
    if not chunks:
        return generate_no_key_structured_notes(lesson_title, chunks, screenshots)

    # Format transcript chunks with exact timestamps and IDs for strict grounding
    transcript_text = "\n\n".join([
        f"[START: {format_seconds_to_mm_ss(c['start_sec'])}, END: {format_seconds_to_mm_ss(c['end_sec'])}, ID: {c.get('id', c['chunk_index'])}]\n{c['content']}"
        for c in chunks
    ])

    system_instruction = (
        "You are an expert college professor and technical curriculum author. "
        "Create complete, self-contained standalone GeeksforGeeks-style Markdown study notes "
        "strictly from this concept clip's transcript slice so a student can master the concept from notes alone without watching the video.\n\n"
        "MANDATORY STRUCTURE:\n"
        "# [Concept Title]\n\n"
        "## 1. Overview & Intuition\n"
        "Explain what this concept is, why it exists, and the core intuition with a clickable [MM:SS] timestamp.\n\n"
        "## 2. Key Definitions, Syntax & Formulas\n"
        "Bullet-point exact formal definitions, notation, mathematical tuples, or code syntax with [MM:SS] timestamps.\n\n"
        "## 3. Step-by-Step Worked Example\n"
        "Walk step-by-step through a concrete worked example with inputs, intermediate transitions, and final result with [MM:SS] timestamps.\n\n"
        "## 4. Comparison / Complexity / Edge Cases Table\n"
        "Provide a clean Markdown comparison or complexity table summarizing tradeoffs and edge cases.\n\n"
        "## 5. Quick Exam Revision Bullets\n"
        "3-5 high-yield bullets for rapid pre-exam revision with [MM:SS] pills.\n\n"
        "CRITICAL RULES:\n"
        "1. Every section and key formula MUST embed clickable [MM:SS] timestamp pills (e.g. [04:12]).\n"
        "2. Ground strictly in the transcript text; never hallucinate external facts.\n"
        "3. Output valid GitHub Flavored Markdown."
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
            if key and not generated_text:
                try:
                    model_used = "gemini-2.5-flash"
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_used}:generateContent"
                    _gemini_headers = {"x-goog-api-key": key}
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
                    resp = await client.post(url, json=payload, headers=_gemini_headers)
                    if resp.status_code == 200:
                        result = resp.json()
                        candidates = result.get("candidates", [])
                        if candidates:
                            content_parts = candidates[0].get("content", {}).get("parts", [])
                            if content_parts:
                                generated_text = content_parts[0].get("text", "")
                    else:
                        logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}; trying fallback")
                except Exception as e:
                    logger.warning(f"Gemini notes generation failed: {e}; trying fallback")

            if groq_key and not generated_text:
                try:
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
                        logger.warning(f"Groq API returned status {resp.status_code}: {resp.text[:200]}; trying fallback")
                except Exception as e:
                    logger.warning(f"Groq notes generation failed: {e}; trying fallback")

            if openrouter_key and not generated_text:
                try:
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
                    logger.warning(f"OpenRouter notes generation failed: {e}")
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
