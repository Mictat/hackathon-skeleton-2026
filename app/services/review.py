from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActorType, Asset, GovernanceStatus, OrgPerson, Review, ReviewAction, Sensitivity, User
from app.services.audit import log_event
from app.services.proposals import apply_proposals, latest_results


class ReviewError(Exception):
    pass


def submit_review(
    db: Session, asset_id: int, reviewer: User, action: str, edits: dict | None = None, comment: str | None = None
) -> Asset:
    """The human half of the product. approve -> apply proposals as-is;
    edited -> proposals then human overrides; rejected -> no curated changes."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise ReviewError(f"asset {asset_id} not found")
    if asset.governance_status in (GovernanceStatus.approved, GovernanceStatus.rejected):
        raise ReviewError(f"asset {asset_id} is {asset.governance_status.value} — reopen first")
    action = ReviewAction(action)

    before = _snapshot(asset)
    if action in (ReviewAction.approved, ReviewAction.edited):
        apply_proposals(db, asset, latest_results(db, asset.id), applied_by=reviewer.email)
        if action == ReviewAction.edited:
            _apply_edits(db, asset, edits or {})

    asset.governance_status = (
        GovernanceStatus.approved
        if action in (ReviewAction.approved, ReviewAction.edited)
        else GovernanceStatus.rejected
    )
    asset.reviewed_by_user_id = reviewer.id
    asset.reviewed_at = datetime.now(timezone.utc)
    if asset.steward_user_id is None:
        asset.steward_user_id = reviewer.id

    after = _snapshot(asset)
    changes = {k: {"before": before.get(k), "after": after[k]} for k in after if before.get(k) != after.get(k)}
    db.add(Review(asset_id=asset.id, reviewer_user_id=reviewer.id, action=action, changes=changes, comment=comment))
    log_event(
        db,
        actor_type=ActorType.human,
        actor=reviewer.email,
        event_type=f"review_{action.value}",
        entity_type="asset",
        entity_id=asset.id,
        payload={"changes": changes, "comment": comment or ""},
    )
    db.commit()
    db.refresh(asset)
    return asset


def reopen_asset(db: Session, asset_id: int, reviewer: User, comment: str | None = None) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise ReviewError("asset not found")
    asset.governance_status = GovernanceStatus.pending_review
    asset.reviewed_by_user_id = reviewer.id
    asset.reviewed_at = datetime.now(timezone.utc)
    db.add(
        Review(
            asset_id=asset.id, reviewer_user_id=reviewer.id, action=ReviewAction.reopened, changes={}, comment=comment
        )
    )
    log_event(
        db,
        actor_type=ActorType.human,
        actor=reviewer.email,
        event_type="review_reopened",
        entity_type="asset",
        entity_id=asset.id,
        payload={"comment": comment or ""},
    )
    db.commit()
    return asset


def _apply_edits(db: Session, asset: Asset, edits: dict) -> None:
    """Human overrides, applied AFTER proposals — last word belongs to the human."""
    if edits.get("description"):
        asset.description = edits["description"].strip()
    if edits.get("business_domain"):
        asset.business_domain = edits["business_domain"].strip().lower()
    if edits.get("sensitivity") in {s.value for s in Sensitivity}:
        asset.sensitivity = Sensitivity(edits["sensitivity"])
    if edits.get("owner_email"):
        person = db.scalar(select(OrgPerson).where(OrgPerson.email == edits["owner_email"]))
        if person:
            asset.owner_person_id = person.id


def _snapshot(asset: Asset) -> dict:
    snap = {
        "description": asset.description,
        "business_domain": asset.business_domain,
        "sensitivity": asset.sensitivity.value if asset.sensitivity else None,
        "owner_person_id": asset.owner_person_id,
    }
    for c in asset.columns:
        if c.is_pii or c.is_key_attribute:
            snap[f"col.{c.name}"] = {"pii": c.is_pii, "pii_type": c.pii_type, "key": c.is_key_attribute}
    return snap
