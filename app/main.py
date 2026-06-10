"""FastAPI app + routes.

Phase 0: boots with a health route and a base template so the scaffold is
demoable. Queue, dashboard, and detail routes arrive in later phases.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Payment-Integrity Claims Reviewer")


@app.get("/health")
def health() -> JSONResponse:
    """Liveness check used by the demo/reset flow and any future CI."""
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Landing page. Becomes the dashboard once detection + ROI land."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "Payment-Integrity Claims Reviewer",
            "tagline": "Rules detect · AI explains · a human decides",
        },
    )
