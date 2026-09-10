from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, EnrichmentResult, OrgPerson, Sensitivity


def latest_results(db: Session, asset_id: int) -> dict[str, EnrichmentResult]:
    """Latest enrichment result per agent (last row wins — survives re-scans)."""
    latest: dict[str, EnrichmentResult] = {}
    for r in db.scalars(
        select(EnrichmentResult).where(EnrichmentResult.asset_id == asset_id).order_by(EnrichmentResult.id)
    ):
        latest[r.agent_name] = r
    return latest


def apply_proposals(db: Session, asset: Asset, results: dict[str, EnrichmentResult], applied_by: str) -> dict:
    """Copy agent proposals -> curated fields. Returns {field: {before, after}}
    for the review record and audit. Agents with no result are simply skipped."""

    def _plain(v):
        return v.value if hasattr(v, "value") else v

    changes: dict = {}

    def set_field(obj, field, new, label):
        old = getattr(obj, field)
        if new is not None and old != new:
            setattr(obj, field, new)
            changes[label] = {"before": _plain(old), "after": _plain(new)}

    cls = results.get("classification")
    if cls:
        p = cls.result
        if p.get("asset_sensitivity"):
            try:
                set_field(asset, "sensitivity", Sensitivity(p["asset_sensitivity"]), "sensitivity")
            except ValueError:
                pass
        colrows = {c["name"]: c for c in p.get("columns", []) if isinstance(c, dict)}
        for col in asset.columns:
            cc = colrows.get(col.name)
            if not cc:
                continue
            set_field(col, "is_pii", bool(cc.get("is_pii")), f"col.{col.name}.is_pii")
            set_field(col, "pii_type", cc.get("pii_type"), f"col.{col.name}.pii_type")
            set_field(col, "pii_confidence", cc.get("confidence"), f"col.{col.name}.pii_conf")

    own = results.get("ownership")
    if own:
        p = own.result
        if p.get("business_domain"):
            set_field(asset, "business_domain", p["business_domain"], "business_domain")
        cands = p.get("owner_candidates") or []
        if cands and cands[0].get("email"):
            person = db.scalar(select(OrgPerson).where(OrgPerson.email == cands[0]["email"]))
            if person:
                set_field(asset, "owner_person_id", person.id, "owner_person_id")

    desc = results.get("description")
    if desc:
        p = desc.result
        if p.get("description"):
            set_field(asset, "description", p["description"], "description")
        key = set(p.get("key_attributes") or [])
        for col in asset.columns:
            set_field(col, "is_key_attribute", col.name in key, f"col.{col.name}.is_key")

    return changes
