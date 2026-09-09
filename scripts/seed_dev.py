"""
Idempotent dev seed with PLACEHOLDER data.
Realistic bank-flavored environment arrives via Governance WS1's generator (day -6).
Run: uv run python -m scripts.seed_dev
"""

from datetime import datetime, timezone

from sqlalchemy import select

import app.models as m
from app.db import SessionLocal
from app.models.enums import (
    AssetType,
    Environment,
    GovernanceStatus,
    PipelineStatus,
    ReviewAction,
    Sensitivity,
    SourceType,
    UserRole,
)
from app.services.audit import log_event
from app.services.settings_svc import set_confidence_threshold

SAMPLE_NOTE = "SAMPLE — replaced by synthetic generator"


def seed() -> None:
    db = SessionLocal()
    try:
        # --- settings ---
        set_confidence_threshold(db, 0.85, updated_by="system")

        # --- users (demo 'log in as' — no auth) ---
        if not db.scalar(select(m.User).where(m.User.email == "admin@bank.example")):
            db.add_all(
                [
                    m.User(
                        name="Admin User",
                        email="admin@bank.example",
                        role=UserRole.admin,
                        team="Data Governance Office",
                    ),
                    m.User(
                        name="Sarah Chen",
                        email="s.chen@bank.example",
                        role=UserRole.steward,
                        team="Retail Data Stewardship",
                    ),
                    m.User(
                        name="Marcus Webb",
                        email="m.webb@bank.example",
                        role=UserRole.steward,
                        team="Risk Data Stewardhip",
                    ),
                ]
            )

        # --- org directory (ownership agent matches against this) ---
        people = [
            ("Sarah Chen", "s.chen@bank.example", "Head of Retail Data", "Retail Data Platform", "Retail Banking"),
            ("Marcus Webb", "m.webb@bank.example", "Risk Data Lead", "Risk Data Management", "Risk Management"),
            ("Priya Sharma", "p.sharma@bank.example", "Core Banking DBA", "Core Systems", "IT & Data"),
            ("David Osei", "d.osei@bank.example", "Finance Data Owner", "Finance Systems", "Finance"),
            ("Elena Petrova", "e.petrova@bank.example", "Compliance Analyst", "Regulatory Reporting", "Compliance"),
            ("Tom Nakamura", "t.nakamura@bank.example", "Marketing Analyst", "Campaign Analytics", "Marketing"),
        ]
        by_email = {}
        for full_name, email, title, team, dept in people:
            person = db.scalar(select(m.OrgPerson).where(m.OrgPerson.email == email))
            if not person:
                person = m.OrgPerson(
                    full_name=full_name, email=email, title=title, team=team, department=dept, notes=SAMPLE_NOTE
                )
                db.add(person)
                db.flush()
            by_email[email] = person

        # --- one registered source ---
        source = db.scalar(select(m.DataSource).where(m.DataSource.name == "Retail Core DB (dev)"))
        if not source:
            source = m.DataSource(
                name="Retail Core DB (dev)",
                source_type=SourceType.postgres,
                environment=Environment.development,
                connection_ref={"ref": "DEV_SAMPLE", "host": "localhost", "database": "bank_sample"},
                status="mock",
                notes=SAMPLE_NOTE,
            )
            db.add(source)
            db.flush()
            log_event(
                db,
                actor_type="system",
                actor="system",
                event_type="source_registered",
                entity_type="data_source",
                entity_id=source.id,
                payload={"name": source.name, "type": source.source_type.value},
            )

        steward = db.scalar(select(m.User).where(m.User.email == "s.chen@bank.example"))
        db.flush()

        def upsert_asset(full_path, **kw):
            asset = db.scalar(select(m.Asset).where(m.Asset.full_path == full_path, m.Asset.source_id == source.id))
            if not asset:
                asset = m.Asset(
                    source_id=source.id,
                    asset_type=AssetType.table,
                    full_path=full_path,
                    name=full_path.split(".")[-1],
                    namespace=full_path.split(".")[0],
                    **kw,
                )
                db.add(asset)
                db.flush()
            return asset

        # 1) Approved asset with a completed review — shows the curated end-state
        a1 = upsert_asset(
            "retail_banking.customer_master",
            description="Master record of all retail customers: identity, contact details, and branch relationships.",
            business_domain="retail",
            sensitivity=Sensitivity.confidential,
            owner_person_id=by_email["s.chen@bank.example"].id,
            steward_user_id=steward.id,
            overall_confidence=0.91,
            pipeline_status=PipelineStatus.enriched,
            governance_status=GovernanceStatus.approved,
            reviewed_by_user_id=steward.id,
            reviewed_at=datetime.now(timezone.utc),
        )
        if not a1.columns:
            a1.columns = [
                m.AssetColumn(
                    name="customer_id",
                    data_type="VARCHAR(20)",
                    ordinal=0,
                    is_key_attribute=True,
                    description="Primary customer identifier",
                ),
                m.AssetColumn(
                    name="full_name",
                    data_type="VARCHAR(120)",
                    ordinal=1,
                    is_pii=True,
                    pii_type="person_name",
                    pii_confidence=0.98,
                ),
                m.AssetColumn(
                    name="email_addr",
                    data_type="VARCHAR(200)",
                    ordinal=2,
                    is_pii=True,
                    pii_type="email",
                    pii_confidence=0.99,
                ),
                m.AssetColumn(
                    name="date_of_birth",
                    data_type="DATE",
                    ordinal=3,
                    is_pii=True,
                    pii_type="date_of_birth",
                    pii_confidence=0.97,
                ),
                m.AssetColumn(name="branch_code", data_type="CHAR(4)", ordinal=4),
            ]
        if not db.scalar(select(m.Review).where(m.Review.asset_id == a1.id)):
            db.add(
                m.Review(
                    asset_id=a1.id,
                    reviewer_user_id=steward.id,
                    action=ReviewAction.approved,
                    changes={"description": {"before": None, "after": a1.description}},
                    comment="Approved proposal as-is.",
                )
            )

        # 2) Low-confidence asset waiting for a steward
        a2 = upsert_asset(
            "retail_banking.daily_transactions",
            business_domain="retail",
            overall_confidence=0.62,
            pipeline_status=PipelineStatus.enriched,
            governance_status=GovernanceStatus.pending_review,
        )
        if not a2.columns:
            a2.columns = [
                m.AssetColumn(name="txn_id", data_type="BIGINT", ordinal=0),
                m.AssetColumn(name="cust_ref", data_type="VARCHAR(20)", ordinal=1),
                m.AssetColumn(name="txn_amt", data_type="NUMERIC(15,2)", ordinal=2),
                m.AssetColumn(name="merchant_desc", data_type="VARCHAR(200)", ordinal=3),
            ]

        # 3) Cryptic legacy table — the LLM's home turf
        a3 = upsert_asset(
            "core.CDM_TBL_08",
            overall_confidence=0.55,
            pipeline_status=PipelineStatus.enriched,
            governance_status=GovernanceStatus.pending_review,
        )
        if not a3.columns:
            a3.columns = [
                m.AssetColumn(name="fld_01", data_type="VARCHAR(30)", ordinal=0),
                m.AssetColumn(name="fld_02", data_type="DECIMAL(12,2)", ordinal=1),
                m.AssetColumn(name="ref_id", data_type="VARCHAR(16)", ordinal=2),
            ]

        # --- glossary ---
        for term, definition, domain in [
            ("Customer Master", "Golden-source dataset of retail customer identity and relationships.", "retail"),
            ("KYC", "Know-Your-Customer records required under AML regulations.", "compliance"),
            ("Payment Event", "Any debit/credit posting against a customer account.", "retail"),
        ]:
            if not db.scalar(select(m.GlossaryTerm).where(m.GlossaryTerm.term == term)):
                db.add(m.GlossaryTerm(term=term, definition=definition, domain=domain, created_by="seed"))

        db.commit()

        n = lambda q: len(db.scalars(select(q)).all())  # noqa: E731
        print(
            f"✔ seeded: {n(m.User)} users, {n(m.OrgPerson)} org people, {n(m.DataSource)} sources, "
            f"{n(m.Asset)} assets, {n(m.GlossaryTerm)} glossary terms, {n(m.AuditEvent)} audit events"
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
