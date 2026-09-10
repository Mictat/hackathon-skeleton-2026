from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal  # noqa: F401 (re-export convenience)
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import DOMAINS, SYSTEM, asset_context
from app.models import OrgPerson

AGENT_NAME = "ownership"

SCHEMA_DOMAIN = {
    "retail_banking": "retail",
    "lending": "lending",
    "risk": "risk",
    "finance": "finance",
    "compliance": "compliance",
    "marketing": "marketing",
    "staging": "it",
    "core": "retail",
    "exports": "retail",
    "tmp": "unknown",
}

DOMAIN_PEOPLE_KEYWORDS = {
    "retail": ("retail",),
    "lending": ("lend",),
    "risk": ("risk",),
    "finance": ("finance",),
    "compliance": ("compliance",),
    "marketing": ("marketing",),
    "it": ("it & data", "data platform", "core systems", "data eng"),
}


class OwnerCandidate(BaseModel):
    email: str
    score: float = Field(ge=0, le=1)
    match_reason: str = ""


class OwnershipResult(BaseModel):
    business_domain: str
    domain_confidence: float = Field(ge=0, le=1)
    owner_candidates: list[OwnerCandidate] = []
    rationale: str = ""


def _directory_lines(db: Session) -> list[str]:
    people = db.scalars(select(OrgPerson).where(OrgPerson.active).order_by(OrgPerson.full_name)).all()
    return [f"- {p.full_name} <{p.email}> — {p.title}, team: {p.team}, dept: {p.department}" for p in people]


def _known_emails(db: Session) -> set[str]:
    return set(db.scalars(select(OrgPerson.email).where(OrgPerson.active)))


def messages_for(db: Session, asset) -> list[dict]:
    user = (
        "Infer the business domain and likely data owner for this asset, using the "
        "org directory below.\n\n"
        f"{asset_context(asset)}\n\n"
        f"Org directory:\n" + "\n".join(_directory_lines(db)) + "\n\n"
        f"business_domain must be one of: {', '.join(DOMAINS)}\n"
        "Owner candidates must be emails from the directory, ranked by score (0-1). "
        "If ownership is genuinely unclear (e.g. an ad-hoc export with no system of "
        "record), return an empty candidate list rather than guessing.\n\n"
        'Return JSON: {"business_domain": str, "domain_confidence": float, '
        '"owner_candidates": [{"email": str, "score": float, "match_reason": str}], '
        '"rationale": str}'
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _heuristic(domain: str, db: Session) -> dict:
    kws = DOMAIN_PEOPLE_KEYWORDS.get(domain, ())
    candidates = []
    for line in _directory_lines(db):
        email = line.split("<")[1].split(">")[0]
        if any(k in line.lower() for k in kws):
            candidates.append(
                {"email": email, "score": 0.55, "match_reason": "team/dept keyword match (offline heuristic)"}
            )
    return {
        "business_domain": domain,
        "domain_confidence": 0.60,
        "owner_candidates": sorted(candidates, key=lambda c: -c["score"])[:3],
        "rationale": "offline heuristic",
        "degraded": True,
    }


def run(db: Session, asset, llm: LLMClient):
    fallback_domain = SCHEMA_DOMAIN.get(asset.namespace or "", "unknown")
    known = _known_emails(db)
    try:
        parsed, from_cache, latency = llm.chat_json(messages_for(db, asset), OwnershipResult)
        domain = parsed.business_domain if parsed.business_domain in DOMAINS else fallback_domain
        candidates = sorted(
            [c for c in parsed.owner_candidates if c.email in known],  # hallucination guard
            key=lambda c: -c.score,
        )[:3]
        payload = {
            "business_domain": domain,
            "domain_confidence": parsed.domain_confidence,
            "owner_candidates": [c.model_dump() for c in candidates],
            "rationale": parsed.rationale,
            "degraded": False,
        }
    except LLMError:
        payload, from_cache, latency = _heuristic(fallback_domain, db), None, 0
        payload["model"] = "directory-heuristic"
    top = payload["owner_candidates"][0]["score"] if payload["owner_candidates"] else 0.20
    agent_conf = round(payload["domain_confidence"] * top, 4)
    payload.setdefault("model", llm.model)
    return (
        payload,
        agent_conf,
        {"model": payload["model"], "from_cache": from_cache, "degraded": payload["degraded"], "latency_ms": latency},
    )
