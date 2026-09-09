"""
Rebuilds the synthetic enterprise environment from data/bank_environment.yaml:
  1. real Postgres database `bank_sample` (schemas, tables, comments, fake rows)
  2. file share under data/file_share/
  3. eval/ground_truth.csv — the labeling oracle for the day -2 eval harness

IMPORTANT: `comment:` fields are written to the DB and ARE visible to agents.
pii/domain/owner/sensitivity/gt_note are GROUND TRUTH ONLY — never written to
the environment. WARNING: regenerating OVERWRITES ground_truth.csv — coordinate
with Governance 2 (their reviewed copy is committed).

Run: uv run tasks.py generate
"""

import csv
import os
import random
import shutil
import re
from datetime import date, timedelta
from pathlib import Path

import yaml
from faker import Faker
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.connectors.sql import resolve_password

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = PROJECT_ROOT / "data" / "bank_environment.yaml"
FILE_SHARE = PROJECT_ROOT / "data" / "file_share"
GROUND_TRUTH = PROJECT_ROOT / "eval" / "ground_truth.csv"

FAKE = Faker()
Faker.seed(42)
random.seed(42)


def pg_literal(s: str) -> str:
    """COMMENT ON ... IS only accepts a string literal, not a bind parameter.
    Inline the value with quotes escaped — a doubled quote can't break out
    of the literal, so this is safe for our YAML-sourced strings."""
    return "'" + str(s).replace("'", "''") + "'"


def pii_value(pii_type: str):
    gen = {
        "person_name": lambda: FAKE.name(),
        "email": lambda: FAKE.email(),
        "phone": lambda: FAKE.phone_number(),
        "date_of_birth": lambda: FAKE.date_of_birth(minimum_age=18, maximum_age=90).isoformat(),
        "address": lambda: FAKE.address().replace("\n", ", "),
        "national_id": lambda: f"{FAKE.random_number(digits=3)}-{FAKE.random_number(digits=2)}-{FAKE.random_number(digits=4)}",
        "income": lambda: round(random.uniform(28000, 240000), 2),
        "bank_account": lambda: FAKE.iban(),
    }.get(pii_type)
    return gen() if gen else FAKE.word()


_KEY_SEQ: dict[str, int] = {}


def _declared_len(col: dict) -> int | None:
    """Max chars for char(n)/varchar(n) columns, else None."""
    t = str(col.get("type", "")).lower()
    if t.startswith(("char", "varchar")):
        m = re.search(r"\((\d+)\)", t)
        if m:
            return int(m.group(1))
    return None


def plain_value(col: dict):
    t = str(col.get("type", "")).lower()
    n = col["name"].lower()
    if col.get("key"):
        _KEY_SEQ[n] = _KEY_SEQ.get(n, 0) + 1
        if t.startswith(("int", "bigint", "smallint")):
            return 100000 + _KEY_SEQ[n]
        return f"{n.split('_')[0][:4].upper()}-{_KEY_SEQ[n]:06d}"
    if "currency" in n:
        return random.choice(["GBP", "EUR", "USD"])
    if n.endswith("_flag"):
        return random.choice(["Y", "N"])  # fits char(1) columns
    if "severity" in n:
        return random.choice(["LOW", "MED", "HIGH"])
    if "employment" in n:
        return random.choice(["EMPLOYED", "SELF-EMP", "RETIRED", "CONTRACT"])
    if "code" in n or n.endswith("_cd"):
        width = min(_declared_len(col) or 4, 8)  # branch_code et al: short codes
        return "".join(random.choices("ABCDEFGHJKLMNPRSTUVWXYZ0123456789", k=width))
    if "status" in n:
        return random.choice(["ACTV", "CLOS", "PEND", "REJ"])
    if t.startswith(("int", "bigint", "smallint")):
        return random.randint(1, 999999)
    if t.startswith(("numeric", "decimal", "float", "double")):
        return round(random.uniform(1, 100000), 2)
    if t.startswith("timestamp"):
        return FAKE.date_time_between(start_date="-2y").replace(microsecond=0).isoformat(sep=" ")
    if t.startswith("date"):
        return (date(2023, 1, 1) + timedelta(days=random.randint(0, 800))).isoformat()
    return FAKE.word()


def value_for(col: dict):
    v = pii_value(col["pii"]) if col.get("pii") else plain_value(col)
    width = _declared_len(col)
    if width and isinstance(v, str) and len(v) > width:
        v = v[:width]  # last-resort truncation — generator must never crash on YAML input
    return v


def _ensure_database(sources: list[dict]) -> dict:
    spec = next(s for s in sources if s["type"] == "postgres")["connection"]
    password = resolve_password(spec.get("password_env", "BANK_SAMPLE_PASSWORD"))
    admin = create_engine(get_settings().database_url)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f'DROP DATABASE IF EXISTS {spec["database"]} WITH (FORCE)'))
        exists = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": spec["user"]}).scalar()
        pw = pg_literal(password)
        if exists:
            c.execute(text(f'ALTER ROLE {spec["user"]} WITH LOGIN PASSWORD {pw}'))
        else:
            c.execute(text(f'CREATE ROLE {spec["user"]} WITH LOGIN PASSWORD {pw}'))
        c.execute(text(f'CREATE DATABASE {spec["database"]} OWNER {spec["user"]}'))
    admin.dispose()
    return spec


def _build_sample_db(spec: dict, schemas: list[dict], views: list[dict]) -> tuple[int, int]:
    password = resolve_password(spec.get("password_env", "BANK_SAMPLE_PASSWORD"))
    dsn = (
        f'postgresql+psycopg://{spec["user"]}:{password}'
        f'@{spec.get("host", "localhost")}:{spec.get("port", 5432)}/{spec["database"]}'
    )
    engine = create_engine(dsn)
    n_cols = 0
    with engine.begin() as c:
        for sch in schemas:
            c.execute(text(f'CREATE SCHEMA "{sch["schema"]}"'))
            for t in sch["tables"]:
                cols = t["columns"]
                defs = []
                for col in cols:
                    d = f'"{col["name"]}" {col["type"]}'
                    if col.get("key"):
                        d += " PRIMARY KEY"
                    if not col.get("nullable", True):
                        d += " NOT NULL"
                    defs.append(d)
                c.execute(text(f'CREATE TABLE "{sch["schema"]}"."{t["name"]}" (\n  ' + ",\n  ".join(defs) + "\n)"))
                if t.get("comment"):
                    c.execute(text(f'COMMENT ON TABLE "{sch["schema"]}"."{t["name"]}" IS {pg_literal(t["comment"])}'))
                for col in cols:
                    if col.get("comment"):
                        c.execute(
                            text(
                                f'COMMENT ON COLUMN "{sch["schema"]}"."{t["name"]}"."{col["name"]}" '
                                f'IS {pg_literal(col["comment"])}'
                            )
                        )
                names = [col["name"] for col in cols]
                placeholders = ", ".join(f":p{i}" for i in range(len(names)))
                target = f'"{sch["schema"]}"."{t["name"]}"'
                col_list = ", ".join(f'"{n}"' for n in names)
                rows = [{f"p{i}": value_for(col) for i, col in enumerate(cols)} for _ in range(t.get("rows", 25))]
                if rows:
                    c.execute(text(f"INSERT INTO {target} ({col_list}) VALUES ({placeholders})"), rows)
                n_cols += len(cols)
        for v in views:
            c.execute(text(f'CREATE VIEW "{v["schema"]}"."{v["name"]}" AS {v["sql"]}'))
        c.execute(text("ANALYZE"))
    engine.dispose()
    n_tables = sum(len(sch["tables"]) for sch in schemas)
    return n_tables, n_cols


def _csv_guess(col: dict):
    n = col["name"].lower()
    if any(k in n for k in ("amt", "balance", "score", "due", "amount", "income")):
        return round(random.uniform(1, 50000), 2)
    if n.endswith("_id") or n == "c_id":
        return random.randint(100000, 999999)
    if "date" in n or n.endswith("_dt"):
        return (date(2024, 1, 1) + timedelta(days=random.randint(0, 500))).isoformat()
    return FAKE.word()


def _build_file_share(files: list[dict]) -> None:
    if FILE_SHARE.exists():
        shutil.rmtree(FILE_SHARE)
    FILE_SHARE.mkdir(parents=True)
    (FILE_SHARE / ".gitkeep").touch()
    for f in files:
        path = FILE_SHARE / f["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        cols = f["columns"]
        rows = f.get("rows", 20)
        if path.suffix == ".parquet":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError:
                print(f"[warn] pyarrow missing — skipped {f['path']}")
                continue
            data = {
                c["name"]: [pii_value(c["pii"]) if c.get("pii") else _csv_guess(c) for _ in range(rows)] for c in cols
            }

            def arrow_type(values):
                v = next((x for x in values if x is not None), "")
                if isinstance(v, int):
                    return pa.int64()
                if isinstance(v, float):
                    return pa.float64()
                return pa.string()

            pq.write_table(
                pa.table({name: pa.array(vals, arrow_type(vals)) for name, vals in data.items()}),
                path,
            )
        else:
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow([c["name"] for c in cols])
                for _ in range(rows):
                    w.writerow([pii_value(c["pii"]) if c.get("pii") else _csv_guess(c) for c in cols])


def _write_ground_truth(data: dict) -> int:
    GROUND_TRUTH.parent.mkdir(exist_ok=True)
    rows = []
    for sch in data["database"]["schemas"]:
        for t in sch["tables"]:
            for col in t["columns"]:
                rows.append(
                    {
                        "source_type": "table",
                        "full_path": f'{sch["schema"]}.{t["name"]}',
                        "column": col["name"],
                        "is_pii": "Y" if col.get("pii") else "N",
                        "pii_type": col.get("pii", ""),
                        "sensitivity": t.get("sensitivity", ""),
                        "domain": t.get("domain", ""),
                        "owner": t.get("owner", ""),
                        "notes": t.get("gt_note", ""),
                    }
                )
    for v in data.get("views", []):
        rows.append(
            {
                "source_type": "view",
                "full_path": f'{v["schema"]}.{v["name"]}',
                "column": "(view)",
                "is_pii": "N",
                "pii_type": "",
                "sensitivity": v.get("sensitivity", ""),
                "domain": v.get("domain", ""),
                "owner": v.get("owner", ""),
                "notes": v.get("gt_note", ""),
            }
        )
    for f in data.get("files", []):
        for col in f["columns"]:
            rows.append(
                {
                    "source_type": "file",
                    "full_path": f["path"],
                    "column": col["name"],
                    "is_pii": "Y" if col.get("pii") else "N",
                    "pii_type": col.get("pii", ""),
                    "sensitivity": f.get("sensitivity", ""),
                    "domain": f.get("domain", ""),
                    "owner": f.get("owner", ""),
                    "notes": f.get("gt_note", ""),
                }
            )
    with GROUND_TRUTH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


ALLOWED_COL_KEYS = {"name", "type", "pii", "key", "comment", "nullable", "gt_note"}
ALLOWED_TABLE_KEYS = {"name", "domain", "owner", "sensitivity", "comment", "rows", "columns", "gt_note"}


def validate_yaml(data: dict) -> None:
    """Catch the classic YAML flow-mapping trap before it becomes a cryptic SQL
    error: an unquoted comma inside a value (e.g. type: numeric(18,2)) silently
    splits the entry and leaves a stray key like '2)'."""
    problems: list[str] = []

    def check_cols(cols: list[dict], where: str) -> None:
        for c in cols:
            extra = set(c) - ALLOWED_COL_KEYS
            if extra:
                problems.append(
                    f'{where}: column "{c.get("name")}" has stray keys {sorted(extra)} — '
                    f'quote values containing commas, e.g. type: "numeric(18,2)"'
                )

    for sch in data.get("database", {}).get("schemas", []):
        for t in sch.get("tables", []):
            where = f'{sch["schema"]}.{t["name"]}'
            t_extra = set(t) - ALLOWED_TABLE_KEYS
            if t_extra:
                problems.append(f"{where}: unexpected table keys {sorted(t_extra)} — typo?")
            check_cols(t.get("columns", []), where)
    for f in data.get("files", []):
        check_cols(f.get("columns", []), f["path"])

    if problems:
        raise SystemExit("[yaml] fix these in data/bank_environment.yaml:\n  - " + "\n  - ".join(problems))


def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text())
    validate_yaml(data)
    spec = _ensure_database(data["sources"])
    n_tables, n_cols = _build_sample_db(spec, data["database"]["schemas"], data.get("views", []))
    _build_file_share(data.get("files", []))
    n_gt = _write_ground_truth(data)
    print(
        f"[ok] bank_sample rebuilt: {len(data['database']['schemas'])} schemas, "
        f"{n_tables} tables, {len(data.get('views', []))} views, {n_cols} columns, "
        f"{len(data.get('files', []))} files"
    )
    print(f"[ok] ground truth -> {GROUND_TRUTH} ({n_gt} rows)")


if __name__ == "__main__":
    main()
