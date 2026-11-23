"""FastAPI auth & tenant dependencies supporting local-first and hosted (Supabase/OIDC) modes."""

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str = "local@study-lms.local"
    role: str = "owner"


def _verify_hs256_jwt(token: str, secret: str) -> dict:
    """Minimal dependency-free HS256 JWT verifier (compatible with Supabase JWT secret)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    header_b64, payload_b64, sig_b64 = parts

    def _b64url_decode(s: str) -> bytes:
        pad = "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s + pad)

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid JWT signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        raise ValueError("JWT expired")
    return payload


def get_current_user(authorization: Optional[str] = Header(default=None)) -> CurrentUser:
    """Resolve active user.

    - AUTH_MODE=local (default): returns local owner with zero login friction.
    - AUTH_MODE=supabase / oidc: requires valid Bearer JWT signed with SUPABASE_JWT_SECRET / JWT_SECRET.
    """
    auth_mode = os.getenv("AUTH_MODE", "local").strip().lower()
    if auth_mode == "local":
        return CurrentUser(id="local", email="local@study-lms.local", role="owner")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.split(" ", 1)[1].strip()
    secret = os.getenv("SUPABASE_JWT_SECRET") or os.getenv("JWT_SECRET") or ""
    if not secret:
        raise HTTPException(status_code=503, detail="Auth secret not configured on server")

    try:
        claims = _verify_hs256_jwt(token, secret)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {exc}") from exc

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject claim")
    return CurrentUser(
        id=str(user_id),
        email=str(claims.get("email", "")),
        role=str(claims.get("role", "authenticated")),
    )
