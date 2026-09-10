from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, DataSource, GovernanceStatus, ScanRun, User
from app.services.settings_svc import get_confidence_threshold
from app.services.users_svc import current_user

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def base_context(db: Session, request: Request) -> dict:
    review_count = (
        db.scalar(
            select(func.count()).select_from(Asset).where(Asset.governance_status == GovernanceStatus.pending_review)
        )
        or 0
    )
    return {
        "request": request,
        "review_count": review_count,
        "users": db.scalars(select(User).order_by(User.id)).all(),
        "user": current_user(db, request),
        "is_htmx": request.headers.get("hx-request") == "true",
    }


def board_context(db: Session) -> dict:
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


def render(request: Request, db: Session, template: str, **extra):
    ctx = base_context(db, request)
    ctx.update(extra)
    return templates.TemplateResponse(request, template, ctx)
