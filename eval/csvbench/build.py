"""Ingest the benchmark CSVs and validate the gold queries.   python -m eval.csvbench.build [--write | --check]

Same checks as eval.build_gold: the validator accepts the query, it runs, the result is non-empty, not a bare 0/NULL,
deterministic (two runs identical), and not tied at a LIMIT boundary. --check recomputes every result hash and compares it with
the committed questions.jsonl, which proves the ingest + data reproduce the same gold answers on another machine.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.ingest import IngestError, TableMeta, ingest_file
from guardrails.executor import execute_safe

from .fetch import CACHE, FetchError, is_verified, load_manifest, raw_path
from .gold_source import GOLD

QUESTIONS = Path(__file__).with_name("questions.jsonl")
BIG = 100_000


@dataclass
class Prepared:
    db_path: Path
    tables: list[TableMeta]

    @property
    def allowed(self) -> set[str]:
        return {t.name for t in self.tables}


def prepare(manifest: dict | None = None, cache: Path = CACHE) -> dict[str, Prepared]:
    """Verify each downloaded file and ingest it into its own SQLite database (cache/csvbench/db/<id>.sqlite)."""
    manifest = manifest or load_manifest()
    out = {}
    for e in manifest["datasets"]:
        if not is_verified(e, cache):
            raise FetchError(f"{e['file']} is missing or fails its SHA-256 check. Run: python -m eval.csvbench.fetch")
        db = Path(cache) / "db" / f"{e['id']}.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        for f in db.parent.glob(f"{e['id']}.sqlite*"):
            f.unlink()
        try:
            res = ingest_file(e["file"], raw_path(e, cache).read_bytes(), str(db))
        except IngestError as ex:
            raise FetchError(f"{e['file']} could not be ingested: {ex}") from ex
        if [t.name for t in res.tables] != [e["table"]]:
            raise FetchError(f"{e['file']}: expected table {e['table']!r}, ingest produced {[t.name for t in res.tables]}")
        out[e["id"]] = Prepared(db, res.tables)
    return out


def norm_rows(rows):
    return [tuple(round(v, 4) if isinstance(v, float) else v for v in r) for r in rows]


def result_hash(rows) -> str:
    return hashlib.sha256(json.dumps(norm_rows(rows), default=str).encode()).hexdigest()[:16]


def check_gold(p: Prepared, sql: str, key) -> tuple[object | None, str | None]:
    """Returns (ExecResult, None) when the gold query is acceptable, else (None, reason)."""
    run = lambda q: execute_safe(p.db_path, q, p.allowed, timeout_s=20, row_limit=BIG)
    a, b = run(sql), run(sql)
    if not a.ok:
        return None, f"gold failed: {a.code} {a.error}"
    if norm_rows(a.rows) != norm_rows(b.rows):
        return None, "nondeterministic"
    if not a.rows:
        return None, "EMPTY result"
    if len(a.rows) == 1 and len(a.rows[0]) == 1 and a.rows[0][0] in (0, 1, None):
        return None, f"TRIVIAL answer {a.rows[0][0]!r} (SELECT 0 / SELECT 1 would match by luck)"
    m = re.search(r"\s+LIMIT\s+(\d+)\s*$", sql, re.I)
    if m:
        if key is None:
            return None, "LIMIT without limit_key (tie unchecked)"
        n = int(m.group(1))
        full = run(sql[:m.start()])
        if len(full.rows) > n and full.rows[n - 1][key] == full.rows[n][key]:
            return None, f"TIE at LIMIT {n}: {full.rows[n - 1][key]!r}"
    if len(a.rows) > 500:
        return None, f"large result ({len(a.rows)} rows)"
    return a, None


def build(gold=GOLD, prepared: dict[str, Prepared] | None = None, manifest: dict | None = None, cache: Path = CACHE):
    prepared = prepared or prepare(manifest, cache)
    counters, problems, records = {}, [], []
    for ds, cat, diff, question, sql, ordered, key in gold:
        counters[ds] = counters.get(ds, 0) + 1
        qid = f"{ds}-{counters[ds]:02d}"
        if ds not in prepared:
            problems.append((qid, f"unknown dataset {ds}"))
            continue
        res, why = check_gold(prepared[ds], sql, key)
        if why:
            problems.append((qid, why))
            continue
        records.append(dict(id=qid, dataset=ds, category=cat, difficulty=diff, question=question, gold_sql=sql, ordered=ordered,
                            n_rows=len(res.rows), n_cols=len(res.columns), result_hash=result_hash(res.rows)))
    return records, problems


def main(argv: list[str]) -> int:
    try:
        records, problems = build()
    except FetchError as e:
        print("ERROR:", e)
        return 1
    for qid, why in problems:
        print(f"  [{qid}] {why}")
    print(f"{len(records)} valid / {len(GOLD)} written")
    if "--check" in argv:
        old = {r["id"]: r for r in map(json.loads, QUESTIONS.read_text().splitlines() if QUESTIONS.exists() else [])}
        bad = [r["id"] for r in records if r["id"] not in old or old[r["id"]]["result_hash"] != r["result_hash"]]
        missing = sorted(set(old) - {r["id"] for r in records})
        print(f"hash check: {len(records) - len(bad)} match, {len(bad)} differ {bad[:5]}, {len(missing)} missing")
        return 1 if (bad or missing or problems) else 0
    if "--write" in argv and not problems:
        QUESTIONS.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        print("wrote", QUESTIONS)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
