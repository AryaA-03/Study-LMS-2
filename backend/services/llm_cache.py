"""Hardened SQLite LLM Response Cache with 30-day TTL, zero memory leaks, and schema compatibility."""

import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("learn_lms.llm_cache")

DEFAULT_TTL_DAYS = 30


def compute_sha256(text: str) -> str:
    """Computes deterministic SHA-256 hex digest for cache keys."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def compute_prompt_hash(prompt: str, model_hint: str = "") -> str:
    """Computes a deterministic SHA-256 hash for a prompt + model key."""
    normalized = f"{model_hint.strip()}::{prompt.strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def ensure_llm_cache_table(db_conn: sqlite3.Connection) -> None:
    """Ensures llm_cache table has required columns (including response_json & expires_at)."""
    db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_cache (
            prompt_hash TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            response_text TEXT NOT NULL,
            response_json TEXT,
            tokens_used INTEGER DEFAULT 0,
            owner_id TEXT NOT NULL DEFAULT 'local',
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cols = {r[1] for r in db_conn.execute("PRAGMA table_info(llm_cache);").fetchall()}
    if "response_json" not in cols:
        db_conn.execute("ALTER TABLE llm_cache ADD COLUMN response_json TEXT;")
    if "expires_at" not in cols:
        db_conn.execute("ALTER TABLE llm_cache ADD COLUMN expires_at TIMESTAMP;")
    if "owner_id" not in cols:
        db_conn.execute("ALTER TABLE llm_cache ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local';")


def get_cached_response(db_conn: sqlite3.Connection, prompt_hash: str) -> Optional[str]:
    """Retrieves a non-expired cached LLM response by prompt_hash."""
    if not db_conn or not prompt_hash:
        return None
    try:
        cols = {r[1] for r in db_conn.execute("PRAGMA table_info(llm_cache);").fetchall()}
        if not cols:
            return None
        val_col = "COALESCE(response_text, response_json)" if "response_json" in cols else "response_text"
        exp_col = "expires_at" if "expires_at" in cols else "NULL"
        row = db_conn.execute(
            f"SELECT {val_col}, {exp_col} FROM llm_cache WHERE prompt_hash = ?;",
            (prompt_hash,),
        ).fetchone()
        if not row:
            return None
        expires_at = row[1]
        if expires_at and str(expires_at) < datetime.now(timezone.utc).isoformat():
            db_conn.execute("DELETE FROM llm_cache WHERE prompt_hash = ?;", (prompt_hash,))
            db_conn.commit()
            return None
        return row[0]
    except Exception as exc:
        logger.warning(f"LLM cache read error: {exc}")
        return None


def set_cached_response(
    db_conn: sqlite3.Connection,
    prompt_hash: str,
    model_name: str,
    response_val: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
    owner_id: str = "local",
) -> None:
    """Stores an LLM response with TTL expiration using canonical llm_cache schema."""
    if not db_conn or not prompt_hash or not response_val:
        return
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    try:
        ensure_llm_cache_table(db_conn)
        db_conn.execute(
            """
            INSERT OR REPLACE INTO llm_cache (prompt_hash, model_name, response_text, response_json, owner_id, expires_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (prompt_hash, model_name, response_val, response_val, owner_id, expires_at),
        )
        db_conn.commit()
    except Exception as exc:
        logger.warning(f"LLM cache write error: {exc}")


def prune_expired_cache(db_conn: sqlite3.Connection) -> int:
    """Removes expired entries from llm_cache."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        cur = db_conn.execute(
            "DELETE FROM llm_cache WHERE expires_at IS NOT NULL AND expires_at < ?;",
            (now_iso,),
        )
        db_conn.commit()
        return cur.rowcount
    except Exception:
        return 0
