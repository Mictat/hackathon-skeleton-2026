from __future__ import annotations

import re

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import PII_TAXONOMY, SYSTEM, asset_context

AGENT_NAME = "classification"
SENSITIVITIES = ("public", "internal", "confidential", "restricted")

REGEX_RULES: list[tuple[str, re.Pattern]] = [  # order = priority
    ("email", re.compile(r"e[-_]?mail|eml", re.I)),
    ("phone", re.compile(r"phone|mob(ile)?|tel|contact[-_]?no", re.I)),
    ("date_of_birth", re.compile(r"\bdob\b|birth", re.I)),
    ("national_id", re.compile(r"\bssn\b|national[-_]?id|\bnin\b|tax[-_]?id", re.I)),
    ("bank_account", re.compile(r"iban|acct[-_]?no|account[-_]?no|bank[-_]?acct", re.I)),
    ("income", re.compile(r"income|salary|earnings", re.I)),
    ("address", re.compile(r"addr", re.I)),
    (
        "person_name",
        re.compile(
            r"full[-_]?name|cust(omer)?[-_]?name|contact[-_]?name|"
            r"surname|last[-_]?name|first[-_]?name|given[-_]?name",
            re.I,
        ),
    ),
]
NON_PERSON = re.compile(r"vendor|supplier|company|corp|merchant|firm|partner|org\b", re.I)
REGEX_CONFIDENCE = 0.96


def regex_classify(column_name: str) -> str | None:
    """Tier 1: deterministic name rules. Conservative — entity-ish columns
    (vendor/company/...) are left for the LLM to judge."""
    if NON_PERSON.search(column_name):
        return None
    for pii_type, pat in REGEX_RULES:
        if pat.search(column_name):
            return pii_type
    return None


class ColumnClass(BaseModel):
    name: str
    is_pii: bool = False
    pii_type: str | None = None
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""
    source: str = "llm"  # regex | llm


class ClassificationResult(BaseModel):
    asset_sensitivity: str
    sensitivity_confidence: float = Field(ge=0, le=1)
    columns: list[ColumnClass] = []


def messages_for(db: Session, asset) -> list[dict]:
    regex_hits = {c.name: regex_classify(c.name) for c in asset.columns}
    known = {n: t for n, t in regex_hits.items() if t}
    to_ask = [n for n, t in regex_hits.items() if not t]
    user = (
        "Classify the PII and sensitivity of this data asset for a bank governance catalog.\n\n"
        f"{asset_context(asset)}\n\n"
        f"PII taxonomy (pii_type values): {', '.join(PII_TAXONOMY)}\n"
        f"Sensitivity levels: {', '.join(SENSITIVITIES)}\n"
        "Guidance: direct personal identifiers and financial data tied to individuals "
        "=> PII. Company (not person) data or aggregates => not PII, though still sensitive.\n\n"
        f"Columns already classified by deterministic rules (do not re-decide): "
        f"{known or '(none)'}\n"
        f"Classify ONLY these columns: {to_ask or '(none)'}\n\n"
        'Return JSON: {"asset_sensitivity": str, "sensitivity_confidence": float, '
        '"columns": [{"name": str, "is_pii": bool, "pii_type": str|null, '
        '"confidence": float, "reasoning": str}]}'
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _fallback_sensitivity(asset, regex_hits: dict) -> tuple[str, float]:
    n = f"{asset.namespace or ''}.{asset.name}".lower()
    if any(k in n for k in ("kyc", "aml", "watchlist", "sanction", "alert")):
        return "restricted", 0.50
    if regex_hits or any(k in n for k in ("customer", "cust", "applicant")):
        return "confidential", 0.55
    return "internal", 0.45


def run(db: Session, asset, llm: LLMClient):
    """Returns (payload, agent_confidence, meta). Never raises on LLM failure."""
    col_names = [c.name for c in asset.columns]
    regex_hits = {n: t for n in col_names if (t := regex_classify(n))}
    to_ask = [n for n in col_names if n not in regex_hits]
    columns_out = {
        n: ColumnClass(
            name=n,
            is_pii=True,
            pii_type=t,
            confidence=REGEX_CONFIDENCE,
            reasoning="deterministic name-pattern rule",
            source="regex",
        )
        for n, t in regex_hits.items()
    }
    sensitivity, sens_conf = _fallback_sensitivity(asset, regex_hits)
    degraded, from_cache, latency, model = True, None, 0, "regex-rules"
    if to_ask:
        try:
            parsed, from_cache, latency = llm.chat_json(messages_for(db, asset), ClassificationResult)
            model = llm.model
            degraded = False
            if parsed.asset_sensitivity in SENSITIVITIES:
                sensitivity, sens_conf = parsed.asset_sensitivity, parsed.sensitivity_confidence
            valid = set(to_ask)  # hallucination guard: only accept real column names
            for cc in parsed.columns:
                if cc.name in valid:
                    cc.source = "llm"
                    columns_out[cc.name] = cc
            for n in to_ask:  # LLM omitted some? mark unclassified, low confidence
                columns_out.setdefault(n, ColumnClass(name=n, is_pii=False, confidence=0.3, reasoning="not classified"))
        except LLMError:
            pass  # keep regex-only degraded result
    payload = {
        "asset_sensitivity": sensitivity,
        "sensitivity_confidence": sens_conf,
        "columns": [c.model_dump() for c in (columns_out.get(n) for n in col_names) if c],
        "degraded": degraded,
    }
    return payload, sens_conf, {"model": model, "from_cache": from_cache, "degraded": degraded, "latency_ms": latency}
