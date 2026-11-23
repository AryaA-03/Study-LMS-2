"""Integration tests for versioned non-destructive migrations and backups."""

import tempfile
import sqlite3
from pathlib import Path
from backend.migrations.runner import apply_migrations, get_current_schema_version, backup_db_before_migration

def test_migration_and_auto_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "test_app.db"
        # Initial migration
        count1 = apply_migrations(tmp_db)
        assert count1 >= 1

        conn = sqlite3.connect(tmp_db)
        ver1 = get_current_schema_version(conn)
        assert ver1 >= 1

        # Seed some data into courses table
        conn.execute("""
            INSERT INTO courses (id, title, goal_query, target_date, minutes_per_day)
            VALUES ('c-test', 'Seeded Course', 'Test Goal', '2026-12-31', 60);
        """)
        conn.commit()
        conn.close()

        # Backup creation test
        backup_file = backup_db_before_migration(tmp_db, ver1)
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0

        # Verify seeded data exists in backup
        conn_b = sqlite3.connect(backup_file)
        row = conn_b.execute("SELECT title FROM courses WHERE id = 'c-test';").fetchone()
        assert row is not None
        assert row[0] == "Seeded Course"
        conn_b.close()

        # Re-running migrations when already at latest should apply 0
        count2 = apply_migrations(tmp_db)
        assert count2 == 0


def test_fts5_cleanup_trigger():
    """Verifies that trg_chunks_delete_fts cleans up chunks_fts when a chunk is deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "test_fts_trigger.db"
        apply_migrations(tmp_db)

        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA foreign_keys = ON;")

        # Insert course, source, lesson, and chunk
        conn.execute("INSERT INTO courses (id, title, goal_query, target_date) VALUES ('c1', 'T', 'G', '2026-12-31');")
        conn.execute("INSERT INTO sources (id, course_id, source_type, title) VALUES ('s1', 'c1', 'web', 'S');")
        conn.execute("INSERT INTO chunks (id, course_id, source_id, chunk_index, token_count, content) VALUES ('chk1', 'c1', 's1', 0, 10, 'Automata Theory');")
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM chunks_fts;").fetchone()[0] == 1

        # Deleting chunk should automatically trigger deletion in chunks_fts
        conn.execute("DELETE FROM chunks WHERE id = 'chk1';")
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM chunks_fts;").fetchone()[0] == 0
        conn.close()
