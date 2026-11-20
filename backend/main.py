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
from backend.routers import courses, schedule, settings, transcripts, notes, screenshots, sources, qa

app = FastAPI(
    title="Learn LMS & Exam Prep API",
    description="Local-first autonomous personal LMS and exam-prep platform.",
    version="0.1.0",
)

# Enable CORS for local client development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logging Middleware for Terminal Observability
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 1)
    # Don't clutter with static asset polling
    if not request.url.path.startswith("/static"):
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response

# Include Routers
app.include_router(courses.router)
app.include_router(schedule.router)
app.include_router(settings.router)
app.include_router(transcripts.router)
app.include_router(notes.router)
app.include_router(screenshots.router)
app.include_router(sources.router)
app.include_router(qa.router)

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
    return {"status": "ok", "version": "0.1.0"}

def export_openapi_spec(output_path: Path = BASE_DIR / "openapi.json"):
    """Dumps locked OpenAPI specification to openapi.json."""
    spec = app.openapi()
    output_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec

if __name__ == "__main__":
    export_openapi_spec()
    print("Locked openapi.json generated successfully.")
