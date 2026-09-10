from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENTS, composite_confidence
from app.llm.client import LLMClient
from app.models import ActorType, Asset, EnrichmentResult, PipelineStatus, ScanRun
from app.services.audit import log_event


def enrich_discovered_assets(db: Session, run: ScanRun, pacing_s: float = 0.0) -> dict:
    """Run the agent suite over every discovered asset of this run's source.
    Per-asset commits keep the board live; per-agent failures are recorded,
    never fatal. Returns stats for run.stats."""
    llm = LLMClient()
    stats = {"enriched": 0, "enrich_failed": 0}
    assets = db.scalars(
        select(Asset)
        .where(Asset.source_id == run.source_id, Asset.pipeline_status == PipelineStatus.discovered)
        .order_by(Asset.id)
    ).all()
    for asset in assets:
        asset.pipeline_status = PipelineStatus.enriching
        db.commit()
        confidences: dict[str, float | None] = {}
        for name, agent in AGENTS.items():
            try:
                payload, conf, meta = agent.run(db, asset, llm)
                db.add(
                    EnrichmentResult(
                        asset_id=asset.id,
                        scan_id=run.id,
                        agent_name=name,
                        result=payload,
                        confidence=conf,
                        model=meta.get("model"),
                        from_cache=bool(meta.get("from_cache")),
                        latency_ms=meta.get("latency_ms", 0) or 0,
                    )
                )
                log_event(
                    db,
                    actor_type=ActorType.agent,
                    actor=f"{name}-agent",
                    event_type="enrichment_proposed",
                    entity_type="asset",
                    entity_id=asset.id,
                    run_id=run.id,
                    payload={
                        "agent": name,
                        "confidence": conf,
                        "from_cache": meta.get("from_cache"),
                        "degraded": meta.get("degraded", False),
                    },
                )
                confidences[name] = conf
            except Exception as e:
                stats["enrich_failed"] += 1
                log_event(
                    db,
                    actor_type=ActorType.agent,
                    actor=f"{name}-agent",
                    event_type="enrichment_failed",
                    entity_type="asset",
                    entity_id=asset.id,
                    run_id=run.id,
                    payload={"error": str(e)[:300]},
                )
        asset.overall_confidence = composite_confidence(confidences)
        asset.pipeline_status = PipelineStatus.enriched
        stats["enriched"] += 1
        run.stats = {**run.stats, **stats}  # JSONB: reassign, never mutate
        db.commit()
        if pacing_s:
            time.sleep(pacing_s)
    stats["llm_calls"] = llm.calls
    stats["cache_hits"] = llm.cache_hits
    return stats
