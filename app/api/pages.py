from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Asset, DataSource, ScanRun
from app.services.scan import start_scan
from app.services.settings_svc import get_confidence_threshold

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter()


def _board_context(db: Session) -> dict:
    gov = dict(
        db.execute(select(Asset.governance_status, func.count(Asset.id)).group_by(Asset.governance_status)).all()
    )
    pipe = dict(db.execute(select(Asset.pipeline_status, func.count(Asset.id)).group_by(Asset.pipeline_status)).all())
    items = []
    for s in db.scalars(select(DataSource).order_by(DataSource.id)):
        last = db.scalar(select(ScanRun).where(ScanRun.source_id == s.id).order_by(ScanRun.id.desc()).limit(1))
        items.append({"s": s, "last": last})
    return {
        "gov_counts": {k.value: v for k, v in gov.items()},
        "pipe_counts": {k.value: v for k, v in pipe.items()},
        "sources": items,
        "threshold": get_confidence_threshold(db),
    }


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "index.html", _board_context(db))


@router.get("/pages/status-board")
def status_board(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "_status_board.html", _board_context(db))


@router.post("/pages/sources/{source_id}/scan")
def scan_source_page(source_id: int, request: Request, db: Session = Depends(get_db)):
    if db.get(DataSource, source_id) is None:
        raise HTTPException(404, "source not found")
    start_scan(source_id)
    return templates.TemplateResponse(request, "_status_board.html", _board_context(db))
