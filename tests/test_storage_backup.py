"""Unit tests for Storage Guard, SQLite Backup, VACUUM, and Course Bundle Export."""

import tempfile
import sqlite3
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_connection
from backend.migrations.runner import apply_migrations
from backend.config import DB_PATH


@pytest.fixture
def client_with_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "app.db"
        apply_migrations(tmp_db)

        # Populate sample course
        conn = init_connection(tmp_db)
        cid = "c_export_test"
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day) VALUES (?, ?, ?, '2026-12-30', 60);", (cid, "Theory of Computation", "TOC"))
        conn.execute("INSERT INTO lessons (id, course_id, title, raw_duration_sec) VALUES ('l1', ?, 'DFA Basics', 600);", (cid,))
        conn.execute("INSERT INTO notes (id, course_id, lesson_id, content_markdown, personal_notes) VALUES ('n1', ?, 'l1', '# DFA Notes', 'My exam tips');", (cid,))
        conn.execute("INSERT INTO flashcards (id, course_id, front, back, due_date) VALUES ('fc1', ?, 'What is DFA?', 'Finite Automaton', '2026-12-01');", (cid,))
        conn.commit()
        conn.close()

        def override_db():
            conn = init_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_db
        # Temporarily point DB_PATH to tmp_db for backup test
        import backend.routers.settings as settings_mod
        orig_db_path = settings_mod.DB_PATH
        settings_mod.DB_PATH = tmp_db

        with TestClient(app) as client:
            yield client, cid, tmp_db

        settings_mod.DB_PATH = orig_db_path
        app.dependency_overrides.clear()


def test_download_sqlite_backup(client_with_db):
    client, cid, db_path = client_with_db
    res = client.get("/api/settings/backup")
    assert res.status_code == 200
    assert "attachment" in res.headers.get("content-disposition", "")
    assert res.headers["content-type"] == "application/vnd.sqlite3"
    # First 16 bytes of SQLite database file
    assert res.content[:16] == b"SQLite format 3\x00"


def test_vacuum_database(client_with_db):
    client, cid, db_path = client_with_db
    res = client.post("/api/settings/vacuum")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "vacuumed successfully" in data["message"].lower()
    assert data["db_size_bytes"] > 0


def test_export_course_bundle(client_with_db):
    client, cid, db_path = client_with_db
    res = client.get(f"/api/courses/{cid}/export")
    assert res.status_code == 200
    bundle = res.json()

    assert bundle["version"] == "1.0"
    assert bundle["course"]["id"] == cid
    assert bundle["course"]["title"] == "Theory of Computation"
    assert len(bundle["lessons"]) == 1
    assert bundle["lessons"][0]["title"] == "DFA Basics"
    assert len(bundle["notes"]) == 1
    assert bundle["notes"][0]["personal_notes"] == "My exam tips"
    assert len(bundle["flashcards"]) == 1
    assert bundle["flashcards"][0]["front"] == "What is DFA?"
