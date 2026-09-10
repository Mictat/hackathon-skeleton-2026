from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors import get_connector
from app.db import SessionLocal
from app.models import ActorType, Asset, AssetColumn, DataSource, PipelineStatus, ScanRun
from app.services.audit import log_event
from app.services.enrich import enrich_discovered_assets


def start_scan(source_id: int, trigger: str = "manual") -> int:
    """Create the run row and execute in a background thread. Returns run_id
    immediately; poll GET /api/runs/{run_id} for live progress."""
    db = SessionLocal()
    try:
        source = db.get(DataSource, source_id)
        if source is None:
            raise ValueError(f"source {source_id} not found")
        run = ScanRun(source_id=source.id, status="queued", trigger=trigger)
        db.add(run)
        db.flush()
        run_id = run.id
        log_event(
            db,
            actor_type=ActorType.system,
            actor="scan-service",
            event_type="scan_started",
            entity_type="data_source",
            entity_id=source.id,
            run_id=run_id,
        )
        db.commit()
    finally:
        db.close()
    threading.Thread(target=_execute_scan, args=(run_id,), daemon=True).start()
    return run_id


def _execute_scan(run_id: int) -> None:
    db = SessionLocal()  # own session per thread
    try:
        run = db.get(ScanRun, run_id)
        source = db.get(DataSource, run.source_id)
        run.status = "running"
        db.commit()
        stats = {"assets_seen": 0, "new": 0, "updated": 0, "columns": 0, "errors": 0}
        pacing = get_settings().scan_pacing_ms / 1000.0
        try:
            connector = get_connector(source)
            ok, detail = connector.test_connection()
            if not ok:
                raise ConnectionError(detail)
            source.status = "connected"
            db.commit()
            for raw in connector.discover():
                try:
                    _, created = _upsert_asset(db, run, source, raw)
                    stats["assets_seen"] += 1
                    stats["new" if created else "updated"] += 1
                    stats["columns"] += len(raw.columns)
                except Exception as e:
                    stats["errors"] += 1
                    print(f"[scan] error on {raw.full_path}: {e}")
                run.stats = {**run.stats, **stats}  # JSONB: reassign, never mutate
                db.commit()
                if pacing:
                    time.sleep(pacing)
            # --- agent pipeline follows discovery in the same run ---
            try:
                print(f"scan enrichment starting for ({run.id})...")
                enrich_stats = enrich_discovered_assets(db, run, get_settings().enrich_pacing_ms / 1000.0)
                print(f"scan enrichment finished! ({run.id}): {enrich_stats}")
                stats.update(enrich_stats)
            except Exception as e:
                log_event(
                    db,
                    actor_type=ActorType.system,
                    actor="scan-service",
                    event_type="enrichment_error",
                    entity_type="data_source",
                    entity_id=source.id,
                    run_id=run.id,
                    payload={"error": str(e)[:300]},
                )
            run.status = "completed"
            log_event(
                db,
                actor_type=ActorType.system,
                actor="scan-service",
                event_type="scan_completed",
                entity_type="data_source",
                entity_id=source.id,
                run_id=run.id,
                payload=stats,
            )
        except Exception as e:
            run.status = "failed"
            run.error = str(e)[:2000]
            source.status = "error"
            log_event(
                db,
                actor_type=ActorType.system,
                actor="scan-service",
                event_type="scan_failed",
                entity_type="data_source",
                entity_id=source.id,
                run_id=run.id,
                payload={"error": run.error},
            )
        run.finished_at = datetime.now(timezone.utc)
        run.stats = {**run.stats, **stats}
        db.commit()
    finally:
        db.close()


def _upsert_asset(db: Session, run: ScanRun, source: DataSource, raw) -> tuple[Asset, bool]:
    asset = db.scalar(select(Asset).where(Asset.source_id == source.id, Asset.full_path == raw.full_path))
    created = asset is None
    if created:
        asset = Asset(
            source_id=source.id,
            scan_id=run.id,
            asset_type=raw.asset_type,
            name=raw.name,
            namespace=raw.namespace,
            full_path=raw.full_path,
            pipeline_status=PipelineStatus.discovered,
        )
        db.add(asset)
        db.flush()
        log_event(
            db,
            actor_type=ActorType.agent,
            actor="discovery-agent",
            event_type="asset_discovered",
            entity_type="asset",
            entity_id=asset.id,
            run_id=run.id,
            payload={"full_path": raw.full_path, "columns": len(raw.columns)},
        )
    else:
        before = {c.name: (c.data_type, c.nullable) for c in asset.columns}
        after = {c.name: (c.data_type, c.nullable) for c in raw.columns}
        asset.scan_id = run.id
        if before != after:
            asset.pipeline_status = PipelineStatus.discovered  # flag for re-enrichment
            log_event(
                db,
                actor_type=ActorType.agent,
                actor="discovery-agent",
                event_type="asset_changed",
                entity_type="asset",
                entity_id=asset.id,
                run_id=run.id,
                payload={"full_path": raw.full_path},
            )
        # NOTE: governance_status and curated fields are NEVER touched here —
        # whether a changed asset needs re-review is a human decision.
    asset.raw_comment = raw.comment
    asset.row_count = raw.row_count
    _sync_columns(db, asset, raw.columns)
    return asset, created


def _sync_columns(db: Session, asset: Asset, raw_columns) -> None:
    """Update type/nullable/ordinal + raw comments; PRESERVE curated flags
    (is_pii, pii_type, is_key_attribute, description). Add new, drop gone."""
    existing = {c.name: c for c in asset.columns}
    seen: set[str] = set()
    for rc in raw_columns:
        seen.add(rc.name)
        col = existing.get(rc.name)
        if col is None:
            asset.columns.append(
                AssetColumn(
                    name=rc.name,
                    data_type=rc.data_type,
                    nullable=rc.nullable,
                    raw_comment=rc.comment,
                    ordinal=rc.ordinal,
                )
            )
        else:
            col.data_type = rc.data_type
            col.nullable = rc.nullable
            col.raw_comment = rc.comment
            col.ordinal = rc.ordinal
    for name, col in existing.items():
        if name not in seen:
            db.delete(col)
    db.flush()
