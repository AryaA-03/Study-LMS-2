"""Authenticated encryption helper for per-user BYOK API keys in hosted multi-user mode.

Uses real AES-256-GCM (via `cryptography`) with HKDF-SHA256 per-secret salt key derivation
and unique 12-byte random nonces. Stored format is versioned (`v1:<salt_b64>:<ct_b64>`)
for safe future key rotation.
"""

import base64
import os
from typing import Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _derive_subkey(master_secret: str, salt: bytes) -> bytes:
    if not master_secret or len(master_secret) < 16:
        raise ValueError("MASTER_ENCRYPTION_KEY must be at least 16 characters.")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"study-lms-user-secret-v1",
    )
    return hkdf.derive(master_secret.encode("utf-8"))


def encrypt_secret(plaintext: str, master_secret: str) -> Tuple[str, str]:
    """Encrypt plaintext with AES-256-GCM + HKDF-SHA256 and return (ciphertext_b64, nonce_b64)."""
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_subkey(master_secret, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    # Prefix salt to ciphertext payload so decrypt derives the exact per-secret subkey
    packed = b"v1:" + salt + ct
    return (
        base64.b64encode(packed).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_secret(ciphertext_b64: str, nonce_b64: str, master_secret: str) -> str:
    """Verify AES-256-GCM authentication tag and decrypt ciphertext."""
    try:
        raw = base64.b64decode(ciphertext_b64)
        nonce = base64.b64decode(nonce_b64)
    except Exception as exc:
        raise ValueError("Corrupted base64 secret payload") from exc

    if not raw.startswith(b"v1:") or len(raw) < 3 + 16 + 16 or len(nonce) != 12:
        raise ValueError("Unsupported or corrupted ciphertext format")

    salt = raw[3:19]
    ct = raw[19:]
    key = _derive_subkey(master_secret, salt)
    try:
        pt = AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:
        raise ValueError("Authentication tag mismatch or wrong master key") from exc
    return pt.decode("utf-8")
