from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import create_engine, inspect, text

from app.config import get_settings
from app.models import AssetType, DataSource
from .base import Connector, RawAsset, RawColumn

SYSTEM_SCHEMAS = {"public", "information_schema", "pg_catalog"}


def resolve_password(password_env: str) -> str:
    """Credentials are stored in the catalog as an env-var NAME only.
    Production sets the real variable; dev falls back to app settings."""
    pw = os.environ.get(password_env)
    return pw if pw else get_settings().sample_db_password


def build_dsn(ref: dict) -> str:
    password_env = ref.get("password_env", "CAIRN_SAMPLE_PASSWORD")
    return (
        f"postgresql+psycopg://{ref.get('user', 'postgres')}:{resolve_password(password_env)}"
        f"@{ref.get('host', 'localhost')}:{ref.get('port', 5432)}/{ref['database']}"
    )


class SQLConnector(Connector):
    """Reflects schemas/tables/views/columns via SQLAlchemy Inspector.
    Works for any SQLAlchemy-supported dialect — swapping databases later
    means changing the DSN, not this code."""

    def __init__(self, source: DataSource):
        super().__init__(source)
        self.engine = create_engine(build_dsn(source.connection_ref), pool_pre_ping=True)
        self.include_schemas = source.connection_ref.get("include_schemas")

    def test_connection(self) -> tuple[bool, str]:
        try:
            with self.engine.connect():
                return True, "connected"
        except Exception as e:
            return False, str(e)

    def discover(self) -> Iterator[RawAsset]:
        insp = inspect(self.engine)
        schemas = [
            s
            for s in insp.get_schema_names()
            if s not in SYSTEM_SCHEMAS and (self.include_schemas is None or s in self.include_schemas)
        ]
        for schema in sorted(schemas):
            for names, atype in (
                (insp.get_table_names(schema), AssetType.table),
                (insp.get_view_names(schema), AssetType.view),
            ):
                for name in sorted(names):
                    yield self._reflect(insp, name, schema, atype)
        self.engine.dispose()

    def _reflect(self, insp, name: str, schema: str, atype: AssetType) -> RawAsset:
        cols = insp.get_columns(name, schema=schema)
        comment = None
        if atype == AssetType.table:  # view comments vary by dialect — skip
            comment = (insp.get_table_comment(name, schema=schema) or {}).get("text")
        definition = None
        if atype == AssetType.view:
            try:
                definition = insp.get_view_definition(name, schema=schema)
            except Exception:
                definition = None
        return RawAsset(
            name=name,
            full_path=f"{schema}.{name}",
            asset_type=atype,
            namespace=schema,
            comment=comment,
            row_count=self._count(schema, name),
            definition=definition,
            columns=[
                RawColumn(
                    name=c["name"],
                    data_type=str(c.get("type") or "") or None,
                    nullable=bool(c.get("nullable", True)),
                    comment=c.get("comment"),
                    ordinal=i + 1,
                )
                for i, c in enumerate(cols)
            ],
        )

    def _count(self, schema: str, name: str) -> int | None:
        try:
            with self.engine.connect() as c:
                return c.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{name}"')).scalar()
        except Exception:
            return None
