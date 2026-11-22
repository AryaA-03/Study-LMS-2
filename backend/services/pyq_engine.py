"""University PYQ (Previous Year Questions) Parsing and FTS5 Matching Engine.

Extracts past exam questions from uploaded PDFs or pasted text, splits them into
individual numbered questions with mark tags, and uses SQLite FTS5 BM25 search
to match questions to course lessons for high-yield frequency weighting.
"""

import io
import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple

from pypdf import PdfReader

logger = logging.getLogger("learn_lms.pyq_engine")

# Common English question words and filler vocabulary to ignore in FTS5 keyword extraction
STOPWORDS = {
    "what", "is", "a", "an", "the", "explain", "describe", "define", "discuss",
    "with", "and", "or", "of", "in", "to", "for", "on", "by", "how", "does",
    "it", "differ", "from", "between", "diagram", "neat", "suitable", "example",
    "examples", "state", "write", "short", "note", "notes", "following", "any",
    "which", "why", "whose", "whom", "where", "when", "can", "could", "should",
    "would", "give", "list", "compare", "contrast", "differentiate", "distinguish",
    "briefly", "various", "detail", "details", "illustrate", "sketch", "show"
}


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts text from PDF bytes using pypdf."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
    return "\n\n".join(pages_text)


def parse_pyq_questions(raw_text: str) -> List[Dict[str, Any]]:
    """Splits raw past paper text into structured individual questions."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Filter out common exam headers and instruction blocks
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if re.search(
            r"^(total no\. of pages|maximum marks|max marks|time allowed|instructions|note:|roll no|semester examination|university|subject code|b\.tech|b\.e\.|m\.tech|bca|mca)",
            stripped,
            re.IGNORECASE
        ):
            continue
        cleaned_lines.append(line)

    filtered_text = "\n".join(cleaned_lines)

    # Question start regex:
    # 1. Q1., Q1(a), Q.1, Question 1:, Question 1(a):
    # 2. 1., 1), 1(a), 1.(a), 1 (a)
    # 3. (a), (b), (i), (ii) preceded by newline
    q_start_pattern = re.compile(
        r"(?:^|\n)\s*"
        r"(?:"
        r"(?:Q(?:uestion)?\.?\s*(\d+(?:[a-zA-Z]|\([a-zA-Z0-9]+\))?))|"
        r"(?:(\d+)\s*[\.\)]\s*(?:\(([a-zA-Z0-9]+)\))?)|"
        r"(?:\(([a-zA-Z0-9]+)\))"
        r")"
        r"\s*[:\.\-\)]?\s*",
        re.MULTILINE
    )

    matches = list(q_start_pattern.finditer(filtered_text))
    if not matches:
        # Fallback: split by paragraphs
        paragraphs = [p.strip() for p in filtered_text.split("\n\n") if len(p.strip()) > 15]
        questions = []
        for i, p in enumerate(paragraphs, 1):
            marks_match = re.search(r"\[\s*(\d+)\s*(?:M|Marks|marks)?\s*\]|\(\s*(\d+)\s*(?:M|Marks|marks)?\s*\)", p)
            marks = int(marks_match.group(1) or marks_match.group(2)) if marks_match else None
            q_clean = re.sub(r"\[\s*(\d+)\s*(?:M|Marks|marks)?\s*\]|\(\s*(\d+)\s*(?:M|Marks|marks)?\s*\)", "", p).strip()
            q_clean = re.sub(r"\s+", " ", q_clean).strip()
            if len(q_clean) >= 5:
                questions.append({
                    "question_number": f"Q{i}",
                    "question_text": q_clean,
                    "marks": marks
                })
        return questions

    questions = []
    current_major_q = "Q1"

    for idx, match in enumerate(matches):
        start_pos = match.end()
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(filtered_text)
        q_body = filtered_text[start_pos:end_pos].strip()

        g1, g2, g3, g4 = match.groups()
        if g1:
            q_num = f"Q{g1}"
            current_major_q = q_num
        elif g2:
            q_num = f"Q{g2}({g3})" if g3 else f"Q{g2}"
            current_major_q = f"Q{g2}"
        elif g4:
            q_num = f"{current_major_q}({g4})"
        else:
            q_num = f"Q{idx + 1}"

        # If question text begins with a sub-label like (a), absorb it into q_num
        sub_m = re.match(r"^\(([a-zA-Z0-9]+)\)\s*", q_body)
        if sub_m:
            sub_id = sub_m.group(1)
            if not q_num.endswith(f"({sub_id})"):
                q_num = f"{q_num}({sub_id})"
            q_body = q_body[sub_m.end():].strip()

        # Extract marks like [5M], [10 Marks], (5 marks), [10]
        marks_match = re.search(r"\[\s*(\d+)\s*(?:M|Marks|marks)?\s*\]|\(\s*(\d+)\s*(?:M|Marks|marks)?\s*\)", q_body)
        marks = None
        if marks_match:
            marks = int(marks_match.group(1) or marks_match.group(2))
            q_body = re.sub(r"\[\s*(\d+)\s*(?:M|Marks|marks)?\s*\]|\(\s*(\d+)\s*(?:M|Marks|marks)?\s*\)", "", q_body).strip()

        q_body = re.sub(r"\s+", " ", q_body).strip()
        if len(q_body) >= 5:
            questions.append({
                "question_number": q_num,
                "question_text": q_body,
                "marks": marks
            })

    return questions


def extract_salient_keywords(text: str) -> List[str]:
    """Extracts non-stopword alphanumeric keywords for FTS5 queries."""
    tokens = re.findall(r"[A-Za-z0-9_]+", text)
    keywords = []
    seen = set()
    for tok in tokens:
        low = tok.lower()
        if len(low) > 1 and low not in STOPWORDS and low not in seen:
            seen.add(low)
            keywords.append(low)
    return keywords


def match_question_to_course(
    db_conn,
    course_id: str,
    question_text: str
) -> Optional[Dict[str, Any]]:
    """Uses SQLite FTS5 BM25 search to match question against course lesson chunks."""
    keywords = extract_salient_keywords(question_text)
    if not keywords:
        return None

    # Construct FTS5 query with OR
    fts_expr = " OR ".join(keywords[:10])
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            SELECT c.id as chunk_id, c.lesson_id, c.content, bm25(chunks_fts) as rank
            FROM chunks_fts f
            JOIN chunks c ON f.id = c.id
            WHERE chunks_fts MATCH ? AND c.course_id = ? AND c.lesson_id IS NOT NULL
            ORDER BY rank ASC
            LIMIT 1;
            """,
            (fts_expr, course_id)
        )
        row = cur.fetchone()
        if row:
            snippet = row["content"][:240].strip() if isinstance(row, dict) else row[2][:240].strip()
            lesson_id = row["lesson_id"] if isinstance(row, dict) else row[1]
            chunk_id = row["chunk_id"] if isinstance(row, dict) else row[0]
            score = float(row["rank"] if isinstance(row, dict) else row[3])
            return {
                "lesson_id": lesson_id,
                "chunk_id": chunk_id,
                "snippet": snippet,
                "bm25_score": score
            }
    except Exception as e:
        logger.debug(f"[PYQ] FTS5 search error for '{fts_expr}': {e}")

    return None


def update_course_pyq_aggregates(db_conn, course_id: str):
    """Recalculates pyq_hit_count and pyq_total_marks on lessons table."""
    cur = db_conn.cursor()
    # Reset all lessons in this course
    cur.execute(
        "UPDATE lessons SET pyq_hit_count = 0, pyq_total_marks = 0 WHERE course_id = ?;",
        (course_id,)
    )

    # Compute aggregates from matched pyq_questions
    cur.execute(
        """
        SELECT matched_lesson_id, COUNT(*) as hit_count, SUM(COALESCE(marks, 0)) as total_marks
        FROM pyq_questions
        WHERE course_id = ? AND matched_lesson_id IS NOT NULL
        GROUP BY matched_lesson_id;
        """,
        (course_id,)
    )
    rows = cur.fetchall()
    for row in rows:
        lid = row["matched_lesson_id"] if isinstance(row, dict) else row[0]
        hits = row["hit_count"] if isinstance(row, dict) else row[1]
        marks = row["total_marks"] if isinstance(row, dict) else row[2]
        cur.execute(
            "UPDATE lessons SET pyq_hit_count = ?, pyq_total_marks = ? WHERE id = ?;",
            (hits, marks, lid)
        )


def ingest_pyq_source(
    db_conn,
    course_id: str,
    title: str,
    raw_text: str,
    filename: str = ""
) -> Dict[str, Any]:
    """Ingests a past paper, extracts questions, matches against chunks, and saves."""
    cur = db_conn.cursor()
    paper_id = f"pyq_{uuid.uuid4().hex[:10]}"
    cur.execute(
        """
        INSERT INTO pyq_papers (id, course_id, title, filename, raw_text)
        VALUES (?, ?, ?, ?, ?);
        """,
        (paper_id, course_id, title, filename, raw_text)
    )

    extracted_questions = parse_pyq_questions(raw_text)
    stored_questions = []
    matched_count = 0

    for q in extracted_questions:
        q_id = f"pyq_q_{uuid.uuid4().hex[:10]}"
        match = match_question_to_course(db_conn, course_id, q["question_text"])
        
        matched_lesson_id = match["lesson_id"] if match else None
        matched_chunk_id = match["chunk_id"] if match else None
        bm25_score = match["bm25_score"] if match else 0.0
        if matched_lesson_id:
            matched_count += 1

        cur.execute(
            """
            INSERT INTO pyq_questions (
                id, course_id, paper_id, question_number, question_text,
                marks, matched_lesson_id, matched_chunk_id, bm25_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                q_id, course_id, paper_id, q["question_number"], q["question_text"],
                q["marks"], matched_lesson_id, matched_chunk_id, bm25_score
            )
        )
        stored_questions.append({
            "id": q_id,
            "question_number": q["question_number"],
            "question_text": q["question_text"],
            "marks": q["marks"],
            "matched_lesson_id": matched_lesson_id,
            "matched_chunk_id": matched_chunk_id,
            "snippet": match["snippet"] if match else ""
        })

    # Update lesson hit counts and marks in database
    update_course_pyq_aggregates(db_conn, course_id)

    return {
        "paper_id": paper_id,
        "title": title,
        "filename": filename,
        "questions_count": len(stored_questions),
        "matched_count": matched_count,
        "questions": stored_questions
    }


def get_course_pyq_summary(db_conn, course_id: str) -> Dict[str, Any]:
    """Retrieves all past papers and high-yield topic stats for a course."""
    cur = db_conn.cursor()
    cur.execute(
        "SELECT id, title, filename, created_at FROM pyq_papers WHERE course_id = ? ORDER BY created_at DESC;",
        (course_id,)
    )
    papers = [dict(row) if hasattr(row, "keys") else {"id": row[0], "title": row[1], "filename": row[2], "created_at": row[3]} for row in cur.fetchall()]

    cur.execute(
        """
        SELECT id, title, pyq_hit_count, pyq_total_marks
        FROM lessons
        WHERE course_id = ? AND pyq_hit_count > 0
        ORDER BY pyq_hit_count DESC, pyq_total_marks DESC;
        """,
        (course_id,)
    )
    high_yield_lessons = [
        dict(row) if hasattr(row, "keys") else {"id": row[0], "title": row[1], "pyq_hit_count": row[2], "pyq_total_marks": row[3]}
        for row in cur.fetchall()
    ]

    cur.execute("SELECT COUNT(*) FROM pyq_questions WHERE course_id = ?;", (course_id,))
    total_q = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM pyq_questions WHERE course_id = ? AND matched_lesson_id IS NOT NULL;", (course_id,))
    matched_q = cur.fetchone()[0]

    return {
        "papers": papers,
        "total_questions": total_q,
        "matched_questions": matched_q,
        "high_yield_lessons": high_yield_lessons
    }


def get_lesson_pyq_questions(db_conn, course_id: str, lesson_id: str) -> List[Dict[str, Any]]:
    """Returns all past paper questions matched to a specific lesson."""
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT q.id, q.question_number, q.question_text, q.marks, q.bm25_score,
               p.title as paper_title, p.filename, c.content as chunk_snippet
        FROM pyq_questions q
        LEFT JOIN pyq_papers p ON q.paper_id = p.id
        LEFT JOIN chunks c ON q.matched_chunk_id = c.id
        WHERE q.course_id = ? AND q.matched_lesson_id = ?
        ORDER BY q.marks DESC NULLS LAST, q.bm25_score ASC;
        """,
        (course_id, lesson_id)
    )
    rows = cur.fetchall()
    return [
        {
            "id": r["id"] if hasattr(r, "keys") else r[0],
            "question_number": r["question_number"] if hasattr(r, "keys") else r[1],
            "question_text": r["question_text"] if hasattr(r, "keys") else r[2],
            "marks": r["marks"] if hasattr(r, "keys") else r[3],
            "bm25_score": r["bm25_score"] if hasattr(r, "keys") else r[4],
            "paper_title": r["paper_title"] if hasattr(r, "keys") else r[5],
            "filename": r["filename"] if hasattr(r, "keys") else r[6],
            "chunk_snippet": (r["chunk_snippet"] if hasattr(r, "keys") else r[7]) or ""
        }
        for r in rows
    ]
