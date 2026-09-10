from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.llm.prompts import SYSTEM, asset_context
from app.models import GlossaryTerm

AGENT_NAME = "description"


class DescriptionResult(BaseModel):
    description: str
    key_attributes: list[str] = []
    glossary_terms: list[str] = []
    confidence: float = Field(ge=0, le=1)


def _glossary(db: Session) -> list[str]:
    return list(db.scalars(select(GlossaryTerm.term).order_by(GlossaryTerm.term)))


def messages_for(db: Session, asset) -> list[dict]:
    user = (
        "Write a catalog entry for this data asset.\n\n"
        f"{asset_context(asset)}\n\n"
        f"Known glossary terms: {', '.join(_glossary(db)) or '(none)'}\n"
        "description: 1-2 sentences in plain business language (what this asset is for). "
        "key_attributes: the column names that identify a record. glossary_terms: only "
        "terms from the list that genuinely apply.\n\n"
        'Return JSON: {"description": str, "key_attributes": [str], '
        '"glossary_terms": [str], "confidence": float}'
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def run(db: Session, asset, llm: LLMClient):
    parsed, from_cache, latency = llm.chat_json(messages_for(db, asset), DescriptionResult)
    col_names = {c.name for c in asset.columns}  # hallucination guards
    payload = {
        "description": parsed.description,
        "key_attributes": [k for k in parsed.key_attributes if k in col_names],
        "glossary_terms": [t for t in parsed.glossary_terms if t.lower() in {g.lower() for g in _glossary(db)}],
        "confidence": parsed.confidence,
        "degraded": False,
    }
    return (
        payload,
        parsed.confidence,
        {"model": llm.model, "from_cache": from_cache, "degraded": False, "latency_ms": latency},
    )
