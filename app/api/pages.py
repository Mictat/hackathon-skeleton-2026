from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Asset, DataSource

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter()


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    status_counts = dict(
        db.execute(select(Asset.governance_status, func.count(Asset.id)).group_by(Asset.governance_status)).all()
    )
    sources = db.scalars(select(DataSource).order_by(DataSource.name)).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "status_counts": {k.value: v for k, v in status_counts.items()},
            "sources": sources,
        },
    )
