import os
import tempfile
from starlette.background import BackgroundTask
from backend.infra.net_guard import validate_ollama_url
from backend.migrations.runner import create_verified_online_backup
"""System settings, yt-dlp maintenance, and storage guard router."""

import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from backend.database import get_db
from backend.config import DATA_DIR, DB_PATH, TIMEZONE_STR, ENV_VARS, update_env_file
import json
from backend.models.schemas import SystemSettingsResponse, UpdateSettingsRequest, TestConnectionRequest, TestConnectionResponse
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
    has_ollama = bool(ENV_VARS.get("OLLAMA_BASE_URL"))

    # Configurable defaults from DB
    def get_setting(key: str, default: Any) -> Any:
        row = db.execute("SELECT value FROM system_settings WHERE key = ?;", (key,)).fetchone()
        return row["value"] if row else default

    min_day = int(get_setting("pref_minutes_per_day", 90))
    speed = float(get_setting("pref_playback_speed", 1.25))
    rest_days_raw = get_setting("pref_rest_days", '["Sunday"]')
    try:
        rest_days = json.loads(rest_days_raw) if isinstance(rest_days_raw, str) else ["Sunday"]
    except Exception:
        rest_days = ["Sunday"]
    buffer_days = int(get_setting("pref_revision_buffer_days", 2))

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
        has_ollama=has_ollama,
        gemini_model=ENV_VARS.get("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_model=ENV_VARS.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        openrouter_model=ENV_VARS.get("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
        openrouter_base_url=ENV_VARS.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        ollama_base_url=ENV_VARS.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=ENV_VARS.get("OLLAMA_MODEL", "llama3.2"),
        default_minutes_per_day=min_day,
        default_playback_speed=speed,
        default_rest_days=rest_days,
        default_revision_buffer_days=buffer_days,
    )

@router.post("")
def update_settings(
    req: UpdateSettingsRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    if req.cookies_browser is not None:
        if req.cookies_browser not in ("", "chrome", "firefox", "safari", "edge", "brave", "chromium"):
            raise HTTPException(status_code=422, detail="Unsupported cookies_browser value.")
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('cookies_browser', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (req.cookies_browser,),
        )
    if req.minutes_per_day is not None:
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('pref_minutes_per_day', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (str(req.minutes_per_day),),
        )
    if req.playback_speed is not None:
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('pref_playback_speed', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (str(req.playback_speed),),
        )
    if req.rest_days is not None:
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('pref_rest_days', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (json.dumps(req.rest_days),),
        )
    if req.revision_buffer_days is not None:
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('pref_revision_buffer_days', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (str(req.revision_buffer_days),),
        )

    # Model and Base URL updates in .env
    env_updates = {}
    if req.gemini_model: env_updates["GEMINI_MODEL"] = req.gemini_model
    if req.groq_model: env_updates["GROQ_MODEL"] = req.groq_model
    if req.openrouter_model: env_updates["OPENROUTER_MODEL"] = req.openrouter_model
    if req.openrouter_base_url: env_updates["OPENROUTER_BASE_URL"] = req.openrouter_base_url
    if req.ollama_base_url: env_updates["OLLAMA_BASE_URL"] = req.ollama_base_url
    if req.ollama_model: env_updates["OLLAMA_MODEL"] = req.ollama_model
    if env_updates:
        try:
            update_env_file(env_updates)
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))

    return {"success": True, "message": "Settings updated successfully."}

@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(req: TestConnectionRequest):
    """Tests real connectivity to the configured LLM provider by making a lightweight HTTP call."""
    provider = req.provider.lower()

    if provider == "gemini":
        key = req.api_key or ENV_VARS.get("GEMINI_API_KEY")
        if not key:
            return TestConnectionResponse(
                success=False, provider="gemini",
                message="Google Gemini API Key is missing.",
                guide="1. Visit Google AI Studio: https://aistudio.google.com/app/apikey\n2. Create a free API key.\n3. Paste the key above and save."
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": key}
                )
                if r.status_code == 200:
                    return TestConnectionResponse(
                        success=True, provider="gemini",
                        message=f"Connection verified: Google Gemini API responded successfully ({req.model or 'gemini-2.5-flash'} ready)."
                    )
                elif r.status_code == 400:
                    return TestConnectionResponse(
                        success=False, provider="gemini",
                        message=f"Gemini API key is invalid or malformed (HTTP 400).",
                        guide="Check your key at https://aistudio.google.com/app/apikey"
                    )
                else:
                    return TestConnectionResponse(
                        success=False, provider="gemini",
                        message=f"Gemini API returned HTTP {r.status_code}. Check your key or quota.",
                    )
        except Exception as e:
            return TestConnectionResponse(
                success=False, provider="gemini",
                message=f"Could not reach Gemini API: {e}",
                guide="Check your internet connection and API key."
            )

    elif provider == "groq":
        key = req.api_key or ENV_VARS.get("GROQ_API_KEY")
        if not key:
            return TestConnectionResponse(
                success=False, provider="groq",
                message="Groq API Key is missing.",
                guide="1. Go to Groq Console: https://console.groq.com/keys\n2. Generate an API key.\n3. Paste the key in the Groq field and save."
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if r.status_code == 200:
                    return TestConnectionResponse(
                        success=True, provider="groq",
                        message=f"Connection verified: Groq API responded successfully ({req.model or 'llama-3.3-70b-versatile'} ready)."
                    )
                else:
                    return TestConnectionResponse(
                        success=False, provider="groq",
                        message=f"Groq API returned HTTP {r.status_code}. Check your API key.",
                    )
        except Exception as e:
            return TestConnectionResponse(
                success=False, provider="groq",
                message=f"Could not reach Groq API: {e}",
            )

    elif provider == "openrouter":
        key = req.api_key or ENV_VARS.get("OPENROUTER_API_KEY")
        if not key:
            return TestConnectionResponse(
                success=False, provider="openrouter",
                message="OpenRouter API Key is missing.",
                guide="1. Create an API key at https://openrouter.ai/keys\n2. Paste it in the OpenRouter key field and save."
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if r.status_code == 200:
                    return TestConnectionResponse(
                        success=True, provider="openrouter",
                        message=f"Connection verified: OpenRouter API responded successfully ({req.model or 'google/gemini-2.5-flash'} available)."
                    )
                else:
                    return TestConnectionResponse(
                        success=False, provider="openrouter",
                        message=f"OpenRouter returned HTTP {r.status_code}. Check your API key.",
                    )
        except Exception as e:
            return TestConnectionResponse(
                success=False, provider="openrouter",
                message=f"Could not reach OpenRouter: {e}",
            )

    elif provider == "ollama":
        raw_ollama = req.base_url or ENV_VARS.get("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            base_url = validate_ollama_url(raw_ollama)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{base_url.rstrip('/')}/api/tags")
                if r.status_code == 200:
                    return TestConnectionResponse(
                        success=True, provider="ollama",
                        message=f"Connection verified: Ollama is running at {base_url}."
                    )
        except Exception:
            pass
        return TestConnectionResponse(
            success=False, provider="ollama",
            message=f"Could not connect to Ollama at {base_url}.",
            guide="1. Download Ollama from https://ollama.com\n2. Run 'ollama run llama3.2' in your terminal.\n3. Verify Ollama responds on http://localhost:11434."
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

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
    """Safely writes API keys and LLM model presets into .env only (never in SQLite)."""
    allowed_keys = {
        "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
        "OLLAMA_BASE_URL", "GEMINI_MODEL", "GROQ_MODEL",
        "OPENROUTER_MODEL", "OPENROUTER_BASE_URL", "OLLAMA_MODEL"
    }
    filtered_updates = {k: v for k, v in keys.items() if k in allowed_keys}
    if filtered_updates:
        try:
            update_env_file(filtered_updates)
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))
    return {"success": True, "message": "API keys and model configurations updated securely in .env"}


@router.get("/backup")
def download_sqlite_backup(request: Request):
    """One-click download of the raw SQLite database for offline backup and portability.
    
    Restricted to localhost only to prevent unintentional LAN DB exfiltration.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(
            status_code=403,
            detail="Database backup is only accessible from localhost."
        )
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_fd, tmp_backup = tempfile.mkstemp(prefix="learn_lms_backup_", suffix=".db")
    os.close(tmp_fd)
    create_verified_online_backup(DB_PATH, Path(tmp_backup))
    return FileResponse(
        path=tmp_backup,
        filename=f"learn_lms_backup_{ts}.db",
        media_type="application/vnd.sqlite3",
        background=BackgroundTask(lambda p=tmp_backup: os.path.exists(p) and os.unlink(p)),
    )


@router.post("/vacuum")
def vacuum_database(db: sqlite3.Connection = Depends(get_db)):
    """Runs SQLite VACUUM to reclaim free space on disk."""
    try:
        vconn = sqlite3.connect(str(DB_PATH), isolation_level=None, timeout=60.0)
        try:
            vconn.execute("VACUUM;")
        finally:
            vconn.close()
        db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        return {
            "success": True,
            "message": "Database vacuumed successfully.",
            "db_size_bytes": db_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VACUUM failed: {str(e)}")



@router.post("/restore")
async def restore_sqlite_backup(request: Request, file: UploadFile = File(...)):
    """Localhost-only validated SQLite database restore with automatic pre-restore backup."""
    from backend.migrations.runner import backup_db_before_migration, get_current_schema_version

    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Database restore is only accessible from localhost.")

    data = await file.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup file exceeds 100 MB limit.")
    if not data.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid SQLite 3 database.")

    tmp_fd, tmp_path = tempfile.mkstemp(prefix="restore_candidate_", suffix=".db")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
        check_conn = sqlite3.connect(tmp_path)
        try:
            res = check_conn.execute("PRAGMA integrity_check;").fetchone()
            if not res or res[0] != "ok":
                raise HTTPException(status_code=400, detail="Uploaded SQLite backup failed integrity check.")
        finally:
            check_conn.close()

        if DB_PATH.exists():
            cur_conn = sqlite3.connect(str(DB_PATH))
            try:
                ver = get_current_schema_version(cur_conn)
            finally:
                cur_conn.close()
            backup_db_before_migration(DB_PATH, ver)

        create_verified_online_backup(Path(tmp_path), DB_PATH)
        return {"success": True, "message": "Database restored and verified successfully."}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
