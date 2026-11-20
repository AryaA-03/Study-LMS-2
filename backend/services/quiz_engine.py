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
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.services.fsrs_engine import create_flashcard

logger = logging.getLogger("learn_lms.quiz_engine")
settings = get_settings()


def extract_key_sentences(text: str) -> List[str]:
    """Splits text into clean sentences suitable for grounding."""
    # Split on sentence boundaries
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for s in raw:
        clean = s.strip()
        # Keep substantive sentences between 30 and 220 chars
        if 30 <= len(clean) <= 220 and not clean.startswith("#") and not clean.startswith("["):
            sentences.append(clean)
    return sentences


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
        content = chunk.get("content", "")
        sentences = extract_key_sentences(content)
        for s in sentences:
            candidates.append({
                "chunk_id": chunk_id,
                "lesson_id": lesson_id,
                "sentence": s,
                "content": content
            })

    if not candidates:
        # Fallback to taking snippet from chunk
        for chunk in chunks:
            candidates.append({
                "chunk_id": chunk["id"],
                "lesson_id": chunk.get("lesson_id"),
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
            words = quote.split()
            first_few = " ".join(words[:4])
            question_text = f"Based on the source material, which statement accurately reflects the discussion on '{first_few}...'?"
            correct_option = quote

        # Build 3 plausible distractors from other sentences or negation
        distractors = [s for s in all_sentences if s != quote and len(s) > 20]
        while len(distractors) < 3:
            distractors.append(f"It is entirely unrelated to {quote[:30]}...")
            distractors.append(f"The source disproves that {quote[:30]}...")
            distractors.append(f"This applies only in non-deterministic environments.")

        chosen_distractors = random.sample(distractors, 3)

        options = [correct_option] + chosen_distractors
        # Shuffle options deterministically
        shuffled_indices = list(range(4))
        random.shuffle(shuffled_indices)
        shuffled_options = [options[i] for i in shuffled_indices]
        correct_index = shuffled_options.index(correct_option)

        q_id = f"q_{idx}_{uuid.uuid4().hex[:6]}"
        explanation = f"Grounded directly in cited chunk [{chunk_id}]: \"{quote}\""

        questions.append({
            "id": q_id,
            "chunk_id": chunk_id,
            "lesson_id": lesson_id,
            "quote": quote,
            "question": question_text,
            "options": shuffled_options,
            "correct_index": correct_index,
            "explanation": explanation,
        })

    return questions


async def generate_llm_questions(
    chunks: List[Dict[str, Any]],
    question_count: int = 5,
    quiz_type: str = "lesson"
) -> List[Dict[str, Any]]:
    """Generates structured citation-grounded MCQs using Gemini 2.5 Flash."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return generate_no_key_questions(chunks, question_count, quiz_type)

    evidence_parts = []
    chunk_map = {}
    for c in chunks[:10]:
        cid = c["id"]
        content = c.get("content", "")
        evidence_parts.append(f"[Chunk ID: {cid}]\n{content}\n")
        chunk_map[cid] = content

    combined_evidence = "\n---\n".join(evidence_parts)

    system_instruction = (
        "You are an expert exam-prep instructor. Generate rigorous, concept-testing multiple choice questions "
        "strictly grounded in the provided source chunks. Every single question MUST include an exact verbatim quote "
        "from one of the chunks, along with that chunk's ID. Do NOT include ungrounded concepts or facts outside the text."
    )

    prompt = f"""
SOURCE CHUNKS:
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                llm_qs = parsed.get("questions", [])

                verified_qs = []
                for idx, q in enumerate(llm_qs):
                    cid = q.get("chunk_id")
                    quote = q.get("quote", "").strip()
                    # Verify quote is actually in the chunk
                    if cid in chunk_map and quote and quote in chunk_map[cid]:
                        q["id"] = f"q_{idx}_{uuid.uuid4().hex[:6]}"
                        # Find lesson_id from chunk
                        chunk_row = next((c for c in chunks if c["id"] == cid), None)
                        q["lesson_id"] = chunk_row.get("lesson_id") if chunk_row else None
                        verified_qs.append(q)

                if len(verified_qs) >= 2:
                    return verified_qs
    except Exception as e:
        logger.warning(f"LLM quiz generation failed or rejected ({e}); falling back to deterministic generation.")

    return generate_no_key_questions(chunks, question_count, quiz_type)


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

    # Retrieve relevant chunks
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
        # If no chunks exist yet, create a synthetic grounded question from course/lesson info
        chunks = [{
            "id": f"chk_synthetic_{uuid.uuid4().hex[:6]}",
            "lesson_id": lesson_id,
            "content": "Theory of Computation studies formal languages, finite automata, and computational complexity.",
        }]

    # Generate questions deterministically (fast, reliable, offline-ready)
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
    time_taken_seconds: int = 0
) -> Dict[str, Any]:
    """Grades submitted quiz answers and executes the Mastery Loop:
    - score >= 80%: Marks topic 'Tested Out' and triggers schedule reflow.
    - score < 60%: Auto-generates FSRS flashcards for missed concepts and marks 'Needs Review'.
    - diagnostic: Marks all correctly answered lesson topics 'Tested Out' and reflows.
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

    for q in questions:
        qid = q["id"]
        # user_answers can have key as qid or string index
        selected = user_answers.get(qid)
        if selected is None and qid in user_answers:
            selected = user_answers[qid]

        if selected == q["correct_index"]:
            correct_count += 1
            if q.get("lesson_id"):
                correct_lesson_ids.add(q["lesson_id"])
        else:
            missed_questions.append(q)

    score = round((correct_count / float(total)) * 100.0, 1)
    passed = score >= 80.0

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
            json.dumps(user_answers),
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
                correct_opt = mq["options"][mq["correct_index"]]
                back = f"Correct Answer: {correct_opt}\n\nEvidence: {mq['explanation']}"
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
                correct_opt = mq["options"][mq["correct_index"]]
                back = f"Answer: {correct_opt}\n\nExplanation: {mq['explanation']}"
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
    }
