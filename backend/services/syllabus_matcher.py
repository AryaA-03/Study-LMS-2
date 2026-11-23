"""Syllabus Parsing and Intelligent Playlist Video Alignment Engine.

Parses university/college course syllabi, topic outlines, and exam curricula,
and automatically matches relevant playlist videos and sections using:
1. Multi-token and acronym title matching with domain synonym expansion.
2. SQLite FTS5 BM25 search across lesson transcripts and chunks.
3. Content & chapter summary matching.
4. Adjustable strictness thresholds (balanced, strict, comprehensive).
"""

import re
import sqlite3
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

logger = logging.getLogger("learn_lms.syllabus_matcher")

# Common domain acronyms and synonym expansions
DOMAIN_SYNONYMS: Dict[str, List[str]] = {
    # Theory of Computation / Automata
    "dfa": ["deterministic finite automata", "deterministic finite automaton", "dfa", "finite automata"],
    "nfa": ["nondeterministic finite automata", "non deterministic finite automata", "nfa"],
    "pda": ["pushdown automata", "pushdown automaton", "pda", "push down automata"],
    "cfg": ["context free grammar", "context free grammars", "cfg", "context-free"],
    "cfl": ["context free language", "context free languages", "cfl"],
    "tm": ["turing machine", "turing machines", "tm"],
    "fsm": ["finite state machine", "finite state machines", "finite automata", "fsm"],
    "fa": ["finite automata", "finite automaton", "finite state machine"],
    "cnf": ["chomsky normal form", "cnf"],
    "gnf": ["greibach normal form", "gnf"],
    "re": ["regular expression", "regular expressions"],
    # DBMS
    "dbms": ["database management system", "database management", "dbms", "database"],
    "rdbms": ["relational database", "relational database management", "rdbms"],
    "sql": ["structured query language", "sql", "ddl", "dml", "dcl"],
    "er": ["entity relationship", "e-r diagram", "er diagram", "er model"],
    "1nf": ["first normal form", "1nf", "normalization"],
    "2nf": ["second normal form", "2nf", "normalization"],
    "3nf": ["third normal form", "3nf", "normalization"],
    "bcnf": ["boyce codd normal form", "bcnf", "boyce-codd"],
    "fd": ["functional dependency", "functional dependencies"],
    "acid": ["atomicity", "consistency", "isolation", "durability", "acid properties", "transactions"],
    # Operating Systems
    "os": ["operating system", "operating systems", "os"],
    "cpu": ["cpu scheduling", "processor scheduling", "central processing unit"],
    "ipc": ["inter process communication", "inter-process communication", "ipc"],
    "fcf": ["first come first serve", "fcfs"],
    "sjf": ["shortest job first", "sjf"],
    "rr": ["round robin", "round-robin"],
    # Data Structures & Algorithms
    "dsa": ["data structures and algorithms", "data structures", "dsa"],
    "bst": ["binary search tree", "bst"],
    "avl": ["avl tree", "balanced tree", "avl"],
    "dp": ["dynamic programming", "dp"],
    # Networking
    "cn": ["computer networks", "computer networking", "cn"],
    "tcp": ["transmission control protocol", "tcp", "tcp/ip"],
    "udp": ["user datagram protocol", "udp"],
    "osi": ["osi model", "open systems interconnection"],
}

# English stop words to ignore during token overlap scoring
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing",
    "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
    # Syllabus noise words
    "unit", "module", "chapter", "section", "lecture", "part", "syllabus", "course",
    "overview", "introduction", "basics", "concept", "concepts", "theory", "study",
}


def clean_tokens(text: str) -> Set[str]:
    """Extracts lowercase alphabetic tokens, stripping punctuation and stopwords."""
    raw = re.sub(r"[\[\]\(\)\{\}\-_,;:\"\'\/\\]", " ", text.lower())
    words = re.findall(r"\b[a-z0-9]{2,}\b", raw)
    return {w for w in words if w not in STOPWORDS}


def expand_synonyms(tokens: Set[str]) -> Set[str]:
    """Expands token set with domain synonyms and full forms."""
    expanded = set(tokens)
    for token in tokens:
        if token in DOMAIN_SYNONYMS:
            for syn in DOMAIN_SYNONYMS[token]:
                expanded.update(clean_tokens(syn))
    return expanded


def parse_syllabus_topics(raw_text: str) -> List[Dict[str, Any]]:
    """Splits raw syllabus text into structured units and discrete subtopics."""
    lines = [line.strip() for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    topics: List[Dict[str, Any]] = []

    current_unit = "General Topics"
    current_unit_index = 0

    # Header noise filter (course code, textbook listings, instructions)
    noise_prefixes = (
        "course code", "course title", "credits", "l-t-p", "prerequisite",
        "textbook", "text books", "reference book", "references", "evaluation",
        "marking scheme", "internal marks", "external marks", "examination",
        "total hours", "objective", "learning outcome", "course outcome", "co1", "co2", "co3"
    )

    for line in lines:
        if not line:
            continue

        lower_line = line.lower()
        if any(lower_line.startswith(p) for p in noise_prefixes):
            continue

        # Detect Unit / Module / Chapter header
        unit_match = re.match(
            r"^(?:unit|module|chapter|section|part)\s*[-:]?\s*([0-9ivxlc]+|[a-z])\s*[-:]?\s*(.*)$",
            line,
            re.IGNORECASE
        )
        if unit_match:
            unit_id = unit_match.group(1).strip()
            unit_desc = unit_match.group(2).strip()
            current_unit_index += 1
            current_unit = f"Unit {unit_id.upper()}: {unit_desc}" if unit_desc else f"Unit {unit_id.upper()}"
            if unit_desc:
                line = unit_desc
            else:
                continue

        # Split line by common topic delimiters: commas, semicolons, bullets, numbered lists
        # E.g. "1. DFA, NFA, Minimization of DFA; Pumping Lemma"
        clean_line = re.sub(r"^[\s\*\-\•\–\—\d+\.]+\s*", "", line)
        delimiters = r"[,;•\*\-\–\—]|\s+\d+\.\s+"
        parts = [p.strip() for p in re.split(delimiters, clean_line) if p.strip()]

        for part in parts:
            # Strip trailing punctuation
            part_cleaned = re.sub(r"^[0-9\.\-\:\)]+\s*", "", part).strip(" .,;:()")
            if len(part_cleaned) >= 3 and not any(part_cleaned.lower().startswith(p) for p in noise_prefixes):
                tokens = clean_tokens(part_cleaned)
                if tokens:
                    topics.append({
                        "unit": current_unit,
                        "topic": part_cleaned,
                        "tokens": tokens,
                        "expanded_tokens": expand_synonyms(tokens),
                    })

    # If parsing found very few topics, treat non-empty lines as individual topics
    if not topics:
        for line in lines:
            trimmed = line.strip(" -*•0123456789.:,;")
            if len(trimmed) >= 3:
                tokens = clean_tokens(trimmed)
                if tokens:
                    topics.append({
                        "unit": "General Topics",
                        "topic": trimmed,
                        "tokens": tokens,
                        "expanded_tokens": expand_synonyms(tokens),
                    })

    return topics


def score_lesson_against_topic(
    lesson_title: str,
    lesson_chapter: str,
    topic: Dict[str, Any],
) -> Tuple[float, str]:
    """Scores how strongly a lesson title and chapter match a syllabus topic.
    Returns (score: 0.0 to 1.0, reason: str).
    """
    title_lower = lesson_title.lower()
    topic_str = topic["topic"].lower()

    # 1. Exact phrase substring match in title (Highest Confidence)
    if len(topic_str) >= 4 and topic_str in title_lower:
        return (0.95, f"Direct title match with '{topic['topic']}'")

    # 2. Exact phrase in chapter title
    if lesson_chapter and len(topic_str) >= 4 and topic_str in lesson_chapter.lower():
        return (0.90, f"Chapter match with '{topic['topic']}'")

    # 3. Token Overlap Scoring
    lesson_tokens = clean_tokens(lesson_title + " " + (lesson_chapter or ""))
    lesson_expanded = expand_synonyms(lesson_tokens)

    topic_tokens = topic["tokens"]
    topic_expanded = topic["expanded_tokens"]

    if not topic_tokens or not lesson_tokens:
        return (0.0, "")

    # Direct token intersection
    direct_common = topic_tokens.intersection(lesson_tokens)
    if len(direct_common) == len(topic_tokens) and len(topic_tokens) > 0:
        return (0.88, f"Full keyword match for '{topic['topic']}'")

    # Expanded intersection (acronyms & synonyms)
    expanded_common = topic_expanded.intersection(lesson_expanded)
    if len(topic_tokens) > 0:
        direct_ratio = len(direct_common) / len(topic_tokens)
        expanded_ratio = min(1.0, len(expanded_common) / len(topic_tokens))
        score = max(direct_ratio, expanded_ratio * 0.85)

        if score >= 0.20:
            matched_words = ", ".join(list(expanded_common)[:3])
            return (round(score, 2), f"Matched on keywords ({matched_words})")

    return (0.0, "")


def match_syllabus_to_course(
    course_id: str,
    syllabus_text: str,
    strictness: str = "balanced",
    db: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Matches course lessons against pasted syllabus text and returns structured breakdown."""
    if not db:
        raise ValueError("A database connection is required for syllabus matching.")

    # Threshold based on strictness
    thresholds = {
        "strict": 0.55,
        "balanced": 0.35,
        "comprehensive": 0.20,
    }
    min_threshold = thresholds.get(strictness.lower(), 0.35)

    # 1. Parse syllabus topics
    parsed_topics = parse_syllabus_topics(syllabus_text)
    if not parsed_topics:
        raise ValueError("Could not extract any recognizable topics from the syllabus text.")

    # 2. Fetch all course lessons
    lessons_rows = db.execute(
        """
        SELECT id, course_id, title, raw_duration_sec, order_index, chapter_title, is_excluded
        FROM lessons
        WHERE course_id = ?
        ORDER BY order_index ASC;
        """,
        (course_id,)
    ).fetchall()

    if not lessons_rows:
        raise ValueError(f"No lessons found for course {course_id}")

    # Check if chunks_fts is available for deep transcript search
    has_fts = False
    try:
        fts_check = db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='chunks_fts';"
        ).fetchone()
        has_fts = bool(fts_check and fts_check[0] > 0)
    except Exception:
        has_fts = False

    # 3. Match each lesson against topics
    lesson_match_results: List[Dict[str, Any]] = []
    topic_lesson_mapping: Dict[str, List[str]] = {t["topic"]: [] for t in parsed_topics}

    total_lessons = len(lessons_rows)
    matched_count = 0
    saved_minutes = 0

    for l in lessons_rows:
        l_id = l["id"]
        title = l["title"]
        chapter = l["chapter_title"] or ""
        duration = l["raw_duration_sec"] or 0
        order_idx = l["order_index"] or 0

        best_score = 0.0
        best_reason = ""
        matched_topics_list: List[str] = []

        # Check against every parsed topic
        for top in parsed_topics:
            t_score, t_reason = score_lesson_against_topic(title, chapter, top)
            if t_score > best_score:
                best_score = t_score
                best_reason = t_reason

            if t_score >= min_threshold:
                if top["topic"] not in matched_topics_list:
                    matched_topics_list.append(top["topic"])
                topic_lesson_mapping[top["topic"]].append(l_id)

        # FTS5 Transcript Booster if title score was low
        if has_fts and best_score < min_threshold and len(title) > 0:
            for top in parsed_topics[:15]:  # Check top topics
                safe_kw = " OR ".join([f'"{w}"' for w in top["tokens"] if len(w) >= 3])
                if not safe_kw:
                    continue
                try:
                    fts_row = db.execute(
                        """
                        SELECT COUNT(*) FROM chunks_fts
                        WHERE chunks_fts MATCH ? AND lesson_id = ?;
                        """,
                        (safe_kw, l_id)
                    ).fetchone()
                    if fts_row and fts_row[0] > 0:
                        fts_score = min(0.65, 0.30 + (fts_row[0] * 0.1))
                        if fts_score > best_score:
                            best_score = fts_score
                            best_reason = f"Transcript content match with '{top['topic']}' ({fts_row[0]} hits)"
                            if top["topic"] not in matched_topics_list:
                                matched_topics_list.append(top["topic"])
                            topic_lesson_mapping[top["topic"]].append(l_id)
                            break
                except Exception:
                    pass

        is_matched = best_score >= min_threshold

        if is_matched:
            matched_count += 1
        else:
            saved_minutes += round(duration / 60)

        lesson_match_results.append({
            "id": l_id,
            "title": title,
            "raw_duration_sec": duration,
            "order_index": order_idx,
            "is_matched": is_matched,
            "match_score": round(best_score, 2),
            "matched_topics": matched_topics_list,
            "match_reason": best_reason if is_matched else "Out of syllabus",
        })

    # Group topics for response
    topics_response = []
    seen_topics = set()
    for top in parsed_topics:
        top_name = top["topic"]
        if top_name in seen_topics:
            continue
        seen_topics.add(top_name)
        matched_ids = list(set(topic_lesson_mapping.get(top_name, [])))
        topics_response.append({
            "topic": top_name,
            "unit": top.get("unit", "General Topics"),
            "matched_lesson_count": len(matched_ids),
            "matched_lesson_ids": matched_ids,
        })

    matched_pct = round((matched_count / total_lessons * 100), 1) if total_lessons > 0 else 0.0

    return {
        "course_id": course_id,
        "total_lessons": total_lessons,
        "matched_lessons_count": matched_count,
        "matched_percentage": matched_pct,
        "saved_minutes": saved_minutes,
        "topics": topics_response,
        "lessons": lesson_match_results,
    }
