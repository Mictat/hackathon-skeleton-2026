from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.templating import board_context, render
from app.connectors import MOCK_TYPES, ConnectorNotAvailable, get_connector
from app.db import get_db
from app.models import Asset, AuditEvent, DataSource, User
from app.models.enums import ActorType, Environment, PipelineStatus, SourceType
from app.models.pipeline import EnrichmentResult, ScanRun
from app.services.audit import log_event
from app.services.scan import start_scan
from app.services.users_svc import COOKIE, current_user

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


def _run_context(db: Session, run_id: int) -> dict | None:
    run = db.get(ScanRun, run_id)
    if run is None:
        return None
    source = db.get(DataSource, run.source_id)
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.run_id == run_id).order_by(AuditEvent.id.desc()).limit(40)
    ).all()
    enriching = db.scalars(
        select(Asset).where(Asset.source_id == run.source_id, Asset.pipeline_status == PipelineStatus.enriching)
    ).all()
    agent_rows = db.execute(
        select(EnrichmentResult.agent_name, func.count(), func.avg(EnrichmentResult.confidence))
        .where(EnrichmentResult.scan_id == run_id)
        .group_by(EnrichmentResult.agent_name)
    ).all()
    assets = {a.id: a for a in db.scalars(select(Asset))}
    return {
        "run": run,
        "source": source,
        "events": events,
        "assets": assets,
        "enriching": enriching,
        "agent_rows": [
            {"name": r[0], "calls": r[1], "avg_conf": round(float(r[2]), 3) if r[2] is not None else None}
            for r in agent_rows
        ],
    }


@router.get("/runs/{run_id}")
def run_page(request: Request, run_id: int, db: Session = Depends(get_db)):
    ctx = _run_context(db, run_id)
    if ctx is None:
        raise HTTPException(404, "run not found")
    return render(request, db, "run_detail.html", **ctx)


@router.get("/pages/runs/{run_id}")
def run_partial(request: Request, run_id: int, db: Session = Depends(get_db)):
    ctx = _run_context(db, run_id)
    if ctx is None:
        raise HTTPException(404, "run not found")
    return render(request, db, "_run_detail.html", **ctx)


@router.get("/sources/new")
def source_new_page(request: Request, flash: str = "", db: Session = Depends(get_db)):
    return render(request, db, "source_new.html", flash=flash)


@router.post("/pages/sources")
def create_source_page(
    request: Request,
    name: str = Form(...),
    source_type: str = Form(...),
    environment: str = Form("development"),
    host: str = Form("localhost"),
    port: int = Form(5433),
    database: str = Form(""),
    user: str = Form(""),
    password_env: str = Form("BANK_SAMPLE_PASSWORD"),
    root: str = Form("data/file_share"),
    db: Session = Depends(get_db),
):
    try:
        st = SourceType(source_type)
        env = Environment(environment)
    except ValueError:
        return RedirectResponse("/sources/new?flash=" + quote("invalid type or environment"), 303)
    if db.scalar(select(DataSource).where(DataSource.name == name)):
        return RedirectResponse("/sources/new?flash=" + quote(f"'{name}' already exists"), 303)

    if st in MOCK_TYPES:
        src = DataSource(
            name=name,
            source_type=st,
            environment=env,
            connection_ref={},
            status="mock",
            notes="Registered for tracking — connector on the roadmap",
        )
        flash = "registered (roadmap connector — tracked, not yet scannable)"
    else:
        ref = (
            {"root": root}
            if st == SourceType.file
            else {"host": host, "port": port, "database": database, "user": user, "password_env": password_env}
        )
        src = DataSource(name=name, source_type=st, environment=env, connection_ref=ref, status="registered")
        db.flush()
        try:
            ok, detail = get_connector(src).test_connection()
            src.status = "connected" if ok else "error"
            flash = "registered and connected" if ok else f"registered, but connection failed: {detail[:120]}"
        except ConnectorNotAvailable as e:
            flash = f"registered — {e}"
    db.add(src)
    db.flush()
    log_event(
        db,
        actor_type=ActorType.system,
        actor=current_user(db, request).email,
        event_type="source_registered",
        entity_type="data_source",
        entity_id=src.id,
        payload={"name": name, "type": st.value},
    )
    db.commit()
    return RedirectResponse(f"/?flash={quote(flash)}", 303)
