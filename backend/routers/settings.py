"""System settings, yt-dlp maintenance, and storage guard router."""

import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from backend.database import get_db
from backend.config import DATA_DIR, DB_PATH, TIMEZONE_STR, ENV_VARS, update_env_file
from backend.models.schemas import SystemSettingsResponse, UpdateSettingsRequest
from backend.services.youtube import get_ytdlp_version, update_ytdlp_package

router = APIRouter(prefix="/api/settings", tags=["settings"])

def get_dir_size(path: Path) -> int:
    """Calculates total size in bytes of a directory."""
    if not path.exists():
        return 0
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total

@router.get("", response_model=SystemSettingsResponse)
def get_system_settings(db: sqlite3.Connection = Depends(get_db)):
    # Cookie browser setting from DB
    cookie_row = db.execute("SELECT value FROM system_settings WHERE key = 'cookies_browser';").fetchone()
    cookies_browser = cookie_row["value"] if cookie_row else None

    # Disk usage
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    transcripts_dir = DATA_DIR / "transcripts"
    screenshots_dir = DATA_DIR / "screenshots"

    transcripts_size = get_dir_size(transcripts_dir)
    screenshots_size = get_dir_size(screenshots_dir)

    # Key presence without leaking values
    has_gemini = bool(ENV_VARS.get("GEMINI_API_KEY"))
    has_groq = bool(ENV_VARS.get("GROQ_API_KEY"))
    has_openrouter = bool(ENV_VARS.get("OPENROUTER_API_KEY"))

    return SystemSettingsResponse(
        ytdlp_version=get_ytdlp_version(),
        cookies_browser=cookies_browser,
        timezone=TIMEZONE_STR,
        data_dir=str(DATA_DIR),
        db_size_bytes=db_size,
        transcripts_size_bytes=transcripts_size,
        screenshots_size_bytes=screenshots_size,
        has_gemini_key=has_gemini,
        has_groq_key=has_groq,
        has_openrouter_key=has_openrouter,
    )

@router.post("")
def update_settings(
    req: UpdateSettingsRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    if req.cookies_browser is not None:
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('cookies_browser', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (req.cookies_browser,),
        )
    return {"success": True, "message": "Settings updated successfully."}

@router.post("/update-ytdlp")
def update_ytdlp():
    """One-click update of yt-dlp to latest PyPI version."""
    result = update_ytdlp_package()
    return result

@router.post("/cleanup-cache")
def cleanup_cache():
    """Cleans cached transcripts and screenshots."""
    transcripts_dir = DATA_DIR / "transcripts"
    screenshots_dir = DATA_DIR / "screenshots"

    cleaned_bytes = 0
    for directory in [transcripts_dir, screenshots_dir]:
        if directory.exists():
            size = get_dir_size(directory)
            cleaned_bytes += size
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "cleaned_bytes": cleaned_bytes,
        "message": f"Cleaned {round(cleaned_bytes / (1024 * 1024), 2)} MB of cached media.",
    }

@router.post("/keys")
def update_api_keys(keys: Dict[str, str]):
    """Safely writes API keys into .env only (never in SQLite)."""
    allowed_keys = {"GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_BASE_URL"}
    filtered_updates = {k: v for k, v in keys.items() if k in allowed_keys}
    if filtered_updates:
        update_env_file(filtered_updates)
    return {"success": True, "message": "API keys updated securely in .env"}


@router.get("/backup")
def download_sqlite_backup():
    """One-click download of the raw SQLite database for offline backup and portability."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=str(DB_PATH),
        filename=f"learn_lms_backup_{ts}.db",
        media_type="application/vnd.sqlite3",
    )


@router.post("/vacuum")
def vacuum_database(db: sqlite3.Connection = Depends(get_db)):
    """Runs SQLite VACUUM to reclaim free space on disk."""
    try:
        db.execute("VACUUM;")
        db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        return {
            "success": True,
            "message": "Database vacuumed successfully.",
            "db_size_bytes": db_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VACUUM failed: {str(e)}")

