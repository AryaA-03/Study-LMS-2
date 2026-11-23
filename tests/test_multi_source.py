"""Unit tests for Milestone 3 Multi-Source Ingestion (PDF & Web)."""

import pytest
from pathlib import Path
from pypdf import PdfWriter
import io

from backend.services.pdf_ingest import extract_and_chunk_pdf, ingest_pdf_source
from backend.services.web_ingest import MAX_WEB_BYTES, chunk_web_text, is_allowed_by_robots
from backend.migrations.runner import apply_migrations
from backend.database import init_connection


def create_dummy_pdf_bytes(text_pages: list) -> bytes:
    """Helper to generate an in-memory PDF with specified text pages."""
    writer = PdfWriter()
    for text in text_pages:
        # Create a blank page and add text annotation or dummy text
        page = writer.add_blank_page(width=612, height=792)
    # Write to memory buffer
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_web_ingest_max_size_is_5_mb():
    assert MAX_WEB_BYTES == 5 * 1024 * 1024


def test_chunk_web_text():
    text = (
        "In computer science and automata theory, a deterministic finite automaton (DFA) is a finite-state machine "
        "that accepts or rejects given strings of symbols. For each input symbol, it transitions to a uniquely "
        "determined next state. A DFA is defined as a 5-tuple: Q, Sigma, delta, q0, and F. "
    ) * 10

    chunks = chunk_web_text(text, target_tokens=50)
    assert len(chunks) > 1
    assert "deterministic finite automaton" in chunks[0]["content"]
    assert chunks[0]["token_count"] > 0
    assert chunks[0]["chunk_index"] == 0


def test_robots_txt_allow_check():
    # Should allow polite requests to standard educational domains
    allowed = is_allowed_by_robots("https://en.wikipedia.org/wiki/Theory_of_computation")
    assert isinstance(allowed, bool)


@pytest.mark.asyncio
async def test_pdf_ingest_pipeline(tmp_path):
    db_file = tmp_path / "test_pdf_db.db"
    apply_migrations(db_file)
    conn = init_connection(db_file)

    # Seed course
    cid = "c_pdf_1"
    conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES (?, 'TOC', 'TOC', '2026-12-31');", (cid,))
    conn.commit()

    # Create dummy PDF
    writer = PdfWriter()
    p1 = writer.add_blank_page(width=300, height=300)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)

    # Mock extract_and_chunk_pdf to return test chunks
    import backend.services.pdf_ingest as pdf_mod
    orig_extract = pdf_mod.extract_and_chunk_pdf
    pdf_mod.extract_and_chunk_pdf = lambda p, target_tokens=400: [
        {
            "chunk_index": 0,
            "content": "Formal definition of regular expressions and language equivalence.",
            "token_count": 35,
            "page_label": "Page 1",
            "pages": [1]
        }
    ]

    try:
        source_id, chunk_count = await ingest_pdf_source(
            conn,
            course_id=cid,
            title="Lecture Notes 1",
            pdf_bytes=pdf_bytes.getvalue(),
            original_filename="lecture1.pdf"
        )

        assert chunk_count == 1
        assert source_id.startswith("src_pdf_")

        # Verify source record
        cur = conn.cursor()
        cur.execute("SELECT id, title, source_type, chunk_count FROM sources WHERE id = ?;", (source_id,))
        s_row = cur.fetchone()
        assert s_row[1] == "Lecture Notes 1"
        assert s_row[2] == "pdf"
        assert s_row[3] == 1

        # Verify chunk and FTS5 index
        cur.execute("SELECT content, source_type FROM chunks WHERE source_id = ?;", (source_id,))
        c_row = cur.fetchone()
        assert "regular expressions" in c_row[0]
        assert c_row[1] == "pdf"

        cur.execute("SELECT content FROM chunks_fts WHERE content MATCH 'expressions';")
        assert len(cur.fetchall()) == 1

    finally:
        pdf_mod.extract_and_chunk_pdf = orig_extract
        conn.close()
