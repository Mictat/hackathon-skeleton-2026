from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ActorType, Asset, DataSource, Environment, ScanRun, SourceType
from app.services.audit import log_event
from app.services.scan import start_scan

router = APIRouter(prefix="/api")


class SourceCreate(BaseModel):
    name: str
    source_type: SourceType
    environment: Environment
    connection_ref: dict = {}
    notes: str | None = None


def run_dict(r: ScanRun) -> dict:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "status": r.status,
        "trigger": r.trigger,
        "stats": r.stats,
        "error": r.error,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def source_dict(db: Session, s: DataSource) -> dict:
    n = db.scalar(select(func.count()).select_from(Asset).where(Asset.source_id == s.id))
    last = db.scalar(select(ScanRun).where(ScanRun.source_id == s.id).order_by(ScanRun.id.desc()).limit(1))
    return {
        "id": s.id,
        "name": s.name,
        "source_type": s.source_type.value,
        "environment": s.environment.value,
        "status": s.status,
        "connection_ref": s.connection_ref,
        "notes": s.notes,
        "asset_count": n,
        "last_run": run_dict(last) if last else None,
    }


@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    if db.scalar(select(DataSource).where(DataSource.name == payload.name)):
        raise HTTPException(409, f"source '{payload.name}' already exists")
    s = DataSource(
        name=payload.name,
        source_type=payload.source_type,
        environment=payload.environment,
        connection_ref=payload.connection_ref,
        notes=payload.notes,
        status="registered",
    )
    db.add(s)
    db.flush()
    log_event(
        db,
        actor_type=ActorType.system,
        actor="api",
        event_type="source_registered",
        entity_type="data_source",
        entity_id=s.id,
        payload={"name": s.name, "type": s.source_type.value},
    )
    db.commit()
    return source_dict(db, s)


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    return [source_dict(db, s) for s in db.scalars(select(DataSource).order_by(DataSource.id))]


@router.post("/sources/{source_id}/scan", status_code=202)
def scan_source(source_id: int, db: Session = Depends(get_db)):
    if db.get(DataSource, source_id) is None:
        raise HTTPException(404, "source not found")
    run_id = start_scan(source_id)
    return {"run_id": run_id, "poll": f"/api/runs/{run_id}"}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ScanRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run_dict(run)
