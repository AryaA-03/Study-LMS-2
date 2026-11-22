"""YouTube discovery, metadata extraction, and deterministic lesson splitting service.

Uses yt-dlp without any YouTube Data API keys.
Implements:
- Video & playlist discovery via ytsearch: and playlist-filtered search URL
- Direct video & playlist URL extraction (zero video download)
- Chapter-based lesson splitting (1 chapter = 1 lesson)
- Deterministic 15-20 min splitting for chapter-less videos
- Resilience: browser cookies support, clear fallback error handling
"""

import sys
import subprocess
import urllib.parse
import json
import logging
from typing import List, Dict, Any, Optional
import httpx
import yt_dlp
from backend.config import get_settings
from backend.services.llm_cache import (
    compute_sha256,
    get_cached_response,
    set_cached_response,
)

logger = logging.getLogger("learn_lms.youtube")

def get_ytdlp_version() -> str:
    """Returns currently installed yt-dlp version."""
    try:
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"

def update_ytdlp_package() -> Dict[str, Any]:
    """Updates yt-dlp via pip in the current Python environment."""
    old_version = get_ytdlp_version()
    try:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Reload yt-dlp module to get updated version
        import importlib
        importlib.reload(yt_dlp)
        new_version = get_ytdlp_version()
        return {
            "success": True,
            "old_version": old_version,
            "new_version": new_version,
            "message": f"Successfully updated yt-dlp from {old_version} to {new_version}.",
        }
    except Exception as e:
        return {
            "success": False,
            "old_version": old_version,
            "new_version": old_version,
            "message": f"Failed to update yt-dlp: {str(e)}",
        }

def get_base_ydl_opts(cookies_browser: Optional[str] = None) -> Dict[str, Any]:
    """Base options for yt-dlp ensuring no video downloads."""
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "socket_timeout": 15,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts

def discover_candidates(
    query: str,
    max_videos: int = 5,
    max_playlists: int = 5,
    cookies_browser: Optional[str] = None,
) -> Dict[str, Any]:
    """Discovers candidate videos and candidate playlists for a learning goal.

    Uses zero-quota ytsearch and YouTube's playlist-filtered search URL:
    https://www.youtube.com/results?search_query=<encoded_query>&sp=EgIQAw%3D%3D
    """
    candidate_videos: List[Dict[str, Any]] = []
    candidate_playlists: List[Dict[str, Any]] = []
    error_message: Optional[str] = None

    opts = get_base_ydl_opts(cookies_browser)

    # 1. Search videos via ytsearch:
    try:
        video_search_query = f"ytsearch{max_videos}:{query}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            video_result = ydl.extract_info(video_search_query, download=False)
            if video_result and "entries" in video_result:
                for entry in video_result["entries"]:
                    if not entry:
                        continue
                    candidate_videos.append({
                        "id": entry.get("id"),
                        "title": entry.get("title", "Untitled Video"),
                        "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": entry.get("duration", 0),
                        "duration_str": format_duration(entry.get("duration", 0)),
                        "channel": entry.get("uploader") or entry.get("channel", "Unknown Channel"),
                        "thumbnails": entry.get("thumbnails", []),
                        "type": "youtube_video",
                    })
    except Exception as e:
        error_message = f"Video search encountered an issue: {str(e)}"

    # 2. Search playlists via YouTube playlist filter URL:
    # sp=EgIQAw%3D%3D filters results strictly to Playlists on YouTube
    try:
        encoded_query = urllib.parse.quote_plus(query)
        playlist_search_url = f"https://www.youtube.com/results?search_query={encoded_query}&sp=EgIQAw%3D%3D"
        with yt_dlp.YoutubeDL(opts) as ydl:
            playlist_result = ydl.extract_info(playlist_search_url, download=False)
            if playlist_result and "entries" in playlist_result:
                for entry in playlist_result["entries"][:max_playlists]:
                    if not entry:
                        continue
                    pl_id = entry.get("id")
                    pl_url = entry.get("url")
                    if not pl_url and pl_id:
                        pl_url = f"https://www.youtube.com/playlist?list={pl_id}"
                    candidate_playlists.append({
                        "id": pl_id,
                        "title": entry.get("title", "Untitled Playlist"),
                        "url": pl_url,
                        "item_count": entry.get("playlist_count"),
                        "channel": entry.get("uploader") or entry.get("channel", "Unknown Channel"),
                        "type": "youtube_playlist",
                    })
    except Exception as e:
        if not error_message:
            error_message = f"Playlist search encountered an issue: {str(e)}"

    # If YouTube rate-limited or failed, surface a clear, generic advisory.
    # Do NOT inject topic-specific hardcoded content (avoids contaminating non-DBMS subjects).
    if not candidate_videos and not candidate_playlists and error_message:
        error_message = (
            f"YouTube search returned no candidates. "
            f"You can paste a direct YouTube video or playlist URL into the manual import field. "
            f"(Details: {error_message})"
        )

    return {
        "candidate_videos": candidate_videos,
        "candidate_playlists": candidate_playlists,
        "error": error_message,
    }

def extract_metadata(url: str, cookies_browser: Optional[str] = None) -> Dict[str, Any]:
    """Extracts metadata for a single video or playlist."""
    opts = get_base_ydl_opts(cookies_browser)
    opts["extract_flat"] = "in_playlist"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info or {}

def format_duration(seconds: Optional[int]) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def merge_short_chapters(
    chapters: List[Dict[str, Any]],
    total_duration: int,
    min_duration_sec: int = 180,
) -> List[Dict[str, Any]]:
    """Merges chapters shorter than min_duration_sec (default 3 min = 180s) into adjacent chapters.

    Prevents micro-fragment lessons (e.g. 10s intro bumpers) while preserving complete video coverage.
    """
    if not chapters:
        return []

    raw_list = []
    for idx, ch in enumerate(chapters):
        ch_title = ch.get("title", f"Chapter {idx + 1}")
        start_sec = int(ch.get("start_time", 0))
        end_sec = int(ch.get("end_time", total_duration))
        duration = end_sec - start_sec
        if duration <= 0:
            continue
        raw_list.append({
            "title": ch_title,
            "start_time": start_sec,
            "end_time": end_sec,
            "duration": duration,
        })

    if len(raw_list) <= 1:
        return raw_list

    merged = []
    i = 0
    while i < len(raw_list):
        curr = dict(raw_list[i])
        # If this chapter is shorter than min_duration_sec, merge with subsequent chapters
        while curr["duration"] < min_duration_sec and (i + 1) < len(raw_list):
            nxt = raw_list[i + 1]
            curr["end_time"] = nxt["end_time"]
            curr["duration"] = curr["end_time"] - curr["start_time"]
            # Combine titles if curr title is not a generic intro/outro and nxt is also short
            c_low = curr["title"].lower()
            if nxt["duration"] >= min_duration_sec:
                curr["title"] = nxt["title"]
            elif not any(kw in c_low for kw in ["intro", "bumper", "teaser", "welcome", "about this video", "break"]):
                curr["title"] = f"{curr['title']} & {nxt['title']}"
            else:
                curr["title"] = nxt["title"]
            i += 1

        # If it is the trailing chapter and still under min_duration_sec, merge into the previous chapter
        if curr["duration"] < min_duration_sec and merged:
            prev = merged[-1]
            prev["end_time"] = curr["end_time"]
            prev["duration"] = prev["end_time"] - prev["start_time"]
        else:
            merged.append(curr)
        i += 1

    return merged

def split_video_by_llm_concepts(
    video_meta: Dict[str, Any],
    total_duration: int,
    db_conn: Optional[Any] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Uses LLM (Gemini / Groq / OpenRouter) to split chapter-less videos into concept-based lessons.

    Adheres strictly to deterministic math guardrails:
    - Slices are contiguous, start at 0 and end exactly at total_duration.
    - Slices stay within natural conceptual bounds (5–25 minutes).
    - Results are SHA-256 cached in SQLite.
    """
    video_id = video_meta.get("id") or "vid"
    video_url = video_meta.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
    video_title = video_meta.get("title", "Video Lecture")
    description = (video_meta.get("description") or "")[:2000]

    # Don't invoke LLM for short videos under 10 minutes
    if total_duration < 600:
        return None

    settings = get_settings()
    has_llm = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if not has_llm:
        return None

    # Check SQLite cache
    cache_key = f"concept_split:{video_id}:{total_duration}"
    prompt_hash = compute_sha256(cache_key)
    if db_conn is not None:
        cached_str = get_cached_response(db_conn, prompt_hash)
        if cached_str:
            try:
                cached_data = json.loads(cached_str)
                if isinstance(cached_data, list) and len(cached_data) > 0:
                    logger.info(f"llm_cache hit for concept splitting: {video_title}")
                    return cached_data
            except Exception:
                pass

    system_instruction = (
        "You are an expert academic curriculum designer and computer science tutor. "
        "Your task is to divide a long educational video lecture into natural, concept-based study lessons."
    )

    prompt = f"""VIDEO TITLE: {video_title}
TOTAL DURATION: {total_duration} seconds (approx {round(total_duration / 60, 1)} minutes)
OUTLINE / DESCRIPTION:
{description}

TASK:
Group this video into natural, logical concept-based study lessons.
RULES:
1. Create between {max(2, total_duration // 1200)} and {max(3, total_duration // 400)} distinct concept lessons.
2. Each lesson duration must ideally be between 300 seconds (5 min) and 1500 seconds (25 min).
3. Slices must be contiguous: the first lesson starts at 0, each next lesson starts where the prior ended, and the last lesson ends at {total_duration}.
4. Give each lesson a clear, professional conceptual title (e.g. 'Overview & Mathematical Foundations', 'Worked Example & Proof').

Return PURE JSON in this schema:
{{
  "lessons": [
    {{
      "title": "string",
      "start_sec": 0,
      "end_sec": 600
    }}
  ]
}}
"""

    raw_lessons = None
    model_name = "gemini-2.5-flash"
    try:
        with httpx.Client(timeout=25.0) as client:
            if settings.GEMINI_API_KEY:
                model_name = "gemini-2.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
                }
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    raw_lessons = json.loads(text).get("lessons", [])
            elif settings.GROQ_API_KEY:
                model_name = "llama-3.3-70b-versatile"
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
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    raw_lessons = json.loads(content).get("lessons", [])
            elif settings.OPENROUTER_API_KEY:
                model_name = "google/gemini-2.5-flash"
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
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    raw_lessons = json.loads(content).get("lessons", [])

        if not raw_lessons or not isinstance(raw_lessons, list) or len(raw_lessons) < 2:
            return None

        # Deterministic math guardrails: normalize boundaries
        normalized_lessons = []
        last_end = 0
        for i, item in enumerate(raw_lessons):
            title = str(item.get("title") or f"Concept {i+1}").strip()
            s_sec = max(last_end, int(item.get("start_sec", last_end)))
            e_sec = int(item.get("end_sec", s_sec + 600))
            if i == 0:
                s_sec = 0
            if i == len(raw_lessons) - 1:
                e_sec = total_duration
            if e_sec <= s_sec:
                e_sec = min(total_duration, s_sec + 300)

            dur = e_sec - s_sec
            if dur <= 0:
                continue

            is_example = any(kw in title.lower() for kw in ["example", "exercise", "gate", "problem", "practice", "solution"])
            normalized_lessons.append({
                "title": f"{video_title} - {title}",
                "chapter_title": title,
                "video_id": video_id,
                "video_url": video_url,
                "start_sec": s_sec,
                "end_sec": e_sec,
                "raw_duration_sec": dur,
                "priority": "deep-dive" if is_example else "core",
                "order_index": i,
            })
            last_end = e_sec

        # Ensure last lesson ends at total_duration
        if normalized_lessons:
            normalized_lessons[-1]["end_sec"] = total_duration
            normalized_lessons[-1]["raw_duration_sec"] = total_duration - normalized_lessons[-1]["start_sec"]

            # Save in SQLite cache
            if db_conn is not None:
                try:
                    set_cached_response(db_conn, prompt_hash, model_name, json.dumps(normalized_lessons))
                except Exception as e:
                    logger.warning(f"Failed to cache concept splitting: {e}")

            logger.info(f"Successfully generated {len(normalized_lessons)} AI concept lessons for '{video_title}'")
            return normalized_lessons
    except Exception as e:
        logger.warning(f"AI concept splitting failed for '{video_title}': {e}; falling back to deterministic slicing.")

    return None

def split_video_into_lessons(
    video_meta: Dict[str, Any],
    default_chunk_min: int = 15,
    min_chapter_sec: int = 180,
    db_conn: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Splits a video into lessons:

    - If chapters are present in metadata: merges any sub-3-minute (180s) chapters, then 1 chapter = 1 lesson
    - If chapter-less: tries AI concept-based lesson splitting (via Gemini/Groq/OpenRouter with SQLite caching)
    - If no LLM key or failure: splits deterministically into fixed 15-20 min lessons with 5-minute trailing merge
    """
    video_id = video_meta.get("id")
    video_url = video_meta.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
    video_title = video_meta.get("title", "Video Lecture")
    total_duration = int(video_meta.get("duration") or 0)
    raw_chapters = video_meta.get("chapters")

    lessons: List[Dict[str, Any]] = []

    if raw_chapters and len(raw_chapters) > 0:
        # Chapter-based splitting with 3-minute merging rule
        effective_chapters = merge_short_chapters(raw_chapters, total_duration, min_duration_sec=min_chapter_sec)
        for idx, ch in enumerate(effective_chapters):
            ch_title = ch.get("title", f"Chapter {idx + 1}")
            start_sec = ch.get("start_time", 0)
            end_sec = ch.get("end_time", total_duration)
            duration = end_sec - start_sec
            if duration <= 0:
                continue
            lessons.append({
                "title": f"{video_title} - {ch_title}",
                "chapter_title": ch_title,
                "video_id": video_id,
                "video_url": video_url,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "raw_duration_sec": duration,
                "priority": "core",
                "order_index": idx,
            })
    else:
        # 1. Try AI concept lesson splitting first
        concept_lessons = split_video_by_llm_concepts(video_meta, total_duration, db_conn=db_conn)
        if concept_lessons:
            return concept_lessons

        # 2. Chapter-less deterministic fallback splitting (15-20 minutes)
        chunk_sec = default_chunk_min * 60
        if total_duration <= 0:
            total_duration = 900  # Default 15 min if duration unknown

        start_sec = 0
        idx = 0
        while start_sec < total_duration:
            end_sec = min(start_sec + chunk_sec, total_duration)
            # If the remaining piece is less than 5 minutes, merge into current chunk
            if (total_duration - end_sec) < 300:
                end_sec = total_duration

            dur = end_sec - start_sec
            time_label = f"[{format_duration(start_sec)} - {format_duration(end_sec)}]"
            lessons.append({
                "title": f"{video_title} {time_label}",
                "chapter_title": time_label,
                "video_id": video_id,
                "video_url": video_url,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "raw_duration_sec": dur,
                "priority": "core",
                "order_index": idx,
            })
            start_sec = end_sec
            idx += 1

    return lessons
