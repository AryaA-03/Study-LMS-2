"""Main FastAPI application for Learn LMS & Exam Prep."""

import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import BASE_DIR
from backend.routers import courses, schedule, settings

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

# Include Routers
app.include_router(courses.router)
app.include_router(schedule.router)
app.include_router(settings.router)

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
