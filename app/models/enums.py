import enum


class SourceType(str, enum.Enum):
    postgres = "postgres"
    mysql = "mysql"
    sqlserver = "sqlserver"
    file = "file"
    s3 = "s3"
    teradata = "teradata"  # mock menu
    snowflake = "snowflake"  # mock menu
    mainframe = "mainframe"  # mock menu
    hadoop = "hadoop"  # mock menu


class Environment(str, enum.Enum):
    production = "production"
    analytics = "analytics"
    development = "development"
    sandbox = "sandbox"


class AssetType(str, enum.Enum):
    table = "table"
    view = "view"
    file = "file"
    report = "report"


class Sensitivity(str, enum.Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


class PipelineStatus(str, enum.Enum):
    discovered = "discovered"  # seen by connector, not yet enriched
    enriching = "enriching"
    enriched = "enriched"
    failed = "failed"


class GovernanceStatus(str, enum.Enum):
    pending = "pending"  # enrichment done, triage not yet applied
    auto_accepted = "auto_accepted"  # confidence >= threshold
    pending_review = "pending_review"  # confidence < threshold
    approved = "approved"
    rejected = "rejected"


class UserRole(str, enum.Enum):
    admin = "admin"
    steward = "steward"
    viewer = "viewer"


class ReviewAction(str, enum.Enum):
    approved = "approved"
    edited = "edited"
    rejected = "rejected"
    reopened = "reopened"


class ActorType(str, enum.Enum):
    system = "system"
    agent = "agent"
    human = "human"
