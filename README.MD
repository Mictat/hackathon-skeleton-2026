# TEMPNAME ⛰️

**AI-powered data discovery & governance.**

TEMPNAME points AI agents at the bank's data environments. They discover assets,
classify PII, infer ownership, and draft descriptions — every proposal
confidence-scored and audit-logged. Stewards review, correct, and approve.
Agents do the grunt work; humans make the judgments.

> Hackathon build — current progress in **Build plan & status** at the bottom.

---

## Quick start

**Prerequisites:** Python 3.11+, Docker, and [uv](https://docs.astral.sh/uv/)
(recommended) or pip.

```bash
git clone <repo-url> cairn && cd cairn
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
docker compose up -d          # Postgres :5433 + Adminer :8081 (Docker Desktop must be running)
uv sync                       # or: python tasks.py install-pip
uv run tasks.py init          # fresh schema + seed data
uv run tasks.py dev           # → http://localhost:8000
```

Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux)
or `pip install uv`.

**Troubleshooting:**
- *Port 5433 already in use* → another local Postgres; change the host port in `docker-compose.yml`.
- *`make dev` connects then fails* → check `docker compose ps` shows `db` as healthy, and `.env` matches `docker-compose.yml` credentials.
- *Schema looks stale after pulling changes* → someone changed a model; run `make init`.
- *`uv` not recognized (Windows)* → reopen the terminal after installing, or
  `pip install uv`. PowerShell installer:
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- *`docker` not recognized* → start Docker Desktop from the Start menu, wait
  for the whale icon, then `uv run tasks.py db-up`.

## How it works

```
 data sources         agent pipeline                human review            consumers
┌──────────────┐   ┌────────────────────────┐   ┌──────────────────┐   ┌────────────────┐
│ Postgres     │──▶│ discovery →            │──▶│ triage by       │──▶│ searchable     │
│ files        │   │ classify / ownership / │   │ confidence:      │   │ catalog, PII   │
│ (mock menu:  │   │ describe, all results  │   │ auto-accept or   │   │ inventory,     │
│  Teradata,   │   │ to enrichment_results  │   │ steward queue    │   │ lineage,       │
│  Snowflake…) │   │ every step audit-logged│   │ approve/edit/    │   │ compliance     │
└──────────────┘   └────────────────────────┘   │ reject           │   │ export         │
                                                └──────────────────┘   └────────────────┘
```

## Task commands

All via `uv run tasks.py <command>` (or `python tasks.py <command>` with an
activated venv). Works identically on Windows, macOS, and Linux.

| Command | What it does |
|---|---|
| `tasks.py install` | `uv sync` |
| `tasks.py db-up` / `db-down` | Start/stop Postgres + Adminer via Docker |
| `tasks.py init` | Reset schema + seed placeholder data |
| `tasks.py dev` | Run app with hot reload (`:8000`) |
| `tasks.py test` | Smoke tests (needs DB up) |
| `tasks.py fmt` | ruff format |

## Build plan & status

| Day | Focus | Status |
|---|---|---|
| −7 | Foundation: schema, app skeleton, seed, contracts doc | ✅ done |
| −6 | Connector framework + SQL & file connectors; synthetic bank-data generator | ✅ done |
| −5 | LLM abstraction + cache; classification / ownership / description agents; confidence scoring | ✅ done |
| −4 | Triage + review workflow, threshold slider, audit events | ✅ done |
| −3 | UI: run dashboard, review queue, catalog, asset detail w/ lineage | ✅ done |
| −2 | Eval harness + accuracy numbers; compliance export | ⬜ |
| −1 | Freeze: rehearsals, deck, recorded demo fallback | ⬜ |
| +1–3 | On-site: adapt to bank intel, tune threshold, add assets, re-measure | ⬜ |

