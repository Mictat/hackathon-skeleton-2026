<!-- # Agent Contracts

This doc is what lets the AI person and backend devs work in parallel on day −5 without a coordination meeting. Every agent returns JSON matching a Pydantic model; every result lands in enrichment_results.result; confidence is always float 0–1.

## Agent output contracts

### Classification agent:
```
{ "asset_sensitivity": "confidential", "confidence": 0.93, "columns": [ { "name": "email_addr", "is_pii": true, "pii_type": "email", "confidence": 0.99, "reasoning": "…" } ], "uncertain_columns": ["cust_ref"] }
```
### Ownership agent:
```
{ "business_domain": "retail", "domain_confidence": 0.90, "owner_candidates": [ { "person_id": 1, "score": 0.88, "match_reason": "Team 'Retail Data Platform' owns source system" } ], "rationale": "…" }
```
### Description agent:
```
{ "description": "…", "key_attributes": ["customer_id"], "glossary_terms": ["Customer Master"], "confidence": 0.82 }
``` -->



# Agent output contracts (v2 — implemented day -5)

Three agents run per asset per scan: classification, ownership, description.
Each writes one `enrichment_results` row: `result` JSON below, `confidence`
(agent-level), `model`, `from_cache`, `latency_ms`. Prompts are built ONLY
from metadata in `app/llm/prompts.py` — never data values.

## Degradation ladder (agents never hard-fail a run)
LLM unreachable/uncached → classification falls back to regex-only,
ownership to directory heuristics, description is skipped
(audit: `enrichment_failed`). Missing agents contribute 0.40 to the composite.

## Composite confidence
overall = 0.45*classification + 0.30*ownership + 0.25*description
ownership agent confidence = domain_confidence * (top candidate score,
or 0.20 if no candidate). Day -4: overall >= settings.confidence_threshold
→ auto_accepted, else pending_review.

## classification result
{asset_sensitivity: public|internal|confidential|restricted,
 sensitivity_confidence, degraded,
 columns: [{name, is_pii, pii_type, confidence, reasoning, source: regex|llm}]}
pii_type taxonomy: person_name, email, phone, date_of_birth, address,
national_id, income, bank_account. Regex tier is authoritative for its
hits (0.96); the LLM classifies the remaining columns only.

## ownership result
{business_domain: retail|lending|risk|finance|compliance|marketing|it|unknown,
 domain_confidence, owner_candidates: [{email, score, match_reason}] (max 3,
 must exist in the org directory), rationale, degraded}

## description result
{description, key_attributes (real column names only),
 glossary_terms (from the glossary only), confidence}

