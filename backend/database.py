import sqlite3
import contextlib
from pathlib import Path
from typing import Generator
from backend.config import DB_PATH

def init_connection(db_file: Path = DB_PATH) -> sqlite3.Connection:
    """Creates an optimized SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_file), timeout=60.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

@contextlib.contextmanager
def get_db_context(db_file: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections with auto-commit/rollback."""
    conn = init_connection(db_file)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency for database session."""
    with get_db_context() as conn:
        yield conn
