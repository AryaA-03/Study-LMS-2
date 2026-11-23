"""Authentication, tenant-isolation, and local-admin dependencies.

Dual-mode design:
  - AUTH_MODE=local (default): Zero-friction single-user mode returning CurrentUser(id='local').
  - AUTH_MODE=supabase (hosted): Enforces strict HS256 JWT validation (alg header, exp, sub,
    optional aud/iss) and tenant ownership scoping on every course/lesson/host route.
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.database import get_db

_bearer = HTTPBearer(auto_error=False)
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: Optional[str] = None
    role: str = "owner"
    auth_mode: str = "local"


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _verify_hs256_jwt(token: str, secret: str) -> Dict[str, Any]:
    """Strictly verify HS256 JWT: header alg, signature, mandatory exp & sub, optional aud/iss."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Malformed bearer token")

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid JWT header")

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Unsupported JWT algorithm")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token signature encoding")

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(status_code=401, detail="Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    now = time.time()
    exp = payload.get("exp")
    if exp is None or not isinstance(exp, (int, float)):
        raise HTTPException(status_code=401, detail="Token missing required exp claim")
    if now > float(exp):
        raise HTTPException(status_code=401, detail="Token expired")

    nbf = payload.get("nbf")
    if nbf is not None and isinstance(nbf, (int, float)) and now < float(nbf) - 5:
        raise HTTPException(status_code=401, detail="Token not yet valid")

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    expected_aud = os.getenv("SUPABASE_JWT_AUD", "").strip()
    if expected_aud:
        aud = payload.get("aud")
        aud_ok = (aud == expected_aud) or (isinstance(aud, list) and expected_aud in aud)
        if not aud_ok:
            raise HTTPException(status_code=401, detail="Invalid token audience")

    expected_iss = os.getenv("SUPABASE_JWT_ISS", "").strip()
    if expected_iss and payload.get("iss") != expected_iss:
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    return payload


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """Resolve authenticated user; zero-friction 'local' user in AUTH_MODE=local."""
    auth_mode = os.getenv("AUTH_MODE", "local").strip().lower()
    if auth_mode == "local":
        return CurrentUser(id="local", email=None, auth_mode="local")

    secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="AUTH_MODE is hosted but SUPABASE_JWT_SECRET is not configured",
        )
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authorization Bearer token required")

    payload = _verify_hs256_jwt(credentials.credentials, secret)
    return CurrentUser(
        id=str(payload["sub"]),
        email=payload.get("email"),
        auth_mode=auth_mode,
    )


def require_local_admin(request: Request) -> None:
    """Restrict host-level operations (.env keys, pip update, raw DB backup/restore) to local mode + loopback."""
    auth_mode = os.getenv("AUTH_MODE", "local").strip().lower()
    if auth_mode != "local":
        raise HTTPException(
            status_code=403,
            detail="Host-level administration endpoints are disabled in hosted mode.",
        )
    client_host = (request.client.host if request.client else "") or ""
    if client_host and client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="Host-level administration endpoints are restricted to localhost.",
        )


def require_course_owner(
    course_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Verify course exists and belongs to the authenticated user (404 on mismatch)."""
    row = db.execute("SELECT * FROM courses WHERE id = ?;", (course_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    owner_id = row["owner_id"] if "owner_id" in row.keys() else "local"
    if user.auth_mode != "local" and owner_id != user.id:
        raise HTTPException(status_code=404, detail="Course not found")
    return row


def require_lesson_owner(
    lesson_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Verify lesson exists and its parent course belongs to the authenticated user."""
    row = db.execute(
        """
        SELECT l.*, c.owner_id AS course_owner_id
        FROM lessons l
        JOIN courses c ON c.id = l.course_id
        WHERE l.id = ?;
        """,
        (lesson_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")
    owner_id = row["course_owner_id"] if "course_owner_id" in row.keys() else "local"
    if user.auth_mode != "local" and owner_id != user.id:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return row
