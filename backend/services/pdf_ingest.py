"""PDF Document Ingestion Service.

Extracts text from local PDF documents using pure-Python pypdf,
splits text into 300-600 token chunks with page number tracking,
and indexes into SQLite chunks and FTS5 chunks_fts tables.
"""

import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

from pypdf import PdfReader
from backend.config import get_settings

logger = logging.getLogger("learn_lms.pdf_ingest")
settings = get_settings()


def get_pdf_upload_dir(course_id: str) -> Path:
    """Returns and ensures directory for uploaded PDFs."""
    dir_path = settings.DATA_DIR / "uploads" / course_id
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def extract_and_chunk_pdf(
    pdf_path: Path,
    target_tokens: int = 400
) -> List[Dict[str, Any]]:
    """Reads PDF and extracts deterministic 300-600 token chunks."""
    reader = PdfReader(str(pdf_path))
    chunks: List[Dict[str, Any]] = []

    current_words: List[str] = []
    current_pages: List[int] = []
    target_words = int(target_tokens * 0.75)

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        page_text = page.extract_text() or ""
        words = page_text.split()

        for word in words:
            current_words.append(word)
            if page_num not in current_pages:
                current_pages.append(page_num)

            is_end = word.endswith((".", "?", "!"))
            if len(current_words) >= target_words and (is_end or len(current_words) >= target_words + 50):
                content = " ".join(current_words)
                token_count = int(len(current_words) * 1.3)
                page_label = f"Page {current_pages[0]}" if len(current_pages) == 1 else f"Pages {current_pages[0]}-{current_pages[-1]}"
                chunks.append({
                    "chunk_index": len(chunks),
                    "content": content,
                    "token_count": token_count,
                    "page_label": page_label,
                    "pages": list(current_pages),
                })
                current_words = []
                current_pages = [page_num]

    if current_words:
        content = " ".join(current_words)
        token_count = int(len(current_words) * 1.3)
        page_label = f"Page {current_pages[0]}" if len(current_pages) == 1 else f"Pages {current_pages[0]}-{current_pages[-1]}"
        chunks.append({
            "chunk_index": len(chunks),
            "content": content,
            "token_count": token_count,
            "page_label": page_label,
            "pages": list(current_pages),
        })

    return chunks


MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024


async def ingest_pdf_source(
    db_conn,
    course_id: str,
    title: str,
    pdf_bytes: bytes,
    original_filename: str
) -> Tuple[str, int]:
    """Saves PDF, chunks text, and indexes into SQLite + FTS5.
    
    Returns (source_id, chunk_count).
    """
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise ValueError(f"PDF exceeds maximum allowed size of 100MB ({len(pdf_bytes)} bytes)")

    upload_dir = get_pdf_upload_dir(course_id)
    source_id = f"src_pdf_{uuid.uuid4().hex[:10]}"
    safe_name = f"{source_id}_{Path(original_filename).name}"
    saved_path = upload_dir / safe_name
    saved_path.write_bytes(pdf_bytes)

    chunks = extract_and_chunk_pdf(saved_path)

    # 1. Record in sources table
    db_conn.execute(
        """
        INSERT INTO sources (id, course_id, source_type, title, url, file_path, is_approved, chunk_count)
        VALUES (?, ?, 'pdf', ?, '', ?, 1, ?);
        """,
        (source_id, course_id, title, str(saved_path), len(chunks))
    )

    # 2. Insert into chunks & chunks_fts
    for chunk in chunks:
        chunk_id = f"chk_pdf_{uuid.uuid4().hex[:10]}"
        content_with_page = f"[{chunk['page_label']}] {chunk['content']}"
        db_conn.execute(
            """
            INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, content, source_type)
            VALUES (?, ?, ?, ?, ?, ?, 'pdf');
            """,
            (chunk_id, course_id, source_id, chunk["chunk_index"], chunk["token_count"], content_with_page)
        )

    db_conn.commit()
    logger.info(f"Ingested PDF source {source_id} with {len(chunks)} chunks")
    return source_id, len(chunks)
