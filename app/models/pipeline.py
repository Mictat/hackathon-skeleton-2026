from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ts_col


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|failed
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    started_at: Mapped[datetime] = ts_col()
    finished_at: Mapped[datetime | None] = ts_col(nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EnrichmentResult(Base):
    __tablename__ = "enrichment_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id", ondelete="SET NULL"), index=True)
    agent_name: Mapped[str] = mapped_column(String(40), index=True)  # classification|ownership|description
    result: Mapped[dict] = mapped_column(JSONB)  # shape per docs/agent_contracts.md
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = ts_col()
