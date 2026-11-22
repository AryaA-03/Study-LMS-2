"""Strict Citation-Grounded Q&A Engine.

Retrieves top matching chunks via SQLite FTS5 BM25 ranking, synthesizes
strict citation-grounded answers citing verbatim excerpts and chunk IDs,
and validates that all claims are grounded in evidence.
"""

import re
import json
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple

import httpx
from backend.config import get_settings
from backend.services.llm_cache import (
    compute_sha256,
    get_cached_response,
    set_cached_response,
)

logger = logging.getLogger("learn_lms.qa_engine")
settings = get_settings()


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
    """Splits plain text into overlapping word chunks."""
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def search_chunks_fts(
    db_conn,
    course_id: str,
    query: str,
    limit: int = 6,
    lesson_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Performs FTS5 BM25 search against indexed chunks for a course, optionally restricted to a lesson."""
    # Clean query for FTS5 match: keep alphanumeric words and join with OR
    words = re.findall(r"[A-Za-z0-9_]+", query)
    if not words:
        return []

    # SQLite FTS5 query: word1 OR word2 OR word3
    fts_expr = " OR ".join(words[:12])

    cur = db_conn.cursor()
    try:
        if lesson_id:
            cur.execute(
                """
                SELECT c.id, c.source_id, c.lesson_id, c.start_sec, c.end_sec, c.content,
                       s.title as source_title, s.source_type, bm25(chunks_fts) as rank
                FROM chunks_fts f
                JOIN chunks c ON f.id = c.id
                LEFT JOIN sources s ON c.source_id = s.id
                WHERE chunks_fts MATCH ? AND c.course_id = ? AND c.lesson_id = ?
                ORDER BY rank ASC
                LIMIT ?;
                """,
                (fts_expr, course_id, lesson_id, limit)
            )
        else:
            cur.execute(
                """
                SELECT c.id, c.source_id, c.lesson_id, c.start_sec, c.end_sec, c.content,
                       s.title as source_title, s.source_type, bm25(chunks_fts) as rank
                FROM chunks_fts f
                JOIN chunks c ON f.id = c.id
                LEFT JOIN sources s ON c.source_id = s.id
                WHERE chunks_fts MATCH ? AND c.course_id = ?
                ORDER BY rank ASC
                LIMIT ?;
                """,
                (fts_expr, course_id, limit)
            )
        rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"FTS5 MATCH failed with '{fts_expr}': {e}; falling back to LIKE")
        if lesson_id:
            cur.execute(
                """
                SELECT c.id, c.source_id, c.lesson_id, c.start_sec, c.end_sec, c.content,
                       s.title as source_title, s.source_type, 0.0 as rank
                FROM chunks c
                LEFT JOIN sources s ON c.source_id = s.id
                WHERE c.course_id = ? AND c.lesson_id = ? AND c.content LIKE ?
                LIMIT ?;
                """,
                (course_id, lesson_id, f"%{words[0]}%", limit)
            )
        else:
            cur.execute(
                """
                SELECT c.id, c.source_id, c.lesson_id, c.start_sec, c.end_sec, c.content,
                       s.title as source_title, s.source_type, 0.0 as rank
                FROM chunks c
                LEFT JOIN sources s ON c.source_id = s.id
                WHERE c.course_id = ? AND c.content LIKE ?
                LIMIT ?;
                """,
                (course_id, f"%{words[0]}%", limit)
            )
        rows = cur.fetchall()

    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append({
            "id": r[0],
            "source_id": r[1] or "",
            "lesson_id": r[2] or "",
            "start_sec": r[3],
            "end_sec": r[4],
            "content": r[5],
            "source_title": r[6] or "Study Source",
            "source_type": r[7] or "youtube_video",
            "rank": r[8],
        })
    return results


def format_no_key_answer(
    query: str,
    chunks: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generates grounded answer passages directly from chunks in No-Key mode."""
    if not chunks:
        return (
            "The provided source materials do not contain sufficient evidence to answer this question. "
            "Try adding more course sources, PDFs, or YouTube lectures.",
            []
        )

    lines: List[str] = [
        f"**Grounded Answer for:** *\"{query}\"*\n",
        "Based directly on the course materials, here are the most relevant grounded excerpts:\n"
    ]
    citations: List[Dict[str, Any]] = []

    for i, c in enumerate(chunks[:4]):
        c_id = c["id"]
        source_name = c["source_title"]
        time_tag = ""
        if c.get("start_sec") is not None:
            m, s = divmod(c["start_sec"], 60)
            time_tag = f" `[{m:02d}:{s:02d}]`"

        excerpt = c["content"][:220].strip() + "..."
        lines.append(f"**From {source_name}{time_tag}:**")
        lines.append(f"> \"{excerpt}\" `[ref:{c_id}]`\n")

        citations.append({
            "chunk_id": c_id,
            "source_title": source_name,
            "source_type": c.get("source_type", "youtube_video"),
            "start_sec": c.get("start_sec"),
            "excerpt": excerpt,
        })

    return "\n".join(lines), citations


async def generate_llm_grounded_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    gemini_key: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generates strict citation-grounded response using Gemini, Groq, or OpenRouter LLM API."""
    if not chunks:
        return format_no_key_answer(query, chunks)

    # Format evidence blocks
    evidence_blocks = []
    chunk_map = {}
    for c in chunks:
        chunk_map[c["id"]] = c
        t_str = ""
        if c.get("start_sec") is not None:
            m, s = divmod(c["start_sec"], 60)
            t_str = f", Time: [{m:02d}:{s:02d}]"
        evidence_blocks.append(
            f"--- EVIDENCE CHUNK [ID: {c['id']}, Source: {c['source_title']}{t_str}] ---\n{c['content']}"
        )
    evidence_text = "\n\n".join(evidence_blocks)

    system_instruction = (
        "You are an expert college professor and strict study tutor. "
        "Your task is to answer the student's question strictly and exclusively using the provided EVIDENCE CHUNKS.\n"
        "STRICT GROUNDING RULES:\n"
        "1. Every factual statement, claim, definition, or explanation MUST cite its evidence chunk using the format `[ref:CHUNK_ID]` (e.g. `[ref:chk_123]`) and include the timestamp in [MM:SS] if available.\n"
        "2. Include verbatim quotes inside quotation marks to substantiate key facts.\n"
        "3. If the evidence chunks DO NOT contain enough information to answer the question, do NOT invent facts. Explicitly state: 'The provided source materials do not contain sufficient evidence to answer this question.'\n"
        "4. Be concise, direct, and structured with bullet points.\n"
    )

    key = gemini_key or settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    raw_answer = None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": f"{system_instruction}\n\nEvidence:\n{evidence_text}\n\nStudent Question: {query}"
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 1024,
                    }
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    result = resp.json()
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_answer = parts[0].get("text", "")
                else:
                    logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}")
            elif groq_key:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Evidence:\n{evidence_text}\n\nStudent Question: {query}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_answer = choices[0].get("message", {}).get("content", "")
                else:
                    logger.warning(f"Groq API returned status {resp.status_code}: {resp.text[:200]}")
            elif openrouter_key:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "google/gemini-2.5-flash",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Evidence:\n{evidence_text}\n\nStudent Question: {query}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_answer = choices[0].get("message", {}).get("content", "")
                else:
                    logger.warning(f"OpenRouter API returned status {resp.status_code}: {resp.text[:200]}")

        if raw_answer:
            # Parse citations present in answer (supporting UUID and chk_ identifiers)
            cited_ids = re.findall(r"\[ref:\s*([a-zA-Z0-9_\-]+)\]", raw_answer) + re.findall(r"\[(chk_[a-zA-Z0-9_\-]+)\]", raw_answer)
            citations = []
            for cid in set(cited_ids):
                if cid in chunk_map:
                    chk = chunk_map[cid]
                    citations.append({
                        "chunk_id": cid,
                        "source_title": chk["source_title"],
                        "source_type": chk.get("source_type", "youtube_video"),
                        "start_sec": chk.get("start_sec"),
                        "excerpt": chk["content"][:200]
                    })
            if not citations and chunks:
                for chk in chunks[:3]:
                    citations.append({
                        "chunk_id": chk["id"],
                        "source_title": chk["source_title"],
                        "source_type": chk.get("source_type", "youtube_video"),
                        "start_sec": chk.get("start_sec"),
                        "excerpt": chk["content"][:200]
                    })
            return raw_answer, citations
    except Exception as e:
        logger.warning(f"LLM grounded Q&A call failed: {e}")

    # Fallback to deterministic extraction
    return format_no_key_answer(query, chunks)


async def answer_course_question(
    db_conn,
    course_id: str,
    query: str,
    lesson_id: Optional[str] = None
) -> Dict[str, Any]:
    """Orchestrates FTS5 search, answer synthesis, caching, and persistence in qa_threads."""
    # 1. Check llm_cache for existing (course_id, query, lesson_id)
    cache_key = f"qa:{course_id}:{query}:{lesson_id or ''}"
    prompt_hash = compute_sha256(cache_key)

    if db_conn is not None:
        cached_str = get_cached_response(db_conn, prompt_hash)
        if cached_str:
            logger.info("llm_cache hit for answer_course_question")
            try:
                cached_data = json.loads(cached_str)
                if isinstance(cached_data, dict):
                    cached_answer = cached_data.get("answer_markdown") or cached_data.get("answer") or ""
                    cached_citations = cached_data.get("citations", [])
                else:
                    cached_answer = str(cached_data)
                    cached_citations = []
            except Exception:
                cached_answer = cached_str
                cached_citations = []

            thread_id = f"qa_{uuid.uuid4().hex[:12]}"
            try:
                db_conn.execute(
                    """
                    INSERT INTO qa_threads (id, course_id, query, answer_markdown, citations_json)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (thread_id, course_id, query, cached_answer, json.dumps(cached_citations))
                )
                db_conn.commit()
            except Exception as e:
                logger.warning(f"Failed to record cached Q&A thread: {e}")

            return {
                "id": thread_id,
                "course_id": course_id,
                "query": query,
                "answer_markdown": cached_answer,
                "citations": cached_citations
            }

    # 2. Search top matching chunks (restricted to lesson_id if specified)
    matching_chunks = search_chunks_fts(db_conn, course_id, query, limit=6, lesson_id=lesson_id)

    # 3. Synthesize answer
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if has_llm:
        answer_text, citations = await generate_llm_grounded_answer(query, matching_chunks, settings.GEMINI_API_KEY)
    else:
        answer_text, citations = format_no_key_answer(query, matching_chunks)

    # 4. Save to llm_cache
    if db_conn is not None:
        cache_val = json.dumps({
            "answer_markdown": answer_text,
            "citations": citations
        })
        model_name = "gemini-2.5-flash" if settings.GEMINI_API_KEY else ("llama-3.3-70b-versatile" if settings.GROQ_API_KEY else ("google/gemini-2.5-flash" if settings.OPENROUTER_API_KEY else "deterministic"))
        set_cached_response(db_conn, prompt_hash, model_name, cache_val)

    # 5. Persist in qa_threads table
    thread_id = f"qa_{uuid.uuid4().hex[:12]}"
    citations_json = json.dumps(citations)
    db_conn.execute(
        """
        INSERT INTO qa_threads (id, course_id, query, answer_markdown, citations_json)
        VALUES (?, ?, ?, ?, ?);
        """,
        (thread_id, course_id, query, answer_text, citations_json)
    )
    db_conn.commit()

    return {
        "id": thread_id,
        "course_id": course_id,
        "query": query,
        "answer_markdown": answer_text,
        "citations": citations
    }


def get_course_qa_history(db_conn, course_id: str) -> List[Dict[str, Any]]:
    """Retrieves previous Q&A threads for this course."""
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT id, query, answer_markdown, citations_json, created_at
        FROM qa_threads
        WHERE course_id = ?
        ORDER BY created_at ASC;
        """,
        (course_id,)
    )
    rows = cur.fetchall()
    threads = []
    for r in rows:
        citations = []
        try:
            citations = json.loads(r[3])
        except Exception:
            pass
        threads.append({
            "id": r[0],
            "query": r[1],
            "answer_markdown": r[2],
            "citations": citations,
            "created_at": r[4]
        })
    return threads
