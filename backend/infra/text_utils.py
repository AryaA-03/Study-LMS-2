"""Shared text, timestamp, chunking, and LLM JSON parsing utilities."""

import json
import re
from typing import Any, Dict, List


def format_timestamp(seconds: int | float | None) -> str:
    """Format seconds into [MM:SS] or [HH:MM:SS] consistently across all services."""
    total = max(0, int(seconds or 0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def parse_llm_json(raw_text: str) -> Any:
    """Safely parse JSON from LLM output, stripping markdown code fences if present."""
    if not raw_text or not isinstance(raw_text, str):
        raise ValueError("Empty LLM response")
    cleaned = raw_text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: extract outermost JSON object or array
        for start_ch, end_ch in (("{", "}"), ("[", "]")):
            s_idx = cleaned.find(start_ch)
            e_idx = cleaned.rfind(end_ch)
            if s_idx != -1 and e_idx > s_idx:
                try:
                    return json.loads(cleaned[s_idx : e_idx + 1])
                except json.JSONDecodeError:
                    continue
        raise


def chunk_text(text: str, target_words: int = 300, overlap_words: int = 40) -> List[Dict[str, Any]]:
    """Split text into overlapping word-bounded chunks."""
    words = (text or "").split()
    if not words:
        return []
    chunks: List[Dict[str, Any]] = []
    step = max(1, target_words - overlap_words)
    idx = 0
    for start in range(0, len(words), step):
        slice_words = words[start : start + target_words]
        if not slice_words:
            break
        chunks.append(
            {
                "chunk_index": idx,
                "content": " ".join(slice_words),
                "token_count": int(len(slice_words) * 1.3),
            }
        )
        idx += 1
        if start + target_words >= len(words):
            break
    return chunks
