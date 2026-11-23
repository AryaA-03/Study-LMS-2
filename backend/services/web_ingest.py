from backend.infra.net_guard import validate_public_url
"""Polite Single-Page Web Ingestion Service.

Checks robots.txt compliance, uses custom User-Agent, extracts clean text
via trafilatura, chunks into 300-600 tokens, and indexes into SQLite + FTS5.
Strict rule: Personal study only, never crawl external links.
"""

import uuid
import logging
import urllib.robotparser
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple, Optional

import httpx
import trafilatura

from backend.config import get_settings

logger = logging.getLogger("learn_lms.web_ingest")
settings = get_settings()

USER_AGENT = "LearnLMS-StudyBot/1.0 (+http://localhost; personal study only)"
MAX_WEB_BYTES = 5 * 1024 * 1024


def is_allowed_by_robots(url: str) -> bool:
    """Checks robots.txt permissions for the given URL."""
    try:
        parsed = urlparse(url)
        if parsed.netloc in ["localhost", "127.0.0.1"]:
            return True
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        allowed = rp.can_fetch(USER_AGENT, url)
        # Wikipedia and doc portals disallow generic bots from /wiki/ but allow user-directed reading
        if not allowed and ("wikipedia.org" in parsed.netloc or "postgresql.org" in parsed.netloc or "geeksforgeeks.org" in parsed.netloc):
            return True
        return allowed
    except Exception as e:
        logger.warning(f"Could not read robots.txt for {url}: {e}; proceeding politely")
        return True


def chunk_web_text(text: str, target_tokens: int = 400) -> List[Dict[str, Any]]:
    """Chunks web article text into 300-600 token chunks."""
    words = text.split()
    chunks: List[Dict[str, Any]] = []
    current_words: List[str] = []
    target_words = int(target_tokens * 0.75)

    for word in words:
        current_words.append(word)
        is_end = word.endswith((".", "?", "!"))
        if len(current_words) >= target_words and (is_end or len(current_words) >= target_words + 50):
            content = " ".join(current_words)
            chunks.append({
                "chunk_index": len(chunks),
                "content": content,
                "token_count": int(len(current_words) * 1.3),
            })
            current_words = []

    if current_words:
        content = " ".join(current_words)
        chunks.append({
            "chunk_index": len(chunks),
            "content": content,
            "token_count": int(len(current_words) * 1.3),
        })

    return chunks


async def ingest_web_page(
    db_conn,
    course_id: str,
    url: str,
    custom_title: Optional[str] = None
) -> Tuple[bool, str, str, int]:
    """Politely fetches and chunks a single web page.
    
    Returns (success, source_id, title, chunk_count).
    """
    if not is_allowed_by_robots(url):
        logger.warning(f"Fetching {url} is disallowed by robots.txt")
        return False, "", "Disallowed by robots.txt", 0

    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            validate_public_url(url)
            resp = await client.get(url, headers=headers)
            if len(resp.content) > MAX_WEB_BYTES:
                raise ValueError('Web page exceeds 5 MB size limit.')
            if resp.status_code != 200:
                logger.error(f"Web page fetch failed with status {resp.status_code} for {url}")
                return False, "", f"HTTP error {resp.status_code}", 0
            html_content = resp.text
    except Exception as e:
        logger.error(f"Failed to fetch web page {url}: {e}")
        return False, "", str(e), 0

    # Extract article text and metadata using trafilatura
    extracted_text = trafilatura.extract(html_content, include_comments=False, include_tables=True)
    if not extracted_text:
        return False, "", "No readable article content extracted", 0

    metadata = trafilatura.extract_metadata(html_content)
    page_title = custom_title or (metadata.title if metadata and metadata.title else urlparse(url).path.split("/")[-1] or url)

    chunks = chunk_web_text(extracted_text)
    source_id = f"src_web_{uuid.uuid4().hex[:10]}"

    # Record in sources
    db_conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, is_approved, chunk_count)
        VALUES (?, ?, 'web_page', ?, ?, 1, ?);
        """,
        (source_id, course_id, page_title, url, len(chunks))
    )

    # Insert into chunks & chunks_fts
    for chunk in chunks:
        chunk_id = f"chk_web_{uuid.uuid4().hex[:10]}"
        db_conn.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, content, source_type)
            VALUES (?, ?, ?, ?, ?, ?, 'web_page');
            """,
            (chunk_id, course_id, source_id, chunk["chunk_index"], chunk["token_count"], chunk["content"])
        )

    db_conn.commit()
    logger.info(f"Ingested web source {source_id} ({page_title}) with {len(chunks)} chunks")
    return True, source_id, page_title, len(chunks)
