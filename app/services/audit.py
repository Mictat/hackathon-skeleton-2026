from sqlalchemy.orm import Session

from app.models import ActorType, AuditEvent


def log_event(
    db: Session,
    *,
    actor_type: ActorType,
    actor: str,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    run_id: int | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type=actor_type,
        actor=actor,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        run_id=run_id,
        payload=payload or {},
    )
    db.add(event)
    return event
