"""FastAPI app + routes.

Dashboard (estimated $ identified, labeled an estimate), the reviewer queue, the
per-flag detail (claim + triggering rule/fields + explanation), and the decision
endpoint that stores each approve/dismiss/escalate as a label.
"""
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import dashboard
from app.models import connect, init_db

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Payment-Integrity Claims Reviewer")

TITLE = "Payment-Integrity Claims Reviewer"
TAGLINE = "Rules detect · AI explains · a human decides"


def _conn():
    """Connection with the schema ensured, so a fresh DB renders empty states
    instead of a 500 ('no such table') before `make seed` has ever run."""
    conn = connect()
    init_db(conn)
    return conn


def _ctx(request: Request, **extra) -> dict:
    return {"request": request, "title": TITLE, "tagline": TAGLINE, **extra}


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    conn = _conn()
    summary = dashboard.summary(conn)
    conn.close()
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request, **summary))


@app.get("/queue", response_class=HTMLResponse)
def queue(request: Request) -> HTMLResponse:
    conn = _conn()
    items = dashboard.review_items(conn)
    conn.close()
    return templates.TemplateResponse(request, "queue.html", _ctx(request, items=items))


@app.get("/flag/{flag_id}", response_class=HTMLResponse)
def flag_detail(request: Request, flag_id: int):
    conn = _conn()
    detail = dashboard.flag_detail(conn, flag_id)
    conn.close()
    if detail is None:
        return HTMLResponse("Flag not found", status_code=404)
    return templates.TemplateResponse(request, "flag_detail.html", _ctx(request, **detail))


@app.post("/flag/{flag_id}/decision")
def decide(
    flag_id: int,
    action: str = Form(...),
    reviewer: str = Form("reviewer"),
    note: str = Form(""),
):
    conn = _conn()
    detail = dashboard.flag_detail(conn, flag_id)
    if detail is None:
        conn.close()
        return HTMLResponse("Flag not found", status_code=404)
    dashboard.record_decision(conn, flag_id, action, reviewer.strip() or "reviewer", note.strip())
    conn.close()
    # Back to the queue so the reviewer moves to the next flag; dashboard recomputes on load.
    return RedirectResponse(url="/queue", status_code=303)
