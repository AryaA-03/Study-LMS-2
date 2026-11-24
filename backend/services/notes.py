"""GeeksforGeeks-Grade Standalone Notes Synthesis Service.

Generates readable, exam-focused standalone study notes strictly grounded in
the lesson's transcript slice via the unified async LLMGateway (with 429 pacing,
configured models, Ollama fallback, and max_tokens=4096).
"""

import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config import get_settings
settings = get_settings()
from backend.infra.llm_gateway import get_llm_gateway
from backend.services.llm_cache import compute_prompt_hash, get_cached_response, set_cached_response
from backend.services.smart_prepare import is_placeholder_lesson_title

logger = logging.getLogger("learn_lms.notes")

_CONVERSATIONAL_PREAMBLE_RE = re.compile(
    r"^(?:(?:sure|certainly|here are|below are|as an expert|as a professor|okay)[^\n]*\n+)+",
    re.IGNORECASE,
)
_REF_WITH_TS_RE = re.compile(r"\[ref:[^,\]]+,\s*(\d{1,2}:\d{2}(?::\d{2})?)\]", re.IGNORECASE)
_REF_BARE_RE = re.compile(r"\[ref:[^\]]+\]", re.IGNORECASE)
_RAW_CHK_LINE_RE = re.compile(r"(?m)^\s*[-*]\s*Sources:\s*chk_[^\n]*\n?")
_RAW_CHK_INLINE_RE = re.compile(r"\bchk_[a-f0-9]{4,}\b", re.IGNORECASE)


def format_seconds_to_mm_ss(seconds: Optional[int]) -> str:
    """Formats seconds to [MM:SS] or [HH:MM:SS] timestamp string."""
    if seconds is None or seconds < 0:
        return "[00:00]"
    sec = int(seconds)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def _clean_generated_markdown(md: str) -> str:
    """Strip conversational preambles and internal chunk IDs while preserving clean [MM:SS] pills."""
    out = (md or "").strip()
    if out.startswith("```markdown"):
        out = re.sub(r"^```markdown\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    elif out.startswith("```"):
        out = re.sub(r"^```\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    out = _CONVERSATIONAL_PREAMBLE_RE.sub("", out).strip()
    out = _REF_WITH_TS_RE.sub(r"[\1]", out)
    out = _REF_BARE_RE.sub("", out)
    out = _RAW_CHK_LINE_RE.sub("", out)
    out = _RAW_CHK_INLINE_RE.sub("", out)
    return out.strip()


def _extract_h1_title(md: str) -> Optional[str]:
    for line in (md or "").splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            cand = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", "", m.group(1)).strip(" -–—:*`")
            if 4 <= len(cand) <= 110 and not is_placeholder_lesson_title(cand):
                return cand
    return None


def _has_any_llm_key() -> bool:
    s = get_settings()
    return bool(s.GEMINI_API_KEY or s.GROQ_API_KEY or s.OPENROUTER_API_KEY)


def generate_no_key_structured_notes(
    lesson_title: str,
    chunks: List[Dict[str, Any]],
    screenshots: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Honest, clean Timestamped Transcript Study Outline (Zero hardcoded subject boilerplate)."""
    if not chunks:
        return (
            f"# {lesson_title}\n\n"
            "> [!NOTE] No transcript or captions have been extracted for this clip yet. "
            "Use **Transcribe** in the lesson menu to fetch subtitles and generate full study notes.\n"
        )

    lines: List[str] = [
        f"# {lesson_title}",
        "",
        "> [!NOTE] **Transcript Study Outline (Offline No-Key Mode)** — Add a free Gemini, Groq, OpenRouter, or local Ollama key in **Settings** to automatically upgrade this outline into full GeeksforGeeks-style tutorial notes.",
        "",
    ]

    grouped: List[Dict[str, Any]] = []
    bucket_sec = 120
    for ch in chunks:
        st = int(ch.get("start_sec") or 0)
        text = re.sub(r"\s+", " ", (ch.get("content") or "").strip())
        text = _RAW_CHK_INLINE_RE.sub("", text).strip()
        if not text:
            continue
        if not grouped or (st - grouped[-1]["start_sec"]) >= bucket_sec:
            grouped.append({"start_sec": st, "texts": [text]})
        else:
            grouped[-1]["texts"].append(text)

    definitions: List[str] = []
    equations: List[str] = []
    seen_defs = set()
    for g in grouped:
        pill = format_seconds_to_mm_ss(g['start_sec'])
        joined = " ".join(g["texts"])
        for sent in re.split(r"(?<=[.!?।])\s+", joined):
            s_clean = sent.strip()
            if len(s_clean) < 25 or len(s_clean) > 240:
                continue
            low = s_clean.lower()
            if any(k in low for k in (" is defined as ", " refers to ", " means ", " stands for ", " denotes ")) and len(definitions) < 5:
                key = low[:45]
                if key not in seen_defs:
                    seen_defs.add(key)
                    definitions.append(f"- {s_clean} {pill}")
            if ("=" in s_clean or "O(" in s_clean) and re.search(r"[A-Za-z]\s*=\s*[A-Za-z0-9(]|O\([^)]+\)", s_clean) and len(equations) < 5:
                equations.append(f"- `{s_clean}` {pill}")

    if definitions:
        lines.append("## Key Definitions Mentioned")
        lines.extend(definitions)
        lines.append("")

    if equations:
        lines.append("## Formulas & Complexity Expressions")
        lines.extend(equations)
        lines.append("")

    lines.append("## Timestamped Lecture Outline")
    for idx, g in enumerate(grouped, start=1):
        pill = format_seconds_to_mm_ss(g['start_sec'])
        body = " ".join(g["texts"])
        sentences = [s.strip() for s in re.split(r"(?<=[.!?।])\s+", body) if len(s.strip()) >= 15]
        lines.append(f"### Segment {idx} {pill}")
        if sentences:
            for s in sentences[:5]:
                lines.append(f"- {s}")
        else:
            lines.append(f"- {body[:400]}")
        lines.append("")

    if screenshots:
        lines.append("## Captured Slides & Keyframes")
        for sc in screenshots:
            cap = sc.get("caption") or f"Slide {sc.get('formatted_time', '')}"
            url = sc.get("url") or ""
            if url:
                lines.append(f"![{cap}]({url})")
        lines.append("")
    return "\n".join(lines).strip()


async def generate_llm_structured_notes(
    lesson_title: str,
    chunks: List[Dict[str, Any]],
    db_conn: Optional[sqlite3.Connection] = None,
    bypass_cache: bool = False,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Generates standalone GeeksforGeeks-grade tutorial notes via unified LLMGateway (max_tokens=4096)."""
    if not chunks:
        return None

    context_lines: List[str] = []
    total_chars = 0
    for ch in chunks:
        ts_str = format_seconds_to_mm_ss(ch.get("start_sec"))
        content = (ch.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        line = f"{ts_str} {content}"
        if total_chars + len(line) + 1 > 18000:
            break
        context_lines.append(line)
        total_chars += len(line) + 1

    context_block = "\n".join(context_lines)
    if not context_block.strip():
        return None

    s = get_settings()
    active_model = s.GEMINI_MODEL if s.GEMINI_API_KEY else (
        s.GROQ_MODEL if s.GROQ_API_KEY else (
            s.OPENROUTER_MODEL if s.OPENROUTER_API_KEY else s.OLLAMA_MODEL
        )
    )
    prompt_hash = compute_prompt_hash(f"gfg_notes_v3|{active_model}|{lesson_title}|{context_block}")
    if db_conn is not None and not bypass_cache:
        cached = get_cached_response(db_conn, prompt_hash)
        if cached:
            cleaned_c = _clean_generated_markdown(cached)
            if len(cleaned_c) >= 20:
                return cleaned_c

    system_instruction = (
        "You are a world-class university CS & engineering textbook author (GeeksforGeeks / MIT OCW editorial standard). "
        "Write crisp, standalone study notes strictly grounded in the provided lecture transcript slice so the student can master the topic WITHOUT needing to rewatch the video. "
        "NEVER invent concepts absent from the transcript. NEVER write conversational intros ('Sure, here are...'). "
        "NEVER include raw chunk IDs like 'chk_001'. Cite exact timestamps using clean `[MM:SS]` format."
    )

    prompt = f"""Lesson Label: {lesson_title}

Timestamped Lecture Transcript Slice:
{context_block}

Write complete, high-clarity standalone Markdown notes following this adaptive editorial structure:
1. `# <Specific Concept Title>` — A sharp, scannable 4-8 word topic title describing the exact concept taught (never use generic 'Part N' or timestamp ranges in the H1).
2. `> [!IMPORTANT]` — 2-3 sentence **TL;DR & Exam Relevance** summarizing what is tested and why this concept matters.
3. `## Core Intuition & How It Works` — Clear conceptual explanation with clickable `[MM:SS]` anchors. Include a clean ASCII diagram/flow ONLY if explaining a data structure, state machine, memory layout, or pipeline.
4. `## Formal Definitions, Rules & Formulas` — Exact terminology, KaTeX math (`$...$` / `$$...$$`), and syntax/code blocks ONLY when actually taught in this clip.
5. `## Worked Example / Step-by-Step Trace` — Include ONLY if the lecturer works through an example, numerical, or derivation; show concrete inputs, intermediate steps, and final result with `[MM:SS]`. Skip this section if purely conceptual.
6. `## Key Distinctions & Exam Traps` — Use a clean Markdown comparison table ONLY when genuinely comparing >=2 concepts, modes, or complexities; otherwise use crisp `> [!TIP]` exam-trap bullets.
7. `## Quick Exam Revision Recap` — 4-6 high-density recall bullets with `[MM:SS]` jump links.
"""

    raw_md, model_used = await get_llm_gateway().generate_text(
        prompt=prompt,
        system_instruction=system_instruction,
        json_mode=False,
        temperature=0.2,
        max_tokens=4096,
        user_secrets=user_secrets,
    )
    if not raw_md:
        return None

    cleaned = _clean_generated_markdown(raw_md)
    if len(cleaned) < 20:
        return None

    if db_conn is not None:
        try:
            set_cached_response(db_conn, prompt_hash, model_used or active_model, cleaned)
        except Exception:
            pass
    return cleaned


async def get_or_generate_lesson_notes(
    db_conn: sqlite3.Connection,
    course_id: str,
    lesson_id: str,
    force_regenerate: bool = False,
    user_secrets: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Retrieves existing notes or synthesizes standalone GfG notes, auto-upgrading stale deterministic notes & placeholder titles."""
    db = db_conn
    cur = db.cursor()

    cur.execute(
        """
        SELECT l.id, l.title, l.video_id, l.video_url, l.start_sec, l.end_sec, l.source_id, l.chapter_title, s.title AS source_title
        FROM lessons l
        LEFT JOIN sources s ON s.id = l.source_id
        WHERE l.id = ? AND l.course_id = ?;
        """,
        (lesson_id, course_id),
    )
    lesson_row = cur.fetchone()
    if not lesson_row:
        raise ValueError(f"Lesson {lesson_id} not found in course {course_id}")

    lesson_title = lesson_row["title"]
    source_title = lesson_row["source_title"] or ""

    cur.execute("SELECT * FROM notes WHERE lesson_id = ?;", (lesson_id,))
    existing = cur.fetchone()
    existing_keys = set(existing.keys()) if existing else set()
    existing_mode = (existing["generation_mode"] if (existing and "generation_mode" in existing_keys) else "deterministic") or "deterministic"
    existing_md = (existing["content_markdown"] if existing else "") or ""

    llm_available = _has_any_llm_key() or bool(user_secrets)
    needs_upgrade = (
        existing is not None
        and existing["is_generated"] == 1
        and existing_mode == "deterministic"
        and llm_available
    )
    is_empty_placeholder = (
        existing is not None
        and ("No transcript or captions" in existing_md or not existing_md.strip())
    )

    if existing and not force_regenerate and existing_md.strip() and not is_empty_placeholder and not needs_upgrade:
        return {
            "id": existing["id"],
            "course_id": existing["course_id"],
            "lesson_id": existing["lesson_id"],
            "content_markdown": existing_md,
            "personal_notes": existing["personal_notes"] or "",
            "is_generated": existing["is_generated"],
            "generation_mode": existing_mode,
            "lesson_title": lesson_title,
            "updated_at": existing["updated_at"],
        }

    cur.execute(
        """
        SELECT id, chunk_index, start_sec, end_sec, content
        FROM chunks
        WHERE lesson_id = ?
        ORDER BY chunk_index ASC, start_sec ASC;
        """,
        (lesson_id,),
    )
    chunks = [dict(r) for r in cur.fetchall()]

    if not chunks and (lesson_row["video_id"] or lesson_row["video_url"]):
        try:
            from backend.services.transcription import ingest_lesson_transcript
            target_vid = lesson_row["video_id"] or lesson_row["video_url"]
            await ingest_lesson_transcript(
                db,
                course_id=course_id,
                source_id=lesson_row["source_id"] or None,
                lesson_id=lesson_id,
                video_id_or_url=target_vid,
                start_sec=int(lesson_row["start_sec"] or 0),
                end_sec=int(lesson_row["end_sec"]) if lesson_row["end_sec"] else None,
            )
            cur.execute(
                """
                SELECT id, chunk_index, start_sec, end_sec, content
                FROM chunks
                WHERE lesson_id = ?
                ORDER BY chunk_index ASC, start_sec ASC;
                """,
                (lesson_id,),
            )
            chunks = [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            logger.warning(f"[Notes] Auto-transcribe fallback for {lesson_id}: {exc}")

    generated_md = await generate_llm_structured_notes(
        lesson_title,
        chunks,
        db_conn=db,
        bypass_cache=force_regenerate,
        user_secrets=user_secrets,
    )
    if generated_md:
        gen_mode = "llm"
        promoted_title = _extract_h1_title(generated_md)
        if promoted_title and (
            is_placeholder_lesson_title(lesson_title)
            or (source_title and lesson_title.strip().lower() == source_title.strip().lower())
        ):
            cur.execute("UPDATE lessons SET title = ? WHERE id = ?;", (promoted_title, lesson_id))
            lesson_title = promoted_title
    else:
        generated_md = generate_no_key_structured_notes(lesson_title, chunks)
        gen_mode = "deterministic"

    now_iso = datetime.now(timezone.utc).isoformat()
    if existing:
        cur.execute(
            """
            UPDATE notes
            SET content_markdown = ?, is_generated = 1, generation_mode = ?, updated_at = ?
            WHERE id = ?;
            """,
            (generated_md, gen_mode, now_iso, existing["id"]),
        )
        note_id = existing["id"]
        personal_notes = existing["personal_notes"] or ""
    else:
        note_id = str(uuid.uuid4())
        personal_notes = ""
        cur.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated, generation_mode, updated_at)
            VALUES (?, ?, ?, ?, '', 1, ?, ?);
            """,
            (note_id, course_id, lesson_id, generated_md, gen_mode, now_iso),
        )
    db.commit()

    return {
        "id": note_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_markdown": generated_md,
        "personal_notes": personal_notes,
        "is_generated": 1,
        "generation_mode": gen_mode,
        "lesson_title": lesson_title,
        "updated_at": now_iso,
    }


def save_personal_notes(
    db: sqlite3.Connection,
    course_id: str,
    lesson_id: str,
    personal_notes: str,
) -> Dict[str, Any]:
    """Saves or updates user's personal study notes for a lesson."""
    cur = db.cursor()
    cur.execute("SELECT * FROM notes WHERE lesson_id = ?;", (lesson_id,))
    existing = cur.fetchone()
    now_iso = datetime.now(timezone.utc).isoformat()

    if existing:
        cur.execute(
            "UPDATE notes SET personal_notes = ?, updated_at = ? WHERE id = ?;",
            (personal_notes, now_iso, existing["id"]),
        )
        note_id = existing["id"]
        content_md = existing["content_markdown"] or ""
        is_gen = existing["is_generated"]
        gen_mode = existing["generation_mode"] if "generation_mode" in existing.keys() else "deterministic"
    else:
        note_id = str(uuid.uuid4())
        content_md = ""
        is_gen = 0
        gen_mode = "deterministic"
        cur.execute(
            """
            INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes, is_generated, generation_mode, updated_at)
            VALUES (?, ?, ?, '', ?, 0, 'deterministic', ?);
            """,
            (note_id, course_id, lesson_id, personal_notes, now_iso),
        )
    db.commit()
    return {
        "id": note_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_markdown": content_md,
        "personal_notes": personal_notes,
        "is_generated": is_gen,
        "generation_mode": gen_mode,
        "updated_at": now_iso,
    }
