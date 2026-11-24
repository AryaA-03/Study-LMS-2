"""Authentication & Hosted Multi-User Encrypted BYOK Secrets Router."""

import sqlite3
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.deps import CurrentUser, get_current_user
from backend.services.user_secrets import (
    ALLOWED_PROVIDERS,
    delete_user_secret,
    list_user_secret_presence,
    upsert_user_secret,
)

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(get_current_user)])


class UserSecretUpsertRequest(BaseModel):
    provider: str = Field(..., description="One of: gemini, groq, openrouter")
    api_key: str = Field(..., min_length=4, max_length=512)


@router.get("/me")
def get_auth_me(
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Returns active user identity and auto-upserts into `users` in hosted mode."""
    if user.auth_mode != "local":
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            db.execute(
                """
                INSERT INTO users (id, email, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET email = COALESCE(excluded.email, users.email);
                """,
                (user.id, user.email or f"{user.id}@users.local", now_iso),
            )
            db.commit()
        except sqlite3.OperationalError:
            pass
    return {
        "id": user.id,
        "email": user.email,
        "auth_mode": user.auth_mode,
        "secrets": list_user_secret_presence(db, user.id),
    }


@router.get("/secrets")
def get_my_secrets_mask(
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> Dict[str, bool]:
    """Returns boolean presence mask for each BYOK provider (never returns plaintext keys)."""
    return list_user_secret_presence(db, user.id)


@router.put("/secrets")
def put_my_secret(
    req: UserSecretUpsertRequest,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Encrypts and stores a user's BYOK API key using AES-256-GCM + HKDF."""
    prov = req.provider.strip().lower()
    if prov not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Provider must be one of {sorted(ALLOWED_PROVIDERS)}")
    if user.auth_mode != "local":
        now_iso = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO users (id, email, created_at) VALUES (?, ?, ?);",
            (user.id, user.email or f"{user.id}@users.local", now_iso),
        )
    try:
        upsert_user_secret(db, user.id, prov, req.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not encrypt secret: {exc}")
    return {"success": True, "provider": prov, "secrets": list_user_secret_presence(db, user.id)}


@router.delete("/secrets/{provider}")
def remove_my_secret(
    provider: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Deletes a stored encrypted BYOK API key for the current user."""
    deleted = delete_user_secret(db, user.id, provider)
    if not deleted:
        raise HTTPException(status_code=404, detail="Secret not found for provider")
    return {"success": True, "provider": provider.lower(), "secrets": list_user_secret_presence(db, user.id)}
