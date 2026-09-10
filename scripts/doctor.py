"""Demo-day readiness checks. Run: uv run tasks.py doctor
Verifies DB, YAML, LLM mode, and — critically — offline replay readiness:
rebuilds every agent prompt for every real asset and checks the cache."""

from pathlib import Path

import yaml
from sqlalchemy import func, select

from app.agents import classification, description, ownership
from app.config import get_settings
from app.db import SessionLocal
from app.llm.client import cache_key
from app.models import Asset, AuditEvent, DataSource, EnrichmentResult
from scripts.generate_bank_env import YAML_PATH, validate_yaml


def main() -> None:
    problems: list[str] = []
    s = get_settings()

    db = SessionLocal()
    try:
        n_assets = db.scalar(select(func.count()).select_from(Asset))
        n_results = db.scalar(select(func.count()).select_from(EnrichmentResult))
        n_audit = db.scalar(select(func.count()).select_from(AuditEvent))
        print(f"[doctor] db ok — assets={n_assets} enrichment_results={n_results} audit={n_audit}")
    except Exception as e:
        print(f"[doctor] db unreachable: {e}")
        return
    finally:
        db.close()

    try:
        validate_yaml(yaml.safe_load(YAML_PATH.read_text()))
        print("[doctor] yaml ok")
    except SystemExit as e:
        problems.append(f"yaml: {e}")

    offline = s.llm_offline or not s.llm_api_key
    print(f"[doctor] llm mode: {'OFFLINE (cache-only)' if offline else 'live'} model={s.llm_model}")

    db = SessionLocal()
    try:
        assets = db.scalars(
            select(Asset).join(DataSource, Asset.source_id == DataSource.id).where(DataSource.status != "mock")
        ).all()
        agents = [("classification", classification), ("ownership", ownership), ("description", description)]
        missing = []
        checked = 0
        for a in assets:
            for name, mod in agents:
                checked += 1
                key = cache_key(s.llm_model, mod.messages_for(db, a))
                if not (Path(s.llm_cache_dir) / f"{key}.json").exists():
                    missing.append(f"{a.full_path}:{name}")
        if missing or len(assets) == 0:
            problems.append(
                f"replay NOT ready — {len(missing)}/{checked} prompts uncached "
                f"(first: {missing[0]}). Run: uv run tasks.py prewarm"
            )
        else:
            print(f"[doctor] replay ready — {checked}/{checked} agent prompts cached")
    finally:
        db.close()

    print("[doctor] VERDICT:", "READY" if not problems else "NOT READY")
    for p in problems:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
