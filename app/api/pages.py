from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.templating import board_context, render
from app.db import get_db
from app.models import Asset, AuditEvent, DataSource, User
from app.services.scan import start_scan
from app.services.users_svc import COOKIE

router = APIRouter()

AUDIT_FILTERS = [
    ("%", "All events"),
    ("scan%", "Scans"),
    ("asset_discovered", "Discovery"),
    ("enrichment%", "Agent enrichment"),
    ("auto_accepted", "Auto-accepts"),
    ("triaged%", "Triage"),
    ("threshold%", "Threshold"),
    ("review%", "Human reviews"),
]


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "index.html", **board_context(db))


@router.get("/pages/status-board")
def status_board(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "_status_board.html", **board_context(db))


@router.post("/pages/sources/{source_id}/scan")
def scan_source_page(source_id: int, request: Request, db: Session = Depends(get_db)):
    if db.get(DataSource, source_id) is None:
        raise HTTPException(404, "source not found")
    start_scan(source_id)
    return render(request, db, "_status_board.html", **board_context(db))


@router.post("/pages/user")
def switch_user(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(404, "user not found")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, str(user_id))
    return resp


@router.get("/audit")
def audit_page(request: Request, filter: str = "%", db: Session = Depends(get_db)):
    q = select(AuditEvent)
    if filter != "%":
        q = q.where(AuditEvent.event_type.like(filter))
    events = db.scalars(q.order_by(AuditEvent.id.desc()).limit(300)).all()
    asset_ids = {e.entity_id for e in events if e.entity_type == "asset"}
    assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_(asset_ids)))} if asset_ids else {}
    return render(request, db, "audit.html", events=events, assets=assets, active_filter=filter, FILTERS=AUDIT_FILTERS)
