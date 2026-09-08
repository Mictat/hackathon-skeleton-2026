# Agent Contracts

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
```
