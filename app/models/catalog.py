from datetime import datetime

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, enum_col, ts_col
from .enums import AssetType, Environment, GovernanceStatus, PipelineStatus, Sensitivity, SourceType


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[SourceType] = enum_col(SourceType)
    environment: Mapped[Environment] = enum_col(Environment)
    connection_ref: Mapped[dict] = mapped_column(JSONB, default=dict)  # host/db/path refs — NEVER credentials
    status: Mapped[str] = mapped_column(String(30), default="registered")  # registered|connected|error|mock
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts_col()

    assets: Mapped[list["Asset"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True)

    asset_type: Mapped[AssetType] = enum_col(AssetType)
    name: Mapped[str] = mapped_column(String(200))
    namespace: Mapped[str | None] = mapped_column(String(200), nullable=True)  # schema / folder
    full_path: Mapped[str] = mapped_column(String(500))

    # ---- Curated catalog fields (written only via review / auto-accept) ----
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_domain: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sensitivity: Mapped[Sensitivity | None] = enum_col(Sensitivity, nullable=True)
    owner_person_id: Mapped[int | None] = mapped_column(ForeignKey("org_people.id", ondelete="SET NULL"), nullable=True)
    steward_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # ---- Agent state ----
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_status: Mapped[PipelineStatus] = enum_col(PipelineStatus, default=PipelineStatus.discovered)
    governance_status: Mapped[GovernanceStatus] = enum_col(GovernanceStatus, default=GovernanceStatus.pending)

    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    discovered_at: Mapped[datetime] = ts_col()
    updated_at: Mapped[datetime] = ts_col(onupdate=func.now())

    # Full-text search (drop this column if create_all complains — re-add on UI day)
    search_vector: Mapped[TSVECTOR] = mapped_column(
        TSVECTOR(),
        Computed(
            "to_tsvector('english', coalesce(name,'') || ' ' || coalesce(namespace,'') || ' ' || coalesce(description,''))",
            persisted=True,
        ),
    )

    source: Mapped["DataSource"] = relationship(back_populates="assets")
    columns: Mapped[list["AssetColumn"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", order_by="AssetColumn.ordinal"
    )
    reviews: Mapped[list["Review"]] = relationship(back_populates="asset", cascade="all, delete-orphan")

    # ---- Discovered raw metadata (agent INPUT — distinct from curated fields) ----
    raw_comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. PG table comment
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_id", "full_path", name="uq_assets_source_path"),
        Index("ix_assets_governance_status", "governance_status"),
        Index("ix_assets_domain", "business_domain"),
        Index("ix_assets_search", "search_vector", postgresql_using="gin"),
    )


class AssetColumn(Base):
    __tablename__ = "asset_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    data_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nullable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Curated classification (proposals live in enrichment_results)
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    pii_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    pii_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_key_attribute: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = ts_col()

    asset: Mapped["Asset"] = relationship(back_populates="columns")

    __table_args__ = (UniqueConstraint("asset_id", "name", name="uq_columns_asset_name"),)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    target_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    edge_type: Mapped[str] = mapped_column(String(40))  # derived_from|loaded_into|feeds|extracted_from
    detected_by: Mapped[str] = mapped_column(String(60))  # heuristic name | agent | manual
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = ts_col()

    __table_args__ = (UniqueConstraint("source_asset_id", "target_asset_id", "edge_type", name="uq_lineage_edge"),)


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(120), unique=True)
    definition: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | agent
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = ts_col()
