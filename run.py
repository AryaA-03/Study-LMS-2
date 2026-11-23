#!/usr/bin/env python3
"""Cross-platform launcher for Learn LMS & Exam Prep.

Sets up .venv, verifies dependencies, ensures ffmpeg is on PATH,
applies pending SQLite migrations, and starts the FastAPI server.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"

def get_venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def get_venv_bin_dir() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts"
    return VENV_DIR / "bin"

def ensure_venv():
    """Creates virtualenv if it does not exist."""
    if not VENV_DIR.exists():
        print("📦 Creating virtual environment (.venv)...")
        # Prefer python3.14 if available, otherwise current sys.executable
        py_exe = sys.executable
        if sys.platform == "darwin":
            for candidate in ["/opt/homebrew/bin/python3.14", "/usr/local/bin/python3.14"]:
                if Path(candidate).exists():
                    py_exe = candidate
                    break
        subprocess.check_call([py_exe, "-m", "venv", str(VENV_DIR)])
        print("✅ Virtual environment created.")

def run_in_venv():
    """Re-executes this launcher inside .venv if not already running in it."""
    venv_python = get_venv_python()
    if sys.executable != str(venv_python) and venv_python.exists():
        # Re-launch with venv python
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

def ensure_dependencies():
    """Installs required packages if missing."""
    venv_python = get_venv_python()
    req_file = BASE_DIR / "requirements.txt"
    try:
        import fastapi
        import uvicorn
        import pydantic
        import yt_dlp
        import imageio_ffmpeg
        import fsrs
        import httpx
    except ImportError:
        print("📥 Installing required dependencies from requirements.txt...")
        subprocess.check_call([str(venv_python), "-m", "pip", "install", "-r", str(req_file)])
        print("✅ Dependencies installed.")

def ensure_ffmpeg():
    """Ensures ffmpeg is available on PATH and in .venv/bin."""
    bin_dir = get_venv_bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_target = bin_dir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

    # Add bin_dir to process PATH
    os.environ["PATH"] = str(bin_dir) + os.path.pathsep + os.environ.get("PATH", "")

    if not ffmpeg_target.exists():
        # Check system ffmpeg first
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            try:
                os.symlink(system_ffmpeg, ffmpeg_target)
                print(f"🔗 Linked system ffmpeg to {ffmpeg_target}")
                return
            except Exception:
                pass

        # Use imageio-ffmpeg binary
        try:
            import imageio_ffmpeg
            src_exe = imageio_ffmpeg.get_ffmpeg_exe()
            if src_exe and Path(src_exe).exists():
                try:
                    os.symlink(src_exe, ffmpeg_target)
                    print(f"🔗 Linked imageio-ffmpeg binary to {ffmpeg_target}")
                except Exception:
                    shutil.copy2(src_exe, ffmpeg_target)
                    print(f"📋 Copied imageio-ffmpeg binary to {ffmpeg_target}")
        except Exception as e:
            print(f"⚠️ Warning: could not set up ffmpeg: {e}")

def run_migrations():
    """Applies pending database migrations."""
    print("🔄 Checking & running SQLite migrations...")
    from backend.migrations.runner import apply_migrations
    applied = apply_migrations()
    print(f"✅ Migrations up to date ({applied} new applied).")

def ensure_port_available(host: str = "127.0.0.1", port: int = 8000):
    """Checks if port is occupied by a stale server instance and terminates it."""
    import socket
    import time
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        is_busy = (s.connect_ex((host, port)) == 0)

    if is_busy:
        print(f"⚠️ Port {port} is currently occupied by a previous server process.")
        if sys.platform != "win32":
            try:
                out = subprocess.check_output(["lsof", "-ti", f":{port}"]).decode().strip()
                pids = [p.strip() for p in out.splitlines() if p.strip() and p.strip() != str(os.getpid())]
                for pid in pids:
                    print(f"❌ Port {port} is in use by PID {pid}. Run: kill {pid} (or set APP_PORT=8001 python run.py)")
                sys.exit(1)
            except Exception as e:
                print(f"⚠️ Could not auto-terminate process on port {port}: {e}")

def start_server():
    """Starts FastAPI server using Uvicorn."""
    import uvicorn
    from backend.config import APP_HOST, APP_PORT, APP_ENV

    ensure_port_available(APP_HOST, APP_PORT)
    reload = (APP_ENV == "development")
    print(f"🚀 Starting Learn LMS on http://{APP_HOST}:{APP_PORT} (Environment: {APP_ENV})...")
    uvicorn.run(
        "backend.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=reload,
        log_level="info",
    )

if __name__ == "__main__":
    ensure_venv()
    run_in_venv()
    ensure_dependencies()
    ensure_ffmpeg()
    run_migrations()
    start_server()
