"""Last-Night Cram Sheet Synthesis Service.

Condenses course lesson notes, high-yield PYQ patterns, essential definitions,
formulas, complexity/comparison tables, and diagram references into a high-density,
print-ready 1-2 page revision sheet.
Cached in SQLite by SHA-256 hash of underlying notes and PYQs.
"""

import os
import re
import uuid
import hashlib
import logging
from typing import Dict, Any, Optional, List

import httpx
from backend.config import get_settings

logger = logging.getLogger("learn_lms.cram_sheet")
settings = get_settings()


def compute_course_notes_hash(db_conn, course_id: str) -> str:
    """Computes SHA-256 hash across course title, target date, lesson notes, and PYQs."""
    cur = db_conn.cursor()
    cur.execute("SELECT title, target_date FROM courses WHERE id = ?;", (course_id,))
    c_row = cur.fetchone()
    c_info = f"{c_row[0] if c_row else ''}:{c_row[1] if c_row else ''}"

    cur.execute(
        """
        SELECT n.content_markdown
        FROM notes n
        JOIN lessons l ON n.lesson_id = l.id
        WHERE l.course_id = ?
        ORDER BY l.order_index ASC;
        """,
        (course_id,)
    )
    notes_parts = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute(
        """
        SELECT question_text, marks
        FROM pyq_questions
        WHERE course_id = ?
        ORDER BY id ASC;
        """,
        (course_id,)
    )
    pyq_parts = [f"{r[0]}:{r[1]}" for r in cur.fetchall()]

    full_payload = c_info + "||" + "||".join(notes_parts) + "||" + "||".join(pyq_parts)
    return hashlib.sha256(full_payload.encode("utf-8")).hexdigest()


def generate_deterministic_cram_sheet(db_conn, course_id: str) -> str:
    """Deterministically extracts high-density exam notes, definitions, comparison tables, and PYQs."""
    cur = db_conn.cursor()
    cur.execute("SELECT title, target_date FROM courses WHERE id = ?;", (course_id,))
    c_row = cur.fetchone()
    course_title = (c_row[0] if c_row else "Course") or "Course"
    target_date = (c_row[1] if c_row else "Upcoming") or "Upcoming"

    # Fetch lessons in order with notes
    cur.execute(
        """
        SELECT l.id, l.title, l.pyq_hit_count, l.pyq_total_marks, n.content_markdown
        FROM lessons l
        LEFT JOIN notes n ON l.id = n.lesson_id
        WHERE l.course_id = ?
        ORDER BY l.order_index ASC;
        """,
        (course_id,)
    )
    lessons = cur.fetchall()

    # Fetch top PYQ questions for the course
    cur.execute(
        """
        SELECT q.question_number, q.question_text, q.marks, p.title as paper_title, l.title as lesson_title
        FROM pyq_questions q
        LEFT JOIN pyq_papers p ON q.paper_id = p.id
        LEFT JOIN lessons l ON q.matched_lesson_id = l.id
        WHERE q.course_id = ? AND q.matched_lesson_id IS NOT NULL
        ORDER BY q.marks DESC NULLS LAST, l.pyq_hit_count DESC
        LIMIT 12;
        """,
        (course_id,)
    )
    top_pyqs = cur.fetchall()

    lines: List[str] = []
    lines.append(f"# {course_title} — Last-Night Exam Cram Sheet\n")
    lines.append(f"> [!IMPORTANT]\n> High-Yield Final Revision Sheet • Target Exam Date: **{target_date}** • Print or Save to PDF for rapid revision.\n")

    # Section 1: High-Yield Topic Weightage Matrix
    lines.append("## ⚡ High-Yield Exam Weightage Matrix\n")
    lines.append("| Topic / Lesson | Exam Weightage | Past Exam Hits | Marks Seen | Status |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")

    for row in lessons:
        lid, title, hits, marks, _ = row
        hits = hits or 0
        marks = marks or 0
        if hits >= 2:
            weight = "**HIGH YIELD 🔥**"
            status = "Must Master"
        elif hits == 1:
            weight = "Medium Yield"
            status = "Core Concept"
        else:
            weight = "Standard"
            status = "Fundamental"
        lines.append(f"| {title} | {weight} | {hits} questions | {marks}M | {status} |")

    lines.append("\n---\n")

    # Section 2: Core Definitions, Formulas & Key Principles
    lines.append("## 📌 Essential Concepts, Definitions & Formulas\n")

    tables_collected: List[str] = []

    for row in lessons:
        lid, title, hits, marks, md = row
        if not md:
            continue

        # Extract definitions (bullet points with bold terms or headers)
        lines.append(f"### {title} {'🔥 (PYQ Hit)' if hits > 0 else ''}\n")

        md_lines = md.split("\n")
        in_table = False
        current_table: List[str] = []
        definition_bullets: List[str] = []

        for line in md_lines:
            s_line = line.strip()
            # Capture Markdown tables
            if s_line.startswith("|") and s_line.endswith("|"):
                in_table = True
                current_table.append(s_line)
                continue
            else:
                if in_table:
                    if len(current_table) >= 3:
                        tables_collected.append(f"#### From: {title}\n" + "\n".join(current_table))
                    current_table = []
                    in_table = False

            # Capture bullet points or bold terms
            if s_line.startswith("- **") or s_line.startswith("* **"):
                definition_bullets.append(s_line)
            elif re.match(r"^[A-Z0-9].*:\s+.+", s_line) and len(s_line) < 200:
                definition_bullets.append(f"- **{s_line}")

        # If table was at the end of markdown
        if in_table and len(current_table) >= 3:
            tables_collected.append(f"#### From: {title}\n" + "\n".join(current_table))

        if definition_bullets:
            for b in definition_bullets[:5]:
                lines.append(b)
        else:
            # Fallback: take first 2 descriptive sentences from markdown
            cleaned_body = re.sub(r"#+.*", "", md).strip()
            sentences = [s.strip() for s in cleaned_body.split(".") if len(s.strip()) > 15]
            for s in sentences[:2]:
                lines.append(f"- {s}.")

        lines.append("")

    lines.append("---\n")

    # Section 3: Collected Comparison & Complexity Tables
    if tables_collected:
        lines.append("## 📊 Core Comparison & Complexity Tables\n")
        for tbl in tables_collected[:4]:
            lines.append(tbl + "\n")
        lines.append("---\n")

    # Section 4: Top University Exam Question Phrasings
    if top_pyqs:
        lines.append("## 🎯 Real Past-Paper Question Phrasings (PYQ)\n")
        lines.append("Practice how university examiners phrase these questions:\n")
        for q in top_pyqs:
            q_num, q_text, marks, paper, l_title = q
            mark_tag = f"[{marks}M]" if marks else ""
            lines.append(f"- **{q_num} {mark_tag}** ({l_title}): *\"{q_text}\"*")
        lines.append("\n---\n")

    # Footer note
    lines.append("> [!TIP]\n> Re-read this cram sheet 1 hour before entering the exam hall. Focus on definitions and the distinction tables.")

    return "\n".join(lines)


async def generate_cram_sheet_with_llm(
    course_title: str,
    target_date: str,
    raw_content_summary: str
) -> Optional[str]:
    """Generates structured cram sheet using configured LLM gateway."""
    gemini_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    if not (gemini_key or groq_key or openrouter_key):
        return None

    system_instruction = (
        "You are an expert university exam strategist. Synthesize the provided course notes, "
        "definitions, comparison tables, and past-paper questions into a dense, high-yield, "
        "print-ready 1-2 page Last-Night Exam Cram Sheet in Markdown.\n"
        "Requirements:\n"
        "1. Include an executive High-Yield Weightage Matrix table.\n"
        "2. Bullet-point essential definitions, core formulas, and key differences.\n"
        "3. Include clean Markdown comparison tables for contrasting concepts.\n"
        "4. Include exact past exam question phrasings.\n"
        "5. Keep prose tight, concise, and academic without fluff or generic filler."
    )

    user_prompt = (
        f"Subject: {course_title}\n"
        f"Target Exam Date: {target_date}\n\n"
        f"Course Content & PYQ Evidence:\n{raw_content_summary[:8000]}"
    )

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            # Try providers in priority order: Gemini → Groq → OpenRouter
            # Each is tried independently so a quota/rate-limit error on one falls through to the next
            if gemini_key:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                    payload = {
                        "contents": [
                            {"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_prompt}"}]}
                        ],
                        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 3000}
                    }
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "")
                    else:
                        logger.warning(f"Gemini cram sheet API returned {resp.status_code}; trying fallback providers")
                except Exception as e:
                    logger.warning(f"Gemini cram sheet call failed: {e}; trying fallback providers")

            if groq_key:
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 3000,
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "")
                    else:
                        logger.warning(f"Groq cram sheet API returned {resp.status_code}; trying fallback providers")
                except Exception as e:
                    logger.warning(f"Groq cram sheet call failed: {e}; trying fallback providers")

            if openrouter_key:
                try:
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": "google/gemini-2.5-flash",
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 3000,
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "")
                    else:
                        logger.warning(f"OpenRouter cram sheet API returned {resp.status_code}")
                except Exception as e:
                    logger.warning(f"OpenRouter cram sheet call failed: {e}")
    except Exception as e:
        logger.warning(f"LLM cram sheet generation failed, falling back to deterministic: {e}")

    return None


async def get_or_create_cram_sheet(
    db_conn,
    course_id: str,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Retrieves existing cram sheet if hash matches, or synthesizes a fresh one."""
    current_hash = compute_course_notes_hash(db_conn, course_id)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT id, content_markdown, notes_hash, is_generated_by_llm, created_at, updated_at FROM cram_sheets WHERE course_id = ?;",
        (course_id,)
    )
    existing = cur.fetchone()

    if existing and not force_refresh:
        sheet_id, content, saved_hash, is_llm, c_at, u_at = existing
        if saved_hash == current_hash:
            logger.info(f"[CramSheet] Cache hit for course {course_id} (hash: {current_hash[:8]})")
            return {
                "id": sheet_id,
                "course_id": course_id,
                "content_markdown": content,
                "notes_hash": saved_hash,
                "is_generated_by_llm": bool(is_llm),
                "created_at": c_at,
                "updated_at": u_at,
                "cached": True
            }

    # Generate fresh cram sheet
    cur.execute("SELECT title, target_date FROM courses WHERE id = ?;", (course_id,))
    c_row = cur.fetchone()
    course_title = (c_row[0] if c_row else "Course") or "Course"
    target_date = (c_row[1] if c_row else "Upcoming") or "Upcoming"

    # Deterministic generation first
    deterministic_content = generate_deterministic_cram_sheet(db_conn, course_id)
    content = deterministic_content
    is_llm = 0

    # Try LLM enrichment if key is set
    llm_content = await generate_cram_sheet_with_llm(course_title, target_date, deterministic_content)
    if llm_content and len(llm_content.strip()) > 100:
        content = llm_content
        is_llm = 1

    sheet_id = existing[0] if existing else f"cram_{uuid.uuid4().hex[:10]}"
    now_ts = None
    if existing:
        cur.execute(
            """
            UPDATE cram_sheets
            SET content_markdown = ?, notes_hash = ?, is_generated_by_llm = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (content, current_hash, is_llm, sheet_id)
        )
        # Fetch updated timestamps
        cur.execute("SELECT created_at, updated_at FROM cram_sheets WHERE id = ?;", (sheet_id,))
        ts_row = cur.fetchone()
        created_at_val = ts_row[0] if ts_row else None
        updated_at_val = ts_row[1] if ts_row else None
    else:
        cur.execute(
            """
            INSERT INTO cram_sheets (id, course_id, content_markdown, notes_hash, is_generated_by_llm)
            VALUES (?, ?, ?, ?, ?);
            """,
            (sheet_id, course_id, content, current_hash, is_llm)
        )
        cur.execute("SELECT created_at, updated_at FROM cram_sheets WHERE id = ?;", (sheet_id,))
        ts_row = cur.fetchone()
        created_at_val = ts_row[0] if ts_row else None
        updated_at_val = ts_row[1] if ts_row else None

    db_conn.commit()

    # Fetch final timestamps for response
    cur.execute("SELECT created_at, updated_at FROM cram_sheets WHERE id = ?;", (sheet_id,))
    ts_row = cur.fetchone()
    created_at_val = ts_row[0] if ts_row else None
    updated_at_val = ts_row[1] if ts_row else None

    return {
        "id": sheet_id,
        "course_id": course_id,
        "content_markdown": content,
        "notes_hash": current_hash,
        "is_generated_by_llm": bool(is_llm),
        "cached": False,
        "created_at": created_at_val,
        "updated_at": updated_at_val,
    }
