from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.templating import render
from app.db import get_db
from app.llm.prompts import DOMAINS
from app.models import Asset, AssetColumn, DataSource, Environment, GovernanceStatus, OrgPerson, Sensitivity
from app.services.settings_svc import get_confidence_threshold

router = APIRouter()

SENSITIVITIES = [s.value for s in Sensitivity]
ENVS = [e.value for e in Environment]
GOV_STATUSES = [g.value for g in GovernanceStatus]


def _truthy(v: str) -> bool:
    return v.lower() in ("on", "true", "1")


def build_query(
    q: str = "",
    domain: str = "",
    sensitivity: str = "",
    dept: str = "",
    source_id: int = 0,
    env: str = "",
    status: str = "",
    pii_only: bool = False,
    unowned: bool = False,
):
    stmt = select(Asset).options(selectinload(Asset.columns), selectinload(Asset.owner), selectinload(Asset.source))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Asset.full_path.ilike(like)
            | Asset.description.ilike(like)
            | Asset.columns.any(AssetColumn.name.ilike(like))
        )
    if domain:
        stmt = stmt.where(Asset.business_domain == domain)
    if sensitivity in SENSITIVITIES:
        stmt = stmt.where(Asset.sensitivity == Sensitivity(sensitivity))
    if dept:
        stmt = stmt.where(Asset.owner.has(OrgPerson.department == dept))
    if source_id:
        stmt = stmt.where(Asset.source_id == source_id)
    if env in ENVS:
        stmt = stmt.where(Asset.source.has(DataSource.environment == Environment(env)))
    if status in GOV_STATUSES:
        stmt = stmt.where(Asset.governance_status == GovernanceStatus(status))
    if pii_only:
        stmt = stmt.where(Asset.columns.any(AssetColumn.is_pii.is_(True)))
    if unowned:
        stmt = stmt.where(Asset.owner_person_id.is_(None))
    return stmt.order_by(Asset.full_path)


def _rows(db: Session, **filters):
    assets = db.scalars(build_query(**filters)).all()
    return [{"a": a, "pii_count": sum(1 for c in a.columns if c.is_pii)} for a in assets]


def _filter_options(db: Session) -> dict:
    return {
        "domains": [d for d in DOMAINS if d != "unknown"],
        "departments": sorted(
            x for x in db.scalars(select(OrgPerson.department).distinct().where(OrgPerson.department.is_not(None))) if x
        ),
        "sources": db.scalars(select(DataSource).order_by(DataSource.name)).all(),
        "environments": ENVS,
        "sensitivities": SENSITIVITIES,
        "gov_statuses": GOV_STATUSES,
    }


@router.get("/catalog")
def catalog_page(
    request: Request,
    q: str = "",
    domain: str = "",
    sensitivity: str = "",
    dept: str = "",
    source_id: int = 0,
    env: str = "",
    status: str = "",
    pii_only: str = "",
    unowned: str = "",
    db: Session = Depends(get_db),
):
    filters = {
        "q": q,
        "domain": domain,
        "sensitivity": sensitivity,
        "dept": dept,
        "source_id": source_id,
        "env": env,
        "status": status,
        "pii_only": _truthy(pii_only),
        "unowned": _truthy(unowned),
    }
    total = db.scalar(select(func.count()).select_from(Asset)) or 0
    with_pii = (
        db.scalar(select(func.count()).select_from(Asset).where(Asset.columns.any(AssetColumn.is_pii.is_(True)))) or 0
    )
    unowned_n = db.scalar(select(func.count()).select_from(Asset).where(Asset.owner_person_id.is_(None))) or 0
    return render(
        request,
        db,
        "catalog.html",
        rows=_rows(db, **filters),
        filters=filters,
        total=total,
        with_pii=with_pii,
        unowned_n=unowned_n,
        threshold=get_confidence_threshold(db),
        **_filter_options(db),
    )


@router.get("/api/catalog")
def api_catalog(
    q: str = "",
    domain: str = "",
    sensitivity: str = "",
    dept: str = "",
    source_id: int = 0,
    env: str = "",
    status: str = "",
    pii_only: str = "",
    unowned: str = "",
    db: Session = Depends(get_db),
):
    """The money query as an API — Cairn is a platform, not just a UI."""
    rows = _rows(
        db,
        q=q,
        domain=domain,
        sensitivity=sensitivity,
        dept=dept,
        source_id=source_id,
        env=env,
        status=status,
        pii_only=_truthy(pii_only),
        unowned=_truthy(unowned),
    )
    return [
        {
            "id": r["a"].id,
            "full_path": r["a"].full_path,
            "source": r["a"].source.name,
            "domain": r["a"].business_domain,
            "sensitivity": r["a"].sensitivity.value if r["a"].sensitivity else None,
            "owner": r["a"].owner.email if r["a"].owner else None,
            "pii_columns": r["pii_count"],
            "confidence": r["a"].overall_confidence,
            "governance_status": r["a"].governance_status.value,
        }
        for r in rows
    ]
