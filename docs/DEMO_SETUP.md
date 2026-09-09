# Demo Setup Runbook

**Audience:** anyone on the team (or a fresh laptop) who needs the app demo-ready.
Written for Windows PowerShell; identical on macOS/Linux.
**Owner:** Governance 3 (demo logistics). If a step is wrong, fix it here
immediately — this doc is the source of truth for demo state.

## When to use this

| Scenario | Section |
|---|---|
| Fresh laptop / new teammate | §2 (≈15 min) |
| Reset to known-good state (rehearsal or demo day) | §3 (≈3 min) |
| Something broke | §7 Troubleshooting |

## 1. Prerequisites (fresh machine only)

- Git
- Docker Desktop — installed **and running** (whale icon in system tray)
- Python 3.11+ (3.12 recommended — see §7 if you're on 3.14)
- uv — PowerShell:
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  then **reopen the terminal**

## 2. Fresh setup

```powershell
git clone <repo-url> cairn
cd cairn
Copy-Item .env.example .env

uv run tasks.py db-up        # Postgres :5433 + Adminer :8081
uv sync                      # first run takes a couple of minutes (pyarrow)

uv run tasks.py demo         # generate -> init -> register, in order
uv run tasks.py dev          # -> http://localhost:8000
```

What `demo` actually chains, in case you need the pieces:

| Command | Does | Expected output |
|---|---|---|
| `tasks.py generate` | rebuilds `bank_sample` DB + `data/file_share/` + `eval/ground_truth.csv` from the YAML | `[ok] bank_sample rebuilt: 8 schemas, 15 tables, 1 views, 95 columns, 3 files` |
| `tasks.py init` | wipes + reseeds the catalog | `[ok] database reset — 12 tables created` then `[ok] seeded: 3 users, 6 org people, 1 sources, 3 assets, 3 glossary terms, 1 audit events` |
| `tasks.py register` | registers the 2 real sources + org directory (idempotent) | `[ok] registered 2 sources, 9 org people` |

**Verify the cold state (before any scan):**

- `http://localhost:8000` shows 3 sources:
  - *Demo Placeholder* — `mock` badge, **no Scan button**, 3 assets
  - *Retail Core DB (PostgreSQL)* — connected, 0 assets, "never" scanned
  - *Analytics File Share* — connected, 0 assets, "never" scanned
- Status cards: In review **2**, Approved **1**, everything else 0
- `uv run tasks.py test` passes

> If the placeholder is named "Retail Core DB (dev)" **and has a Scan
> button**, the seed-dev patch (rename + `status="mock"`) isn't applied —
> apply it, then re-run `tasks.py init`.

**Warm it up:** click **Scan** on both real sources, then check §5.

## 3. Demo-day / rehearsal reset (≈3 min)

```powershell
git pull
uv sync
uv run tasks.py db-up
uv run tasks.py reset      # catalog only: init + register — no regeneration
uv run tasks.py dev
```

- Use `reset` (not `demo`) during the week: it never touches
  `eval/ground_truth.csv`, so Governance 2's reviewed copy is safe.
- Use the full `tasks.py demo` only on a fresh machine or after the YAML
  changed (and warn Governance 2 — `generate` rewrites their file).
- Verify the cold state (§2 checklist), then rehearse the scan once.

## 4. Show mode (.env)

```
ATLAS_SCAN_PACING_MS=150
```

- 150 ms/asset → the Retail Core scan visibly streams (~2.5 s for 16 assets)
- Settings are read once at app start — **restart `tasks.py dev`** after
  editing `.env`
- Use `0` while setting up/verifying (fast), `150` for rehearsal and stage
- ⏳ Day −5 adds LLM cache pre-warm + replay-mode settings here

## 5. Known-good numbers (post-scan "warm" state)

The single check that everything is healthy:

| Check | Expected |
|---|---|
| Bank environment | 8 schemas, 15 tables, 1 view, 3 files |
| Total assets | **22** (19 real + 3 placeholder) |
| Governance cards | Pending **19** · In review **2** · Approved **1** |
| Pipeline pills | Discovered **19** · Enriched **3** |
| Retail Core DB | connected, 16 assets, run `completed (+16 new)` |
| Analytics File Share | connected, 3 assets, run `completed (+3 new)` |
| Re-scan either source | `new: 0`, governance states untouched |

Adminer — `http://localhost:8081`, system **PostgreSQL**, server `db`,
user `cairn`, password `cairn_dev`, database `cairn`:

```sql
SELECT event_type, count(*) FROM audit_log
WHERE event_type LIKE 'scan%' OR event_type = 'asset_discovered'
GROUP BY event_type;
```

Against `bank_sample` (user `bank`, password `bank_dev`):

```sql
SELECT obj_description('retail_banking.customer_master'::regclass);  -- the golden-source comment
SELECT obj_description('core.CDM_TBL_08'::regclass);                 -- NULL: no hints for the agents
```

> **When Governance 1 adds tables to the YAML, update this table.** It's how
> the whole team knows what "healthy" looks like.

## 6. What you can demo today (day −6 state, ~90 seconds)

1. **Board, cold:** "This bank has data everywhere and no map of it."
2. **Click Scan** on Retail Core DB — Discovered pill climbs to 16,
   run badge goes `running → completed`.
3. **Click Scan** on the file share — +3 more.
4. **"Every step is audit-logged"** — run the audit SQL above in Adminer.
5. **The honesty moment** (Adminer, `bank_sample`): real tables, real types,
   comments on the obvious tables, `NULL` on `CDM_TBL_08` — *"the agents see
   only this. No labels. Ground truth lives outside the environment."*

⏳ Sections that fill in as features land — this runbook is the demo-day
source of truth:

- **Day −5:** run enrichment + pre-warm the LLM cache (zero-internet replay)
- **Day −4:** seed the demo review state (an approved example for the story)
- **Day −3:** link to `docs/demo_script.md` (Governance 3 owns the script)
- **Day −2:** accuracy numbers + compliance export steps
- **Day −1:** final freeze checklist + recorded fallback video

## 7. Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| `make: not recognized` | We don't use make — every command is `uv run tasks.py <cmd>` |
| `uv` not recognized | Reopen the terminal after installing, or `pip install uv` |
| Docker errors / "cannot connect to daemon" | Start Docker Desktop, wait for the whale icon, then `uv run tasks.py db-up` |
| Port 5433 already in use | A local Postgres is running. Change the host port in `docker-compose.yml`, in `ATLAS_DATABASE_URL` (.env), **and** in the YAML's `connection.port`, then `tasks.py demo` |
| Scan fails: connection refused, port 5432 | A source's `connection_ref` is incomplete (needs host, port 5433, user `bank`). See the error: `Invoke-RestMethod http://localhost:8000/api/sources` |
| `generate` exits with `[yaml] fix these...` | Unquoted comma in a type — quote it: `type: "numeric(18,2)"` |
| Board looks stale / missing tables after `git pull` | Models changed; `create_all` never alters — run `uv run tasks.py demo` |
| Deep SQLAlchemy errors on Python 3.14 | `uv python pin 3.12`, delete `.venv`, `uv sync` |
| Placeholder has a Scan button / named "Retail Core DB (dev)" | Apply the seed-dev patch (rename + `status="mock"`), re-run `tasks.py init` |

## 8. Demo-day kit

- [ ] Primary laptop **and backup laptop**, both verified against §5
- [ ] Recorded full-demo video (day −1) — local copy, not only cloud
- [ ] Phone hotspot (venue WiFi is a risk; day −5 replay mode removes the dependency)
- [ ] Browser: fresh profile, only two tabs — `:8000` and `:8081`, zoom set
- [ ] Adminer creds known: `cairn`/`cairn_dev`, `bank`/`bank_dev`, server `db`
- [ ] Run the §3 reset **30 minutes before** going on stage
- [ ] Rehearse the scan once after reset
