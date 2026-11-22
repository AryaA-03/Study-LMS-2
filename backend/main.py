"""Main FastAPI application for Learn LMS & Exam Prep."""

import json
import time
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Configure Rich Terminal Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("learn_lms")

from backend.config import BASE_DIR
from backend.routers import (
    courses,
    schedule,
    settings,
    transcripts,
    notes,
    screenshots,
    sources,
    qa,
    quizzes,
    flashcards,
    pyq,
    cram_sheet,
)

app = FastAPI(
    title="Learn LMS & Exam Prep API",
    description="Local-first autonomous personal LMS and exam-prep platform.",
    version="0.6.0",
)

# Enable CORS for local client development (restricted to local origins, no invalid wildcard+credentials)
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
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logging Middleware for Terminal Observability
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        if not request.url.path.startswith("/static"):
            code = response.status_code
            if code < 300:
                status_badge = f"\033[92m[{code} OK]\033[0m"
            elif code < 400:
                status_badge = f"\033[94m[{code} REDIRECT]\033[0m"
            elif code < 500:
                status_badge = f"\033[93m[{code} CLIENT_ERR]\033[0m"
            else:
                status_badge = f"\033[91m[{code} SERVER_ERR]\033[0m"
            
            query = f"?{request.url.query}" if request.url.query else ""
            logger.info(f"{request.method} {request.url.path}{query} -> {status_badge} ({duration_ms}ms)")
        
        # Only no-cache API/HTML responses; let static assets benefit from HTTP caching
        if not request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        logger.error(f"\033[91m[EXCEPTION]\033[0m {request.method} {request.url.path} ({duration_ms}ms): {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(exc)}"})

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
def health_check():
    return {"status": "ok", "version": "0.6.0"}

def export_openapi_spec(output_path: Path = BASE_DIR / "openapi.json"):
    """Dumps locked OpenAPI specification to openapi.json."""
    spec = app.openapi()
    output_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec

if __name__ == "__main__":
    export_openapi_spec()
    print("Locked openapi.json generated successfully.")
