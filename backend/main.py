"""Main FastAPI application for Learn LMS & Exam Prep."""

import json
import logging
import time
import uuid
from pathlib import Path
import sqlite3
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure Rich Terminal Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("learn_lms")

from backend.config import BASE_DIR
from backend.database import get_db
from backend.routers import (
    courses,
    cram_sheet,
    flashcards,
    jobs,
    notes,
    pyq,
    qa,
    quizzes,
    schedule,
    screenshots,
    settings,
    sources,
    transcripts,
)

app = FastAPI(
    title="Learn LMS & Exam Prep API",
    description="Local-first autonomous personal LMS and exam-prep platform.",
    version="0.8.0",
)

# Restrict CORS to explicit local origins and methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:8008",
        "http://127.0.0.1:8008",
        "http://localhost:7860",
        "http://127.0.0.1:7860",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        if not request.url.path.startswith("/static"):
            code = response.status_code
            query = f"?{request.url.query}" if request.url.query else ""
            logger.info(f"{request.method} {request.url.path}{query} -> [{code}] ({duration_ms}ms)")

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if not request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        error_id = uuid.uuid4().hex[:12]
        logger.error(
            f"[EXCEPTION error_id={error_id}] {request.method} {request.url.path} ({duration_ms}ms): {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error (ref: {error_id})", "error_id": error_id},
        )


# Include Routers
app.include_router(courses.router)
app.include_router(schedule.router)
app.include_router(settings.router)
app.include_router(transcripts.router)
app.include_router(notes.router)
app.include_router(screenshots.router)
app.include_router(sources.router)
app.include_router(qa.router)
app.include_router(quizzes.router)
app.include_router(flashcards.router)
app.include_router(jobs.router)
app.include_router(pyq.router)
app.include_router(cram_sheet.router)

# Mount Static Assets & Templates
STATIC_DIR = BASE_DIR / "frontend" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    """Renders main single-page application shell."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/healthz")
def health_check(db: sqlite3.Connection = Depends(get_db)):
    """Verifies database connectivity and reports active schema version."""
    try:
        db.execute("SELECT 1;").fetchone()
        schema_version = 0
        try:
            row = db.execute("SELECT MAX(version) FROM schema_migrations;").fetchone()
            schema_version = int(row[0]) if (row and row[0] is not None) else 0
        except sqlite3.OperationalError:
            schema_version = 0
        return {"status": "ok", "db": "ok", "version": "0.8.0", "schema_version": schema_version}
    except Exception as exc:
        logger.error(f"Health check DB failure: {exc}")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error", "version": "0.8.0"},
        )


def export_openapi_spec(output_path: Path = BASE_DIR / "openapi.json"):
    """Dumps locked OpenAPI specification to openapi.json."""
    spec = app.openapi()
    output_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec


if __name__ == "__main__":
    export_openapi_spec()
    print("Locked openapi.json generated successfully.")
