"""Last-Night Cram Sheet Synthesis Service.

Condenses course lesson notes, transcript chunks, high-yield PYQ patterns, essential
definitions, LaTeX formulas, algorithms, worked examples, and comparison tables into a
genuinely useful, print-ready 1-2 page revision cheat sheet — with ZERO generic boilerplate.
Cached in SQLite by SHA-256 hash of underlying notes, chunks, and PYQs.
"""

import hashlib
import logging
import re
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from backend.config import get_settings
from backend.infra.llm_gateway import get_llm_gateway

logger = logging.getLogger("learn_lms.cram_sheet")


def format_seconds_to_mm_ss(seconds: Optional[int]) -> str:
    """Formats integer seconds to [MM:SS] or [HH:MM:SS]."""
    if seconds is None:
        return "[00:00]"
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def compute_course_notes_hash(db_conn, course_id: str) -> str:
    """Computes SHA-256 hash across course title, target date, lesson notes, chunks, and PYQs."""
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
        (course_id,),
    )
    notes_parts = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0)
        FROM chunks
        WHERE course_id = ?;
        """,
        (course_id,),
    )
    ch_row = cur.fetchone()
    chunk_sig = f"{ch_row[0] if ch_row else 0}:{ch_row[1] if ch_row else 0}"

    cur.execute(
        """
        SELECT question_text, marks
        FROM pyq_questions
        WHERE course_id = ?
        ORDER BY id ASC;
        """,
        (course_id,),
    )
    pyq_parts = [f"{r[0]}:{r[1]}" for r in cur.fetchall()]

    full_payload = "v2||" + c_info + "||" + chunk_sig + "||" + "||".join(notes_parts) + "||" + "||".join(pyq_parts)
    return hashlib.sha256(full_payload.encode("utf-8")).hexdigest()


def _extract_structured_elements(md: str, fallback_pill: str) -> Dict[str, Any]:
    """Extract real definitions, formulas, callouts, tables, and concise key points from lesson notes."""
    definitions: List[str] = []
    formulas: List[str] = []
    key_points: List[str] = []
    tables: List[str] = []
    callouts: List[str] = []

    if not md:
        return {
            "definitions": definitions,
            "formulas": formulas,
            "key_points": key_points,
            "tables": tables,
            "callouts": callouts,
        }

    lines = md.split("\n")
    in_table = False
    cur_table: List[str] = []
    in_math_block = False
    cur_math: List[str] = []
    in_code_block = False

    for raw_line in lines:
        s = raw_line.strip()

        if s.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Capture display LaTeX blocks $$...$$
        if s.startswith("$$"):
            if s.endswith("$$") and len(s) > 4:
                formulas.append(f"{s} {fallback_pill}")
            else:
                if in_math_block:
                    cur_math.append(s)
                    formulas.append(" ".join(cur_math) + f" {fallback_pill}")
                    cur_math = []
                    in_math_block = False
                else:
                    in_math_block = True
                    cur_math = [s]
            continue
        if in_math_block:
            cur_math.append(s)
            continue

        # Capture Markdown tables
        if s.startswith("|") and s.endswith("|"):
            in_table = True
            cur_table.append(s)
            continue
        elif in_table:
            if len(cur_table) >= 3:
                tables.append("\n".join(cur_table))
            cur_table = []
            in_table = False

        # Skip metadata/headers/horizontal rules/HTML comments
        if not s or s.startswith("#") or s.startswith("---") or s.startswith("<!--") or s.startswith("!["):
            continue
        if "Grounded strictly across" in s or "Concept Clip Time Range" in s or s.startswith("- Sources:"):
            continue

        # Capture callout lines (> **Exam Tip**, > [!IMPORTANT] content)
        if s.startswith(">"):
            clean_q = s.lstrip(">").strip()
            if clean_q and not clean_q.startswith("[!"):
                callouts.append(clean_q)
            continue

        # Inline LaTeX / formula equations
        if ("$" in s and re.search(r"\$[^$]+\$", s)) or re.search(r"[=→∈∀∃∑∏δΣΓΩΘ≤≥≠]|O\([^)]+\)", s):
            clean_f = re.sub(r"^[-*•]\s+", "", s)
            if 8 <= len(clean_f) <= 240:
                if "[" not in clean_f:
                    clean_f = f"{clean_f} {fallback_pill}"
                formulas.append(clean_f)

        # Bold definitions: - **Term**: explanation
        m_def = re.match(r"^[-*•]\s+(?:\[[\d:]+\]\s*)?\*\*([^*]{2,60})\*\*\s*[:—-]\s*(.+)$", s)
        if m_def:
            term, desc = m_def.group(1).strip(), m_def.group(2).strip()
            if term.lower() not in {"sources", "concept clip time range", "note", "tip"} and len(desc) >= 12:
                pill_part = "" if re.search(r"\[\d{1,2}:\d{2}", desc) else f" {fallback_pill}"
                definitions.append(f"- **{term}**: {desc[:220]}{pill_part}")
                continue

        # Numbered steps or concise bullets
        if re.match(r"^([-*•]|\d+\.)\s+", s) and 18 <= len(s) <= 240:
            cleaned = re.sub(r"^[-*•]\s+", "- ", s)
            if not re.search(r"\[\d{1,2}:\d{2}", cleaned):
                cleaned = f"{cleaned} {fallback_pill}"
            key_points.append(cleaned)

    if in_table and len(cur_table) >= 3:
        tables.append("\n".join(cur_table))

    return {
        "definitions": definitions,
        "formulas": formulas,
        "key_points": key_points,
        "tables": tables,
        "callouts": callouts,
    }


def _extract_transcript_highlights(db_conn, lesson_id: str) -> List[str]:
    """When lesson notes aren't generated yet, extract real high-signal sentences from transcript chunks."""
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT start_sec, content
        FROM chunks
        WHERE lesson_id = ?
        ORDER BY chunk_index ASC
        LIMIT 8;
        """,
        (lesson_id,),
    )
    rows = cur.fetchall()
    highlights: List[str] = []
    signal_re = re.compile(
        r"\b(defined as|definition|consists of|formula|equation|theorem|lemma|property|complexity|difference between|whereas|algorithm|step|means that|transition|important|remember|exam|rule|condition)\b",
        re.IGNORECASE,
    )
    for start_sec, content in rows:
        if not content:
            continue
        pill = format_seconds_to_mm_ss(start_sec)
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        for sent in sentences:
            s = sent.strip()
            if 35 <= len(s) <= 220 and (signal_re.search(s) or len(highlights) < 2):
                highlights.append(f"- {pill} {s}")
                if len(highlights) >= 3:
                    return highlights
    return highlights


def _build_structured_digest(db_conn, course_id: str) -> Tuple[str, Dict[str, Any]]:
    """Collect real notes, transcript excerpts, topics, and PYQs for both deterministic and LLM synthesis."""
    cur = db_conn.cursor()
    cur.execute("SELECT title, target_date FROM courses WHERE id = ?;", (course_id,))
    c_row = cur.fetchone()
    course_title = (c_row[0] if c_row else "Course") or "Course"
    target_date = (c_row[1] if c_row else "Upcoming") or "Upcoming"

    cur.execute(
        """
        SELECT l.id, l.title, l.chapter_title, l.pyq_hit_count, l.pyq_total_marks,
               n.content_markdown, l.start_sec, l.end_sec, l.is_excluded
        FROM lessons l
        LEFT JOIN notes n ON l.id = n.lesson_id
        WHERE l.course_id = ? AND COALESCE(l.is_excluded, 0) = 0
        ORDER BY l.order_index ASC;
        """,
        (course_id,),
    )
    lessons = cur.fetchall()

    cur.execute(
        """
        SELECT q.question_number, q.question_text, q.marks, p.title as paper_title, l.title as lesson_title, l.start_sec
        FROM pyq_questions q
        LEFT JOIN pyq_papers p ON q.paper_id = p.id
        LEFT JOIN lessons l ON q.matched_lesson_id = l.id
        WHERE q.course_id = ?
        ORDER BY q.marks DESC NULLS LAST, COALESCE(l.pyq_hit_count, 0) DESC
        LIMIT 15;
        """,
        (course_id,),
    )
    top_pyqs = cur.fetchall()

    # Group lessons by chapter_title (Topic Group)
    topics: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    studied_count = 0
    pending_titles: List[str] = []

    for row in lessons:
        lid, title, chapter_title, hits, marks, md, start_sec, end_sec, _ = row
        pill = format_seconds_to_mm_ss(start_sec or 0)
        topic_name = (chapter_title or "").strip() or re.sub(r"\|.*$", "", title).strip()

        extracted = _extract_structured_elements(md or "", pill)
        transcript_pts: List[str] = []
        has_real_content = bool(
            extracted["definitions"] or extracted["formulas"] or extracted["key_points"] or extracted["tables"]
        )
        if not has_real_content:
            transcript_pts = _extract_transcript_highlights(db_conn, lid)
            has_real_content = bool(transcript_pts)

        if has_real_content:
            studied_count += 1
        else:
            pending_titles.append(f"{pill} {title}")

        topics.setdefault(topic_name, []).append(
            {
                "id": lid,
                "title": title,
                "pill": pill,
                "hits": hits or 0,
                "marks": marks or 0,
                "extracted": extracted,
                "transcript_pts": transcript_pts,
                "has_real_content": has_real_content,
            }
        )

    # Build a clean, high-density digest for the LLM (up to 24,000 chars)
    digest_lines: List[str] = [f"Course: {course_title} | Exam Date: {target_date}"]
    for topic_name, items in topics.items():
        total_hits = sum(i["hits"] for i in items)
        total_marks = sum(i["marks"] for i in items)
        digest_lines.append(f"\n### TOPIC: {topic_name} (PYQ hits: {total_hits}, marks: {total_marks})")
        for item in items:
            if not item["has_real_content"]:
                continue
            digest_lines.append(f"Lesson {item['pill']} {item['title']}:")
            for d in item["extracted"]["definitions"][:4]:
                digest_lines.append(d)
            for f in item["extracted"]["formulas"][:3]:
                digest_lines.append(f"- FORMULA: {f}")
            for t in item["extracted"]["tables"][:2]:
                digest_lines.append(t)
            for k in item["extracted"]["key_points"][:3]:
                digest_lines.append(k)
            for tp in item["transcript_pts"][:3]:
                digest_lines.append(tp)

    if top_pyqs:
        digest_lines.append("\n### PAST EXAM QUESTIONS (PYQs):")
        for q_num, q_text, marks, paper, l_title, l_start in top_pyqs:
            pill = format_seconds_to_mm_ss(l_start)
            digest_lines.append(f"- {q_num or 'Q'} [{marks or '?'}M] ({l_title or 'General'} {pill}): {q_text}")

    meta = {
        "course_title": course_title,
        "target_date": target_date,
        "topics": topics,
        "top_pyqs": top_pyqs,
        "total_lessons": len(lessons),
        "studied_count": studied_count,
        "pending_titles": pending_titles,
    }
    return "\n".join(digest_lines), meta


def generate_deterministic_cram_sheet(db_conn, course_id: str) -> str:
    """Deterministically compiles a genuinely useful, zero-boilerplate Cram Sheet from notes, transcripts & PYQs."""
    _, meta = _build_structured_digest(db_conn, course_id)
    course_title = meta["course_title"]
    target_date = meta["target_date"]
    topics = meta["topics"]
    top_pyqs = meta["top_pyqs"]
    total_lessons = meta["total_lessons"]
    studied_count = meta["studied_count"]
    pending_titles = meta["pending_titles"]

    lines: List[str] = []
    lines.append(f"# {course_title} — Last-Night Exam Cram Sheet\n")
    lines.append(
        f"> [!IMPORTANT]\n"
        f"> **Exam Date:** {target_date} • **Grounded Coverage:** {studied_count}/{total_lessons} lessons synthesized • "
        f"Click any `[MM:SS]` pill to jump straight to that moment in the lecture.\n"
    )

    if studied_count == 0:
        lines.append(
            "> [!TIP]\n"
            "> No lesson notes or transcripts have been generated yet. Click **Synthesize Full Syllabus** above "
            "to automatically transcribe your lectures and build a complete formula & concept cheat sheet.\n"
        )

    # 1. High-Yield Topic Priority Matrix (grouped by Topic, not 50 noisy rows)
    lines.append("## ⚡ High-Yield Exam Weightage Matrix\n")
    lines.append("| Topic Unit | Lessons | Exam Priority | PYQ Hits / Marks | Jump |")
    lines.append("| :--- | :---: | :--- | :---: | :---: |")
    for topic_name, items in topics.items():
        total_hits = sum(i["hits"] for i in items)
        total_marks = sum(i["marks"] for i in items)
        first_pill = items[0]["pill"]
        if total_hits >= 2 or total_marks >= 10:
            priority = "**HIGH YIELD 🔥**"
        elif total_hits == 1:
            priority = "Medium Yield"
        else:
            priority = "Core Syllabus"
        pyq_str = f"{total_hits} Qs ({total_marks}M)" if total_hits > 0 else "—"
        lines.append(f"| {topic_name} | {len(items)} | {priority} | {pyq_str} | {first_pill} |")
    lines.append("")

    # 2. Key Formulas, Formal Rules & Complexity Cheatsheet
    all_formulas: List[str] = []
    seen_f = set()
    for topic_name, items in topics.items():
        for item in items:
            for f in item["extracted"]["formulas"]:
                key = f.lower()[:60]
                if key not in seen_f:
                    seen_f.add(key)
                    all_formulas.append(f"- **{topic_name}**: {f}")

    if all_formulas:
        lines.append("## 📐 Must-Know Formulas, Formal Tuples & Rules\n")
        for f_line in all_formulas[:18]:
            lines.append(f_line)
        lines.append("")

    # 3. Topic-by-Topic Rapid Revision Breakdown (ONLY real extracted content — ZERO filler!)
    lines.append("## 📐 Essential Key Formulas, Definitions & Rapid Revision\n")
    tables_collected: List[Tuple[str, str, str]] = []

    for topic_name, items in topics.items():
        real_items = [i for i in items if i["has_real_content"]]
        if not real_items:
            continue

        total_hits = sum(i["hits"] for i in real_items)
        badge = " 🔥" if total_hits > 0 else ""
        lines.append(f"### {topic_name}{badge}\n")

        for item in real_items:
            ex = item["extracted"]
            for tbl in ex["tables"]:
                tables_collected.append((topic_name, item["pill"], tbl))

            # Prefer formal definitions, then key points, then transcript highlights
            emitted = 0
            for d in ex["definitions"][:3]:
                lines.append(d)
                emitted += 1
            for k in ex["key_points"][:3]:
                if emitted >= 5:
                    break
                lines.append(k)
                emitted += 1
            if emitted == 0:
                for tp in item["transcript_pts"][:3]:
                    lines.append(tp)
                    emitted += 1
            for c in ex["callouts"][:1]:
                lines.append(f"> **Exam Trap / Note ({item['pill']}):** {c}")
        lines.append("")

    # 4. Comparison & Distinction Tables
    if tables_collected:
        lines.append("## 📊 Key Comparison & Complexity Tables\n")
        for t_name, t_pill, tbl in tables_collected[:6]:
            lines.append(f"#### {t_name} {t_pill}\n{tbl}\n")

    # 5. Real Past Exam Questions (PYQs)
    if top_pyqs:
        lines.append("## 🎯 Past Exam Questions (PYQ Focus)\n")
        for q_num, q_text, marks, paper, l_title, l_start in top_pyqs[:10]:
            mark_tag = f"[{marks}M]" if marks else ""
            pill = format_seconds_to_mm_ss(l_start)
            loc = f"({l_title} {pill})" if l_title else ""
            lines.append(f"- **{q_num or 'Q'} {mark_tag}** {loc}: {q_text}")
        lines.append("")

    # 6. Pending lessons disclosure (transparent instead of fake boilerplate)
    if pending_titles:
        lines.append("## ⏳ Lessons Pending Notes Synthesis\n")
        preview = ", ".join(pending_titles[:10])
        more = f" (+{len(pending_titles) - 10} more)" if len(pending_titles) > 10 else ""
        lines.append(
            f"Run **Synthesize Full Syllabus** to automatically include these unstudied lessons: {preview}{more}.\n"
        )

    return "\n".join(lines)


async def generate_cram_sheet_with_llm(
    course_title: str,
    target_date: str,
    raw_content_summary: str,
) -> Optional[str]:
    """Generates a genuinely exam-ready Cram Sheet using the unified LLM gateway."""
    settings = get_settings()
    import os
    if not (settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY or os.getenv('OLLAMA_BASE_URL')):
        return None

    system_instruction = (
        "You are a top university computer science & engineering exam strategist. "
        "Create a razor-sharp, high-density, print-ready 1-2 page Last-Night Exam Cram Sheet in Markdown "
        "strictly grounded in the provided course digest.\n\n"
        "STRICT QUALITY RULES:\n"
        "1. NEVER write generic filler or vague advice (e.g., never write 'understand foundational concepts' or 'master properties'). "
        "Every single bullet must state a concrete definition, formula, theorem, complexity, algorithm step, edge case, or comparison.\n"
        "2. Preserve clickable `[MM:SS]` timestamp pills from the source material next to each major concept and formula.\n"
        "3. Organize into these exact high-yield sections:\n"
        "   - `# <Subject> — Last-Night Exam Cram Sheet` + Exam Date callout\n"
        "   - `## ⚡ High-Yield Exam Weightage Matrix` (compact table: Topic | Priority | Key Exam Angle | Jump `[MM:SS]`)\n"
        "   - `## 📐 Core Formulas, Formal Definitions & Complexities` (use clean LaTeX `$...$` where helpful)\n"
        "   - `## 📊 Must-Know Comparison & Distinction Tables` (at least 1–2 crisp Markdown tables contrasting key concepts from the syllabus)\n"
        "   - `## 🧠 Step-by-Step Algorithms, Worked Patterns & Common Exam Traps` (concise numbered steps + `> [!IMPORTANT]` traps)\n"
        "   - `## 🎯 Past-Paper / Rapid-Fire Recall Check` (real PYQs if provided, or 5 rapid self-test prompts with 1-line answers)\n"
        "4. Keep total length tight and scannable so it prints cleanly onto 1–2 A4 pages."
    )

    user_prompt = (
        f"Subject: {course_title}\n"
        f"Target Exam Date: {target_date}\n\n"
        f"Grounded Course Digest:\n{raw_content_summary[:24000]}"
    )

    try:
        result, _ = await get_llm_gateway().generate_text(
            prompt=user_prompt,
            system_instruction=system_instruction,
            temperature=0.2,
        )
        if result and len(result.strip()) > 200:
            return result.strip()
    except Exception as e:
        logger.warning(f"LLM cram sheet generation failed, falling back to deterministic: {e}")

    return None


async def synthesize_full_syllabus_cram_sheet(
    db_conn,
    course_id: str,
    batch_size: int = 5,
    prune_intermediate_chunks: bool = True,
) -> Dict[str, Any]:
    """Progressively transcribes and synthesizes notes across the entire playlist/syllabus in batches of 3-5,
    pruning intermediate raw transcript chunks for older batches on large playlists,
    and produces a comprehensive full-course revision cheat sheet.
    """
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT l.id, l.title, l.video_id, l.source_id, l.order_index, s.url, n.content_markdown, l.start_sec, l.end_sec
        FROM lessons l
        LEFT JOIN sources s ON l.source_id = s.id
        LEFT JOIN notes n ON l.id = n.lesson_id
        WHERE l.course_id = ? AND COALESCE(l.is_excluded, 0) = 0
        ORDER BY l.order_index ASC;
        """,
        (course_id,),
    )
    lessons = cur.fetchall()
    if not lessons:
        raise ValueError(f"No lessons found for course {course_id}")

    missing_lessons = [l for l in lessons if not l[6]]
    logger.info(f"[CramSheet] Full-syllabus synthesis: {len(lessons)} total lessons, {len(missing_lessons)} missing notes.")

    if missing_lessons:
        from backend.services.transcription import ingest_lesson_transcript
        from backend.services.notes import get_or_generate_lesson_notes

        for i in range(0, len(missing_lessons), batch_size):
            batch = missing_lessons[i:i + batch_size]
            for row in batch:
                lid, title, vid_id, src_id, ord_idx, s_url, _, l_start, l_end = row
                target_vid = vid_id or s_url or ""
                cur.execute("SELECT COUNT(*) FROM chunks WHERE lesson_id = ?;", (lid,))
                if cur.fetchone()[0] == 0 and target_vid:
                    try:
                        await ingest_lesson_transcript(
                            db_conn,
                            course_id=course_id,
                            source_id=src_id or None,
                            lesson_id=lid,
                            video_id_or_url=target_vid,
                            start_sec=int(l_start or 0),
                            end_sec=int(l_end) if l_end else None,
                        )
                    except Exception as te:
                        logger.warning(f"[CramSheet] Transcript ingest error for {title}: {te}")

                try:
                    await get_or_generate_lesson_notes(db_conn, course_id, lid, force_regenerate=False)
                except Exception as ne:
                    logger.warning(f"[CramSheet] Note synthesis error for {title}: {ne}")

            if prune_intermediate_chunks and len(lessons) > 15:
                batch_lids = [b[0] for b in batch]
                placeholders = ",".join(["?"] * len(batch_lids))
                cur.execute(f"DELETE FROM chunks WHERE lesson_id IN ({placeholders});", batch_lids)
                db_conn.commit()

    return await get_or_create_cram_sheet(db_conn, course_id, force_refresh=True)


async def get_or_create_cram_sheet(
    db_conn,
    course_id: str,
    force_refresh: bool = False,
    full_syllabus: bool = False,
) -> Dict[str, Any]:
    """Retrieves existing cram sheet if hash matches, or synthesizes a fresh one."""
    if full_syllabus:
        return await synthesize_full_syllabus_cram_sheet(db_conn, course_id)

    current_hash = compute_course_notes_hash(db_conn, course_id)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT id, content_markdown, notes_hash, is_generated_by_llm, created_at, updated_at FROM cram_sheets WHERE course_id = ?;",
        (course_id,),
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
                "cached": True,
            }

    digest, meta = _build_structured_digest(db_conn, course_id)
    course_title = meta["course_title"]
    target_date = meta["target_date"]

    deterministic_content = generate_deterministic_cram_sheet(db_conn, course_id)
    content = deterministic_content
    is_llm = 0

    if meta["studied_count"] > 0:
        llm_content = await generate_cram_sheet_with_llm(course_title, target_date, digest)
        if llm_content and len(llm_content.strip()) > 200:
            content = llm_content
            is_llm = 1

    sheet_id = existing[0] if existing else f"cram_{uuid.uuid4().hex[:10]}"
    if existing:
        cur.execute(
            """
            UPDATE cram_sheets
            SET content_markdown = ?, notes_hash = ?, is_generated_by_llm = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (content, current_hash, is_llm, sheet_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO cram_sheets (id, course_id, content_markdown, notes_hash, is_generated_by_llm)
            VALUES (?, ?, ?, ?, ?);
            """,
            (sheet_id, course_id, content, current_hash, is_llm),
        )

    db_conn.commit()

    cur.execute("SELECT created_at, updated_at FROM cram_sheets WHERE id = ?;", (sheet_id,))
    ts_row = cur.fetchone()
    return {
        "id": sheet_id,
        "course_id": course_id,
        "content_markdown": content,
        "notes_hash": current_hash,
        "is_generated_by_llm": bool(is_llm),
        "cached": False,
        "created_at": ts_row[0] if ts_row else None,
        "updated_at": ts_row[1] if ts_row else None,
    }
