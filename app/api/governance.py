from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.templating import board_context, render
from app.db import get_db
from app.models import ActorType, Asset, DataSource, GovernanceStatus, OrgPerson, Review, User
from app.services.audit import log_event
from app.services.proposals import latest_results
from app.services.review import ReviewError, reopen_asset, submit_review
from app.services.settings_svc import clamp_threshold, get_confidence_threshold, set_confidence_threshold
from app.services.triage import apply_triage
from app.services.users_svc import current_user

router = APIRouter()

TABS = [
    ("pending_review", "Needs review"),
    ("auto_accepted", "Auto-accepted"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


def _queue_rows(db: Session, status: str) -> list[dict]:
    assets = db.scalars(
        select(Asset)
        .where(Asset.governance_status == GovernanceStatus(status))
        .order_by(Asset.overall_confidence.asc().nulls_last(), Asset.id)
    ).all()
    src_names = {s.id: s.name for s in db.scalars(select(DataSource))}
    rows = []
    for a in assets:
        results = latest_results(db, a.id)
        cls = results["classification"].result if "classification" in results else {}
        own = results["ownership"].result if "ownership" in results else {}
        dsc = results["description"].result if "description" in results else {}
        parts = []
        if cls.get("asset_sensitivity"):
            parts.append(cls["asset_sensitivity"])
        if own.get("business_domain"):
            parts.append(own["business_domain"])
        if (own.get("owner_candidates") or [{}])[0].get("email"):
            parts.append(own["owner_candidates"][0]["email"])
        if dsc.get("description"):
            parts.append(dsc["description"][:80] + ("…" if len(dsc["description"]) > 80 else ""))
        rows.append(
            {
                "asset": a,
                "source_name": src_names.get(a.source_id, "?"),
                "proposed_summary": " · ".join(parts) or "no proposals",
                "pii_count": sum(1 for c in cls.get("columns", []) if c.get("is_pii")),
            }
        )
    return rows


# ---------- pages ----------


@router.get("/review")
def review_page(request: Request, status: str = "pending_review", flash: str = "", db: Session = Depends(get_db)):
    if status not in dict(TABS):
        status = "pending_review"
    return render(request, db, "review_queue.html", tabs=TABS, status=status, rows=_queue_rows(db, status), flash=flash)


@router.get("/pages/review-queue")
def review_queue_partial(
    request: Request, status: str = "pending_review", flash: str = "", db: Session = Depends(get_db)
):
    if status not in dict(TABS):
        status = "pending_review"
    return render(request, db, "_review_queue_table.html", status=status, rows=_queue_rows(db, status), flash=flash)


@router.get("/assets/{asset_id}")
def asset_detail(request: Request, asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    results = latest_results(db, asset_id)
    cls = results["classification"].result if "classification" in results else {}
    own = results["ownership"].result if "ownership" in results else {}
    dsc = results["description"].result if "description" in results else {}
    top_owner = (own.get("owner_candidates") or [{}])[0]
    owner = db.get(OrgPerson, asset.owner_person_id) if asset.owner_person_id else None
    user_map = {u.id: u.name for u in db.scalars(select(User))}
    reviews = [
        {"rv": rv, "reviewer_name": user_map.get(rv.reviewer_user_id, "?")}
        for rv in db.scalars(select(Review).where(Review.asset_id == asset_id).order_by(Review.id.desc()))
    ]
    prefill = {
        "description": asset.description or dsc.get("description") or "",
        "domain": asset.business_domain or own.get("business_domain") or "",
        "sensitivity": (asset.sensitivity.value if asset.sensitivity else cls.get("asset_sensitivity") or ""),
        "owner_email": (owner.email if owner else top_owner.get("email") or ""),
    }
    return render(
        request,
        db,
        "asset_detail.html",
        asset=asset,
        source=db.get(DataSource, asset.source_id),
        results=results,
        people=db.scalars(select(OrgPerson).where(OrgPerson.active).order_by(OrgPerson.full_name)).all(),
        owner=owner,
        steward=db.get(User, asset.steward_user_id) if asset.steward_user_id else None,
        reviewer=(db.get(User, asset.reviewed_by_user_id) if asset.reviewed_by_user_id else None),
        reviews=reviews,
        prefill=prefill,
        threshold=get_confidence_threshold(db),
    )


# ---------- form actions ----------


@router.post("/assets/{asset_id}/review")
def asset_review_submit(
    asset_id: int,
    request: Request,
    action: str = Form(...),
    description: str = Form(""),
    business_domain: str = Form(""),
    sensitivity: str = Form(""),
    owner_email: str = Form(""),
    comment: str = Form(""),
    db: Session = Depends(get_db),
):
    reviewer = current_user(db, request)
    edits = {
        "description": description,
        "business_domain": business_domain,
        "sensitivity": sensitivity,
        "owner_email": owner_email,
    }
    try:
        submit_review(db, asset_id, reviewer, action, edits if action == "edited" else None, comment or None)
    except ReviewError as e:
        raise HTTPException(409, str(e))
    return RedirectResponse(f"/review?flash={quote(action)}", status_code=303)


@router.post("/review/{asset_id}/quick-approve")
def quick_approve(asset_id: int, request: Request, db: Session = Depends(get_db)):
    reviewer = current_user(db, request)
    try:
        submit_review(db, asset_id, reviewer, "approved", None, "Quick-approved from review queue")
    except ReviewError as e:
        raise HTTPException(409, str(e))
    return render(
        request,
        db,
        "_review_queue_table.html",
        status="pending_review",
        rows=_queue_rows(db, "pending_review"),
        flash=f"Approved asset #{asset_id} as proposed",
    )


@router.post("/assets/{asset_id}/reopen")
def reopen(asset_id: int, request: Request, comment: str = Form(""), db: Session = Depends(get_db)):
    try:
        reopen_asset(db, asset_id, current_user(db, request), comment or None)
    except ReviewError as e:
        raise HTTPException(409, str(e))
    return RedirectResponse(f"/assets/{asset_id}", status_code=303)


@router.post("/settings/threshold")
def set_threshold(request: Request, threshold: float = Form(...), db: Session = Depends(get_db)):
    print("threshold change called...")
    user = current_user(db, request)
    before = get_confidence_threshold(db)
    value = clamp_threshold(threshold)
    print(f"threshold change value: {value}")
    set_confidence_threshold(db, value, updated_by=user.email)
    print("applying triage...")
    stats = apply_triage(db)  # instant re-triage: no re-scan, no LLM calls
    print("finished triage")
    log_event(
        db,
        actor_type=ActorType.human,
        actor=user.email,
        event_type="threshold_changed",
        payload={"before": before, "after": value, **stats},
    )
    db.commit()
    return render(request, db, "_board.html", **board_context(db))


# ---------- JSON API (platform story + scriptable demos) ----------


class ReviewBody(BaseModel):
    action: str
    description: str | None = None
    business_domain: str | None = None
    sensitivity: str | None = None
    owner_email: str | None = None
    comment: str | None = None
    reviewer_email: str | None = None


@router.post("/api/assets/{asset_id}/review")
def api_review(asset_id: int, body: ReviewBody, db: Session = Depends(get_db)):
    reviewer = db.scalar(select(User).where(User.email == (body.reviewer_email or "s.chen@bank.example")))
    if reviewer is None:
        raise HTTPException(400, f"unknown reviewer_email: {body.reviewer_email}")
    try:
        asset = submit_review(
            db,
            asset_id,
            reviewer,
            body.action,
            body.model_dump(exclude={"action", "comment", "reviewer_email"}, exclude_none=True)
            if body.action == "edited"
            else None,
            body.comment,
        )
    except ReviewError as e:
        raise HTTPException(409, str(e))
    return {"asset_id": asset.id, "governance_status": asset.governance_status.value, "reviewer": reviewer.email}


class ThresholdBody(BaseModel):
    value: float


@router.post("/api/settings/threshold")
def api_threshold(body: ThresholdBody, db: Session = Depends(get_db)):
    before = get_confidence_threshold(db)
    value = clamp_threshold(body.value)
    set_confidence_threshold(db, value, updated_by="api")
    stats = apply_triage(db)
    return {"before": before, "after": value, **stats}


@router.get("/api/review-queue")
def api_queue(status: str = "pending_review", db: Session = Depends(get_db)):
    return [
        {
            "id": r["asset"].id,
            "full_path": r["asset"].full_path,
            "confidence": r["asset"].overall_confidence,
            "source": r["source_name"],
            "proposed": r["proposed_summary"],
            "pii_columns": r["pii_count"],
        }
        for r in _queue_rows(db, status)
    ]
