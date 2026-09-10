from app.agents import classification, description, ownership
from app.agents.classification import regex_classify

AGENTS = {"classification": classification, "ownership": ownership, "description": description}
WEIGHTS = {"classification": 0.45, "ownership": 0.30, "description": 0.25}
MISSING_AGENT_SCORE = 0.40  # neutral-low: a failed agent drags confidence down, never up


def composite_confidence(confidences: dict[str, float | None]) -> float:
    """overall = 0.45*classification + 0.30*ownership + 0.25*description
    (missing agent -> 0.40). Day -4: overall >= threshold -> auto_accept."""
    total = 0.0
    for name, weight in WEIGHTS.items():
        c = confidences.get(name)
        total += weight * (MISSING_AGENT_SCORE if c is None else min(max(c, 0.0), 1.0))
    return round(total, 4)


__all__ = ["AGENTS", "WEIGHTS", "composite_confidence", "regex_classify"]
