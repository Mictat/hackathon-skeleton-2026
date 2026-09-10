from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from app.models import AssetType, DataSource
from .base import Connector, RawAsset, RawColumn

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FileConnector(Connector):
    """Scans a directory tree for CSV/parquet. For CSVs, column types are
    sniffed from the first 200 rows (headers + samples are metadata)."""

    def __init__(self, source: DataSource):
        super().__init__(source)
        root = source.connection_ref.get("root", "data/file_share")
        self.root = (Path(root) if Path(root).is_absolute() else PROJECT_ROOT / root).resolve()

    def test_connection(self) -> tuple[bool, str]:
        return (True, str(self.root)) if self.root.is_dir() else (False, f"missing: {self.root}")

    def discover(self) -> Iterator[RawAsset]:
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".csv":
                yield self._csv(path)
            elif path.suffix.lower() == ".parquet":
                asset = self._parquet(path)
                if asset:
                    yield asset

    def _csv(self, path: Path) -> RawAsset:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            sample = [row for _, row in zip(range(200), reader) if row]
        stat = path.stat()
        rel = path.relative_to(self.root)
        return RawAsset(
            name=path.stem,
            full_path=str(rel).replace("\\", "/"),
            asset_type=AssetType.file,
            namespace=str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else None,
            comment=f"CSV file, {stat.st_size / 1024:.0f} KB",
            # f"{datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d}",
            row_count=max(sum(1 for _ in path.open(encoding="utf-8")) - 1, 0),
            columns=[
                RawColumn(
                    name=h, data_type=self._guess([r[i] for r in sample if i < len(r) and r[i] != ""]), ordinal=i + 1
                )
                for i, h in enumerate(header)
            ],
        )

    @staticmethod
    def _guess(vals: list[str]) -> str | None:
        if not vals:
            return None
        try:
            [int(v.replace(",", "")) for v in vals]
            return "INTEGER"
        except ValueError:
            pass
        try:
            [float(v.replace(",", "")) for v in vals]
            return "NUMERIC"
        except ValueError:
            pass
        try:
            [date.fromisoformat(v) for v in vals]
            return "DATE"
        except ValueError:
            pass
        return "TEXT"

    def _parquet(self, path: Path) -> RawAsset | None:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            print(f"[warn] pyarrow not installed — skipping {path.name}")
            return None
        pf = pq.ParquetFile(path)
        stat = path.stat()
        rel = path.relative_to(self.root)
        return RawAsset(
            name=path.stem,
            full_path=str(rel).replace("\\", "/"),
            asset_type=AssetType.file,
            namespace=str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else None,
            comment=f"Parquet file, {stat.st_size / 1024:.0f} KB",
            # f"{datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d}",
            row_count=pf.metadata.num_rows,
            columns=[
                RawColumn(name=f.name, data_type=str(f.type), nullable=bool(f.nullable), ordinal=i + 1)
                for i, f in enumerate(pf.schema_arrow)
            ],
        )
