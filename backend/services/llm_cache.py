"""SQLite LLM Response Caching Service.

Provides SHA-256 content-hash deduplication and caching for LLM requests
(Structured Notes, Q&A Engine, Quiz Generation) backed by the SQLite `llm_cache` table.
"""

import hashlib
import json
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger("learn_lms.llm_cache")


def ensure_llm_cache_table(db_conn) -> None:
    """Ensures llm_cache table exists with all expected columns."""
    if not db_conn:
        return
    try:
        cur = db_conn.cursor()
        cur.execute("PRAGMA table_info(llm_cache);")
        cols = {row[1] for row in cur.fetchall()}
        if not cols:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    prompt_hash TEXT PRIMARY KEY,
                    model TEXT,
                    model_name TEXT,
                    response_json TEXT,
                    response_text TEXT,
                    tokens_used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            if "response_json" not in cols:
                try:
                    cur.execute("ALTER TABLE llm_cache ADD COLUMN response_json TEXT;")
                except Exception:
                    pass
            if "response_text" not in cols:
                try:
                    cur.execute("ALTER TABLE llm_cache ADD COLUMN response_text TEXT;")
                except Exception:
                    pass
            if "model" not in cols:
                try:
                    cur.execute("ALTER TABLE llm_cache ADD COLUMN model TEXT;")
                except Exception:
                    pass
            if "model_name" not in cols:
                try:
                    cur.execute("ALTER TABLE llm_cache ADD COLUMN model_name TEXT;")
                except Exception:
                    pass
        db_conn.commit()
    except Exception as e:
        logger.warning(f"Error ensuring llm_cache table: {e}")


def compute_sha256(content: str) -> str:
    """Computes SHA-256 hex digest of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_cached_response(db_conn, prompt_hash: str) -> Optional[str]:
    """Retrieves cached response text or json by prompt_hash if present."""
    if not db_conn:
        return None
    try:
        cur = db_conn.cursor()
        cur.execute("PRAGMA table_info(llm_cache);")
        cols = {row[1] for row in cur.fetchall()}
        if not cols:
            return None

        if "response_json" in cols and "response_text" in cols:
            cur.execute(
                "SELECT COALESCE(response_json, response_text) FROM llm_cache WHERE prompt_hash = ? LIMIT 1;",
                (prompt_hash,)
            )
        elif "response_json" in cols:
            cur.execute("SELECT response_json FROM llm_cache WHERE prompt_hash = ? LIMIT 1;", (prompt_hash,))
        elif "response_text" in cols:
            cur.execute("SELECT response_text FROM llm_cache WHERE prompt_hash = ? LIMIT 1;", (prompt_hash,))
        else:
            return None

        row = cur.fetchone()
        if row and row[0] is not None:
            return str(row[0])
    except Exception as e:
        logger.warning(f"Error reading llm_cache: {e}")
    return None


def set_cached_response(
    db_conn,
    prompt_hash: str,
    model: str,
    response_val: str,
    tokens_used: int = 0
) -> None:
    """Stores response into SQLite llm_cache table."""
    if not db_conn:
        return
    try:
        ensure_llm_cache_table(db_conn)
        cur = db_conn.cursor()
        cur.execute("PRAGMA table_info(llm_cache);")
        cols = {row[1] for row in cur.fetchall()}

        insert_cols = ["prompt_hash"]
        insert_vals = [prompt_hash]

        if "model" in cols:
            insert_cols.append("model")
            insert_vals.append(model)
        if "model_name" in cols:
            insert_cols.append("model_name")
            insert_vals.append(model)
        if "response_json" in cols:
            insert_cols.append("response_json")
            insert_vals.append(response_val)
        if "response_text" in cols:
            insert_cols.append("response_text")
            insert_vals.append(response_val)
        if "tokens_used" in cols:
            insert_cols.append("tokens_used")
            insert_vals.append(tokens_used)

        placeholders = ", ".join(["?"] * len(insert_cols))
        colnames = ", ".join(insert_cols)
        cur.execute(
            f"INSERT OR REPLACE INTO llm_cache ({colnames}) VALUES ({placeholders});",
            tuple(insert_vals)
        )
        db_conn.commit()
    except Exception as e:
        logger.warning(f"Error writing to llm_cache: {e}")
