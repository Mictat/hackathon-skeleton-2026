from app.models import DataSource, SourceType
from .base import Connector, RawAsset, RawColumn
from .files import FileConnector
from .sql import SQLConnector

CONNECTOR_MAP = {
    SourceType.postgres: SQLConnector,
    SourceType.mysql: SQLConnector,
    SourceType.sqlserver: SQLConnector,
    SourceType.file: FileConnector,
}

MOCK_TYPES = {SourceType.teradata, SourceType.snowflake, SourceType.mainframe, SourceType.hadoop}


class ConnectorNotAvailable(Exception):
    pass


def get_connector(source: DataSource) -> Connector:
    cls = CONNECTOR_MAP.get(source.source_type)
    if cls is None:
        hint = " (mock menu item — UI placeholder only)" if source.source_type in MOCK_TYPES else ""
        raise ConnectorNotAvailable(f"No connector implemented for source_type={source.source_type.value}{hint}")
    return cls(source)


__all__ = [
    "Connector",
    "RawAsset",
    "RawColumn",
    "get_connector",
    "ConnectorNotAvailable",
    "SQLConnector",
    "FileConnector",
]
