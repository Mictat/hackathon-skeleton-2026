from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

from app.models import AssetType, DataSource


@dataclass
class RawColumn:
    name: str
    data_type: str | None = None
    nullable: bool = True
    comment: str | None = None
    ordinal: int = 0


@dataclass
class RawAsset:
    name: str
    full_path: str
    asset_type: AssetType
    namespace: str | None = None
    comment: str | None = None
    row_count: int | None = None
    columns: list[RawColumn] = field(default_factory=list)


class Connector(ABC):
    """A connector DISCOVERS metadata only — names, types, comments, counts.
    It must never read or return data values."""

    def __init__(self, source: DataSource):
        self.source = source

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """(ok, detail) — used at registration time."""

    @abstractmethod
    def discover(self) -> Iterator[RawAsset]:
        """Yield assets one at a time so the scan service can commit
        incrementally (this is what makes the live dashboard possible)."""
