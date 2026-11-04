"""Build the static replay site (GitHub Pages) from saved, verified answers and recorded red-team runs.

  python -m eval.export_static --out site

Nothing here calls a model. Example answers are re-executed against the real database through the same guardrails the API uses;
"blocked" examples are the model's real attempts recorded by `python -m eval.redteam`, re-validated here. Every response has
the exact JSON shape of /api/ask, so the page renders it with the same code as the live app.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from app.api import make_response, policy_response
from app.config import Settings
from app.intent import write_intent
from app.schema import extract_schema
from guardrails.executor import execute_safe
from guardrails.validator import validate_sql

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DEMO = ROOT / "app" / "demo_answers.json"
RESULTS = ROOT / "results"
POLICY_PROMPTS = ["Please truncate the Customer table", "Update every track price to zero"]
MAX_BLOCKED = 6


def _schema(allowed_db=None):
    return [{"table": t.name, "rows": t.row_count,
             "columns": [{"name": c.name, "type": c.type, "pk": c.pk} for c in t.columns],
             "foreign_keys": [f"{f.column} -> {f.ref_table}.{f.ref_column}" for f in t.fks]} for t in extract_schema()]


def build_examples(demo: list[dict], st: Settings, tables: set[str], db_path) -> list[dict]:
    out = []
    for d in demo:
        res = execute_safe(db_path, d["sql"], tables, st.query_timeout_s, st.row_limit)
        if not res.ok:
            continue                                            # never publish an example that no longer runs
        used = sorted(validate_sql(d["sql"], tables).tables)
        out.append(make_response(question=d["question"], approach="self_correct", res=res, sql=d["sql"], tables=used, attempts=1,
                                 source="saved", model=st.model, row_limit=st.row_limit))
    return out


def build_blocked(redteam: dict | None, st: Settings, tables: set[str], db_path) -> list[dict]:
    if not redteam:
        return []
    picked, per_code = [], {}
    for r in redteam.get("rows", []):
        if r.get("outcome") != "blocked" or not r.get("sql"):
            continue
        per_code[r["code"]] = per_code.get(r["code"], 0) + 1
        if per_code[r["code"]] <= 2:
            picked.append(r)
    out = []
    for r in picked[:MAX_BLOCKED]:
        res = execute_safe(db_path, r["sql"], tables, st.query_timeout_s, st.row_limit)   # re-validate: must still be blocked
        if res.ok:
            continue
        out.append(make_response(question=r["prompt"], approach=redteam.get("approach", "self_correct"), res=res, sql=r["sql"], tables=[],
                                 attempts=1, source="recorded", model=st.model, row_limit=st.row_limit))
    return out


def build_policy(st: Settings) -> list[dict]:
    return [policy_response(q, "self_correct", st.model, st.row_limit) for q in POLICY_PROMPTS if write_intent(q)]


def export(out: Path, demo_path: Path = DEMO, redteam_path: Path | None = None, db_path=None) -> dict:
    from app.schema import DEFAULT_DB
    db_path = db_path or DEFAULT_DB
    st = Settings()
    tables = {t["table"] for t in _schema()}
    demo = json.loads(Path(demo_path).read_text()) if Path(demo_path).exists() else []
    if redteam_path is None:
        found = sorted(RESULTS.glob("redteam__*__safe.json"))
        redteam_path = found[0] if found else None
    redteam = json.loads(Path(redteam_path).read_text()) if redteam_path and Path(redteam_path).exists() else None

    examples = build_examples(demo, st, tables, db_path)
    if not examples:
        raise SystemExit("no usable saved examples: run `python -m eval.export_demo` first (the static page would be empty)")
    data = {"examples": examples, "blocked": build_blocked(redteam, st, tables, db_path) + build_policy(st), "schema": _schema(),
            "model": st.model}

    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    html = (STATIC / "index.html").read_text()
    html = (html.replace('<html lang="en">', '<html lang="en" data-mode="static">')
                .replace('href="/static/app.css"', 'href="app.css"')
                .replace('<script src="/static/app.js" defer></script>', '<script src="static-api.js"></script>\n  <script src="app.js" defer></script>'))
    (out / "index.html").write_text(html)
    for name in ("app.css", "app.js", "static-api.js"):
        shutil.copy(STATIC / name, out / name)
    (out / "data.json").write_text(json.dumps(data))
    (out / ".nojekyll").write_text("")
    return {"examples": len(examples), "blocked": len(data["blocked"]), "out": str(out)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    a = ap.parse_args()
    r = export(Path(a.out))
    print(f"wrote {r['out']}: {r['examples']} verified examples, {r['blocked']} blocked requests")


if __name__ == "__main__":
    main()
