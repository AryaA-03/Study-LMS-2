import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

_ENV_LOCK = threading.Lock()
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def load_env_vars() -> Dict[str, str]:
    """Read .env if present without mutating process environment."""
    env_file = BASE_DIR / ".env"
    env_vars: Dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


ENV_VARS: Dict[str, str] = load_env_vars()

# Ensure .venv/bin (or Scripts on Windows) is on PATH so local binaries are found
_venv_bin_name = "Scripts" if os.name == "nt" else "bin"
VENV_BIN = BASE_DIR / ".venv" / _venv_bin_name
if VENV_BIN.exists() and str(VENV_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{VENV_BIN}{os.pathsep}{os.environ.get('PATH', '')}"

# App configuration
APP_ENV = os.getenv("APP_ENV", ENV_VARS.get("APP_ENV", "development"))
AUTH_MODE = os.getenv("AUTH_MODE", ENV_VARS.get("AUTH_MODE", "local"))
DATA_DIR_NAME = os.getenv("DATA_DIR", ENV_VARS.get("DATA_DIR", "data-dev"))
DATA_DIR = Path(DATA_DIR_NAME) if Path(DATA_DIR_NAME).is_absolute() else (BASE_DIR / DATA_DIR_NAME)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "app.db"
BACKUPS_DIR = DATA_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Timezone
TIMEZONE_STR = os.getenv("TIMEZONE", ENV_VARS.get("TIMEZONE", "Asia/Kolkata"))
try:
    LOCAL_TZ = ZoneInfo(TIMEZONE_STR)
except Exception:
    LOCAL_TZ = ZoneInfo("Asia/Kolkata")

# Network & Server Config
APP_HOST = os.getenv("APP_HOST", ENV_VARS.get("APP_HOST", "127.0.0.1"))
_raw_port = os.getenv("APP_PORT", ENV_VARS.get("APP_PORT", "8000"))
try:
    APP_PORT = int(_raw_port)
except Exception:
    APP_PORT = 8000


def get_now() -> datetime:
    """Returns current localized timestamp."""
    return datetime.now(LOCAL_TZ)


def get_today_str() -> str:
    """Returns current date string in ISO format YYYY-MM-DD."""
    return get_now().strftime("%Y-%m-%d")


def _validate_env_pair(key: str, value: str) -> None:
    """Prevent .env newline/control-character injection."""
    if not _ENV_KEY_RE.match(key):
        raise ValueError(f"Invalid environment variable name: {key!r}")
    if any(ch in value for ch in ("\r", "\n", "\0")):
        raise ValueError(f"Invalid control/newline characters in value for {key}")


def update_env_file(updates: Dict[str, str]) -> None:
    """Atomically update .env with 0600 permissions and refresh ENV_VARS in place."""
    validated: Dict[str, str] = {}
    for k, v in updates.items():
        sval = "" if v is None else str(v)
        _validate_env_pair(k, sval)
        validated[k] = sval

    env_file = BASE_DIR / ".env"
    with _ENV_LOCK:
        lines = []
        existing_keys = set()
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()

        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in validated:
                    new_lines.append(f"{k}={validated[k]}")
                    existing_keys.add(k)
                    continue
            new_lines.append(line)

        for k, v in validated.items():
            if k not in existing_keys:
                new_lines.append(f"{k}={v}")

        payload = "\n".join(new_lines) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=".env.tmp.", dir=str(BASE_DIR))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(payload)
            try:
                os.chmod(tmp_name, 0o600)
            except OSError:
                pass
            os.replace(tmp_name, env_file)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

        # Mutate ENV_VARS in place so all modules importing ENV_VARS see updates immediately
        refreshed = load_env_vars()
        ENV_VARS.clear()
        ENV_VARS.update(refreshed)


class Settings:
    @property
    def BASE_DIR(self) -> Path:
        return BASE_DIR

    @property
    def PROJECT_ROOT(self) -> Path:
        return BASE_DIR

    @property
    def DATA_DIR(self) -> Path:
        return DATA_DIR

    @property
    def DB_PATH(self) -> Path:
        return DB_PATH

    @property
    def LOCAL_TZ(self) -> ZoneInfo:
        return LOCAL_TZ

    @property
    def ACTIVE_LLM_PROVIDER(self) -> str:
        return os.getenv("ACTIVE_LLM_PROVIDER") or ENV_VARS.get("ACTIVE_LLM_PROVIDER") or "auto"

    @property
    def GEMINI_API_KEY(self) -> Optional[str]:
        return os.getenv("GEMINI_API_KEY") or ENV_VARS.get("GEMINI_API_KEY")

    @property
    def GROQ_API_KEY(self) -> Optional[str]:
        return os.getenv("GROQ_API_KEY") or ENV_VARS.get("GROQ_API_KEY")

    @property
    def OPENROUTER_API_KEY(self) -> Optional[str]:
        return os.getenv("OPENROUTER_API_KEY") or ENV_VARS.get("OPENROUTER_API_KEY")

    @property
    def GEMINI_MODEL(self) -> str:
        return os.getenv("GEMINI_MODEL") or ENV_VARS.get("GEMINI_MODEL") or "gemini-2.5-flash"

    @property
    def GROQ_MODEL(self) -> str:
        return os.getenv("GROQ_MODEL") or ENV_VARS.get("GROQ_MODEL") or "llama-3.3-70b-versatile"

    @property
    def OPENROUTER_MODEL(self) -> str:
        return os.getenv("OPENROUTER_MODEL") or ENV_VARS.get("OPENROUTER_MODEL") or "google/gemini-2.5-flash"

    @property
    def OPENROUTER_BASE_URL(self) -> str:
        return os.getenv("OPENROUTER_BASE_URL") or ENV_VARS.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return os.getenv("OLLAMA_BASE_URL") or ENV_VARS.get("OLLAMA_BASE_URL") or "http://localhost:11434"

    @property
    def OLLAMA_MODEL(self) -> str:
        return os.getenv("OLLAMA_MODEL") or ENV_VARS.get("OLLAMA_MODEL") or "llama3.2"


_settings = Settings()


def get_settings() -> Settings:
    return _settings
