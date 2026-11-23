"""Playlist & Multi-Video Topic Clustering Service.

Automatically combines related short playlist videos (e.g., "DFA Part 1", "DFA Part 2",
"DFA Example 1", "DFA Practice Problem") into unified structured topic groups stored in
`lessons.chapter_title`, and classifies lesson roles (`concept`, `example`, `practice`)
using title patterns and subtitle/transcript keyword overlap.
"""

import re
import sqlite3
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

_STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "of", "in", "on", "to", "for", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "as", "at", "it", "this", "that", "how",
    "what", "why", "when", "into", "about", "using", "via", "vs", "versus", "full",
    "complete", "course", "tutorial", "lecture", "video", "class", "series", "gate",
    "cs", "cse", "ugc", "net", "exam", "prep", "playlist", "hindi", "english",
}

_STRIP_PATTERNS = [
    r"\|.*$",                                         # "| Neso Academy", "| Gate Smashers"
    r"\[[^\]]*\]",                                    # "[HD]", "[Part 1]"
    r"\(\s*(?:part|pt|lec|lecture|ep|episode|vid|video|ex|example|prob|problem|q|question|solved|practice|basics?|intro|introduction|hindi|english|hd)\b[^)]*\)",
    r"\b(?:part|pt|lecture|lec|lesson|module|unit|chapter|ep|episode|video|vid)\s*[-:#.]?\s*\d+\b",
    r"\b(?:example|examples|ex|problem|problems|prob|question|questions|numerical|numericals|exercise|practice|solved|solution|solutions|demo|case\s*study)\s*[-:#.]?\s*\d*\b",
    r"\b(?:introduction\s+to|intro\s+to|basics?\s+of|overview\s+of|summary\s+of|revision\s+of)\b",
    r"(?:^|\s)#\d+\b",                                # "#12"
    r"^\s*\d+\s*[\.\-\):]\s*",                        # "01. ", "12 - "
    r"\s*[-–—:]\s*\d+\s*$",                           # trailing "- 1"
]

_EXAMPLE_RE = re.compile(
    r"\b(example|examples|ex\s*\d|problem|problems|solved|numerical|exercise|practice|question|questions|walkthrough|demo|worked|trace|dry\s*run|construct|design\s+a|convert|conversion\s+example|gate\s+\d{4}|pyq)\b",
    re.IGNORECASE,
)


def classify_lesson_role(title: str) -> str:
    """Classify a lesson as 'example' or 'concept' for accurate Lesson Rail filtering."""
    if not title:
        return "concept"
    if _EXAMPLE_RE.search(title):
        return "example"
    return "concept"


def normalize_topic_stem(title: str) -> str:
    """Strip episode/part/example markers and channel suffixes to extract the core topic stem."""
    s = (title or "").strip()
    for pat in _STRIP_PATTERNS:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    # Remove leftover empty brackets or trailing punctuation
    s = re.sub(r"\(\s*\)", " ", s)
    s = re.sub(r"[\-–—:|/]+$", " ", s)
    s = re.sub(r"^[\-–—:|/]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _stem_tokens(text: str) -> Set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS and not w.isdigit()}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _pick_group_label(stems: List[str], original_titles: List[str]) -> str:
    """Choose the cleanest human-readable topic title for a cluster of videos."""
    candidates = [s for s in stems if len(s) >= 3]
    if candidates:
        # Prefer the shortest non-trivial stem that appears most frequently
        counts = Counter(c.lower() for c in candidates)
        best_lower = max(
            counts.keys(),
            key=lambda k: (counts[k], -len(k)),
        )
        for c in candidates:
            if c.lower() == best_lower:
                return c[:80]
    fallback = re.sub(r"\|.*$", "", original_titles[0]).strip()
    return (fallback or "Core Concepts")[:80]


def group_playlist_lessons(
    lessons: List[Dict[str, Any]],
    transcript_keywords: Optional[Dict[str, Set[str]]] = None,
    similarity_threshold: float = 0.45,
) -> List[Dict[str, Any]]:
    """Cluster sequential playlist videos into unified Topic Groups.

    Each input dict should have at least `id` and `title` (and optionally `chapter_title`,
    `order_index`). Returns a list of dicts:
        [{"lesson_id": ..., "chapter_title": ..., "role": "concept"|"example", "group_size": N}]
    """
    if not lessons:
        return []

    transcript_keywords = transcript_keywords or {}
    clusters: List[List[Tuple[Dict[str, Any], str, Set[str]]]] = []

    for les in lessons:
        title = str(les.get("title") or "")
        stem = normalize_topic_stem(title)
        t_tokens = _stem_tokens(stem)
        kw_tokens = transcript_keywords.get(str(les.get("id", "")), set())

        if not clusters:
            clusters.append([(les, stem, t_tokens)])
            continue

        # Compare against the current open cluster (playlist videos are sequential)
        prev_cluster = clusters[-1]
        anchor_stem = prev_cluster[0][1]
        anchor_tokens = prev_cluster[0][2]
        last_tokens = prev_cluster[-1][2]

        sim_anchor = _jaccard(t_tokens, anchor_tokens)
        sim_last = _jaccard(t_tokens, last_tokens)
        sim_title = max(sim_anchor, sim_last)

        # Check substring containment for stems like "DFA" vs "DFA Examples"
        stem_l = stem.lower()
        anchor_l = anchor_stem.lower()
        contained = (
            bool(stem_l and anchor_l)
            and min(len(stem_l), len(anchor_l)) >= 3
            and (stem_l in anchor_l or anchor_l in stem_l)
        )

        # Optional subtitle/transcript overlap boost when available
        sim_sub = 0.0
        if kw_tokens:
            prev_kw = transcript_keywords.get(str(prev_cluster[-1][0].get("id", "")), set())
            if prev_kw:
                sim_sub = _jaccard(kw_tokens, prev_kw)

        # If this video is explicitly an example/problem with a short/generic stem (e.g., "Example 1"),
        # attach it directly to the preceding topic cluster!
        is_generic_example = (
            classify_lesson_role(title) == "example" and len(t_tokens) <= 1
        )

        should_merge = (
            contained
            or is_generic_example
            or sim_title >= similarity_threshold
            or (sim_title >= 0.25 and sim_sub >= 0.30)
        )

        # Avoid overly huge mega-clusters (> 10 videos in one topic)
        if should_merge and len(prev_cluster) < 10:
            prev_cluster.append((les, stem, t_tokens))
        else:
            clusters.append([(les, stem, t_tokens)])

    results: List[Dict[str, Any]] = []
    for cluster in clusters:
        stems = [item[1] for item in cluster]
        titles = [str(item[0].get("title") or "") for item in cluster]
        label = _pick_group_label(stems, titles)
        for les, _, _ in cluster:
            results.append(
                {
                    "lesson_id": les["id"],
                    "chapter_title": label,
                    "role": classify_lesson_role(str(les.get("title") or "")),
                    "group_size": len(cluster),
                }
            )
    return results


def cluster_course_topics(db: sqlite3.Connection, course_id: str) -> Dict[str, Any]:
    """Run topic clustering across all lessons in a course and persist `chapter_title`."""
    rows = db.execute(
        """
        SELECT id, title, chapter_title, order_index
        FROM lessons
        WHERE course_id = ?
        ORDER BY order_index ASC, id ASC;
        """,
        (course_id,),
    ).fetchall()

    if not rows:
        return {"course_id": course_id, "lessons_updated": 0, "topics_created": 0, "topics": []}

    lessons = [
        {"id": r["id"], "title": r["title"], "chapter_title": r["chapter_title"], "order_index": r["order_index"]}
        for r in rows
    ]

    # Collect top transcript keywords per lesson when chunks exist
    transcript_keywords: Dict[str, Set[str]] = {}
    chunk_rows = db.execute(
        "SELECT lesson_id, content FROM chunks WHERE course_id = ?;",
        (course_id,),
    ).fetchall()
    by_lesson: Dict[str, List[str]] = {}
    for cr in chunk_rows:
        lid = cr["lesson_id"]
        if lid:
            by_lesson.setdefault(lid, []).append(cr["content"] or "")
    for lid, texts in by_lesson.items():
        words = re.findall(r"[a-zA-Z]{3,}", " ".join(texts[:8]).lower())
        counts = Counter(w for w in words if w not in _STOPWORDS)
        transcript_keywords[lid] = {w for w, _ in counts.most_common(12)}

    grouped = group_playlist_lessons(lessons, transcript_keywords=transcript_keywords)

    topic_counts: Dict[str, int] = {}
    for item in grouped:
        label = item["chapter_title"]
        topic_counts[label] = topic_counts.get(label, 0) + 1
        db.execute(
            "UPDATE lessons SET chapter_title = ? WHERE id = ? AND course_id = ?;",
            (label, item["lesson_id"], course_id),
        )
    db.commit()

    return {
        "course_id": course_id,
        "lessons_updated": len(grouped),
        "topics_created": len(topic_counts),
        "topics": [{"title": k, "lesson_count": v} for k, v in topic_counts.items()],
    }
