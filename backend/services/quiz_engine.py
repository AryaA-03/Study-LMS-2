"""Citation Quiz & Diagnostic Pre-Test Engine.

Generates strictly grounded multiple-choice questions (MCQs) citing source chunks,
manages timed mock exams, and executes the Mastery Loop:
- Score >= 80% marks lesson "Tested Out" and triggers automatic schedule reflow.
- Score < 60% generates targeted FSRS flashcards for missed concepts and flags review.
- Diagnostic pre-tests allow instant test-out of mastered topics with schedule reflow.
"""

import json
import uuid
import random
import re
import logging
import asyncio
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.services.fsrs_engine import create_flashcard
from backend.services.llm_cache import (
    compute_sha256,
    get_cached_response,
    set_cached_response,
)

logger = logging.getLogger("learn_lms.quiz_engine")
settings = get_settings()


def run_sync(coro):
    """Executes an async coroutine synchronously, handling running event loops safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


VIDEO_NOISE_PATTERN = re.compile(
    r"(\[music\]|\[applause\]|\[laughter\]|"
    r"\bwelcome\s+(to|back|everyone)\b|"
    r"\bhello\s+everyone\b|"
    r"\b(see\s+you|watching\s+and\s+see\s+you|thank\s+you\s+for\s+watching|thanks\s+for\s+watching)\b|"
    r"\b(subscribe|hit\s+the\s+bell|like\s+and\s+subscribe|leave\s+a\s+comment|comment\s+below)\b|"
    r"\b(in\s+this\s+video|in\s+the\s+next\s+video|in\s+the\s+next\s+lecture|next\s+lecture\s+onwards)\b|"
    r"\b(goodbye|bye\s+bye|stay\s+tuned)\b)",
    re.IGNORECASE
)


def extract_key_sentences(text: str) -> List[str]:
    """Splits text into clean sentences suitable for grounding, strictly filtering video noise and boilerplate."""
    # Split on sentence boundaries
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for s in raw:
        clean = s.strip()
        # Remove inline audio tokens
        clean = re.sub(r"\[(?:Music|Applause|Laughter)\]", "", clean, flags=re.IGNORECASE).strip()
        # Skip video noise, outro, and social prompts
        if VIDEO_NOISE_PATTERN.search(clean):
            continue
        words = clean.split()
        # Keep substantive sentences between 35 and 220 chars with at least 6 substantive words
        if len(words) >= 6 and 35 <= len(clean) <= 220 and not clean.startswith("#") and not clean.startswith("["):
            sentences.append(clean)
    return sentences


async def _evaluate_short_answer_llm(question: Dict[str, Any], student_answer: str) -> Dict[str, Any]:
    """Evaluates subjective short answer against university exam rubrics via Gemini/Groq/OpenRouter."""
    prompt = f"""You are a university engineering professor and strict exam evaluator grading a 5-mark subjective question.

QUESTION:
{question.get('question')}

GROUNDING QUOTE FROM TEXTBOOK / TRANSCRIPT:
{question.get('quote')}

SAMPLE MODEL SOLUTION:
{question.get('sample_solution')}

RUBRIC:
1. Definition & Conceptual Core (up to 2.0 Marks): Clear definition, intuition, and formal role.
2. Technical Mechanism & Working Steps (up to 2.0 Marks): Detailed mechanism, properties, architecture, or algorithmic formulation.
3. Practical Example & Application (up to 1.0 Mark): Concrete scenario, code snippet, or engineering application.
Total Maximum Marks: 5.0

STUDENT'S SUBMITTED ANSWER:
{student_answer}

TASK:
Grade the student's answer strictly according to the 3-part rubric.
Output pure JSON adhering to this exact schema:
{{
  "marks_awarded": float,
  "breakdown": {{
    "definition": float,
    "mechanism": float,
    "example": float
  }},
  "feedback": "Concise 1-2 sentence constructive examiner remark highlighting strengths and missing rubric elements."
}}
"""
    system_instruction = "You are a university computer science examiner. Grade subjective answers fairly and rigorously based on the provided 3-part rubric."

    api_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    async with httpx.AsyncClient(timeout=25.0) as client:
        if api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(raw_text)
                else:
                    logger.warning(f"Gemini rubric eval returned {resp.status_code}; trying fallback providers")
            except Exception as e:
                logger.warning(f"Gemini rubric eval failed: {e}; trying fallback providers")

        if groq_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    raw_text = resp.json()["choices"][0]["message"]["content"]
                    return json.loads(raw_text)
                else:
                    logger.warning(f"Groq rubric eval returned {resp.status_code}; trying fallback providers")
            except Exception as e:
                logger.warning(f"Groq rubric eval failed: {e}; trying fallback providers")

        if openrouter_key:
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "google/gemini-2.5-flash",
                    "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    raw_text = resp.json()["choices"][0]["message"]["content"]
                    return json.loads(raw_text)
                else:
                    logger.warning(f"OpenRouter rubric eval returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"OpenRouter rubric eval failed: {e}")
    return {}


def evaluate_short_answer_with_rubric(
    question: Dict[str, Any],
    student_answer: str,
    conn=None
) -> Dict[str, Any]:
    """Evaluates a 5-mark subjective question against university exam rubrics.
    
    Rubric criteria:
    - Definition & Conceptual Core (2.0 marks max)
    - Technical Mechanism & Working Steps (2.0 marks max)
    - Practical Example / Application (1.0 mark max)
    Total maximum: 5.0 marks.
    
    Supports SHA-256 caching in llm_cache and deterministic fallback when offline.
    """
    q_id = question.get("id", "q_sa")
    max_marks = float(question.get("max_marks", 5.0))
    cleaned = (student_answer or "").strip()

    if not cleaned:
        return {
            "question_id": q_id,
            "marks_awarded": 0.0,
            "max_marks": max_marks,
            "breakdown": {"definition": 0.0, "mechanism": 0.0, "example": 0.0},
            "feedback": "No answer provided.",
        }

    # Check llm_cache
    cache_key = f"rubric_eval:{q_id}:{cleaned}"
    prompt_hash = compute_sha256(cache_key)
    if conn is not None:
        cached_str = get_cached_response(conn, prompt_hash)
        if cached_str:
            try:
                cached_data = json.loads(cached_str)
                if isinstance(cached_data, dict) and "marks_awarded" in cached_data:
                    logger.info(f"llm_cache hit for evaluate_short_answer_with_rubric ({q_id})")
                    return cached_data
            except Exception:
                pass

    # Check for LLM key
    has_key = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if has_key:
        try:
            eval_res = run_sync(_evaluate_short_answer_llm(question, cleaned))
            if eval_res and "marks_awarded" in eval_res:
                eval_res["question_id"] = q_id
                eval_res["max_marks"] = max_marks
                if conn is not None:
                    set_cached_response(conn, prompt_hash, "gemini-2.5-flash", json.dumps(eval_res))
                return eval_res
        except Exception as e:
            logger.warning(f"LLM rubric grading failed ({e}); falling back to deterministic evaluator.")

    # Deterministic rubric evaluator
    words = cleaned.split()
    word_count = len(words)
    sample_sol = question.get("sample_solution", "")
    quote = question.get("quote", "")

    sample_tokens = set(re.findall(r"\w+", sample_sol.lower()))
    quote_tokens = set(re.findall(r"\w+", quote.lower()))
    stopwords = {"the", "a", "an", "is", "are", "in", "of", "and", "to", "for", "with", "on", "as", "by", "this", "that", "it", "at", "be"}
    target_keywords = (sample_tokens | quote_tokens) - stopwords

    student_tokens = set(re.findall(r"\w+", cleaned.lower()))
    overlap = len(target_keywords & student_tokens)
    overlap_ratio = min(1.0, overlap / max(3, len(target_keywords) * 0.35)) if target_keywords else 0.5

    # 1. Definition (max 2.0 marks)
    def_markers = ["defined", "means", "refers", "is a", "is an", "concept", "structure", "technique", "algorithm", "property", "consists"]
    has_def = any(m in cleaned.lower() for m in def_markers) or overlap >= 2
    def_score = 0.5
    if has_def:
        def_score += 0.5
    if overlap_ratio >= 0.25:
        def_score += 0.5
    if overlap_ratio >= 0.55:
        def_score += 0.5
    def_score = min(2.0, def_score)

    # 2. Mechanism (max 2.0 marks)
    mech_markers = ["how", "step", "process", "working", "mechanism", "computes", "stores", "traverses", "executes", "complexity", "time", "space", "order", "state", "transition"]
    has_mech = any(m in cleaned.lower() for m in mech_markers)
    mech_score = 0.5 if word_count >= 12 else 0.0
    if has_mech:
        mech_score += 0.5
    if word_count >= 25:
        mech_score += 0.5
    if overlap_ratio >= 0.45 and word_count >= 20:
        mech_score += 0.5
    mech_score = min(2.0, mech_score)

    # 3. Example / Application (max 1.0 mark)
    ex_markers = ["example", "e.g.", "for instance", "such as", "case", "like", "consider", "`", "use case", "application"]
    has_ex = any(m in cleaned.lower() for m in ex_markers)
    ex_score = 1.0 if has_ex else (0.5 if word_count >= 35 else 0.0)

    total_marks = round(min(max_marks, def_score + mech_score + ex_score), 1)

    feedback_parts = [f"Definition: {def_score}/2.0", f"Mechanism: {mech_score}/2.0", f"Example: {ex_score}/1.0"]
    feedback = f"Rubric breakdown: {', '.join(feedback_parts)}."
    if not has_ex:
        feedback += " Consider adding a concrete code or real-world example to secure full marks."

    result = {
        "question_id": q_id,
        "marks_awarded": total_marks,
        "max_marks": max_marks,
        "breakdown": {
            "definition": def_score,
            "mechanism": mech_score,
            "example": ex_score,
        },
        "feedback": feedback,
    }

    if conn is not None:
        set_cached_response(conn, prompt_hash, "deterministic-rubric", json.dumps(result))

    return result


def generate_no_key_questions(
    chunks: List[Dict[str, Any]],
    question_count: int = 5,
    quiz_type: str = "lesson"
) -> List[Dict[str, Any]]:
    """Generates grounded MCQs deterministically from chunks with zero LLM API key."""
    if not chunks:
        return []

    # Gather candidate sentences and definitions across chunks
    candidates = []
    for chunk in chunks:
        chunk_id = chunk["id"]
        lesson_id = chunk.get("lesson_id")
        start_sec = int(chunk.get("start_sec") or 0)
        end_sec = int(chunk.get("end_sec") or start_sec)
        content = chunk.get("content", "")
        sentences = extract_key_sentences(content)
        for s in sentences:
            candidates.append({
                "chunk_id": chunk_id,
                "lesson_id": lesson_id,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "sentence": s,
                "content": content
            })

    if not candidates:
        # Fallback to taking snippet from chunk
        for chunk in chunks:
            start_sec = int(chunk.get("start_sec") or 0)
            candidates.append({
                "chunk_id": chunk["id"],
                "lesson_id": chunk.get("lesson_id"),
                "start_sec": start_sec,
                "end_sec": int(chunk.get("end_sec") or start_sec),
                "sentence": chunk.get("content", "")[:120].strip(),
                "content": chunk.get("content", "")
            })

    # Pick up to question_count candidates
    random.seed(42)  # Deterministic seed for reproducible tests
    selected = random.sample(candidates, min(len(candidates), question_count))

    # Collect distinct sentences to use as distractors
    all_sentences = [c["sentence"] for c in candidates]

    questions = []
    for idx, item in enumerate(selected):
        quote = item["sentence"]
        chunk_id = item["chunk_id"]
        lesson_id = item["lesson_id"]

        # Formulate grounded question
        # If sentence contains "is" or "are" or "means", turn into inquiry
        if re.search(r"\b(is|are|means|defined as|refers to)\b", quote, re.IGNORECASE):
            parts = re.split(r"\b(is|are|means|defined as|refers to)\b", quote, maxsplit=1, flags=re.IGNORECASE)
            subject = parts[0].strip()
            predicate = parts[1].strip() + " " + parts[2].strip() if len(parts) >= 3 else quote
            question_text = f"According to the cited material, what is stated regarding '{subject}'?"
            correct_option = f"{subject} {predicate}"
        else:
            # Extract key concept or formulate meaningful question
            question_text = f"Based on the course lecture content, which statement accurately describes the core principle of this topic?"
            correct_option = quote

        # Build 3 plausible distractors from other clean sentences or academic formulations
        distractors = [s for s in all_sentences if s != quote and len(s) > 25]
        academic_fallbacks = [
            "It restricts memory structures strictly to linear sequential arrays without state transitions.",
            "It eliminates boundary validation checks by executing unbounded randomized trials.",
            "It is formulated as an undecidable model with zero computational constraints.",
            "It assumes instantaneous unbounded storage without state persistence.",
        ]
        fb_idx = 0
        while len(distractors) < 3:
            distractors.append(academic_fallbacks[fb_idx % len(academic_fallbacks)])
            fb_idx += 1

        chosen_distractors = random.sample(distractors, 3)

        options = [correct_option] + chosen_distractors
        # Shuffle options deterministically
        shuffled_indices = list(range(4))
        random.shuffle(shuffled_indices)
        shuffled_options = [options[i] for i in shuffled_indices]
        correct_index = shuffled_options.index(correct_option)

        q_id = f"q_{idx}_{uuid.uuid4().hex[:6]}"
        t_sec = int(item.get("start_sec") or 0)
        h, rem = divmod(t_sec, 3600)
        m, s = divmod(rem, 60)
        t_str = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
        explanation = f"Grounded directly in cited chunk [{chunk_id}] at {t_str}: \"{quote}\""

        questions.append({
            "id": q_id,
            "chunk_id": chunk_id,
            "lesson_id": lesson_id,
            "timestamp_sec": t_sec,
            "timestamp_str": t_str,
            "replay_url": f"#seek={t_sec}",
            "quote": quote,
            "question": question_text,
            "options": shuffled_options,
            "correct_index": correct_index,
            "explanation": explanation,
            "question_type": "mcq",
            "max_marks": 1.0,
            "rubric": None,
            "sample_solution": None,
        })

    # For university mock exams, generate Section B: 5-mark subjective questions with rubrics
    if quiz_type == "mock_exam" and candidates:
        sa_count = min(2, max(1, question_count // 3))
        sa_candidates = [c for c in candidates if c not in selected][:sa_count]
        if not sa_candidates:
            sa_candidates = candidates[:sa_count]

        for s_idx, item in enumerate(sa_candidates):
            quote = item["sentence"]
            chunk_id = item["chunk_id"]
            lesson_id = item["lesson_id"]
            sa_t_sec = int(item.get("start_sec") or 0)
            h, rem = divmod(sa_t_sec, 3600)
            m, s = divmod(rem, 60)
            sa_t_str = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"

            if re.search(r"\b(is|are|means|defined as|refers to)\b", quote, re.IGNORECASE):
                parts = re.split(r"\b(is|are|means|defined as|refers to)\b", quote, maxsplit=1, flags=re.IGNORECASE)
                subject = parts[0].strip()
            else:
                words = quote.split()
                subject = " ".join(words[:4])

            sa_id = f"q_sa_{s_idx}_{uuid.uuid4().hex[:6]}"
            questions.append({
                "id": sa_id,
                "chunk_id": chunk_id,
                "lesson_id": lesson_id,
                "timestamp_sec": sa_t_sec,
                "timestamp_str": sa_t_str,
                "replay_url": f"#seek={sa_t_sec}",
                "quote": quote,
                "question": f"Explain the core concept, technical working mechanism, and practical application of '{subject}'. (5 Marks)",
                "options": [],
                "correct_index": 0,
                "explanation": f"Grounded directly in cited chunk [{chunk_id}] at {sa_t_str}: \"{quote}\"",
                "question_type": "short_answer",
                "max_marks": 5.0,
                "rubric": [
                    "Definition & Conceptual Core (2.0 Marks): Clear definition, intuition, and formal role.",
                    "Technical Mechanism & Steps (2.0 Marks): Detailed explanation of working principle, properties, or operations.",
                    "Practical Example & Application (1.0 Mark): Concrete scenario, code snippet, or engineering use-case."
                ],
                "sample_solution": f"Core Definition: {quote}\n\nTechnical Working Principle: {item.get('content', quote)[:240]}\n\nPractical Application: Widely utilized in engineering algorithms and production systems for reliable data processing.",
            })

    return questions


async def generate_llm_questions(
    chunks: List[Dict[str, Any]],
    question_count: int = 5,
    quiz_type: str = "lesson",
    conn=None
) -> List[Dict[str, Any]]:
    """Generates structured citation-grounded MCQs using Gemini 2.5 Flash, Groq, or OpenRouter."""
    has_key = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if not has_key or not chunks:
        return generate_no_key_questions(chunks, question_count, quiz_type)

    evidence_parts = []
    chunk_map = {}
    for c in chunks[:10]:
        cid = c["id"]
        content = c.get("content", "")
        evidence_parts.append(f"[Chunk ID: {cid}]\n{content}\n")
        chunk_map[cid] = content

    combined_evidence = "\n---\n".join(evidence_parts)

    prompt_hash = compute_sha256(f"quiz:{question_count}:{quiz_type}:{combined_evidence}")
    if conn is not None:
        cached_str = get_cached_response(conn, prompt_hash)
        if cached_str:
            try:
                cached_qs = json.loads(cached_str)
                if isinstance(cached_qs, list) and len(cached_qs) >= 2:
                    logger.info("llm_cache hit for generate_llm_questions")
                    return cached_qs
            except Exception:
                pass

    if quiz_type == "mock_exam":
        system_instruction = (
            "You are a university engineering exam creator. Generate a dual-section examination: "
            "Section A: High-yield citation-grounded multiple-choice questions (1 mark each, question_type='mcq'). "
            "Section B: In-depth 5-mark subjective questions (question_type='short_answer') each with a 3-part rubric "
            "(Definition 2.0 marks, Mechanism 2.0 marks, Example 1.0 mark) and a model sample solution. "
            "All questions must strictly cite exact verbatim quotes and chunk IDs from the provided text."
        )
        prompt = f"""SOURCE CHUNKS:
{combined_evidence}

TASK:
Generate a university mock exam with:
- Section A: {max(2, question_count - 2)} citation-grounded MCQs (1 Mark each, question_type="mcq").
- Section B: {min(2, max(1, question_count // 3))} subjective questions (5 Marks each, question_type="short_answer").

For MCQs:
- 'chunk_id': must match one of the provided Chunk IDs.
- 'quote': exact verbatim substring from that chunk.
- 'question': clear conceptual question.
- 'question_type': 'mcq'
- 'max_marks': 1.0
- 'options': array of 4 choices.
- 'correct_index': integer index (0-3).
- 'explanation': concise explanation referencing quote.

For Short Answer (5 Marks):
- 'chunk_id': must match one of the provided Chunk IDs.
- 'quote': exact verbatim substring from that chunk.
- 'question': subjective prompt (e.g. 'Explain the conceptual core, technical working mechanism, and practical application of ... (5 Marks)')
- 'question_type': 'short_answer'
- 'max_marks': 5.0
- 'rubric': ['Definition & Conceptual Core (2.0 Marks)', 'Technical Mechanism & Steps (2.0 Marks)', 'Practical Example & Application (1.0 Mark)']
- 'sample_solution': comprehensive model answer covering definition, mechanism, and example.
- 'options': []
- 'correct_index': 0
- 'explanation': explanation referencing quote.

Output pure JSON adhering to this schema:
{{
  "questions": [
    {{
      "chunk_id": "string",
      "quote": "string",
      "question": "string",
      "question_type": "mcq",
      "max_marks": 1.0,
      "options": ["string", "string", "string", "string"],
      "correct_index": 0,
      "explanation": "string"
    }},
    {{
      "chunk_id": "string",
      "quote": "string",
      "question": "string",
      "question_type": "short_answer",
      "max_marks": 5.0,
      "rubric": ["string", "string", "string"],
      "sample_solution": "string",
      "options": [],
      "correct_index": 0,
      "explanation": "string"
    }}
  ]
}}
"""
    else:
        system_instruction = (
            "You are an expert exam-prep instructor. Generate rigorous, concept-testing multiple choice questions "
            "strictly grounded in the provided source chunks. Every single question MUST include an exact verbatim quote "
            "from one of the chunks, along with that chunk's ID. Do NOT include ungrounded concepts or facts outside the text."
        )
        prompt = f"""SOURCE CHUNKS:
{combined_evidence}

TASK:
Generate exactly {question_count} high-yield multiple-choice questions testing core concepts from these chunks.
Requirements:
1. 'chunk_id': must match one of the provided Chunk IDs.
2. 'quote': exact verbatim substring from that chunk justifying the correct answer.
3. 'question': clear, unambiguous conceptual or application question.
4. 'options': array of 4 distinct choices.
5. 'correct_index': integer index (0, 1, 2, or 3) of the correct choice.
6. 'explanation': concise explanation referencing the quote.

Output pure JSON adhering to this schema:
{{
  "questions": [
    {{
      "chunk_id": "string",
      "quote": "string",
      "question": "string",
      "options": ["string", "string", "string", "string"],
      "correct_index": 0,
      "explanation": "string"
    }}
  ]
}}
"""

    api_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY
    model_used = "gemini-2.5-flash"

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            llm_qs = []
            if api_key:
                try:
                    model_used = "gemini-2.5-flash"
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_used}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.2
                        }
                    }
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw_text)
                        llm_qs = parsed.get("questions", [])
                    else:
                        logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}; trying fallback")
                except Exception as e:
                    logger.warning(f"Gemini quiz call failed: {e}; trying fallback")

            if not llm_qs and groq_key:
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
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["choices"][0]["message"]["content"]
                        parsed = json.loads(raw_text)
                        llm_qs = parsed.get("questions", [])
                    else:
                        logger.warning(f"Groq API returned status {resp.status_code}: {resp.text[:200]}; trying fallback")
                except Exception as e:
                    logger.warning(f"Groq quiz call failed: {e}; trying fallback")

            if not llm_qs and openrouter_key:
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
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["choices"][0]["message"]["content"]
                        parsed = json.loads(raw_text)
                        llm_qs = parsed.get("questions", [])
                    else:
                        logger.warning(f"OpenRouter API returned status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    logger.warning(f"OpenRouter quiz call failed: {e}")

            verified_qs = []
            for idx, q in enumerate(llm_qs):
                cid = q.get("chunk_id")
                quote = q.get("quote", "").strip()
                q_type = q.get("question_type", "mcq")
                # Verify quote is actually in the chunk (with whitespace normalization tolerance)
                quote_valid = False
                if cid in chunk_map and quote:
                    if quote in chunk_map[cid]:
                        quote_valid = True
                    else:
                        q_norm = " ".join(quote.split())
                        c_norm = " ".join(chunk_map[cid].split())
                        if q_norm.lower() in c_norm.lower():
                            quote_valid = True

                if quote_valid:
                    q["id"] = f"q_{idx}_{uuid.uuid4().hex[:6]}"
                    chunk_row = next((c for c in chunks if c["id"] == cid), None)
                    q["lesson_id"] = chunk_row.get("lesson_id") if chunk_row else None
                    t_sec = int(chunk_row.get("start_sec") or 0) if chunk_row else 0
                    h, rem = divmod(t_sec, 3600)
                    m, s = divmod(rem, 60)
                    t_str = f"[{h:02d}:{m:02d}:{s:02d}]" if h > 0 else f"[{m:02d}:{s:02d}]"
                    q["timestamp_sec"] = t_sec
                    q["timestamp_str"] = t_str
                    q["replay_url"] = f"#seek={t_sec}"
                    if q_type == "short_answer":
                        q["question_type"] = "short_answer"
                        q["max_marks"] = float(q.get("max_marks", 5.0))
                        q["options"] = q.get("options", [])
                        q["correct_index"] = 0
                        q["rubric"] = q.get("rubric") or [
                            "Definition & Conceptual Core (2.0 Marks): Clear definition, intuition, and formal role.",
                            "Technical Mechanism & Steps (2.0 Marks): Detailed explanation of working principle, properties, or operations.",
                            "Practical Example & Application (1.0 Mark): Concrete scenario, code snippet, or engineering use-case."
                        ]
                        q["sample_solution"] = q.get("sample_solution") or f"Model Answer: {quote}\nMechanism: {chunk_map[cid][:200]}"
                    else:
                        q["question_type"] = "mcq"
                        q["max_marks"] = float(q.get("max_marks", 1.0))
                        q["rubric"] = None
                        q["sample_solution"] = None
                    verified_qs.append(q)

            if len(verified_qs) >= 2:
                if conn is not None:
                    set_cached_response(conn, prompt_hash, model_used, json.dumps(verified_qs))
                return verified_qs
    except Exception as e:
        logger.warning(f"LLM quiz generation failed or rejected ({e}); falling back to deterministic generation.")

async def _generate_diagnostic_questions_llm(
    conn,
    course_id: str,
    sampled_lessons: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Generates CourseIt-style diagnostic placement test questions via LLM."""
    has_key = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if not has_key or not sampled_lessons:
        return []

    system_instruction = (
        "You are an academic curriculum director and diagnostic placement test specialist. "
        "Your task is to generate a CourseIt-style diagnostic pre-test across the syllabus topics of the course. "
        "Each question corresponds to one specific syllabus topic and must evaluate whether the student "
        "already possesses sufficient foundational mastery of that topic to test out of it.\n"
        "Strict requirements:\n"
        "1. Exactly 1 clear conceptual or analytical question per provided topic.\n"
        "2. Absolutely NEVER include video outro phrases ('watching and see you', 'goodbye', 'subscribe', 'in the next video'), greetings, or timestamps.\n"
        "3. Focus on formal definitions, mechanisms, state transitions, or core properties of the topic.\n"
        "4. Exactly 4 distinct, plausible choices per question.\n"
        "5. Accurate correct_index (0, 1, 2, or 3) and concise explanation."
    )

    lesson_items_text = []
    for idx, l in enumerate(sampled_lessons):
        lid = l["id"]
        ltitle = l["title"]
        ch_title = l.get("chapter_title") or ltitle
        lesson_items_text.append(f"Topic {idx + 1}: Lesson ID: {lid} | Title: {ltitle} | Chapter: {ch_title}")

    user_prompt = (
        f"Course ID: {course_id}\n\n"
        f"Topics to assess:\n" + "\n".join(lesson_items_text) + "\n\n"
        "Output pure JSON adhering to this schema:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "lesson_id": "string (matching lesson id)",\n'
        '      "topic_name": "string (lesson title)",\n'
        '      "question": "string",\n'
        '      "options": ["string", "string", "string", "string"],\n'
        '      "correct_index": 0,\n'
        '      "explanation": "string"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    prompt_hash = compute_sha256(f"diagnostic:{course_id}:{len(sampled_lessons)}")
    if conn is not None:
        cached_str = get_cached_response(conn, prompt_hash)
        if cached_str:
            try:
                cached_data = json.loads(cached_str)
                if isinstance(cached_data, list) and len(cached_data) >= len(sampled_lessons) // 2:
                    return cached_data
            except Exception:
                pass

    api_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    raw_response = None
    model_used = None

    async with httpx.AsyncClient(timeout=25.0) as client:
        if api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.15}
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    raw_response = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    model_used = "gemini-2.5-flash"
            except Exception as e:
                logger.warning(f"Gemini diagnostic generation failed: {e}; trying fallback")

        if not raw_response and groq_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.15
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    raw_response = resp.json()["choices"][0]["message"]["content"]
                    model_used = "groq-llama-3.3-70b"
            except Exception as e:
                logger.warning(f"Groq diagnostic generation failed: {e}; trying fallback")

        if not raw_response and openrouter_key:
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "google/gemini-2.5-flash",
                    "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.15
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    raw_response = resp.json()["choices"][0]["message"]["content"]
                    model_used = "openrouter-gemini-2.5-flash"
            except Exception as e:
                logger.warning(f"OpenRouter diagnostic generation failed: {e}")

    if not raw_response:
        return []

    try:
        data = json.loads(raw_response)
        parsed_qs = data.get("questions", [])
        verified_qs = []
        for idx, q in enumerate(parsed_qs):
            lid = q.get("lesson_id")
            matched_l = next((l for l in sampled_lessons if l["id"] == lid), None)
            if not matched_l and idx < len(sampled_lessons):
                matched_l = sampled_lessons[idx]
                lid = matched_l["id"]

            tname = matched_l["title"] if matched_l else q.get("topic_name", f"Topic {idx + 1}")
            opts = q.get("options", [])
            if len(opts) == 4 and "question" in q:
                verified_qs.append({
                    "id": f"diag_q_{idx}_{uuid.uuid4().hex[:6]}",
                    "lesson_id": lid,
                    "topic_name": tname,
                    "topic_index": idx + 1,
                    "chunk_id": f"syllabus_{lid[:8] if lid else 'gen'}",
                    "quote": f"Syllabus Topic: {tname}",
                    "question": q["question"],
                    "options": opts,
                    "correct_index": int(q.get("correct_index", 0)) % 4,
                    "explanation": q.get("explanation", f"Core placement question for topic '{tname}'."),
                    "question_type": "mcq",
                    "max_marks": 1.0,
                })
        if len(verified_qs) >= 2:
            if conn is not None and model_used:
                set_cached_response(conn, prompt_hash, model_used, json.dumps(verified_qs))
            return verified_qs
    except Exception as parse_err:
        logger.warning(f"Failed to parse LLM diagnostic JSON: {parse_err}")

    return []


def clean_topic_title(title: str) -> str:
    """Extracts clean, readable chapter or topic name from noisy video titles."""
    if not title:
        return "Topic"
    ch_match = re.search(r"\((Chapter[-\s]?\d+[^)]*)\)\s*[-:]?\s*(.*)", title, re.IGNORECASE)
    if ch_match:
        ch = ch_match.group(1).replace("-", " ")
        rest = ch_match.group(2).strip()
        return f"{ch}: {rest[:40]}..." if len(rest) > 40 else (f"{ch}: {rest}" if rest else ch)
    if "|" in title:
        parts = [p.strip() for p in title.split("|")]
        return parts[-1]
    cleaned = re.sub(r"^(?:Lecture|Lesson|Video|Part|Ch\.|Chapter)\s*\d+[:.\s-]*", "", title, flags=re.IGNORECASE)
    return cleaned.strip() or title


def generate_diagnostic_questions(
    conn,
    course_id: str,
    question_count: int = 5
) -> List[Dict[str, Any]]:
    """Generates a high-yield CourseIt-style diagnostic placement pre-test.
    
    1. Distributes questions evenly across the course syllabus lessons.
    2. Filters out video noise/chatter/boilerplates.
    3. Grounds each question in that specific lesson's core concept or technical mechanism.
    4. Attaches lesson_id and topic_name so correct answers directly test out the topic.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, chapter_title, order_index
        FROM lessons
        WHERE course_id = ?
        ORDER BY order_index ASC;
        """,
        (course_id,)
    )
    lessons = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    if not lessons:
        return []

    # Sample lessons evenly across the syllabus
    if len(lessons) <= question_count:
        sampled_lessons = lessons
    else:
        step = (len(lessons) - 1) / max(1, question_count - 1)
        sampled_indices = [round(i * step) for i in range(question_count)]
        seen_idx = set()
        sampled_lessons = []
        for idx in sampled_indices:
            if idx not in seen_idx:
                seen_idx.add(idx)
                sampled_lessons.append(lessons[idx])

    # Try LLM generation if key configured
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if has_llm:
        try:
            llm_qs = run_sync(_generate_diagnostic_questions_llm(conn, course_id, sampled_lessons))
            if llm_qs and len(llm_qs) >= max(2, len(sampled_lessons) // 2):
                return llm_qs
        except Exception as e:
            logger.warning(f"[Diagnostic] LLM placement generation failed ({e}); falling back to deterministic.")

    # High-yield deterministic placement test generator
    questions = []
    for idx, l in enumerate(sampled_lessons):
        lid = l["id"]
        raw_title = l["title"]
        clean_title = clean_topic_title(raw_title)
        ch_title = l.get("chapter_title") or clean_title

        # Check for clean transcript sentences for this lesson
        cur.execute("SELECT id, content FROM chunks WHERE lesson_id = ? ORDER BY chunk_index ASC;", (lid,))
        crows = cur.fetchall()
        clean_sentences = []
        for cid, content in crows:
            sents = extract_key_sentences(content)
            for s in sents:
                clean_sentences.append((cid, s))

        q_obj = None
        # Approach A: Ground from clean lesson sentence if definition exists
        for cid, s in clean_sentences:
            if re.search(r"\b(is a|is an|defined as|refers to|consists of)\b", s, re.IGNORECASE):
                parts = re.split(r"\b(is a|is an|defined as|refers to|consists of)\b", s, maxsplit=1, flags=re.IGNORECASE)
                subject = parts[0].strip()
                predicate = parts[1].strip() + " " + parts[2].strip() if len(parts) >= 3 else s
                if 3 <= len(subject) <= 50 and len(subject.split()) <= 6:
                    question_text = f"In the study of '{clean_title}', what is the core role or definition of '{subject}'?"
                    correct_option = f"{subject} {predicate}"
                    distractors = [
                        f"It restricts {subject} strictly to static linear arrays without transitions.",
                        f"It eliminates formal boundary states by executing unbounded randomized trials.",
                        f"It is an undecidable formulation with zero input validation.",
                    ]
                    options = [correct_option] + distractors
                    random.seed(idx + 42)
                    random.shuffle(options)
                    q_obj = {
                        "id": f"diag_q_{idx}_{uuid.uuid4().hex[:6]}",
                        "lesson_id": lid,
                        "topic_name": clean_title,
                        "topic_index": idx + 1,
                        "chunk_id": cid,
                        "quote": s,
                        "question": question_text,
                        "options": options,
                        "correct_index": options.index(correct_option),
                        "explanation": f"Grounded in lesson content [{cid}]: \"{s}\"",
                        "question_type": "mcq",
                        "max_marks": 1.0,
                    }
                    break

        # Approach B: Academic domain concept heuristics
        if not q_obj:
            t_lower = raw_title.lower() + " " + clean_title.lower()
            if "pushdown" in t_lower or "pda" in t_lower:
                question_text = "What primary architectural component enables a Pushdown Automaton (PDA) to recognize Context-Free Languages beyond standard Finite Automata?"
                correct_option = "An auxiliary Last-In-First-Out (LIFO) stack data structure for tracking nested or balanced symbols."
                distractors = [
                    "A bidirectional read-write tape head capable of unbounded arbitrary memory movement.",
                    "An infinite array with direct O(1) random-access indexing.",
                    "A non-deterministic lookup table with zero intermediate storage.",
                ]
                explanation = "Pushdown automata extend finite automata with a stack memory, enabling them to recognize languages with nested or balanced structures."
            elif "deterministic" in t_lower or "dfa" in t_lower:
                question_text = "Which formal condition is strictly required for a Deterministic Finite Automaton (DFA)?"
                correct_option = "For every state and every alphabet symbol, there is exactly one unique transition to a next state, with no epsilon moves."
                distractors = [
                    "A state may execute empty-string (epsilon) transitions without consuming input.",
                    "Multiple concurrent transitions for the same input character are evaluated in parallel.",
                    "State transitions can push and pop symbols from an unbounded memory stack.",
                ]
                explanation = "A DFA is strictly deterministic: exactly one transition is defined for each state-symbol pair, and epsilon moves are forbidden."
            elif "finite state" in t_lower or "fsm" in t_lower or "automata (intro" in t_lower:
                question_text = "What is the fundamental theoretical memory limitation of Finite State Machines (FSMs)?"
                correct_option = "They possess strictly finite memory and cannot maintain an unbounded counter to recognize languages like aⁿbⁿ."
                distractors = [
                    "They cannot compute boolean logic or state-based switching.",
                    "They require non-deterministic guessing to recognize simple regular patterns.",
                    "They can only process input strings consisting of single-bit binary characters.",
                ]
                explanation = "Because an FSM has a finite set of states, it cannot count arbitrarily large numbers of matching symbols."
            elif "pumping lemma" in t_lower:
                question_text = "What is the primary academic purpose of the Pumping Lemma in formal language theory?"
                correct_option = "To formally prove by contradiction that a specific candidate language is NOT regular."
                distractors = [
                    "To deterministically minimize the number of states in an arbitrary DFA.",
                    "To convert non-deterministic finite automata into equivalent context-free grammars.",
                    "To prove that every context-sensitive language is decidable in polynomial time.",
                ]
                explanation = "The Pumping Lemma establishes a necessary condition for all regular languages, making it a standard tool to prove non-regularity by contradiction."
            elif "turing" in t_lower:
                question_text = "What fundamental capability characterizes a Turing Machine compared to Automata with bounded memory?"
                correct_option = "An infinite memory tape with a read-write head that can move both left and right across cells."
                distractors = [
                    "Guaranteed halting within strictly polynomial time bounds for all inputs.",
                    "A static read-only memory buffer with zero write capability.",
                    "Execution restricted exclusively to finite prefix regular expressions.",
                ]
                explanation = "A Turing Machine uses an infinite read-write tape with bidirectional movement, serving as the universal mathematical model of computation."
            elif "er diagram" in t_lower or "entity" in t_lower or "relational model" in t_lower:
                question_text = f"In relational database design ({clean_title}), what characterizes a 'Weak Entity Set'?"
                correct_option = "An entity set that lacks sufficient attributes to form a primary key on its own and depends on an identifying owner entity."
                distractors = [
                    "A temporary table with strictly read-only nullable attributes.",
                    "A table that cannot participate in database foreign key relationships.",
                    "An entity whose primary key consists solely of auto-incrementing timestamps.",
                ]
                explanation = "A weak entity set lacks a primary key of its own and requires a foreign key relationship with an identifying strong entity set."
            elif "indexing" in t_lower or "b-tree" in t_lower or "b+tree" in t_lower:
                question_text = f"What is the primary algorithmic benefit of using a B-Tree / B+Tree structure for database indexing ({clean_title})?"
                correct_option = "Maintaining balanced multi-level nodes that guarantee O(log N) operations for point lookups, insertions, and range scans."
                distractors = [
                    "Eliminating secondary storage by keeping all database pages in volatile CPU cache.",
                    "Replacing disk block addressing with raw non-sequential hashing.",
                    "Restricting index scans strictly to single-attribute equality matches.",
                ]
                explanation = "B-Trees keep search keys sorted across balanced height-bounded nodes, providing efficient log-time retrieval and range scans."
            elif "recovery" in t_lower or "concurrency" in t_lower or "2pl" in t_lower or "locking" in t_lower:
                question_text = f"In transaction concurrency control ({clean_title}), what guarantee is provided by the Two-Phase Locking (2PL) protocol?"
                correct_option = "Conflict serializability of concurrent execution schedules."
                distractors = [
                    "Total prevention of all transaction deadlock states without aborts.",
                    "Immediate durability of non-committed buffer cache writes.",
                    "Zero read-write locking overhead across concurrent transactions.",
                ]
                explanation = "The Two-Phase Locking (2PL) protocol mathematically guarantees that concurrent transaction schedules are conflict-serializable."
            elif "relational calculus" in t_lower or "calculus" in t_lower or "algebra" in t_lower:
                question_text = f"What is the primary distinction between Relational Algebra and Relational Calculus ({clean_title})?"
                correct_option = "Relational Algebra is procedural (specifying how to retrieve data), while Relational Calculus is declarative (specifying what data to retrieve)."
                distractors = [
                    "Relational Calculus operates exclusively on physical B-tree records.",
                    "Relational Algebra cannot express natural join operations.",
                    "Relational Calculus requires procedural execution loops for every foreign key.",
                ]
                explanation = "Relational algebra defines a step-by-step procedural query sequence; relational calculus is non-procedural and declarative."
            elif "grammar" in t_lower or "cfg" in t_lower or "cfl" in t_lower:
                question_text = "In Context-Free Grammars (CFGs), which structural rule defines production transitions?"
                correct_option = "Each production rule replaces a single non-terminal symbol with a string of terminals and/or non-terminals."
                distractors = [
                    "Production rules may replace arbitrary strings of terminals with an empty symbol.",
                    "The left-hand side of every rule must contain at least two terminal characters.",
                    "Productions must be evaluated strictly in reverse chronological order.",
                ]
                explanation = "A CFG requires that every production rule has exactly one non-terminal on its left-hand side."
            else:
                question_text = f"In the syllabus curriculum, which core principle or operational requirement is evaluated in '{clean_title}'?"
                correct_option = f"Establishing formal state definitions, transition boundaries, and analytical rules for {clean_title}."
                distractors = [
                    "Executing brute-force random trials without terminating boundary states.",
                    "Replacing structural state verification with unconstrained direct memory access.",
                    "Assuming all input alphabets are infinite without formal syntax constraints.",
                ]
                explanation = f"'{clean_title}' systematically formalizes computational state boundaries, input processing rules, and problem-solving mechanisms."

            options = [correct_option] + distractors
            random.seed(idx + 101)
            random.shuffle(options)
            q_obj = {
                "id": f"diag_q_{idx}_{uuid.uuid4().hex[:6]}",
                "lesson_id": lid,
                "topic_name": clean_title,
                "topic_index": idx + 1,
                "chunk_id": f"syllabus_{lid[:8]}",
                "quote": f"Topic: {clean_title}",
                "question": question_text,
                "options": options,
                "correct_index": options.index(correct_option),
                "explanation": explanation,
                "question_type": "mcq",
                "max_marks": 1.0,
            }

        questions.append(q_obj)

    return questions


def create_and_store_quiz(
    conn,
    course_id: str,
    quiz_type: str = "lesson",
    lesson_id: Optional[str] = None,
    question_count: int = 5,
    custom_title: Optional[str] = None
) -> Dict[str, Any]:
    """Generates and persists a new quiz, diagnostic test, or mock exam."""
    cur = conn.cursor()

    # Diagnostic Pre-Tests follow the CourseIt curriculum placement model
    if quiz_type == "diagnostic":
        questions = generate_diagnostic_questions(conn, course_id, question_count=question_count)
        title = custom_title or "3-Minute Course Diagnostic Pre-Test"
        quiz_id = f"qz_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO quizzes (
                id, course_id, lesson_id, quiz_type, title,
                questions_json, score, passed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                quiz_id,
                course_id,
                None,
                quiz_type,
                title,
                json.dumps(questions),
                0.0,
                0,
                datetime.now(timezone.utc).isoformat()
            )
        )
        conn.commit()
        return {
            "id": quiz_id,
            "course_id": course_id,
            "lesson_id": None,
            "quiz_type": quiz_type,
            "title": title,
            "questions": questions,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # Retrieve relevant chunks for lesson quiz or mock exam
    if lesson_id:
        cur.execute(
            "SELECT * FROM chunks WHERE lesson_id = ? ORDER BY chunk_index ASC;",
            (lesson_id,)
        )
        chunks = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        if not chunks:
            # Fallback to course chunks
            cur.execute("SELECT * FROM chunks WHERE course_id = ? LIMIT 15;", (course_id,))
            chunks = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        
        # Get lesson title
        cur.execute("SELECT title FROM lessons WHERE id = ?;", (lesson_id,))
        lrow = cur.fetchone()
        ltitle = lrow[0] if lrow else "Lesson"
        title = custom_title or f"Quiz: {ltitle}"
    else:
        # Diagnostic pre-test or mock exam across all course chunks
        cur.execute(
            "SELECT * FROM chunks WHERE course_id = ? ORDER BY RANDOM() LIMIT 25;",
            (course_id,)
        )
        chunks = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        if quiz_type == "diagnostic":
            title = custom_title or "Course Diagnostic Pre-Test"
        elif quiz_type == "mock_exam":
            title = custom_title or "Timed Full Mock Exam"
        else:
            title = custom_title or "Course Review Quiz"

    if not chunks:
        # If no transcript chunks exist yet, sample grounded questions directly from course syllabus lessons
        cur.execute(
            "SELECT id, title, chapter_title FROM lessons WHERE course_id = ? ORDER BY order_index ASC LIMIT 25;",
            (course_id,)
        )
        l_rows = cur.fetchall()
        if l_rows:
            chunks = []
            for idx, lr in enumerate(l_rows):
                lid = lr[0]
                ltitle = lr[1]
                ch_title = lr[2] or ltitle
                chunks.append({
                    "id": f"chk_les_{lid[:8]}_{idx}",
                    "lesson_id": lid,
                    "content": f"{ltitle} is a foundational course topic. Understanding {ch_title} is defined as a primary requirement for exam problem solving and analytical correctness.",
                })
        else:
            chunks = [{
                "id": f"chk_synthetic_{uuid.uuid4().hex[:6]}",
                "lesson_id": lesson_id,
                "content": "Core syllabus concepts and principles are defined as the fundamental baseline for this examination.",
            }]

    # Generate questions: use LLM if GEMINI_API_KEY / Groq / OpenRouter is available, else fallback
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    questions = []
    if has_llm:
        try:
            questions = run_sync(generate_llm_questions(chunks, question_count=question_count, quiz_type=quiz_type, conn=conn))
        except Exception as e:
            logger.warning(f"LLM quiz generation execution error ({e}); falling back to deterministic generation.")
            questions = []

    if not questions:
        questions = generate_no_key_questions(chunks, question_count=question_count, quiz_type=quiz_type)

    quiz_id = f"qz_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO quizzes (
            id, course_id, lesson_id, quiz_type, title,
            questions_json, score, passed, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            quiz_id,
            course_id,
            lesson_id,
            quiz_type,
            title,
            json.dumps(questions),
            None,
            0,
            datetime.now(timezone.utc).isoformat(),
        )
    )
    conn.commit()

    return {
        "id": quiz_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "quiz_type": quiz_type,
        "title": title,
        "questions": questions,
        "score": None,
        "passed": False,
        "time_taken_seconds": None,
    }


def grade_and_apply_mastery(
    conn,
    quiz_id: str,
    user_answers: Dict[str, int],
    short_answers: Optional[Dict[str, str]] = None,
    time_taken_seconds: int = 0
) -> Dict[str, Any]:
    """Grades submitted quiz answers and executes the Mastery Loop:
    - score >= 80%: Marks topic 'Tested Out' and triggers schedule reflow.
    - score < 60%: Auto-generates FSRS flashcards for missed concepts and marks 'Needs Review'.
    - diagnostic: Marks all correctly answered lesson topics 'Tested Out' and reflows.
    - mock_exam: Dual Section A (MCQs) and Section B (5-Mark Rubric Subjective) university exam evaluation.
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM quizzes WHERE id = ?;", (quiz_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Quiz {quiz_id} not found.")

    col_names = [d[0] for d in cur.description]
    quiz = dict(zip(col_names, row))
    course_id = quiz["course_id"]
    lesson_id = quiz.get("lesson_id")
    quiz_type = quiz.get("quiz_type", "lesson")
    questions = json.loads(quiz["questions_json"])

    total = len(questions)
    if total == 0:
        return {"score": 0.0, "passed": False, "correct_count": 0, "total_questions": 0}

    correct_count = 0
    missed_questions = []
    correct_lesson_ids = set()
    short_answers = short_answers or {}
    short_answer_evals = []

    total_marks_possible = 0.0
    total_marks_obtained = 0.0

    for q in questions:
        qid = q["id"]
        q_type = q.get("question_type", "mcq")
        max_marks = float(q.get("max_marks", 1.0 if q_type == "mcq" else 5.0))
        total_marks_possible += max_marks

        if q_type == "short_answer":
            student_text = short_answers.get(qid, "")
            eval_res = evaluate_short_answer_with_rubric(q, student_text, conn=conn)
            short_answer_evals.append(eval_res)
            awarded = float(eval_res["marks_awarded"])
            total_marks_obtained += awarded
            if awarded >= (max_marks * 0.8):
                correct_count += 1
                if q.get("lesson_id"):
                    correct_lesson_ids.add(q["lesson_id"])
            elif awarded < (max_marks * 0.6):
                missed_questions.append(q)
        else:
            selected = user_answers.get(qid)
            if selected is None and qid in user_answers:
                selected = user_answers[qid]

            if selected is not None and int(selected) == q["correct_index"]:
                correct_count += 1
                total_marks_obtained += max_marks
                if q.get("lesson_id"):
                    correct_lesson_ids.add(q["lesson_id"])
            else:
                missed_questions.append(q)

    score = round((total_marks_obtained / max(0.1, total_marks_possible)) * 100.0, 1)
    passed = score >= 80.0

    user_answers_payload = {
        "mcq": user_answers,
        "short_answers": short_answers,
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE quizzes
        SET score = ?,
            passed = ?,
            time_taken_seconds = ?,
            completed_at = ?,
            user_answers_json = ?
        WHERE id = ?;
        """,
        (
            score,
            1 if passed else 0,
            time_taken_seconds,
            now_iso,
            json.dumps(user_answers_payload),
            quiz_id,
        )
    )
    conn.commit()

    tested_out_lessons: List[str] = []
    flashcards_created = 0
    mastery_status = "standard"

    if quiz_type == "lesson" and lesson_id:
        if score >= 80.0:
            # Mark lesson Tested Out!
            conn.execute("UPDATE lessons SET is_tested_out = 1 WHERE id = ?;", (lesson_id,))
            conn.commit()
            tested_out_lessons.append(lesson_id)
            mastery_status = "mastered"
            logger.info(f"[Mastery] Lesson {lesson_id} scored {score}% >= 80%. Marked Tested Out.")
        elif score < 60.0:
            mastery_status = "needs_review"
            # Generate FSRS flashcards for missed concepts
            for mq in missed_questions:
                front = f"Review Concept: {mq['question']}"
                if mq.get("question_type") == "short_answer":
                    back = f"Sample Solution:\n{mq.get('sample_solution', '')}\n\nEvidence: {mq.get('explanation', '')}"
                else:
                    correct_opt = mq["options"][mq["correct_index"]] if mq.get("options") else ""
                    back = f"Correct Answer: {correct_opt}\n\nEvidence: {mq.get('explanation', '')}"
                create_flashcard(
                    conn=conn,
                    course_id=course_id,
                    front=front,
                    back=back,
                    lesson_id=lesson_id,
                    chunk_id=mq.get("chunk_id"),
                    source_quote=mq.get("quote"),
                )
                flashcards_created += 1
            logger.info(f"[Mastery] Lesson {lesson_id} scored {score}% < 60%. Generated {flashcards_created} FSRS flashcards.")
        else:
            mastery_status = "completed"

    elif quiz_type == "diagnostic":
        mastery_status = "diagnostic_applied"
        # Test out any lesson where user answered correctly
        for lid in correct_lesson_ids:
            conn.execute("UPDATE lessons SET is_tested_out = 1 WHERE id = ?;", (lid,))
            tested_out_lessons.append(lid)
        conn.commit()
        logger.info(f"[Diagnostic] Tested out {len(tested_out_lessons)} lessons via diagnostic pre-test.")

    elif quiz_type == "mock_exam":
        mastery_status = "mock_exam_completed"
        # For mock exam, also generate flashcards for missed questions so student can drill them
        if score < 80.0:
            for mq in missed_questions:
                front = f"Mock Exam Review: {mq['question']}"
                if mq.get("question_type") == "short_answer":
                    back = f"Sample Solution:\n{mq.get('sample_solution', '')}\n\nEvidence: {mq.get('explanation', '')}"
                else:
                    correct_opt = mq["options"][mq["correct_index"]] if mq.get("options") else ""
                    back = f"Answer: {correct_opt}\n\nExplanation: {mq.get('explanation', '')}"
                create_flashcard(
                    conn=conn,
                    course_id=course_id,
                    front=front,
                    back=back,
                    lesson_id=mq.get("lesson_id"),
                    chunk_id=mq.get("chunk_id"),
                    source_quote=mq.get("quote"),
                )
                flashcards_created += 1

    return {
        "quiz_id": quiz_id,
        "score": score,
        "passed": passed,
        "correct_count": correct_count,
        "total_questions": total,
        "mastery_status": mastery_status,
        "tested_out_lessons": tested_out_lessons,
        "flashcards_created": flashcards_created,
        "missed_count": len(missed_questions),
        "short_answer_evaluations": short_answer_evals,
        "total_marks_obtained": round(total_marks_obtained, 1),
        "total_marks_possible": round(total_marks_possible, 1),
    }
