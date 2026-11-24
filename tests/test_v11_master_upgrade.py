"""Comprehensive v11 Master Upgrade verification tests covering Phases 1 through 5."""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.database import get_db, init_connection
from backend.main import app
from backend.migrations.runner import apply_migrations
from backend.services.concept_partitioner import (
    extract_deterministic_topic_title,
    partition_video_async,
)
from backend.services.cram_sheet_engine import (
    generate_cram_sheet_with_llm,
    synthesize_full_syllabus_cram_sheet,
)
from backend.services.notes import (
    generate_no_key_structured_notes,
    get_or_generate_lesson_notes,
)
from backend.services.smart_prepare import smart_prepare_course


def _make_jwt(sub: str, secret: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": f"{sub}@example.com", "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


@pytest.mark.asyncio
async def test_phase1_cram_sheet_preserves_100pct_chunks_on_18_lessons(tmp_path):
    """BUG-01: Full-syllabus Cram Sheet on >15 lessons must NEVER delete chunks or chunks_fts."""
    db_path = tmp_path / "cram_preserve.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    try:
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'DBMS', 'DBMS', '2026-12-30');")
        for i in range(18):
            lid = f"l_{i}"
            conn.execute(
                "INSERT INTO lessons (id, course_id, title, chapter_title, start_sec, end_sec, raw_duration_sec, order_index) VALUES (?, 'c1', ?, ?, ?, ?, 600, ?);",
                (lid, f"Topic {i}", f"Unit {(i // 4) + 1}", i * 600, (i + 1) * 600, i),
            )
            conn.execute(
                "INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content) VALUES (?, 'c1', ?, 0, 20, ?, ?, ?);",
                (f"chk_{i}", lid, i * 600, (i + 1) * 600, f"B+ Tree indexing and ACID transactions in topic {i}."),
            )
        conn.commit()

        before_chunks = conn.execute("SELECT COUNT(*) FROM chunks WHERE course_id = 'c1';").fetchone()[0]
        before_fts = conn.execute("SELECT COUNT(*) FROM chunks_fts WHERE course_id = 'c1';").fetchone()[0]
        assert before_chunks == 18
        assert before_fts == 18

        await synthesize_full_syllabus_cram_sheet(conn, "c1", prune_intermediate_chunks=True)

        after_chunks = conn.execute("SELECT COUNT(*) FROM chunks WHERE course_id = 'c1';").fetchone()[0]
        after_fts = conn.execute("SELECT COUNT(*) FROM chunks_fts WHERE course_id = 'c1';").fetchone()[0]
        assert after_chunks == 18
        assert after_fts == 18
    finally:
        conn.close()


def test_phase1_and_5_tenant_isolation_all_routers_and_secrets_vault(tmp_path, monkeypatch):
    """SEC-01 & Phase 5: User B gets 404 across all course/lesson routers under AUTH_MODE=supabase; encrypted secrets round-trip."""
    db_path = tmp_path / "supabase_isolation.db"
    apply_migrations(db_path)
    secret = "test-supabase-jwt-secret-32-chars-min"
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "master-key-for-v11-aes256gcm-testing")

    def _override_db():
        conn = init_connection(db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        hdr_a = {"Authorization": f"Bearer {_make_jwt('alice', secret)}"}
        hdr_b = {"Authorization": f"Bearer {_make_jwt('bob', secret)}"}

        # Auth /me + encrypted BYOK secrets vault
        me_a = client.get("/api/auth/me", headers=hdr_a)
        assert me_a.status_code == 200
        assert me_a.json()["id"] == "alice"

        put_sec = client.put("/api/auth/secrets", headers=hdr_a, json={"provider": "gemini", "api_key": "AIza-test-secret-key"})
        assert put_sec.status_code == 200
        assert put_sec.json()["secrets"]["gemini"] is True

        # Bob does NOT see Alice's secrets
        bob_sec = client.get("/api/auth/secrets", headers=hdr_b)
        assert bob_sec.status_code == 200
        assert bob_sec.json()["gemini"] is False

        # Delete secret
        del_sec = client.delete("/api/auth/secrets/gemini", headers=hdr_a)
        assert del_sec.status_code == 200
        assert del_sec.json()["secrets"]["gemini"] is False

        # Alice creates course + lesson
        cid = client.post("/api/courses", headers=hdr_a, json={"title": "OS", "goal_query": "OS", "target_date": "2026-12-25"}).json()["id"]
        mt = client.post(
            f"/api/courses/{cid}/sources/manual-transcript",
            headers=hdr_a,
            json={"title": "Virtual Memory", "transcript_text": "Paging divides memory into fixed-size frames and pages.", "url": ""},
        )
        assert mt.status_code == 200
        lid = mt.json()["lesson_id"]

        # Bob is denied (404) across ALL routers
        for path in [
            f"/api/courses/{cid}",
            f"/api/courses/{cid}/lessons",
            f"/api/courses/{cid}/sources",
            f"/api/courses/{cid}/schedule",
            f"/api/courses/{cid}/quizzes",
            f"/api/courses/{cid}/flashcards",
            f"/api/courses/{cid}/pyq",
            f"/api/courses/{cid}/qa",
            f"/api/courses/{cid}/cram-sheet",
            f"/api/lessons/{lid}/notes",
            f"/api/lessons/{lid}/chunks",
            f"/api/lessons/{lid}/status",
            f"/api/lessons/{lid}/screenshots",
        ]:
            r = client.get(path, headers=hdr_b)
            assert r.status_code == 404, f"Expected 404 for Bob on {path}, got {r.status_code}"

        # Unauthenticated request gets 401
        assert client.get(f"/api/courses/{cid}").status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_phase2_semantic_partitioner_and_overlap_safe_smart_prepare(tmp_path):
    """QUAL-02: Async partitioner returns module_title + title; smart_prepare preserves completed clip with ZERO duplicates."""
    db_path = tmp_path / "phase2_smart.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    try:
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'DBMS Marathon', 'DBMS', '2026-12-30');")
        conn.execute(
            "INSERT INTO sources (id, course_id, source_type, title, url, external_id, is_approved) VALUES ('s1', 'c1', 'youtube_video', 'Complete DBMS', 'https://youtu.be/abc12345678', 'abc12345678', 1);"
        )
        # Seed 3 placeholder "— Part N" lessons, with Part 1 already completed!
        for i, (st, en, status) in enumerate([(0, 720, "completed"), (720, 1440, "not_started"), (1440, 2160, "not_started")]):
            conn.execute(
                """
                INSERT INTO lessons (id, course_id, source_id, title, video_id, video_url, start_sec, end_sec, raw_duration_sec, status, order_index)
                VALUES (?, 'c1', 's1', ?, 'abc12345678', 'https://youtu.be/abc12345678', ?, ?, 720, ?, ?);
                """,
                (f"old_{i}", f"Complete DBMS — Part {i+1}", st, en, status, i),
            )
        conn.commit()

        # Verify deterministic title extractor produces domain terms (not greetings)
        det_title = extract_deterministic_topic_title(
            [{"content": "Hello everyone welcome guys today we learn Normalization BCNF Functional Dependencies and Decomposition"}],
            "Complete DBMS",
            1,
        )
        assert "hello" not in det_title.lower()
        assert "Normalization" in det_title or "BCNF" in det_title

        fake_captions = [
            {"start_sec": 0, "end_sec": 700, "content": "ER Diagrams Entities Attributes and Primary Keys"},
            {"start_sec": 700, "end_sec": 1450, "content": "Normalization 1NF 2NF 3NF and BCNF Decomposition"},
            {"start_sec": 1450, "end_sec": 2160, "content": "B+ Tree Indexing and Leaf Node Range Queries"},
        ]
        mock_llm_json = json.dumps({
            "clips": [
                {"start_sec": 0, "end_sec": 720, "module_title": "Unit 1: ER Modeling", "title": "ER Diagrams & Key Constraints", "priority_tag": "core"},
                {"start_sec": 720, "end_sec": 1440, "module_title": "Unit 2: Normalization", "title": "3NF & BCNF Decomposition", "priority_tag": "core"},
                {"start_sec": 1440, "end_sec": 2160, "module_title": "Unit 3: Indexing", "title": "B+ Tree Leaf-Node Chaining", "priority_tag": "core"},
            ]
        })

        with patch("backend.services.smart_prepare.fetch_youtube_captions", new=AsyncMock(return_value=fake_captions)), \
             patch("backend.infra.llm_gateway.LLMGateway.generate_text", new=AsyncMock(return_value=(mock_llm_json, "gemini:mock"))):
            res = await smart_prepare_course(conn, "c1", force_repartition=False)
            assert res["repartitioned_sources"] == 1
            assert res["new_semantic_clips"] == 3

        rows = conn.execute("SELECT title, chapter_title, status, start_sec, end_sec FROM lessons WHERE course_id = 'c1' ORDER BY order_index;").fetchall()
        # ZERO duplicate clips (exactly 3, not 4!)
        assert len(rows) == 3
        assert rows[0]["title"] == "ER Diagrams & Key Constraints"
        assert rows[0]["chapter_title"] == "Unit 1: ER Modeling"
        # Completion preserved by >= 60% time overlap!
        assert rows[0]["status"] == "completed"
        assert rows[1]["status"] == "not_started"
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_phase3_notes_zero_boilerplate_cache_bypass_and_auto_upgrade(tmp_path, monkeypatch):
    """QUAL-01: Deterministic notes have zero Automata boilerplate or chk_ leaks; force_regenerate bypasses cache; deterministic auto-upgrades to llm."""
    db_path = tmp_path / "phase3_notes.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    try:
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'DBMS', 'DBMS', '2026-12-30');")
        conn.execute(
            "INSERT INTO lessons (id, course_id, title, start_sec, end_sec, raw_duration_sec, order_index) VALUES ('l1', 'c1', 'Complete DBMS [00:00 - 12:00]', 0, 720, 720, 0);"
        )
        conn.execute(
            "INSERT INTO chunks (id, course_id, lesson_id, chunk_index, token_count, start_sec, end_sec, content) VALUES ('chk_abc123', 'c1', 'l1', 0, 30, 30, 180, 'ACID stands for Atomicity, Consistency, Isolation, and Durability in database transactions.');"
        )
        conn.commit()

        # 1. Deterministic no-key notes: zero boilerplate, zero chk_ leak
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with patch("backend.infra.llm_gateway.LLMGateway.generate_text", new=AsyncMock(return_value=(None, None))):
            det_res = await get_or_generate_lesson_notes(conn, "c1", "l1", force_regenerate=False)
            assert det_res["generation_mode"] == "deterministic"
            assert "Aspect 1 (" not in det_res["content_markdown"]
            assert "Watch for empty strings" not in det_res["content_markdown"]
            assert "chk_abc123" not in det_res["content_markdown"]

        # 2. Now configure an API key -> opening the lesson auto-upgrades 'deterministic' -> 'llm' AND promotes placeholder title!
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        llm_md_1 = "# ACID Properties & Transaction Isolation\n\n> [!IMPORTANT] Core exam concept [00:30].\n\n## Core Intuition\nAtomicity ensures all-or-nothing execution [00:30]."
        llm_md_2 = "# ACID Properties & Transaction Isolation\n\n> [!IMPORTANT] Regenerated fresh version [00:30].\n\n## Core Intuition\nFresh regenerated content [00:30]."
        mock_gen = AsyncMock(side_effect=[(llm_md_1, "gemini:mock"), (llm_md_2, "gemini:mock")])
        with patch("backend.infra.llm_gateway.LLMGateway.generate_text", new=mock_gen):
            up_res = await get_or_generate_lesson_notes(conn, "c1", "l1", force_regenerate=False)
            assert up_res["generation_mode"] == "llm"
            assert up_res["lesson_title"] == "ACID Properties & Transaction Isolation"
            assert "Atomicity ensures" in up_res["content_markdown"]

            # 3. force_regenerate=True bypasses llm_cache and fetches fresh output
            regen_res = await get_or_generate_lesson_notes(conn, "c1", "l1", force_regenerate=True)
            assert "Regenerated fresh version" in regen_res["content_markdown"]
            assert mock_gen.call_count == 2
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_phase3_two_pass_cram_sheet_covers_all_modules_on_25_lessons(tmp_path, monkeypatch):
    """QUAL-03: 2-pass Map-Reduce Cram Sheet covers all 5 modules of a 25-lesson course with zero truncation."""
    db_path = tmp_path / "phase3_cram25.db"
    apply_migrations(db_path)
    conn = init_connection(db_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    try:
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'Operating Systems', 'OS', '2026-12-30');")
        for i in range(25):
            unit = f"Unit {(i // 5) + 1}"
            lid = f"l_{i}"
            conn.execute(
                "INSERT INTO lessons (id, course_id, title, chapter_title, start_sec, end_sec, raw_duration_sec, order_index) VALUES (?, 'c1', ?, ?, ?, ?, 600, ?);",
                (lid, f"OS Topic {i}", unit, i * 600, (i + 1) * 600, i),
            )
            conn.execute(
                "INSERT INTO notes (id, course_id, lesson_id, content_markdown, is_generated, generation_mode) VALUES (?, 'c1', ?, ?, 1, 'llm');",
                (f"n_{i}", lid, f"# OS Topic {i}\n- Key fact for {unit} topic {i} with formula $T = {i}+1$ [{i:02d}:00].\n" + ("Detail " * 150)),
            )
        conn.commit()

        seen_prompts = []
        async def _fake_gen(prompt, **kwargs):
            seen_prompts.append(prompt)
            if "Output a dense Markdown Fact Block" in prompt:
                return ("- Compressed module facts with formulas and [00:00].", "gemini:mock")
            # Pass 2: verify ALL 5 units are present in the Pass-2 reduce prompt!
            assert "MODULE: Unit 1" in prompt
            assert "MODULE: Unit 5" in prompt
            return ("# Operating Systems — Master Cram Sheet\n\n## 1. High-Yield Exam Weightage Matrix\nCovers Unit 1 through Unit 5 completely [00:00].\n" + ("x" * 120), "gemini:mock")

        with patch("backend.infra.llm_gateway.LLMGateway.generate_text", new=AsyncMock(side_effect=_fake_gen)):
            md = await generate_cram_sheet_with_llm(conn, "c1", force_refresh=True)
            assert md is not None
            assert "Unit 5" in md
            # 5 Pass-1 module compressions + 1 Pass-2 master synthesis = 6 calls
            assert len(seen_prompts) == 6
    finally:
        conn.close()
