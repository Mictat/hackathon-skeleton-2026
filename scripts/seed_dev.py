"""Idempotent dev seed. The synthetic bank environment (sources, org people,
assets) comes from data/bank_environment.yaml via tasks.py generate/register.
This seeds only what the YAML doesn't cover: demo users, glossary, settings.
Run: uv run tasks.py init"""

from sqlalchemy import select

import app.models as m
from app.db import SessionLocal
from app.services.settings_svc import set_confidence_threshold


def seed() -> None:
    db = SessionLocal()
    try:
        set_confidence_threshold(db, 0.85, updated_by="system")

        if not db.scalar(select(m.User).where(m.User.email == "admin@bank.example")):
            db.add_all(
                [
                    m.User(name="Admin User", email="admin@bank.example", team="Data Governance Office"),
                    m.User(name="Sarah Chen", email="s.chen@bank.example", team="Retail Data Stewardship"),
                    m.User(name="Marcus Webb", email="m.webb@bank.example", team="Risk Data Stewardship"),
                ]
            )

        for term, definition, domain in [
            ("Customer Master", "Golden-source dataset of retail customer identity and relationships.", "retail"),
            ("KYC", "Know-Your-Customer records required under AML regulations.", "compliance"),
            ("Payment Event", "Any debit/credit posting against a customer account.", "retail"),
        ]:
            if not db.scalar(select(m.GlossaryTerm).where(m.GlossaryTerm.term == term)):
                db.add(m.GlossaryTerm(term=term, definition=definition, domain=domain, created_by="seed"))

        db.commit()
        print(
            f"[ok] seeded: {len(db.scalars(select(m.User)).all())} users, "
            f"{len(db.scalars(select(m.GlossaryTerm)).all())} glossary terms "
            f"(sources/org/assets arrive via 'tasks.py register')"
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
