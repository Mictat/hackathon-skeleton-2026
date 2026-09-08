from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def enum_col(enum_cls, **kwargs):
    """VARCHAR-backed enum (not native PG enum) — easy to change, readable in Adminer.
    IMPORTANT: keep enum member name == value (e.g. pending_review = "pending_review")."""
    return mapped_column(SAEnum(enum_cls, native_enum=False, length=40), **kwargs)


def ts_col(**kwargs):
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kwargs)
