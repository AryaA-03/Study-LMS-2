"""Secret-redacting logging filter so API keys and Bearer tokens never leak into logs."""

import logging
import re

_SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"gsk_[0-9A-Za-z_-]{20,}"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"sk-or-v1-[0-9A-Za-z_-]{20,}"), "[REDACTED_OPENROUTER_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"([?&]key=)[^&\s\"']+"), r"\1[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """Scrub known API key and bearer token patterns from a string."""
    if not text:
        return text
    out = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
        return True


def install_secret_redaction() -> None:
    """Attach SecretRedactingFilter to the root logger and learn_lms logger."""
    filt = SecretRedactingFilter()
    for name in ("", "learn_lms", "uvicorn", "uvicorn.access", "uvicorn.error", "httpx"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, SecretRedactingFilter) for f in lg.filters):
            lg.addFilter(filt)
