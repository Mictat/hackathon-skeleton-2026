from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActorType, Asset, AssetType, DataSource, LineageEdge, ScanRun
from app.services.audit import log_event

GENERIC_COLUMNS = {"id", "date", "status", "type", "currency", "amount", "created_at", "updated_at", "notes", "name"}
_PATH_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def detect_lineage(db: Session, run: ScanRun | None = None) -> dict:
    """Deterministic lineage agent. Two signals:
    1. view SQL references (schema.table in the stored definition) -> certain
    2. distinctive column-name overlap between files and tables -> inferred
    Runs across the WHOLE estate (files derive from DB tables = cross-source).
    Edges are informational (shown, badge 'inferred'); human-confirmed and
    column-level lineage are roadmap items."""
    stmt = select(Asset).join(DataSource, Asset.source_id == DataSource.id).where(DataSource.status != "mock")
    assets = db.scalars(stmt).all()
    by_path = {a.full_path.lower(): a for a in assets}
    proposals: list[tuple[int, int, str, str, float]] = []

    for v in assets:
        if v.asset_type == AssetType.view and v.raw_definition:
            for m in _PATH_RE.finditer(v.raw_definition):
                base = by_path.get(f"{m.group(1).lower()}.{m.group(2).lower()}")
                if base and base.id != v.id and base.asset_type == AssetType.table:
                    proposals.append((base.id, v.id, "derived_from", "view-sql", 1.0))

    tables = [a for a in assets if a.asset_type == AssetType.table]
    for f in [a for a in assets if a.asset_type == AssetType.file]:
        fcols = {c.name.lower() for c in f.columns} - GENERIC_COLUMNS
        if not fcols:
            continue
        best: tuple[Asset, float] | None = None
        for t in tables:
            tcols = {c.name.lower() for c in t.columns} - GENERIC_COLUMNS
            shared = fcols & tcols
            if not shared:
                continue
            jac = len(shared) / len(fcols | tcols)
            if len(shared) >= 3 or jac >= 0.5:
                score = round(min(max(len(shared) / 4.0, jac), 0.95), 2)
                if best is None or score > best[1]:
                    best = (t, score)
        if best:
            proposals.append((best[0].id, f.id, "extracted_from", "column-overlap", best[1]))

    new_edges = 0
    for src_id, tgt_id, etype, detected_by, conf in proposals:
        edge = db.scalar(
            select(LineageEdge).where(
                LineageEdge.source_asset_id == src_id,
                LineageEdge.target_asset_id == tgt_id,
                LineageEdge.edge_type == etype,
            )
        )
        if edge:
            edge.detected_by, edge.confidence = detected_by, conf
        else:
            db.add(
                LineageEdge(
                    source_asset_id=src_id,
                    target_asset_id=tgt_id,
                    edge_type=etype,
                    detected_by=detected_by,
                    confidence=conf,
                )
            )
            new_edges += 1
            log_event(
                db,
                actor_type=ActorType.agent,
                actor="lineage-agent",
                event_type="lineage_edge_detected",
                entity_type="asset",
                entity_id=tgt_id,
                run_id=run.id if run else None,
                payload={"from_asset_id": src_id, "edge_type": etype, "detected_by": detected_by, "confidence": conf},
            )
    db.commit()
    return {"new_edges": new_edges}
