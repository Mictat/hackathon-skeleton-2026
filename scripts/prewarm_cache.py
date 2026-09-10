"""Live-mode full run that fills the LLM cache. Run with internet + API key.
Leaves the catalog in the fully-enriched 'warm' state (a valid demo state).
Run: uv run tasks.py prewarm   (does reset + register first)"""

import time
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import DataSource, ScanRun
from app.services.scan import start_scan


def main() -> None:
    s = get_settings()
    if s.llm_offline or not s.llm_api_key:
        raise SystemExit("[prewarm] live mode required: set ATLAS_LLM_API_KEY, ATLAS_LLM_OFFLINE=0")
    db = SessionLocal()
    try:
        sources = [x for x in db.scalars(select(DataSource).order_by(DataSource.id)) if x.status != "mock"]
        for src in sources:
            print(f"[prewarm] scanning '{src.name}' with live LLM...")
            run_id = start_scan(src.id, trigger="prewarm")
            deadline = time.time() + 900
            while time.time() < deadline:
                db.expire_all()
                run = db.get(ScanRun, run_id)
                if run and run.status in ("completed", "failed"):
                    break
                time.sleep(1)
            print(
                f"[prewarm] {src.name}: {run.status} enriched={run.stats.get('enriched', 0)} "
                f"llm_calls={run.stats.get('llm_calls', 0)} "
                f"cache_hits={run.stats.get('cache_hits', 0)}" + (f" error={run.error}" if run.error else "")
            )
    finally:
        db.close()
    cache = Path(s.llm_cache_dir)
    n = len(list(cache.glob("*.json"))) if cache.exists() else 0
    print(f"[prewarm] cache now holds {n} responses -> {cache}/")
