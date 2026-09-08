from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

THRESHOLD_KEY = "confidence_threshold"
DEFAULT_THRESHOLD = 0.85


def get_confidence_threshold(db: Session) -> float:
    row = db.get(Setting, THRESHOLD_KEY)
    return float(row.value["value"]) if row else DEFAULT_THRESHOLD


def set_confidence_threshold(db: Session, value: float, updated_by: str = "system") -> None:
    row = db.get(Setting, THRESHOLD_KEY)
    if row:
        row.value = {"value": value}  # reassign, don't mutate — see JSONB gotcha below
        row.updated_by = updated_by
    else:
        db.add(Setting(key=THRESHOLD_KEY, value={"value": value}, updated_by=updated_by))
