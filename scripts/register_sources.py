"""Registers YAML-defined sources + org directory into Cairn (idempotent).
Run AFTER generate: uv run tasks.py register"""

from pathlib import Path

import yaml
from sqlalchemy import select

from app.connectors import get_connector
from app.db import SessionLocal
from app.models import ActorType, DataSource, Environment, OrgPerson, SourceType
from app.services.audit import log_event

YAML_PATH = Path(__file__).resolve().parents[1] / "data" / "bank_environment.yaml"
TYPE_MAP = {"postgres": SourceType.postgres, "file": SourceType.file}
ENV_MAP = {
    "production": Environment.production,
    "analytics": Environment.analytics,
    "development": Environment.development,
    "sandbox": Environment.sandbox,
}


def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text())
    db = SessionLocal()
    try:
        for p in data.get("people", []):
            if not db.scalar(select(OrgPerson).where(OrgPerson.email == p["email"])):
                db.add(OrgPerson(**p))
        db.flush()
        for s in data["sources"]:
            src = db.scalar(select(DataSource).where(DataSource.name == s["name"]))
            if not src:
                src = DataSource(
                    name=s["name"],
                    source_type=TYPE_MAP[s["type"]],
                    environment=ENV_MAP[s["environment"]],
                    connection_ref=s["connection"],
                    status="registered",
                )
                db.add(src)
                db.flush()
                log_event(
                    db,
                    actor_type=ActorType.system,
                    actor="env-registration",
                    event_type="source_registered",
                    entity_type="data_source",
                    entity_id=src.id,
                    payload={"name": src.name},
                )
            try:
                connector = get_connector(src)
                ok, _detail = connector.test_connection()
                src.status = "connected" if ok else "error"
            except Exception:
                src.status = "registered"
        db.commit()
        print(f"[ok] registered {len(data['sources'])} sources, " f"{len(data.get('people', []))} org people")
    finally:
        db.close()


if __name__ == "__main__":
    main()
