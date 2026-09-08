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

**Verify it's working:**

| Check | Where |
|---|---|
| Status board (3 seeded assets, 3 governance states) | `http://localhost:8000` |
| Health check | `http://localhost:8000/api/health` |
| Browse the database (no CLI needed) | `http://localhost:8081` — system: PostgreSQL, server: `db`, user: `TEMPNAME`, password: `TEMPNAME_dev` |
| Smoke tests | `make test` (requires Docker DB running) |

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
│ Postgres     │──▶│ discovery →            │──▶│ triage by        │──▶│ searchable     │
│ files        │   │ classify / ownership / │   │ confidence:      │   │ catalog, PII   │
│ (mock menu:  │   │ describe, all results  │   │ auto-accept or   │   │ inventory,     │
│  Teradata,   │   │ to enrichment_results │   │ steward queue    │   │ lineage,       │
│  Snowflake…) │   │ every step audit-logged│  │ approve/edit/     │   │ compliance     │
└──────────────┘   └────────────────────────┘   │ reject            │   │ export         │
                                                └──────────────────┘   └────────────────┘
```

## Repository structure

```
TEMPNAME/
├── app/
│   ├── main.py             # FastAPI app factory; create_all runs on startup
│   ├── config.py           # pydantic-settings — all TEMPNAME_* env vars
│   ├── db.py               # engine, session factory, get_db dependency
│   ├── api/                # routes (health, home page); grows each day
│   ├── models/             # SQLAlchemy models — 12 tables, the whole catalog schema
│   ├── services/           # audit_log helper, settings (confidence threshold)
│   ├── templates/          # Jinja2 (status board today; full UI on day −3)
│   └── static/
├── scripts/
│   ├── reset_db.py         # drop + recreate all tables
│   └── seed_dev.py         # idempotent seed — PLACEHOLDER data until the
│   │                       #   synthetic bank-data generator replaces the content
├── docs/
│   └── agent_contracts.md  # JSON shapes every agent must return — READ THIS
│                           #   before touching agent or enrichment code
├── tests/
├── docker-compose.yml      # Postgres (pgvector-ready) :5433, Adminer :8081
├── pyproject.toml          # dependency source of truth
├── uv.lock                 # exact resolved versions — COMMITTED, keeps us aligned
├── requirements.txt        # generated pip mirror (`make requirements`)
└── tasks.py                # cross-platform task runner (replaces Makefile)
```

## Design decisions

The "why" behind the schema — read once, save arguments later:

1. **Two layers of truth.** `enrichment_results` stores what *agents proposed*
   (raw JSON + confidence + model). Curated fields on `assets` /
   `asset_columns` store what *humans approved*. A review action copies
   proposal → curated. This separation **is** the product: "AI proposes,
   humans dispose." Never collapse them.
2. **`audit_log` is append-only.** Every event — discovery, proposal,
   auto-accept, threshold change, review, export — lands here with actor
   (agent name or human). It's our compliance artifact and the answer to
   "what exactly did the AI decide?" No update/delete code paths, ever.
3. **Assets carry two status axes.** `pipeline_status` = where the agent
   pipeline is; `governance_status` = triage/review state. The confidence
   threshold re-triages between `auto_accepted` and `pending_review`
   **without re-running anything** — that's the slider demo moment.
4. **Credentials never enter the database.** `data_sources.connection_ref`
   holds a reference (host/db/path), not secrets. Secrets live in `.env`
   and are never committed.
5. **`create_all` never alters existing tables.** Change a model ⇒ `make init`
   (drop + recreate + reseed). Consequence: *if it's not in a seed script,
   it doesn't exist.* All demo state must be reproducible from
   `reset_db + seed + one scan run`.
6. **Confidence is `Float`**, not `Numeric` — avoids Decimal/JSON friction
   end-to-end. Always 0.0–1.0.
7. **Enum convention: member name == value** (e.g. `pending_review = "pending_review"`),
   stored as VARCHAR. Readable in Adminer, safe to filter on in queries.
8. **JSONB gotcha:** in-place mutation (`row.value["x"] = y`) is not tracked
   by SQLAlchemy and silently won't persist. Always reassign the whole dict.
9. **LLM calls are abstracted, cached, metadata-only.** Provider is
   swappable (public API for the hackathon; bank-hosted model in production),
   responses cache to `.llm_cache/` (deterministic demo, no internet needed
   at the venue), and only schema *metadata* is ever sent — never data values.
10. **UI = Jinja2 + htmx + Tailwind/DaisyUI** (day −3). Server-rendered
    fragments mean backend devs own the whole frontend; no JS build step.

## Team conventions

- **`app/models/` is owned by backend dev 1.** Everyone else PRs; they merge.
  One owner stops the schema forking.
- **Changed/added a dependency?** Update `pyproject.toml` → `uv sync` →
  `make requirements` → commit all three files together.
- **Changed a model?** Run `make init`, and update `scripts/seed_dev.py` if
  needed so the demo stays reproducible.
- **Agent output shapes are contracts.** They're specified in
  `docs/agent_contracts.md`. Change the doc first, then the code.
- **Never commit `.env`, API keys, or real data.** Synthetic data only.

## Environment variables

All prefixed `TEMPNAME_` (see `app/config.py`):

| Variable | Purpose | Default |
|---|---|---|
| `TEMPNAME_DATABASE_URL` | Postgres DSN | `postgresql+psycopg://TEMPNAME:TEMPNAME_dev@localhost:5433/TEMPNAME` |
| `TEMPNAME_LLM_PROVIDER` | LLM provider id (abstraction layer) | `openai` |
| `TEMPNAME_LLM_MODEL` | Model id | `gpt-4o-mini` |
| `TEMPNAME_LLM_API_KEY` | API key (from `.env`, never committed) | — |
| `TEMPNAME_LLM_CACHE_DIR` | Response cache directory (gitignored) | `.llm_cache` |

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
| `tasks.py requirements` | Regenerate `requirements.txt` from lockfile |
| `tasks.py install-pip` | Install via pip instead of uv |

## Build plan & status

| Day | Focus | Status |
|---|---|---|
| −7 | Foundation: schema, app skeleton, seed, contracts doc | ✅ done |
| −6 | Connector framework + SQL & file connectors; synthetic bank-data generator | ⬜ |
| −5 | LLM abstraction + cache; classification / ownership / description agents; confidence scoring | ⬜ |
| −4 | Triage + review workflow, threshold slider, audit events | ⬜ |
| −3 | UI: run dashboard, review queue, catalog, asset detail w/ lineage | ⬜ |
| −2 | Eval harness + accuracy numbers; compliance export | ⬜ |
| −1 | Freeze: rehearsals, deck, recorded demo fallback | ⬜ |
| +1–3 | On-site: adapt to bank intel, tune threshold, add assets, re-measure | ⬜ |

