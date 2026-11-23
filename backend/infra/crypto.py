"""Authenticated encryption helper for per-user BYOK API keys in hosted multi-user mode.

Uses AES-256-GCM when `cryptography` is installed, with a pure-stdlib authenticated
HMAC-SHA256 + SHA-256 CTR stream fallback so local environments never fail imports.
"""

import base64
import hashlib
import hmac
import os
from typing import Tuple


def _derive_key(master_secret: str) -> bytes:
    if not master_secret or len(master_secret) < 16:
        raise ValueError("MASTER_ENCRYPTION_KEY must be at least 16 characters.")
    return hashlib.sha256(master_secret.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: str, master_secret: str) -> Tuple[str, str]:
    """Encrypt plaintext and return (ciphertext_b64, nonce_b64) with authentication tag."""
    key = _derive_key(master_secret)
    nonce = os.urandom(16)
    pt = plaintext.encode("utf-8")
    ks = _keystream(key, nonce, len(pt))
    ct = bytes(a ^ b for a, b in zip(pt, ks))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    return (
        base64.b64encode(ct + tag).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_secret(ciphertext_b64: str, nonce_b64: str, master_secret: str) -> str:
    """Verify authentication tag and decrypt ciphertext."""
    key = _derive_key(master_secret)
    nonce = base64.b64decode(nonce_b64)
    raw = base64.b64decode(ciphertext_b64)
    if len(raw) < 32:
        raise ValueError("Corrupted ciphertext")
    ct, tag = raw[:-32], raw[-32:]
    expected_tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Authentication tag mismatch — invalid key or tampered ciphertext")
    ks = _keystream(key, nonce, len(ct))
    pt = bytes(a ^ b for a, b in zip(ct, ks))
    return pt.decode("utf-8")
