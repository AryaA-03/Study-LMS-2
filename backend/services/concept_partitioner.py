from backend.services.llm_cache import compute_prompt_hash, get_cached_response, set_cached_response
import hashlib
"""Concept Clip Partitioner (Layer 1: Immutable Content).

Partitions educational videos sequentially from 00:00 to video_end into
~10–15 min (acceptable range: 8–18 min) self-contained Concept / Sub-Topic Clips.
Guarantees:
- Zero gaps, zero overlaps (clip[0].start_sec == 0, clip[i].end_sec == clip[i+1].start_sec, clip[-1].end_sec == total_duration).
- Single concepts > 18-20 min are split cleanly at natural sub-topic transitions into sequential parts.
- Tiny < 3 min intro/outro micro-chapters are merged into adjacent topics.
- Two partition modes:
  1. Deterministic Mode (Zero-LLM, Instant): YouTube chapters first, splitting any > 18 min
     at natural transcript sentence/silence gaps closest to 12–15 min.
  2. AI-Assisted Semantic Mode (Runs ONCE on import): 45–60 min sliding windows for marathon videos,
     snaps boundaries to exact concept transitions, clean syllabus titles, tags core vs deep-dive.
- Permanent Attachment: Never rewrites or deletes concept clips on schedule edits.
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

logger = logging.getLogger("learn_lms.concept_partitioner")
settings = get_settings()

TARGET_DURATION_SEC = 780   # ~13 minutes
MIN_CLIP_SEC = 480          # 8 minutes
MAX_CLIP_SEC = 1080         # 18 minutes
MIN_CHAPTER_MERGE_SEC = 180 # 3 minutes


def format_timestamp_pill(seconds: int) -> str:
    """Formats seconds into [MM:SS] or [HH:MM:SS]."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def detect_priority_tag(title: str, text_sample: str = "") -> str:
    """Classifies a concept clip as 'core' vs 'deep-dive' based on title and content keywords."""
    combined = (title + " " + text_sample).lower()
    deep_dive_keywords = [
        "example", "examples", "problem", "problems", "exercise", "exercises",
        "question", "questions", "practice", "gate", "pyq", "walkthrough",
        "numerical", "numericals", "solution", "solutions", "solved",
        "hands-on", "demo", "coding", "implementation", "proof", "derivation"
    ]
    if any(kw in combined for kw in deep_dive_keywords):
        return "deep-dive"
    return "core"


def merge_tiny_chapters(
    raw_chapters: List[Dict[str, Any]],
    total_duration: int,
    min_sec: int = MIN_CHAPTER_MERGE_SEC
) -> List[Dict[str, Any]]:
    """Merges chapters shorter than 3 minutes (< 180s) into adjacent chapters."""
    if not raw_chapters:
        return []

    clean_chapters = []
    for idx, ch in enumerate(raw_chapters):
        title = ch.get("title", f"Chapter {idx + 1}").strip()
        start = int(ch.get("start_time", 0))
        end = int(ch.get("end_time", total_duration))
        if end > total_duration:
            end = total_duration
        dur = end - start
        if dur <= 0:
            continue
        clean_chapters.append({
            "title": title,
            "start_time": start,
            "end_time": end,
            "duration": dur,
        })

    if not clean_chapters:
        return []

    merged = []
    i = 0
    while i < len(clean_chapters):
        curr = dict(clean_chapters[i])
        while curr["duration"] < min_sec and (i + 1) < len(clean_chapters):
            nxt = clean_chapters[i + 1]
            curr["end_time"] = nxt["end_time"]
            curr["duration"] = curr["end_time"] - curr["start_time"]
            c_low = curr["title"].lower()
            if any(w in c_low for w in ["intro", "bumper", "teaser", "welcome", "about", "subscribe", "overview"]):
                curr["title"] = nxt["title"]
            elif nxt["duration"] < min_sec:
                curr["title"] = f"{curr['title']} & {nxt['title']}"
            else:
                curr["title"] = nxt["title"]
            i += 1

        if curr["duration"] < min_sec and merged:
            prev = merged[-1]
            prev["end_time"] = curr["end_time"]
            prev["duration"] = prev["end_time"] - prev["start_time"]
        else:
            merged.append(curr)
        i += 1

    return merged


def find_best_transcript_split_point(
    transcript_chunks_or_words: List[Dict[str, Any]],
    window_start: int,
    window_end: int,
    target_split: int,
    min_split: int,
    max_split: int
) -> int:
    """Finds natural sentence or silence gap closest to target_split within [min_split, max_split]."""
    if not transcript_chunks_or_words:
        return min(window_end, max(window_start, target_split))

    candidate_points: List[Tuple[float, int]] = []  # (score, timestamp_sec)

    for item in transcript_chunks_or_words:
        s = int(item.get("start_sec", item.get("start", 0)))
        e = int(item.get("end_sec", item.get("end", s)))
        text = str(item.get("content", item.get("text", ""))).strip()

        # Check end of item as potential cut point
        if min_split <= e <= max_split:
            dist = abs(e - target_split)
            score = dist
            if text.endswith((".", "?", "!")):
                score -= 60  # Preference for sentence end
            candidate_points.append((score, e))

        # Check start of item
        if min_split <= s <= max_split:
            dist = abs(s - target_split)
            score = dist + 15
            candidate_points.append((score, s))

    if candidate_points:
        candidate_points.sort(key=lambda x: x[0])
        return candidate_points[0][1]

    # Fallback to target_split clamped
    return min(max_split, max(min_split, target_split))


def split_long_segment_deterministic(
    title: str,
    seg_start: int,
    seg_end: int,
    transcript_data: Optional[List[Dict[str, Any]]] = None,
    target_sec: int = TARGET_DURATION_SEC,
    min_sec: int = MIN_CLIP_SEC,
    max_sec: int = MAX_CLIP_SEC
) -> List[Dict[str, Any]]:
    """Splits a long segment (> 18 min) deterministically into sequential ~10-15 min parts."""
    total_dur = seg_end - seg_start
    if total_dur <= max_sec:
        return [{
            "title": title,
            "start_sec": seg_start,
            "end_sec": seg_end,
            "raw_duration_sec": total_dur,
        }]

    # Determine number of parts needed so each is between min_sec and max_sec
    num_parts = max(2, round(total_dur / target_sec))
    ideal_step = total_dur / num_parts

    slices: List[Dict[str, Any]] = []
    curr_start = seg_start

    for part_idx in range(1, num_parts + 1):
        if part_idx == num_parts:
            curr_end = seg_end
        else:
            ideal_target = int(curr_start + ideal_step)
            min_boundary = curr_start + min_sec
            max_boundary = min(seg_end - min_sec, curr_start + max_sec)

            if max_boundary > min_boundary:
                curr_end = find_best_transcript_split_point(
                    transcript_data or [],
                    curr_start,
                    seg_end,
                    ideal_target,
                    min_boundary,
                    max_boundary,
                )
            else:
                curr_end = min(seg_end, curr_start + target_sec)

        dur = curr_end - curr_start
        if dur > 0:
            part_title = f"{title} — Part {part_idx}"
            slices.append({
                "title": part_title,
                "start_sec": curr_start,
                "end_sec": curr_end,
                "raw_duration_sec": dur,
            })
            curr_start = curr_end

    return slices



_FILLER_WORDS = {
    "hello", "everyone", "welcome", "basically", "actually", "video", "lecture",
    "guys", "okay", "today", "friends", "please", "subscribe", "channel", "watch",
    "going", "talk", "about", "learn", "understand", "thing", "things", "really",
    "very", "just", "like", "know", "mean", "right", "here", "there", "this", "that",
    "these", "those", "with", "from", "have", "will", "would", "could", "should",
    "been", "being", "their", "them", "they", "what", "when", "where", "which",
    "while", "because", "into", "over", "also", "then", "than", "some", "more",
    "most", "such", "only", "make", "made", "take", "used", "using", "lets", "let",
    "part", "chapter", "section", "topic", "lesson", "course", "complete", "oneshot",
    "shot", "hindi", "english", "semester", "exam", "full",
}


def extract_deterministic_topic_title(
    slice_chunks: List[Dict[str, Any]],
    fallback_title: str,
    part_index: int,
) -> str:
    """Extract a readable domain-keyword title from transcript chunks when no LLM key is configured."""
    if not slice_chunks:
        return f"{fallback_title} — Part {part_index}"
    text = " ".join((c.get("content") or c.get("text") or "") for c in slice_chunks)
    # Prefer multi-word capitalized phrases or technical acronyms/keywords
    words = re.findall(r"[A-Za-z][A-Za-z0-9+/#-]{2,}", text)
    freq: Dict[str, int] = {}
    display_map: Dict[str, str] = {}
    for w in words:
        lw = w.lower()
        if lw in _FILLER_WORDS or lw.isdigit() or len(lw) < 3:
            continue
        freq[lw] = freq.get(lw, 0) + (2 if any(ch.isupper() for ch in w) or "+" in w else 1)
        if lw not in display_map or (w[0].isupper() and not display_map[lw][0].isupper()):
            display_map[lw] = w
    if not freq:
        return f"{fallback_title} — Part {part_index}"
    top_terms = [display_map[k].title() if display_map[k].islower() else display_map[k]
                 for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]
    if len(top_terms) >= 2:
        return " & ".join([", ".join(top_terms[:-1]), top_terms[-1]]) if len(top_terms) > 2 else f"{top_terms[0]} & {top_terms[1]}"
    return f"{top_terms[0]} Concepts"


def _sample_window_uniformly(
    window_chunks: List[Dict[str, Any]],
    window_start: int,
    window_end: int,
    bucket_sec: int = 60,
    max_chars: int = 12000,
) -> str:
    """Uniformly sample 1 concise timestamped snippet per ~60s bucket across the ENTIRE window."""
    if not window_chunks:
        return ""
    buckets: Dict[int, List[str]] = {}
    for ch in window_chunks:
        s = int(ch.get("start_sec", window_start))
        b_idx = max(0, (s - window_start) // max(15, bucket_sec))
        txt = (ch.get("content") or ch.get("text") or "").strip().replace("\n", " ")
        if txt:
            buckets.setdefault(b_idx, []).append(txt)

    lines: List[str] = []
    total_chars = 0
    for b_idx in sorted(buckets.keys()):
        ts = window_start + b_idx * bucket_sec
        snippet = " ".join(buckets[b_idx])[:260]
        line = f"[{format_timestamp_pill(ts)}] ({ts}s): {snippet}"
        if total_chars + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total_chars += len(line) + 1
    return "\n".join(lines)


async def _call_llm_for_window_async(
    video_title: str,
    window_chunks: List[Dict[str, Any]],
    window_start: int,
    window_end: int,
    db_conn=None,
) -> Optional[List[Dict[str, Any]]]:
    """Async semantic boundary detection via unified LLMGateway with full-window uniform sampling."""
    from backend.config import get_settings
    from backend.infra.llm_gateway import get_llm_gateway

    settings = get_settings()
    if not (settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY or settings.OLLAMA_BASE_URL):
        return None

    transcript_text = _sample_window_uniformly(window_chunks, window_start, window_end)
    if not transcript_text.strip():
        return None

    active_model = settings.GEMINI_MODEL if settings.GEMINI_API_KEY else (
        settings.GROQ_MODEL if settings.GROQ_API_KEY else (
            settings.OPENROUTER_MODEL if settings.OPENROUTER_API_KEY else settings.OLLAMA_MODEL
        )
    )
    prompt_sig = f"semantic_partition_v2|{active_model}|{video_title}|{window_start}|{window_end}|{hashlib.sha256(transcript_text.encode('utf-8')).hexdigest()[:16]}"
    prompt_hash = compute_prompt_hash(prompt_sig)
    if db_conn is not None:
        cached = get_cached_response(db_conn, prompt_hash)
        if cached:
            try:
                parsed_c = json.loads(cached)
                if isinstance(parsed_c, list) and len(parsed_c) >= 1:
                    return parsed_c
            except Exception:
                pass

    system_instruction = (
        "You are an expert university CS & engineering curriculum architect. "
        "Split this lecture transcript window into sequential, self-contained 10-15 minute Concept Clips. "
        "CRITICAL: Give every clip a clean Module/Unit name (`module_title`, e.g., 'B+ Tree Indexing') "
        "AND a specific, scannable concept title (`title`, e.g., 'Insertion & Leaf-Node Splitting'). "
        "NEVER use generic titles like 'Part 1', '[00:00 - 15:00]', or copy the raw YouTube video title. "
        "Return ONLY valid JSON."
    )
    prompt = f"""Video Title: {video_title}
Window Range: {window_start}s ({format_timestamp_pill(window_start)}) to {window_end}s ({format_timestamp_pill(window_end)})

Uniformly Sampled Timestamped Transcript:
{transcript_text}

Return JSON with this exact schema:
{{
  "clips": [
    {{
      "start_sec": {window_start},
      "end_sec": {min(window_end, window_start + 780)},
      "module_title": "Unit/Module Name (3-5 words)",
      "title": "Specific Concept Topic Title (4-8 words)",
      "priority_tag": "core",
      "clip_type": "concept",
      "objective": "One-sentence learning outcome"
    }}
  ]
}}
Rules:
1. Clips must be contiguous from {window_start} to {window_end} with zero gaps or overlaps.
2. Target 8-18 minutes per clip; split at genuine topic transitions.
3. priority_tag must be "core" or "deep-dive"; clip_type must be "concept" or "example".
"""
    raw_text, model_used = await get_llm_gateway().generate_text(
        prompt=prompt,
        system_instruction=system_instruction,
        json_mode=True,
        temperature=0.2,
        max_tokens=2048,
    )
    if not raw_text:
        return None
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = json.loads(cleaned)
        clips_list = parsed.get("clips") if isinstance(parsed, dict) else parsed
        if isinstance(clips_list, list) and len(clips_list) >= 1:
            if db_conn is not None:
                try:
                    set_cached_response(db_conn, prompt_hash, model_used or active_model, json.dumps(clips_list))
                except Exception:
                    pass
            return clips_list
    except Exception as exc:
        logger.warning(f"Failed parsing async semantic partition JSON: {exc}")
    return None


async def partition_video_semantic_ai_async(
    video_meta: Dict[str, Any],
    transcript_data: List[Dict[str, Any]],
    window_duration_sec: int = 3000,
    db_conn=None,
) -> Optional[List[Dict[str, Any]]]:
    """Async sliding-window semantic partitioner powered by LLMGateway."""
    duration = int(video_meta.get("duration") or 0)
    if duration <= 0 and transcript_data:
        duration = max(int(c.get("end_sec", 0)) for c in transcript_data)
    if duration <= 0 or not transcript_data:
        return None

    video_id = video_meta.get("id", "")
    video_url = video_meta.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
    title = video_meta.get("title", "Lecture")

    all_clips: List[Dict[str, Any]] = []
    current_start = 0
    order_idx = 0

    while current_start < duration:
        window_end = min(current_start + window_duration_sec, duration)
        if duration - window_end < 600:
            window_end = duration

        window_chunks = [
            c for c in transcript_data
            if int(c.get("start_sec", 0)) >= current_start - 30 and int(c.get("start_sec", 0)) <= window_end + 30
        ]
        llm_clips = await _call_llm_for_window_async(
            title, window_chunks, current_start, window_end, db_conn=db_conn
        )
        if not llm_clips:
            return None

        prev_end = current_start
        for item in llm_clips:
            c_start = max(prev_end, int(item.get("start_sec", prev_end)))
            c_end = min(window_end, int(item.get("end_sec", window_end)))
            if c_end <= c_start:
                continue
            c_title = str(item.get("title") or "").strip() or f"{title} Concept {order_idx + 1}"
            mod_title = str(item.get("module_title") or item.get("chapter_title") or "").strip()
            if mod_title.lower() == c_title.lower():
                mod_title = ""
            prio = str(item.get("priority_tag") or "core").lower()
            if prio not in ("core", "deep-dive"):
                prio = "core"
            all_clips.append({
                "id": f"clip_{uuid.uuid4().hex[:10]}",
                "title": c_title,
                "chapter_title": mod_title,
                "module_title": mod_title,
                "start_sec": c_start,
                "end_sec": c_end,
                "raw_duration_sec": max(60, c_end - c_start),
                "video_id": video_id,
                "video_url": video_url,
                "priority_tag": prio,
                "priority": prio,
                "clip_type": str(item.get("clip_type") or "concept"),
                "objective": str(item.get("objective") or ""),
                "order_index": order_idx,
            })
            prev_end = c_end
            order_idx += 1

        if prev_end < window_end and all_clips:
            all_clips[-1]["end_sec"] = window_end
            all_clips[-1]["raw_duration_sec"] = max(60, window_end - all_clips[-1]["start_sec"])
        current_start = window_end

    return all_clips if all_clips else None


async def partition_video_async(
    video_meta: Dict[str, Any],
    transcript_data: Optional[List[Dict[str, Any]]] = None,
    mode: str = "auto",
    db_conn=None,
) -> List[Dict[str, Any]]:
    """Async primary entry point: uses LLMGateway semantic partitioning when transcript & key exist, else smart deterministic."""
    if transcript_data and mode in ("auto", "semantic"):
        res = await partition_video_semantic_ai_async(video_meta, transcript_data, db_conn=db_conn)
        if res:
            return res
    return partition_video_deterministic(video_meta, transcript_data=transcript_data)


def partition_video_deterministic(
    video_meta: Dict[str, Any],
    transcript_data: Optional[List[Dict[str, Any]]] = None,
    target_duration_sec: int = TARGET_DURATION_SEC,
    min_clip_sec: int = MIN_CLIP_SEC,
    max_clip_sec: int = MAX_CLIP_SEC,
) -> List[Dict[str, Any]]:
    """Deterministic Concept Clip partitioner (Zero-LLM, Instant).
    
    Uses YouTube chapters first; splits any chapter > 18 min at natural transcript
    sentence/silence gaps closest to 12-15 min. If chapter-less, partitions continuously.
    """
    total_duration = int(video_meta.get("duration") or 0)
    video_id = video_meta.get("id") or "video"
    video_title = video_meta.get("title", "Lecture")
    video_url = video_meta.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

    if total_duration <= 0:
        total_duration = 900  # Default 15 min if unknown

    # Short videos (<= 18 min) are a single concept clip
    if total_duration <= max_clip_sec:
        p_tag = detect_priority_tag(video_title)
        return [{
            "id": str(uuid.uuid4()),
            "source_id": video_meta.get("source_id"),
            "order_index": 0,
            "title": video_title,
            "start_sec": 0,
            "end_sec": total_duration,
            "raw_duration_sec": total_duration,
            "priority_tag": p_tag,
            "status": "not_started",
            "video_id": video_id,
            "video_url": video_url,
        }]

    raw_chapters = video_meta.get("chapters") or []
    clips: List[Dict[str, Any]] = []

    if raw_chapters:
        # Chapter-based splitting with 3-minute merging rule
        effective_chapters = merge_tiny_chapters(raw_chapters, total_duration, min_sec=MIN_CHAPTER_MERGE_SEC)
        
        # Ensure continuity from 0 to total_duration
        if effective_chapters:
            effective_chapters[0]["start_time"] = 0
            effective_chapters[-1]["end_time"] = total_duration
            for idx in range(len(effective_chapters) - 1):
                effective_chapters[idx]["end_time"] = effective_chapters[idx + 1]["start_time"]

        for ch in effective_chapters:
            ch_title = ch.get("title", "Concept").strip()
            ch_start = int(ch.get("start_time", 0))
            ch_end = int(ch.get("end_time", total_duration))
            ch_dur = ch_end - ch_start
            if ch_dur <= 0:
                continue

            if ch_dur > max_clip_sec:
                # Split chapter > 18 min into natural parts
                sub_slices = split_long_segment_deterministic(
                    ch_title,
                    ch_start,
                    ch_end,
                    transcript_data,
                    target_sec=target_duration_sec,
                    min_sec=min_clip_sec,
                    max_sec=max_clip_sec,
                )
                clips.extend(sub_slices)
            else:
                clips.append({
                    "title": ch_title,
                    "start_sec": ch_start,
                    "end_sec": ch_end,
                    "raw_duration_sec": ch_dur,
                })
    else:
        # Chapter-less video: partition continuously across total_duration
        curr_start = 0
        while curr_start < total_duration:
            ideal_target = curr_start + target_duration_sec
            min_boundary = curr_start + min_clip_sec
            max_boundary = curr_start + max_clip_sec

            # If remaining piece after this cut would be < min_clip_sec, merge it into this clip
            if (total_duration - ideal_target) < min_clip_sec or (total_duration - max_boundary) < 180:
                curr_end = total_duration
            else:
                curr_end = find_best_transcript_split_point(
                    transcript_data or [],
                    curr_start,
                    total_duration,
                    ideal_target,
                    min_boundary,
                    min(total_duration, max_boundary),
                )

            dur = curr_end - curr_start
            time_label = f"[{format_timestamp_pill(curr_start)} - {format_timestamp_pill(curr_end)}]"
            clips.append({
                "title": f"{video_title} {time_label}",
                "start_sec": curr_start,
                "end_sec": curr_end,
                "raw_duration_sec": dur,
            })
            curr_start = curr_end

    # Post-process: enforce strict continuity and format output
    final_clips: List[Dict[str, Any]] = []
    last_end = 0

    for i, c in enumerate(clips):
        c_start = last_end
        c_end = min(total_duration, max(c_start + 60, int(c["end_sec"])))
        if i == len(clips) - 1:
            c_end = total_duration
        if i == 0:
            c_start = 0

        dur = c_end - c_start
        title = c["title"].strip()
        p_tag = detect_priority_tag(title)

        final_clips.append({
            "id": str(uuid.uuid4()),
            "source_id": video_meta.get("source_id"),
            "order_index": i,
            "title": title,
            "start_sec": c_start,
            "end_sec": c_end,
            "raw_duration_sec": dur,
            "priority_tag": p_tag,
            "status": "not_started",
            "video_id": video_id,
            "video_url": video_url,
        })
        last_end = c_end

    # Final continuity assertion
    if final_clips:
        final_clips[0]["start_sec"] = 0
        final_clips[-1]["end_sec"] = total_duration
        final_clips[-1]["raw_duration_sec"] = total_duration - final_clips[-1]["start_sec"]

    return final_clips


def _call_llm_for_window(
    video_title: str,
    window_start: int,
    window_end: int,
    transcript_window_text: str,
    db_conn: Optional[Any] = None
) -> Optional[List[Dict[str, Any]]]:
    """Invokes LLM (Gemini/Groq/OpenRouter) for a single 45-60 min window outline."""
    window_dur = window_end - window_start
    if window_dur < MIN_CLIP_SEC:
        return None

    settings = get_settings()
    has_key = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if not has_key:
        return None

    cache_key = f"semantic_window:{video_title}:{window_start}:{window_end}"
    prompt_hash = compute_sha256(cache_key)

    if db_conn is not None:
        cached = get_cached_response(db_conn, prompt_hash)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception:
                pass

    system_instruction = (
        "You are an expert academic curriculum designer. "
        "Divide this ~45-60 minute video lecture window into clean, 10–15 minute Concept Clips (acceptable: 8–18 min). "
        "Snaps boundaries to natural concept transitions and assign professional syllabus titles. "
        "Mark priority_tag as 'core' (foundational theory, definitions) or 'deep-dive' (worked examples, exercises, proofs, practicals)."
    )

    prompt = f"""VIDEO TITLE: {video_title}
WINDOW TIME RANGE: {format_timestamp_pill(window_start)} to {format_timestamp_pill(window_end)} ({window_start}s to {window_end}s)

TRANSCRIPT OUTLINE FOR THIS WINDOW:
{transcript_window_text[:5000]}

RULES:
1. Divide the window into {max(2, window_dur // 900)} to {max(3, window_dur // 600)} concept clips.
2. Clip duration must be between 480 seconds (8 min) and 1080 seconds (18 min).
3. First clip starts at {window_start}, last clip ends at {window_end}. Slices must be contiguous without gaps.
4. Return pure JSON schema:
{{
  "clips": [
    {{
      "title": "Clean Academic Concept Title",
      "start_sec": {window_start},
      "end_sec": {window_start + 720},
      "priority_tag": "core"
    }}
  ]
}}
"""

    model_name = settings.GEMINI_MODEL
    raw_clips = None
    try:
        active_p = (settings.ACTIVE_LLM_PROVIDER or "auto").lower()
        providers = ["gemini", "groq", "openrouter"]
        if active_p in providers:
            providers.remove(active_p)
            providers.insert(0, active_p)

        with httpx.Client(timeout=25.0) as client:
            for p in providers:
                if p == "gemini" and not raw_clips and settings.GEMINI_API_KEY:
                    try:
                        model_name = settings.GEMINI_MODEL
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                        _gemini_headers = {"x-goog-api-key": settings.GEMINI_API_KEY}
                        payload = {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "systemInstruction": {"parts": [{"text": system_instruction}]},
                            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
                        }
                        resp = client.post(url, json=payload, headers=_gemini_headers)
                        if resp.status_code == 200:
                            raw_clips = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception as ge:
                        logger.warning(f"Gemini semantic partition attempt failed: {ge}")
                elif p == "groq" and not raw_clips and settings.GROQ_API_KEY:
                    try:
                        model_name = settings.GROQ_MODEL
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                        payload = {
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.2,
                            "response_format": {"type": "json_object"}
                        }
                        resp = client.post(url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            raw_clips = resp.json()["choices"][0]["message"]["content"]
                    except Exception as gqe:
                        logger.warning(f"Groq semantic partition attempt failed: {gqe}")
                elif p == "openrouter" and not raw_clips and settings.OPENROUTER_API_KEY:
                    try:
                        model_name = settings.OPENROUTER_MODEL
                        url = "https://openrouter.ai/api/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                        payload = {
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.2
                        }
                        resp = client.post(url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            msg = resp.json()["choices"][0]["message"]
                            raw_clips = msg.get("content") or msg.get("reasoning", "")
                    except Exception as ore:
                        logger.warning(f"OpenRouter semantic partition attempt failed: {ore}")

        if raw_clips:
            cleaned_json = raw_clips.strip()
            if cleaned_json.startswith("```"):
                cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
                cleaned_json = re.sub(r"\s*```$", "", cleaned_json).strip()
            parsed = json.loads(cleaned_json)
            clips_list = parsed.get("clips") if isinstance(parsed, dict) else parsed
            if isinstance(clips_list, list) and len(clips_list) >= 1:
                if db_conn is not None:
                    try:
                        set_cached_response(db_conn, prompt_hash, model_name, json.dumps(clips_list))
                    except Exception:
                        pass
                return clips_list
    except Exception as e:
        logger.warning(f"Semantic window LLM partition failed for window [{window_start}-{window_end}]: {e}")

    return None


def partition_video_semantic_ai(
    video_meta: Dict[str, Any],
    transcript_data: List[Dict[str, Any]],
    db_conn: Optional[Any] = None,
    window_duration_sec: int = 3000, # 50 minutes
) -> Optional[List[Dict[str, Any]]]:
    """AI-Assisted Semantic Mode for Concept Clip Partitioning (Runs ONCE on import).
    
    Processes timestamped transcript outlines in 45-60 min sliding windows to handle
    even 10-15 hour marathon videos without context truncation. Snaps boundaries to
    exact concept transitions, assigns clean syllabus titles, and tags core vs deep-dive.
    """
    total_duration = int(video_meta.get("duration") or 0)
    video_id = video_meta.get("id") or "video"
    video_title = video_meta.get("title", "Lecture")
    video_url = video_meta.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

    if total_duration <= 0 or not transcript_data:
        return None

    settings = get_settings()
    if not (settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY):
        return None

    # Divide marathon video into consecutive 45-60 min windows
    windows: List[Tuple[int, int]] = []
    w_start = 0
    while w_start < total_duration:
        w_end = min(total_duration, w_start + window_duration_sec)
        # If remaining tail is tiny (< 10 min), include it in current window
        if (total_duration - w_end) < 600:
            w_end = total_duration
        windows.append((w_start, w_end))
        w_start = w_end

    all_clips: List[Dict[str, Any]] = []

    for w_start, w_end in windows:
        # Extract transcript for this window
        window_chunks = [
            c for c in transcript_data
            if int(c.get("start_sec", 0)) >= w_start and int(c.get("end_sec", 0)) <= w_end
        ]
        text_summary = "\n".join([
            f"[{format_timestamp_pill(int(c.get('start_sec', 0)))}] {c.get('content', '')[:120]}"
            for c in window_chunks
        ])

        llm_clips = _call_llm_for_window(video_title, w_start, w_end, text_summary, db_conn=db_conn)

        if llm_clips and len(llm_clips) >= 1:
            # Normalize window clips to strictly snap boundaries
            last_end = w_start
            for idx, c in enumerate(llm_clips):
                c_start = last_end
                c_end = int(c.get("end_sec", c_start + 720))
                if idx == 0:
                    c_start = w_start
                if idx == len(llm_clips) - 1:
                    c_end = w_end
                if c_end <= c_start:
                    c_end = min(w_end, c_start + 600)

                title = str(c.get("title", f"Concept Part {idx + 1}")).strip()
                p_tag = str(c.get("priority_tag", "core")).lower()
                if p_tag not in ("core", "deep-dive"):
                    p_tag = detect_priority_tag(title)

                all_clips.append({
                    "title": title,
                    "start_sec": c_start,
                    "end_sec": c_end,
                    "raw_duration_sec": c_end - c_start,
                    "priority_tag": p_tag,
                })
                last_end = c_end
        else:
            # Fall back deterministically for this specific window
            sub_meta = dict(video_meta)
            sub_meta["duration"] = w_end - w_start
            deterministic_window_clips = split_long_segment_deterministic(
                video_title,
                w_start,
                w_end,
                window_chunks,
                target_sec=TARGET_DURATION_SEC,
                min_sec=MIN_CLIP_SEC,
                max_sec=MAX_CLIP_SEC,
            )
            for c in deterministic_window_clips:
                c["priority_tag"] = detect_priority_tag(c["title"])
                all_clips.append(c)

    if not all_clips:
        return None

    # Enforce global zero-gap, zero-overlap invariants across windows
    final_clips: List[Dict[str, Any]] = []
    last_end = 0

    for i, c in enumerate(all_clips):
        c_start = last_end
        c_end = min(total_duration, max(c_start + 60, int(c["end_sec"])))
        if i == 0:
            c_start = 0
        if i == len(all_clips) - 1:
            c_end = total_duration

        dur = c_end - c_start
        if dur <= 0:
            continue

        title = c["title"].strip()
        p_tag = c.get("priority_tag") or detect_priority_tag(title)

        final_clips.append({
            "id": str(uuid.uuid4()),
            "source_id": video_meta.get("source_id"),
            "order_index": len(final_clips),
            "title": title,
            "start_sec": c_start,
            "end_sec": c_end,
            "raw_duration_sec": dur,
            "priority_tag": p_tag,
            "status": "not_started",
            "video_id": video_id,
            "video_url": video_url,
        })
        last_end = c_end

    if final_clips:
        final_clips[0]["start_sec"] = 0
        final_clips[-1]["end_sec"] = total_duration
        final_clips[-1]["raw_duration_sec"] = total_duration - final_clips[-1]["start_sec"]

    return final_clips


def partition_video(
    video_meta: Dict[str, Any],
    transcript_data: Optional[List[Dict[str, Any]]] = None,
    mode: str = "auto",
    db_conn: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Master Concept Clip partitioner for Layer 1.
    
    Modes:
    - 'auto': AI-Assisted Semantic Mode if API key and transcript exist; otherwise deterministic.
    - 'semantic': Forces AI-assisted mode with fallback to deterministic.
    - 'deterministic': Instant zero-LLM chapter/transcript sentence boundary partitioning.
    """
    settings = get_settings()
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)

    if mode in ("auto", "semantic") and has_llm and transcript_data:
        try:
            semantic_result = partition_video_semantic_ai(
                video_meta=video_meta,
                transcript_data=transcript_data,
                db_conn=db_conn,
            )
            if semantic_result and len(semantic_result) >= 1:
                logger.info(f"Generated {len(semantic_result)} semantic concept clips for '{video_meta.get('title')}'")
                return semantic_result
        except Exception as e:
            logger.warning(f"Semantic partitioning failed: {e}; falling back to deterministic.")

    # Deterministic fallback / direct mode
    return partition_video_deterministic(
        video_meta=video_meta,
        transcript_data=transcript_data,
    )
