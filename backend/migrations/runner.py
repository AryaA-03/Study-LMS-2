"""Atomic SQLite schema migration runner with verified online backups."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from backend.config import BACKUPS_DIR, DB_PATH
from backend.database import init_connection

VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


def create_verified_online_backup(source_db: Path, dest_db: Path) -> Path:
    """Create a consistent SQLite backup using the official online backup API."""
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(source_db), timeout=60.0)
    dst_conn = sqlite3.connect(str(dest_db), timeout=60.0)
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()

    check_conn = sqlite3.connect(str(dest_db))
    try:
        result = check_conn.execute("PRAGMA integrity_check;").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(
                f"Backup integrity check failed: {result[0] if result else 'unknown'}"
            )
    finally:
        check_conn.close()
    return dest_db


def backup_db_before_migration(
    db_path: Path, current_version: int, backups_dir: Path | None = None
) -> Path:
    """Creates a timestamped, integrity-verified backup before applying schema changes."""
    target_dir = Path(backups_dir) if backups_dir is not None else BACKUPS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_file = target_dir / f"app_v{current_version}_{ts}.db"
    if db_path.exists() and db_path.stat().st_size > 0:
        create_verified_online_backup(db_path, backup_file)
    return backup_file


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """Returns the highest applied migration version or 0."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    cur = conn.execute("SELECT MAX(version) FROM schema_migrations;")
    row = cur.fetchone()
    return int(row[0]) if (row and row[0] is not None) else 0


def _split_sql_statements(sql: str) -> List[str]:
    """Split a SQL script into individual complete statements, preserving triggers."""
    statements: List[str] = []
    buffer: List[str] = []
    for line in sql.splitlines(keepends=True):
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith("--")):
            continue
        buffer.append(line)
        candidate = "".join(buffer)
        if sqlite3.complete_statement(candidate):
            stmt = candidate.strip()
            if stmt:
                statements.append(stmt)
            buffer = []
    remainder = "".join(buffer).strip()
    if remainder and not all(
        ln.strip().startswith("--") or not ln.strip() for ln in remainder.splitlines()
    ):
        statements.append(remainder)
    return statements


def apply_migrations(db_path: Path = DB_PATH) -> int:
    """Applies all pending migrations atomically inside explicit transactions."""
    db_path = Path(db_path)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    conn = init_connection(db_path)
    # Enable WAL once at migration/startup time (not on every request)
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        current_version = get_current_schema_version(conn)
        migration_files = sorted(VERSIONS_DIR.glob("*.sql"))
        pending = []

        for f in migration_files:
            match = re.match(r"^(\d+)_(.+)\.sql$", f.name)
            if match:
                ver = int(match.group(1))
                name = match.group(2)
                if ver > current_version:
                    pending.append((ver, name, f))

        if not pending:
            return 0

        backup_db_before_migration(db_path, current_version)

        applied_count = 0
        # Use manual transaction control so multi-statement migrations are truly atomic
        conn.isolation_level = None
        for ver, name, f in pending:
            sql = f.read_text(encoding="utf-8")
            statements = _split_sql_statements(sql)
            conn.execute("BEGIN IMMEDIATE;")
            try:
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                    (ver, name),
                )
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
            applied_count += 1
            current_version = ver

        return applied_count
    finally:
        conn.close()


if __name__ == "__main__":
    count = apply_migrations()
    print(f"Migrations applied: {count}")
