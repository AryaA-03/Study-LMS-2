"""2-Pass Map-Reduce Last-Night Exam Cram Sheet Engine.

Produces a dense, A4-printable Master Exam Cheat Sheet across:
  - Full Course (default)
  - Single Video (`source_id`)
  - Single Module (`chapter_title`)

Architecture:
  - Pass 1 (Map): Group lessons by Module (`chapter_title`) and compress each module
    into a high-density Module Fact Block cached per-module in `llm_cache`.
  - Pass 2 (Reduce): Assemble all Module Fact Blocks + top PYQ hits into a complete
    6-section Master Cram Sheet with ZERO 24,000-character truncation and ZERO chunk deletion.
"""

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.config import get_settings
from backend.infra.llm_gateway import get_llm_gateway
from backend.services.llm_cache import compute_prompt_hash, get_cached_response, set_cached_response

logger = logging.getLogger("learn_lms.cram_sheet")

_RAW_CHK_RE = re.compile(r"\[ref:[^\]]+\]|\bchk_[a-f0-9]{4,}\b", re.IGNORECASE)


def format_seconds_to_mm_ss(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "00:00"
    sec = int(seconds)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fetch_scoped_lessons(
    db_conn,
    course_id: str,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT l.id, l.title, l.chapter_title, l.source_id, l.video_id, l.start_sec, l.end_sec,
               COALESCE(l.pyq_hit_count, 0) AS pyq_hit_count, l.order_index,
               n.content_markdown, n.personal_notes, s.url AS source_url
        FROM lessons l
        LEFT JOIN notes n ON n.lesson_id = l.id
        LEFT JOIN sources s ON s.id = l.source_id
        WHERE l.course_id = ? AND COALESCE(l.is_excluded, 0) = 0
    """
    params: List[Any] = [course_id]
    if source_id:
        sql += " AND l.source_id = ?"
        params.append(source_id)
    if chapter_title:
        sql += " AND COALESCE(l.chapter_title, '') = ?"
        params.append(chapter_title)
    sql += " ORDER BY l.order_index ASC;"
    cur = db_conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def compute_course_notes_hash(
    db_conn,
    course_id: str,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
) -> str:
    """Computes a deterministic SHA-256 hash over scoped lesson notes + PYQ hits for cache invalidation."""
    lessons = _fetch_scoped_lessons(db_conn, course_id, source_id=source_id, chapter_title=chapter_title)
    pyq_rows = db_conn.execute(
        "SELECT id, question_text, matched_lesson_id FROM pyq_questions WHERE course_id = ? ORDER BY id ASC;",
        (course_id,),
    ).fetchall()
    h = hashlib.sha256()
    h.update(f"scope:{source_id or 'all'}|{chapter_title or 'all'}|v2".encode("utf-8"))
    for les in lessons:
        h.update(f"{les['id']}|{les['title']}|{les['chapter_title']}|{les['pyq_hit_count']}|".encode("utf-8"))
        h.update((les.get("content_markdown") or "")[:500].encode("utf-8"))
    for p in pyq_rows:
        h.update(f"{p[0]}|{p[2]}|".encode("utf-8"))
    return h.hexdigest()


def _extract_lesson_highlights(db_conn, lesson: Dict[str, Any]) -> Dict[str, Any]:
    """Extract real formulas, tables, definitions, and tips from lesson notes or transcript chunks."""
    md = _RAW_CHK_RE.sub("", lesson.get("content_markdown") or "")
    # Ignore poisoned legacy fallback text if any remains
    if "Aspect 1 (" in md or "Watch for empty strings" in md:
        md = ""
    pill = f"[{format_seconds_to_mm_ss(lesson.get('start_sec'))}]"
    formulas: List[str] = []
    tips: List[str] = []
    bullets: List[str] = []
    tables: List[str] = []

    if md.strip():
        in_table = False
        cur_table: List[str] = []
        for raw_line in md.splitlines():
            line = raw_line.strip()
            if line.startswith("|") and line.endswith("|"):
                in_table = True
                cur_table.append(line)
                continue
            elif in_table:
                if len(cur_table) >= 3:
                    tables.append("\n".join(cur_table[:8]))
                cur_table = []
                in_table = False

            if "$$" in line or (re.search(r"[A-Za-z]\s*=\s*[A-Za-z0-9(\\]|O\([^)]+\)", line) and len(line) < 160):
                clean_f = line.lstrip("-* ").strip()
                if clean_f and clean_f not in formulas:
                    formulas.append(clean_f if "[" in clean_f else f"{clean_f} {pill}")
            elif line.startswith("> [!IMPORTANT]") or line.startswith("> [!TIP]"):
                clean_t = re.sub(r"^>\s*\[!(?:IMPORTANT|TIP)\]\s*", "", line).strip()
                if clean_t:
                    tips.append(clean_t if "[" in clean_t else f"{clean_t} {pill}")
            elif line.startswith("- ") and len(line) > 22:
                b = line[2:].strip()
                if not b.lower().startswith("sources:"):
                    bullets.append(b if "[" in b else f"{b} {pill}")
        if in_table and len(cur_table) >= 3:
            tables.append("\n".join(cur_table[:8]))
    else:
        rows = db_conn.execute(
            "SELECT start_sec, content FROM chunks WHERE lesson_id = ? ORDER BY chunk_index ASC LIMIT 8;",
            (lesson["id"],),
        ).fetchall()
        for r in rows:
            txt = _RAW_CHK_RE.sub("", (r[1] or "").strip())
            if len(txt) >= 25:
                bullets.append(f"{txt[:180]} [{format_seconds_to_mm_ss(r[0])}]")

    return {
        "lesson_id": lesson["id"],
        "title": lesson["title"],
        "module": (lesson.get("chapter_title") or "Core Syllabus").strip() or "Core Syllabus",
        "pill": pill,
        "pyq_hits": int(lesson.get("pyq_hit_count") or 0),
        "formulas": formulas[:5],
        "tips": tips[:3],
        "bullets": bullets[:6],
        "tables": tables[:2],
        "raw_md": md[:3500],
    }


def generate_deterministic_cram_sheet(
    db_conn,
    course_id: str,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
) -> str:
    """Clean, duplicate-free deterministic A4 Last-Night Exam Cram Sheet."""
    c_row = db_conn.execute("SELECT title FROM courses WHERE id = ?;", (course_id,)).fetchone()
    course_title = (c_row[0] if c_row else "Course") or "Course"
    lessons = _fetch_scoped_lessons(db_conn, course_id, source_id=source_id, chapter_title=chapter_title)
    if not lessons:
        return f"# {course_title} — Last-Night Exam Cram Sheet\n\nNo active lessons found for this scope yet."

    scope_label = f"Module: {chapter_title}" if chapter_title else ("Single Video Scope" if source_id else "Full Course Syllabus")
    pyqs = db_conn.execute(
        """
        SELECT pq.question_text, pq.marks, l.title AS lesson_title, l.start_sec
        FROM pyq_questions pq
        LEFT JOIN lessons l ON l.id = pq.matched_lesson_id
        WHERE pq.course_id = ?
        ORDER BY pq.marks DESC, pq.id ASC
        LIMIT 12;
        """,
        (course_id,),
    ).fetchall()

    modules: Dict[str, List[Dict[str, Any]]] = {}
    all_formulas: List[str] = []
    all_tables: List[Tuple[str, str]] = []
    all_tips: List[str] = []

    for les in lessons:
        hl = _extract_lesson_highlights(db_conn, les)
        modules.setdefault(hl["module"], []).append(hl)
        for f in hl["formulas"]:
            if f not in all_formulas:
                all_formulas.append(f)
        for t in hl["tables"]:
            all_tables.append((hl["title"], t))
        for tip in hl["tips"]:
            if tip not in all_tips:
                all_tips.append(tip)

    out: List[str] = [
        f"# {course_title} — Last-Night Exam Cram Sheet",
        f"*{scope_label} · {len(lessons)} Topics across {len(modules)} Modules*",
        "",
        "## 1. High-Yield Exam Weightage Matrix",
        "| Module | Topics | PYQ Hits | Start Jump |",
        "|---|---|---|---|",
    ]
    for mod_name, items in modules.items():
        hits = sum(i["pyq_hits"] for i in items)
        first_pill = items[0]["pill"]
        out.append(f"| **{mod_name}** | {len(items)} | {hits} | {first_pill} |")
    out.append("")

    if all_formulas:
        out.append("## 2. Master Formula, Theorem & Complexity Reference")
        for f in all_formulas[:25]:
            out.append(f"- {f}")
        out.append("")

    if all_tables:
        out.append("## 3. Core Distinctions & Comparison Matrices")
        for title, tbl in all_tables[:5]:
            out.append(f"### {title}")
            out.append(tbl)
            out.append("")

    pending_lessons: List[str] = []
    out.append("## 4. Module-by-Module Rapid Recall Sheet")
    for mod_name, items in modules.items():
        out.append(f"### {mod_name}")
        for it in items:
            pyq_tag = f" *(PYQ ×{it['pyq_hits']})*" if it["pyq_hits"] > 0 else ""
            if it["bullets"] or it["raw_md"]:
                out.append(f"**{it['title']}** {it['pill']}{pyq_tag}")
                for b in (it["bullets"][:4] or [f"Review core concept at {it['pill']}."]):
                    out.append(f"- {b}")
                out.append("")
            else:
                pending_lessons.append(f"- {it['title']} {it['pill']}")
    if pending_lessons:
        out.append("## Lessons Pending Notes Synthesis")
        out.extend(pending_lessons)
        out.append("")

    if all_tips:
        out.append("## 5. Common Exam Traps & Key Rules")
        for tip in all_tips[:12]:
            out.append(f"- {tip}")
        out.append("")

    if pyqs:
        out.append("## 6. Top Repeated PYQs & Focus Areas")
        for idx, p in enumerate(pyqs, start=1):
            pill = f" [{format_seconds_to_mm_ss(p[3])}]" if p[3] is not None else ""
            marks = f" ({p[1]})" if p[1] else ""
            out.append(f"{idx}. **{p[0]}**{marks}{pill}")
        out.append("")

    return "\n".join(out).strip()


async def _compress_module_pass1(
    db_conn,
    course_title: str,
    module_name: str,
    module_lessons: List[Dict[str, Any]],
    force_refresh: bool = False,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Pass 1 (Map): Compress a single module's lessons into a high-density Module Fact Block."""
    parts: List[str] = []
    for hl in module_lessons:
        body = hl["raw_md"][:2400] if hl["raw_md"] else "\n".join(f"- {b}" for b in hl["bullets"])
        parts.append(f"### {hl['title']} {hl['pill']} (PYQ hits: {hl['pyq_hits']})\n{body}")
    module_raw = "\n\n".join(parts)[:18000]

    prompt_hash = compute_prompt_hash(f"cram_pass1_v2|{course_title}|{module_name}|{module_raw}")
    if not force_refresh:
        cached = get_cached_response(db_conn, prompt_hash)
        if cached:
            return cached

    system_inst = (
        "You are an exam-prep distillation specialist. Compress this module into a razor-sharp, zero-fluff Fact Block "
        "preserving ALL exact formulas (KaTeX), complexities, comparison pairs, numerical steps, and `[MM:SS]` timestamps."
    )
    prompt = f"""Course: {course_title}
Module: {module_name}

Source Notes & Transcripts:
{module_raw}

Output a dense Markdown Fact Block (max 450 words) with:
- Exact definitions & rules `[MM:SS]`
- Formulas / complexities in KaTeX (`$...$`)
- Key comparisons / contrasts
- Common exam traps / edge cases
"""
    fact_block, model_used = await get_llm_gateway().generate_text(
        prompt=prompt,
        system_instruction=system_inst,
        json_mode=False,
        temperature=0.15,
        max_tokens=1500,
        user_secrets=user_secrets,
    )
    if fact_block:
        fact_block = _RAW_CHK_RE.sub("", fact_block).strip()
        try:
            set_cached_response(db_conn, prompt_hash, model_used or "gateway", fact_block)
        except Exception:
            pass
    return fact_block


async def generate_cram_sheet_with_llm(
    db_conn,
    course_id: str,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
    force_refresh: bool = False,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """2-Pass Map-Reduce Exam Cram Sheet Synthesis covering ALL modules without 24k truncation."""
    s = get_settings()
    if not (s.GEMINI_API_KEY or s.GROQ_API_KEY or s.OPENROUTER_API_KEY or s.OLLAMA_BASE_URL or user_secrets):
        return None

    c_row = db_conn.execute("SELECT title FROM courses WHERE id = ?;", (course_id,)).fetchone()
    course_title = (c_row[0] if c_row else "Course") or "Course"
    lessons = _fetch_scoped_lessons(db_conn, course_id, source_id=source_id, chapter_title=chapter_title)
    if not lessons:
        return None

    modules: Dict[str, List[Dict[str, Any]]] = {}
    for les in lessons:
        hl = _extract_lesson_highlights(db_conn, les)
        modules.setdefault(hl["module"], []).append(hl)

    # Pass 1 (Map): Compress EVERY module independently so zero units are ever truncated
    module_fact_blocks: List[str] = []
    for mod_name, mod_lessons in modules.items():
        fb = await _compress_module_pass1(
            db_conn, course_title, mod_name, mod_lessons, force_refresh=force_refresh, user_secrets=user_secrets
        )
        if fb:
            module_fact_blocks.append(f"## MODULE: {mod_name}\n{fb}")
        else:
            # Fallback compact digest for this module if a single pass-1 call fails
            lines = [f"## MODULE: {mod_name}"]
            for hl in mod_lessons:
                lines.append(f"- **{hl['title']}** {hl['pill']}: " + "; ".join(hl["bullets"][:2]))
            module_fact_blocks.append("\n".join(lines))

    pyqs = db_conn.execute(
        """
        SELECT pq.question_text, pq.marks, l.start_sec
        FROM pyq_questions pq
        LEFT JOIN lessons l ON l.id = pq.matched_lesson_id
        WHERE pq.course_id = ?
        ORDER BY pq.marks DESC, pq.id ASC LIMIT 12;
        """,
        (course_id,),
    ).fetchall()
    pyq_block = "\n".join(
        f"- {p[0]} ({p[1] or 'Exam Q'}) [{format_seconds_to_mm_ss(p[2])}]"
        for p in pyqs
    ) or "None uploaded yet."

    combined_facts = "\n\n".join(module_fact_blocks)
    scope_desc = f"Module: {chapter_title}" if chapter_title else ("Single Video" if source_id else "Full Course")

    # Pass 2 (Reduce): Synthesize Master A4 Cram Sheet
    system_inst = (
        "You are a senior university professor writing a razor-sharp, high-density Last-Night Exam Cram Sheet. "
        "Cover EVERY single module provided without omitting later units. Use crisp Markdown tables, KaTeX math (`$...$`), "
        "and clickable `[MM:SS]` timestamp jump pills. Never emit generic filler or raw chunk IDs."
    )
    prompt = f"""Course: {course_title} ({scope_desc} — {len(modules)} Modules, {len(lessons)} Topics)

Compressed Module Fact Blocks (ALL Modules Included):
{combined_facts}

Uploaded Past Exam Questions (PYQs):
{pyq_block}

Assemble the Master Last-Night Exam Cram Sheet with these 6 sections:
1. `## 1. High-Yield Exam Weightage Matrix` (Markdown table: Module | Key Exam Angles | Jump `[MM:SS]`)
2. `## 2. Master Formula, Theorem & Complexity Reference` (Compact KaTeX reference table)
3. `## 3. Core Distinctions & Comparison Matrices` (Side-by-side high-frequency exam comparisons)
4. `## 4. Module-by-Module Rapid Recall Sheet` (Cover ALL {len(modules)} modules with ultra-dense testable bullets + `[MM:SS]`)
5. `## 5. Step-by-Step Numerical / Derivation Recipes & Common Exam Traps`
6. `## 6. Top Repeated PYQs & 2-Line Model Answer Keys`
"""
    final_md, _ = await get_llm_gateway().generate_text(
        prompt=prompt,
        system_instruction=system_inst,
        json_mode=False,
        temperature=0.2,
        max_tokens=4096,
        user_secrets=user_secrets,
    )
    if final_md and len(final_md.strip()) >= 150:
        return _RAW_CHK_RE.sub("", final_md).strip()
    return None


async def synthesize_full_syllabus_cram_sheet(
    db_conn,
    course_id: str,
    batch_size: int = 5,
    prune_intermediate_chunks: bool = False,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Progressively ensures transcript + notes across all scoped lessons (NEVER deleting chunks) and runs 2-pass synthesis."""
    from backend.services.notes import get_or_generate_lesson_notes
    from backend.services.transcription import ingest_lesson_transcript

    lessons = _fetch_scoped_lessons(db_conn, course_id, source_id=source_id, chapter_title=chapter_title)
    for les in lessons:
        lid = les["id"]
        if not (les.get("content_markdown") or "").strip():
            c_cnt = db_conn.execute("SELECT COUNT(*) FROM chunks WHERE lesson_id = ?;", (lid,)).fetchone()[0]
            if c_cnt == 0 and (les.get("video_id") or les.get("source_url")):
                try:
                    await ingest_lesson_transcript(
                        db_conn,
                        course_id=course_id,
                        source_id=les.get("source_id") or None,
                        lesson_id=lid,
                        video_id_or_url=les.get("video_id") or les.get("source_url"),
                        start_sec=int(les.get("start_sec") or 0),
                        end_sec=int(les["end_sec"]) if les.get("end_sec") else None,
                    )
                except Exception as te:
                    logger.warning(f"[CramSheet] Transcript ingest error for {les['title']}: {te}")
            try:
                await get_or_generate_lesson_notes(db_conn, course_id, lid, force_regenerate=False, user_secrets=user_secrets)
            except Exception as ne:
                logger.warning(f"[CramSheet] Note synthesis error for {les['title']}: {ne}")

    return await get_or_create_cram_sheet(
        db_conn,
        course_id,
        force_refresh=True,
        full_syllabus=False,
        source_id=source_id,
        chapter_title=chapter_title,
        user_secrets=user_secrets,
    )


async def get_or_create_cram_sheet(
    db_conn,
    course_id: str,
    force_refresh: bool = False,
    full_syllabus: bool = False,
    source_id: Optional[str] = None,
    chapter_title: Optional[str] = None,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Retrieves cached Cram Sheet or generates via 2-pass Map-Reduce synthesis."""
    if full_syllabus:
        return await synthesize_full_syllabus_cram_sheet(
            db_conn,
            course_id,
            source_id=source_id,
            chapter_title=chapter_title,
            user_secrets=user_secrets,
        )

    notes_hash = compute_course_notes_hash(db_conn, course_id, source_id=source_id, chapter_title=chapter_title)
    is_full_course = not source_id and not chapter_title

    if is_full_course and not force_refresh:
        existing = db_conn.execute("SELECT * FROM cram_sheets WHERE course_id = ?;", (course_id,)).fetchone()
        if existing:
            cur_cs = db_conn.execute("SELECT id, course_id, content_markdown, notes_hash, is_generated_by_llm, created_at, updated_at FROM cram_sheets WHERE course_id = ?;", (course_id,)).fetchone()
            if cur_cs and cur_cs[3] == notes_hash and (cur_cs[2] or "").strip():
                return {
                    "id": cur_cs[0],
                    "course_id": cur_cs[1],
                    "content_markdown": cur_cs[2],
                    "notes_hash": cur_cs[3],
                    "is_generated_by_llm": bool(cur_cs[4]),
                    "cached": True,
                    "created_at": cur_cs[5],
                    "updated_at": cur_cs[6],
                }

    llm_md = await generate_cram_sheet_with_llm(
        db_conn,
        course_id,
        source_id=source_id,
        chapter_title=chapter_title,
        force_refresh=force_refresh,
        user_secrets=user_secrets,
    )
    if llm_md:
        content_md = llm_md
        is_llm = True
    else:
        content_md = generate_deterministic_cram_sheet(
            db_conn, course_id, source_id=source_id, chapter_title=chapter_title
        )
        is_llm = False

    now_iso = datetime.now(timezone.utc).isoformat()
    sheet_id = f"cram_{uuid.uuid4().hex[:10]}"

    if is_full_course:
        existing = db_conn.execute("SELECT id, created_at FROM cram_sheets WHERE course_id = ?;", (course_id,)).fetchone()
        if existing:
            sheet_id = existing[0]
            db_conn.execute(
                """
                UPDATE cram_sheets
                SET content_markdown = ?, notes_hash = ?, is_generated_by_llm = ?, updated_at = ?
                WHERE id = ?;
                """,
                (content_md, notes_hash, int(is_llm), now_iso, sheet_id),
            )
            created_at = existing[1]
        else:
            db_conn.execute(
                """
                INSERT INTO cram_sheets (id, course_id, content_markdown, notes_hash, is_generated_by_llm, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (sheet_id, course_id, content_md, notes_hash, int(is_llm), now_iso, now_iso),
            )
            created_at = now_iso
        db_conn.commit()
    else:
        created_at = now_iso

    return {
        "id": sheet_id,
        "course_id": course_id,
        "content_markdown": content_md,
        "notes_hash": notes_hash,
        "is_generated_by_llm": is_llm,
        "cached": False,
        "created_at": created_at,
        "updated_at": now_iso,
    }
