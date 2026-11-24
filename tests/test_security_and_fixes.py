"""Side-by-side verification suite for Phase 0, Phase 1, and Phase 2 foundation fixes.

Runs cleanly with stdlib `unittest` (and pytest) against an isolated temporary directory.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

USER_PLAYLIST_URL = "https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev&si=2citoXJbxnLRp3yS"
USER_LONG_VIDEO_URL = "https://youtu.be/NlLM3sVF8wY?si=MhJJiMOjzevBjiRn"


class TestPhase0To2Fixes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="study_lms_verify_")
        self.tmp_path = Path(self.tmpdir.name)
        self.db_path = self.tmp_path / "app.db"
        self.backups_dir = self.tmp_path / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATA_DIR"] = str(self.tmp_path)
        os.environ["APP_ENV"] = "test"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_01_migrations_001_to_010_and_idempotency(self):
        from backend.migrations.runner import apply_migrations, create_verified_online_backup
        import backend.migrations.runner as runner_mod

        runner_mod.BACKUPS_DIR = self.backups_dir
        applied = apply_migrations(self.db_path)
        self.assertEqual(applied, 14)
        reapplied = apply_migrations(self.db_path)
        self.assertEqual(reapplied, 0)

        # Verify Migration 010 tables, columns, indexes, and triggers
        conn = sqlite3.connect(str(self.db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("jobs", tables)
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertIn("trg_chunks_update_fts", triggers)
        self.assertIn("trg_chunks_delete_fts", triggers)

        # Verify owner_id column exists on courses
        cols = {r[1] for r in conn.execute("PRAGMA table_info(courses)")}
        self.assertIn("owner_id", cols)

        # Verify online WAL backup produces integrity_check = ok
        backup_out = self.backups_dir / "verified_online.db"
        create_verified_online_backup(self.db_path, backup_out)
        self.assertTrue(backup_out.exists())
        conn.close()

    def test_02_net_guard_ssrf_and_user_youtube_urls(self):
        from backend.infra.net_guard import (
            validate_ollama_url,
            validate_public_url,
            validate_youtube_url_or_id,
        )

        # Both user-provided YouTube URLs must be accepted
        self.assertEqual(validate_youtube_url_or_id(USER_PLAYLIST_URL), USER_PLAYLIST_URL)
        self.assertEqual(validate_youtube_url_or_id(USER_LONG_VIDEO_URL), USER_LONG_VIDEO_URL)
        self.assertEqual(validate_youtube_url_or_id("NlLM3sVF8wY"), "NlLM3sVF8wY")

        # Non-YouTube / SSRF URLs must be rejected
        for bad in [
            "http://127.0.0.1:8000/api/settings",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "https://evil.example.com/watch?v=NlLM3sVF8wY",
        ]:
            with self.assertRaises(ValueError):
                validate_youtube_url_or_id(bad)

        # Public URL SSRF guard blocks loopback, private, link-local, metadata
        for bad_ssrf in [
            "http://127.0.0.1:8000/",
            "http://localhost:11434/api/tags",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.1/",
            "file:///etc/passwd",
            "ftp://example.com/file",
        ]:
            with self.assertRaises(ValueError):
                validate_public_url(bad_ssrf, resolve_dns=False)

        # Ollama guard allows loopback in local mode, blocks remote & hosted mode
        self.assertEqual(validate_ollama_url("http://localhost:11434", "local"), "http://localhost:11434")
        with self.assertRaises(ValueError):
            validate_ollama_url("http://169.254.169.254:11434", "local")
        with self.assertRaises(ValueError):
            validate_ollama_url("http://localhost:11434", "oidc")

    def test_03_env_injection_blocked_and_live_refresh(self):
        import backend.config as cfg

        orig_base = cfg.BASE_DIR
        cfg.BASE_DIR = self.tmp_path
        try:
            # Newline injection must raise ValueError
            with self.assertRaises(ValueError):
                cfg.update_env_file({"GEMINI_API_KEY": "abc\nAPP_HOST=0.0.0.0"})
            with self.assertRaises(ValueError):
                cfg.update_env_file({"INVALID-KEY": "123"})

            # Valid update refreshes ENV_VARS in place (same dict object identity!)
            dict_id_before = id(cfg.ENV_VARS)
            cfg.update_env_file({"GEMINI_API_KEY": "test_key_123"})
            self.assertEqual(id(cfg.ENV_VARS), dict_id_before)
            self.assertEqual(cfg.ENV_VARS.get("GEMINI_API_KEY"), "test_key_123")
        finally:
            cfg.BASE_DIR = orig_base

    def test_04_quiz_question_schema_preserves_timestamps(self):
        from backend.models.schemas import QuizQuestion

        q = QuizQuestion(
            id="q1",
            chunk_id="c1",
            quote="B+ trees keep all keys in leaves.",
            question="Where are keys stored in a B+ tree?",
            options=["Root only", "Leaf nodes", "Internal only", "None"],
            correct_index=1,
            explanation="B+ trees store data pointers in leaf nodes.",
            timestamp_sec=742,
            timestamp_str="12:22",
            replay_url="https://youtu.be/NlLM3sVF8wY?t=742",
        )
        dumped = q.model_dump() if hasattr(q, "model_dump") else q.dict()
        self.assertEqual(dumped["timestamp_sec"], 742)
        self.assertEqual(dumped["timestamp_str"], "12:22")
        self.assertIn("t=742", dumped["replay_url"])

    def test_05_screenshot_path_traversal_blocked(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import backend.config as cfg
        import sys, types
        sys.modules.setdefault("yt_dlp", types.ModuleType("yt_dlp"))
        from backend.routers import screenshots as ss_router

        orig_data = cfg.DATA_DIR
        cfg.DATA_DIR = self.tmp_path
        app = FastAPI()
        app.include_router(ss_router.router)
        client = TestClient(app)
        try:
            r1 = client.get("/api/screenshots/..%2F..%2F/etc/passwd")
            self.assertIn(r1.status_code, (400, 403, 404))
            r2 = client.get("/api/screenshots/course1/lesson1/..%2Fsecret.jpg")
            self.assertIn(r2.status_code, (400, 403, 404))
            # Verify GET did NOT create directories on disk
            self.assertFalse((self.tmp_path / "screenshots" / "course1").exists())
        finally:
            cfg.DATA_DIR = orig_data

    def test_06_scheduler_all_7_rest_days_does_not_hang(self):
        from datetime import date
        from backend.scheduler.engine import generate_schedule

        lessons = [{"id": "l1", "title": "Intro", "raw_duration_sec": 1800, "order_index": 0}]
        result = generate_schedule(
            course_id="c1",
            lessons=lessons,
            minutes_per_day=60,
            playback_speed=1.0,
            rest_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            revision_buffer_days=0,
            start_date=date(2026, 11, 23),
            target_date=date(2026, 12, 1),
        )
        self.assertIsNotNone(result)

    def test_07_frontend_pyodide_removed_and_no_legacy_crashes(self):
        repo_root = Path(__file__).resolve().parent.parent
        self.assertFalse((repo_root / "frontend/static/js/pyodide_worker.js").exists())
        self.assertFalse((repo_root / "frontend/static/js/app.js").exists())
        self.assertFalse((repo_root / "frontend/templates/index.html").exists())

