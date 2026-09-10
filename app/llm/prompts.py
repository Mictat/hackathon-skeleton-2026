"""Prompt builders — METADATA ONLY. Never put data values in messages.
The same builders are used by enrichment AND `tasks.py doctor`, so a doctor
cache check is guaranteed to match the real prompts."""

SYSTEM = (
    "You are an AI data-governance agent working inside a bank. You receive only "
    "structural metadata (names, types, comments, row counts) — never data values. "
    "Answer strictly as JSON matching the requested schema. Be conservative: when "
    "unsure, lower your confidence rather than guessing."
)

PII_TAXONOMY = ["person_name", "email", "phone", "date_of_birth", "address", "national_id", "income", "bank_account"]
DOMAINS = ["retail", "lending", "risk", "finance", "compliance", "marketing", "it", "unknown"]


def asset_context(asset) -> str:
    cols = []
    for c in asset.columns:
        bits = [f"{c.name} {c.data_type or ''}".strip()]
        if c.raw_comment:
            bits.append(f"comment: {c.raw_comment}")
        cols.append("  - " + ", ".join(bits))
    lines = [f"Asset: {asset.full_path}", f"Type: {asset.asset_type.value}  Rows: {asset.row_count}"]
    if asset.raw_comment:
        lines.append(f"Asset comment: {asset.raw_comment}")
    lines.append("Columns:")
    lines += cols or ["  (none)"]
    return "\n".join(lines)
