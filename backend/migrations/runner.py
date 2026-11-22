import sqlite3
import shutil
import re
from pathlib import Path
from datetime import datetime
from backend.config import DB_PATH, BACKUPS_DIR
from backend.database import init_connection

VERSIONS_DIR = Path(__file__).resolve().parent / "versions"

def backup_db_before_migration(db_path: Path, current_version: int) -> Path:
    """Creates a timestamped backup before applying any schema modification."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUPS_DIR / f"app_v{current_version}_{ts}.db"
    if db_path.exists() and db_path.stat().st_size > 0:
        shutil.copy2(db_path, backup_file)
        # Also copy WAL and SHM if present
        for ext in ["-wal", "-shm"]:
            sidecar = Path(str(db_path) + ext)
            if sidecar.exists():
                shutil.copy2(sidecar, Path(str(backup_file) + ext))
        # Verify backup integrity before applying migration
        try:
            check_conn = sqlite3.connect(str(backup_file))
            result = check_conn.execute("PRAGMA integrity_check;").fetchone()
            check_conn.close()
            if result and result[0] != "ok":
                raise RuntimeError(f"Backup integrity check failed: {result[0]}. Aborting migration.")
        except Exception as integrity_err:
            raise RuntimeError(f"Cannot verify backup at {backup_file}: {integrity_err}") from integrity_err
    return backup_file

def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """Returns the highest applied migration version or 0."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur = conn.execute("SELECT MAX(version) FROM schema_migrations;")
    row = cur.fetchone()
    return int(row[0]) if (row and row[0] is not None) else 0

def apply_migrations(db_path: Path = DB_PATH) -> int:
    """Applies all pending migrations non-destructively, taking automated backups."""
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    conn = init_connection(db_path)
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

        # Create automated backup before applying pending migrations
        backup_db_before_migration(db_path, current_version)

        applied_count = 0
        for ver, name, f in pending:
            sql = f.read_text(encoding="utf-8")
            with conn:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                    (ver, name),
                )
            applied_count += 1
            current_version = ver

        return applied_count
    finally:
        conn.close()

if __name__ == "__main__":
    count = apply_migrations()
    print(f"Migrations applied: {count}")
