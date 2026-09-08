from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, enum_col, ts_col
from .enums import ActorType, ReviewAction, UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[UserRole] = enum_col(UserRole, default=UserRole.steward)
    team: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = ts_col()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[ReviewAction] = enum_col(ReviewAction)
    changes: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"field": {"before": x, "after": y}}
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts_col()

    asset: Mapped["Asset"] = relationship(back_populates="reviews")  # noqa: F821


class AuditEvent(Base):
    """APPEND-ONLY. No update/delete code paths are ever written against this table."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = ts_col()
    actor_type: Mapped[ActorType] = enum_col(ActorType)
    actor: Mapped[str] = mapped_column(String(120))  # "classification-agent", "j.okafor@bank"
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = ts_col()
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
