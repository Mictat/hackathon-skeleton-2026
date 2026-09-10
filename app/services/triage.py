from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActorType, Asset, DataSource, GovernanceStatus, PipelineStatus, ScanRun
from app.services.audit import log_event
from app.services.proposals import apply_proposals, latest_results
from app.services.settings_svc import get_confidence_threshold

RE_TRIAGEABLE = (GovernanceStatus.pending, GovernanceStatus.auto_accepted, GovernanceStatus.pending_review)


def apply_triage(db: Session, run: ScanRun | None = None, actor: str = "triage-engine") -> dict:
    """confidence >= threshold -> auto_accepted (proposals applied);
    else pending_review. Never touches approved/rejected or mock-source assets.
    Idempotent: assets already in their target state are skipped silently."""
    threshold = get_confidence_threshold(db)
    q = (
        select(Asset)
        .join(DataSource, Asset.source_id == DataSource.id)
        .where(
            DataSource.status != "mock",
            Asset.governance_status.in_(RE_TRIAGEABLE),
            Asset.pipeline_status == PipelineStatus.enriched,
        )
    )
    if run is not None:
        q = q.where(Asset.source_id == run.source_id)
    q = q.order_by(Asset.id)
    stats = {"auto_accepted": 0, "pending_review": 0, "threshold": threshold}
    for asset in db.scalars(q):
        conf = asset.overall_confidence or 0.0
        if conf >= threshold:
            if asset.governance_status != GovernanceStatus.auto_accepted:
                results = latest_results(db, asset.id)
                apply_proposals(db, asset, results, applied_by=actor)
                asset.governance_status = GovernanceStatus.auto_accepted
                stats["auto_accepted"] += 1
                log_event(
                    db,
                    actor_type=ActorType.system,
                    actor=actor,
                    event_type="auto_accepted",
                    entity_type="asset",
                    entity_id=asset.id,
                    run_id=run.id if run else None,
                    payload={"confidence": conf, "threshold": threshold, "agents": sorted(results)},
                )
        elif asset.governance_status != GovernanceStatus.pending_review:
            asset.governance_status = GovernanceStatus.pending_review
            stats["pending_review"] += 1
            log_event(
                db,
                actor_type=ActorType.system,
                actor=actor,
                event_type="triaged_for_review",
                entity_type="asset",
                entity_id=asset.id,
                run_id=run.id if run else None,
                payload={"confidence": conf, "threshold": threshold},
            )
    db.commit()
    return stats
