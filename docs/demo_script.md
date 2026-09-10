# 5-minute demo script

**NEVER DEBUG LIVE**

## Pre-stage (T-30, from DEMO_SETUP.md)

- [ ] `uv run tasks.py reset` + `dev`, pacing ON (`TEMPNAME_SCAN_PACING_MS=150`,
      `TEMPNAME_ENRICH_PACING_MS=600`), `TEMPNAME_LLM_OFFLINE=1`, doctor = READY
- [ ] Browser: fresh profile, two tabs (`:8000`, `:8081`), zoom ~110%
- [ ] Acting as Sarah Chen (navbar)
- [ ] Video backup open locally; hotspot ready

## The script

### Act 1 — The problem (0:00–0:30) — board, cold
> "We asked around the bank what data environments exist. Nobody could give us
> a complete picture — and that's a *governance* problem, not an IT problem.
> Unmapped data is unmanaged risk: unknown PII, unknown owners, unknown lineage."

*(Board: 2 sources, zero assets.)*
> "Today, mapping one environment takes months of manual interviews and
> spreadsheets. Watch what happens when agents do it."

### Act 2 — The run (0:30–2:15)
1. Click **＋ Register source** → pick **Snowflake — roadmap** → name it
   "Wholesale Payments (Snowflake)" → Register.
   > "Onboarding an environment is *configuration, not a project*. Even
   > not-yet-connected environments are tracked — coverage you can see."
2. Back on the board → **Scan** on Retail Core DB. Click the `running` badge →
   the run page: assets streaming, then per-asset: three agents fan out —
   classification, ownership, description. Point at the event stream.
   > "Every proposal is confidence-scored and audit-logged with provenance —
   > model, cache, latency. We only ever send **metadata**: names, types,
   > comments. Never a single data value."
3. Let it finish; back to the board.
   > "Nineteen assets, fully profiled, in about two minutes. Manually?
   *Months.*"
4. **Scan** the file share → +3. "Same story for files — including the
   uncontrolled extracts people drop on shares."

### Act 3 — Governance (2:15–3:45)
1. **The slider:** drag to ~0.70.
   > "The institution decides how much judgment to delegate. Watch the
   > workload re-price itself — instantly, no re-scan. Drag it up, humans
   > decide more. Nothing already approved ever moves."
2. **Review queue** (lowest confidence first — say why):
   > "The queue is ordered by where human judgment adds the most value."
   Open **core.CDM_TBL_08** — cryptic legacy table.
   > "Regex found nothing here. The LLM read the metadata and proposed that
   > fld_02 and fld_03 look like name and date-of-birth."
   Edit-and-approve: fix the description, set owner **Priya Sharma**, comment
   "fld mapping confirmed with Core Systems".
3. Quick-approve one obvious asset from the queue. **Reject**
   `tmp_2023_q1_export` — comment: "uncontrolled extract — flagged to Marketing."
4. **Audit page** → filter *Human reviews*.
   > "Every decision — agent and human — with who, what, when, and the diff."

### Act 4 — The payoff (3:45–5:00)
1. **Catalog** → preset chip **🔒 Customer PII · Retail Banking**.
   > "'Show me every customer-PII dataset owned by Retail Banking' —
   > instant. This query took stakeholder interviews last quarter."
2. Clear filters, search `retail_customers`:
   > "And here's the finding: a marketing-owned PII extract sitting on a
   > file share — with lineage pointing back at the customer master.
   > That's a governance incident we just discovered in a demo."
3. Closer:
   > "Agents propose; the institution chooses how much to trust them; humans
   > dispose; everything is provenance-tracked. Discovery in minutes, not
   > months — and onboarding the next environment is five minutes of config.
   > That's Solve Smart, Grow Strong, Scale Fast."



## Q&A bank (one-line answers, expand naturally)
- **"You'd send metadata to a public LLM?"** — "Provider is swappable config; production runs bank-hosted or approved-vendor models. And metadata only — never data values; that's enforced in the connector layer, not policy."
- **"How does this fit Collibra/Alation?"** — "We feed governed catalogs — our connector menu is how we plug into the estate. We're the automation layer that fills them."
- **"What about lineage?"** — "Source-level, inferred from metadata, shown with confidence. Column-level and human-confirmed lineage are on the roadmap."
- **"What if the agents are wrong?"** — "That's the whole design: confidence scores, a threshold the institution sets, and a review queue for everything below it. Wrong proposals never reach the catalog silently."
- **"Scale?"** — "Marginal cost per environment is config. Agents fan out per asset; the pipeline already survived an LLM outage in testing — it degrades, never dies."

