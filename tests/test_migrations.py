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
