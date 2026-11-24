"""Encrypted Per-User BYOK Secrets Vault (AES-256-GCM + HKDF) for Hosted Mode."""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict

from backend.infra.crypto import decrypt_secret, encrypt_secret

ALLOWED_PROVIDERS = {"gemini", "groq", "openrouter"}


def _get_master_key() -> str:
    key = os.getenv("MASTER_ENCRYPTION_KEY", "").strip()
    if not key:
        raise ValueError("MASTER_ENCRYPTION_KEY environment variable is required to store encrypted secrets.")
    return key


def upsert_user_secret(db: sqlite3.Connection, user_id: str, provider: str, plaintext_key: str) -> None:
    prov = provider.strip().lower()
    if prov not in ALLOWED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    master_key = _get_master_key()
    ciphertext_b64, nonce_b64 = encrypt_secret(plaintext_key.strip(), master_key)
    now_iso = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO user_secrets (id, user_id, provider, ciphertext_b64, nonce_b64, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, provider) DO UPDATE SET
            ciphertext_b64 = excluded.ciphertext_b64,
            nonce_b64 = excluded.nonce_b64,
            updated_at = excluded.updated_at;
        """,
        (str(uuid.uuid4()), user_id, prov, ciphertext_b64, nonce_b64, now_iso, now_iso),
    )
    db.commit()


def delete_user_secret(db: sqlite3.Connection, user_id: str, provider: str) -> bool:
    prov = provider.strip().lower()
    cur = db.execute(
        "DELETE FROM user_secrets WHERE user_id = ? AND provider = ?;",
        (user_id, prov),
    )
    db.commit()
    return cur.rowcount > 0


def list_user_secret_presence(db: sqlite3.Connection, user_id: str) -> Dict[str, bool]:
    try:
        rows = db.execute(
            "SELECT provider FROM user_secrets WHERE user_id = ?;",
            (user_id,),
        ).fetchall()
        present = {r[0] for r in rows}
    except sqlite3.OperationalError:
        present = set()
    return {p: (p in present) for p in sorted(ALLOWED_PROVIDERS)}


def get_user_decrypted_secrets(db: sqlite3.Connection, user_id: str) -> Dict[str, str]:
    try:
        master_key = _get_master_key()
        rows = db.execute(
            "SELECT provider, ciphertext_b64, nonce_b64 FROM user_secrets WHERE user_id = ?;",
            (user_id,),
        ).fetchall()
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for prov, ct, nonce in rows:
        try:
            out[prov] = decrypt_secret(ct, nonce, master_key)
        except Exception:
            pass
    return out
