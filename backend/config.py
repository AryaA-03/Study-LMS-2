import os
from pathlib import Path
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from datetime import datetime

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env if present
def load_env_vars() -> Dict[str, str]:
    env_file = BASE_DIR / ".env"
    env_vars: Dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars

ENV_VARS = load_env_vars()

# App configuration
APP_ENV = os.getenv("APP_ENV", ENV_VARS.get("APP_ENV", "development"))
DATA_DIR_NAME = os.getenv("DATA_DIR", ENV_VARS.get("DATA_DIR", "data-dev"))
DATA_DIR = BASE_DIR / DATA_DIR_NAME
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
APP_PORT = int(os.getenv("APP_PORT", ENV_VARS.get("APP_PORT", "8000")))

def get_now() -> datetime:
    """Returns current localized timestamp."""
    return datetime.now(LOCAL_TZ)

def get_today_str() -> str:
    """Returns current date string in ISO format YYYY-MM-DD."""
    return get_now().strftime("%Y-%m-%d")

def update_env_file(updates: Dict[str, str]) -> None:
    """Safe update to .env preserving existing comments and ordering."""
    env_file = BASE_DIR / ".env"
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
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                existing_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}")

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Refresh cache
    global ENV_VARS
    ENV_VARS = load_env_vars()
