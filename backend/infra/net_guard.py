"""SSRF protection and outbound URL / media allowlist validation."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

YOUTUBE_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }
)

YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
YOUTUBE_PLAYLIST_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,64}$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_forbidden_ip(ip_str: str) -> bool:
    """Return True if IP is loopback, private, link-local, multicast, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str, resolve_dns: bool = True) -> str:
    """Validate an untrusted URL for safe outbound HTTP(S) fetching (anti-SSRF).

    Blocks non-http(s) schemes, credentials in URLs, loopback/RFC1918/link-local/metadata IPs.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")
    cleaned = url.strip()
    if len(cleaned) > 2048:
        raise ValueError("URL exceeds maximum allowed length.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}. Only http/https allowed.")
    if not parsed.hostname:
        raise ValueError("URL is missing a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URLs are not permitted.")

    host = parsed.hostname.lower().rstrip(".")
    if host in LOOPBACK_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError(f"Access to local/internal host '{host}' is blocked.")

    # Direct IP literal check
    try:
        ipaddress.ip_address(host)
        if _is_forbidden_ip(host):
            raise ValueError(f"Access to non-public IP '{host}' is blocked.")
        return cleaned
    except ValueError as exc:
        if "blocked" in str(exc):
            raise

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve hostname '{host}': {exc}") from exc
        for info in infos:
            ip_addr = info[4][0]
            if _is_forbidden_ip(ip_addr):
                raise ValueError(f"Hostname '{host}' resolves to blocked internal IP '{ip_addr}'.")

    return cleaned


def validate_youtube_url_or_id(url_or_id: str) -> str:
    """Validate that an input is either an 11-char YouTube video ID or a YouTube URL."""
    if not url_or_id or not isinstance(url_or_id, str):
        raise ValueError("YouTube URL or video ID is required.")
    cleaned = url_or_id.strip()
    if YOUTUBE_VIDEO_ID_RE.match(cleaned):
        return cleaned

    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("YouTube URL must use http:// or https://.")
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_ALLOWED_HOSTS:
        raise ValueError(
            f"Host '{host}' is not an allowed YouTube domain. Only youtube.com and youtu.be URLs are permitted."
        )
    if parsed.username or parsed.password:
        raise ValueError("Credentials in YouTube URLs are not permitted.")
    return cleaned


def validate_ollama_url(url: str, auth_mode: str = "local") -> str:
    """Restrict Ollama endpoint to loopback in local mode and disallow in hosted mode."""
    if auth_mode != "local":
        raise ValueError("Local Ollama endpoints are disabled in hosted multi-user mode.")
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ollama URL must use http:// or https://.")
    host = (parsed.hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ValueError("Ollama URL must point to localhost / 127.0.0.1 / ::1.")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
