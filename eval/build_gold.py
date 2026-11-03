"""Validate gold queries and write eval/questions.jsonl.  Usage: python -m eval.build_gold [--write]

Checks per question: validator accepts it, runs OK, non-empty, deterministic (2 runs identical),
no tie at the LIMIT boundary (when limit_key is given). Split: stratified dev/test (seeded).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from app.schema import DEFAULT_DB, table_names
from guardrails.executor import execute_safe

from .gold_source import GOLD

OUT = Path(__file__).parent / "questions.jsonl"
TABLES = set(table_names())
BIG = 100_000
DEV_FRACTION = 0.35
SEED = 42


def norm_rows(rows):
    return [tuple(round(v, 4) if isinstance(v, float) else v for v in r) for r in rows]


def run(sql):
    return execute_safe(DEFAULT_DB, sql, TABLES, timeout_s=20, row_limit=BIG)


def main(write: bool):
    problems, records = [], []
    for i, (cat, diff, question, sql, ordered, key) in enumerate(GOLD, 1):
        qid = f"q{i:03d}"
        a, b = run(sql), run(sql)
        if not a.ok:
            problems.append((qid, f"gold failed: {a.code} {a.error}")); continue
        if norm_rows(a.rows) != norm_rows(b.rows):
            problems.append((qid, "nondeterministic")); continue
        if not a.rows:
            problems.append((qid, "EMPTY result")); continue
        if len(a.rows) == 1 and len(a.rows[0]) == 1 and a.rows[0][0] in (0, None):
            problems.append((qid, f"TRIVIAL answer {a.rows[0][0]!r} (a wrong query could match by luck)")); continue
        m = re.search(r"\s+LIMIT\s+(\d+)\s*$", sql, re.I)
        if m and key is not None:
            n = int(m.group(1))
            full = run(sql[:m.start()])
            if len(full.rows) > n and full.rows[n - 1][key] == full.rows[n][key]:
                problems.append((qid, f"TIE at LIMIT {n}: {full.rows[n-1][key]!r}")); continue
        if m and key is None and not re.search(r"LIMIT\s+1\s*$", sql, re.I):
            problems.append((qid, "LIMIT without limit_key (tie unchecked)")); continue
        if len(a.rows) > 500:
            problems.append((qid, f"large result ({len(a.rows)} rows)"))
        h = hashlib.sha256(json.dumps(norm_rows(a.rows), default=str).encode()).hexdigest()[:16]
        records.append(dict(id=qid, category=cat, difficulty=diff, question=question, gold_sql=sql,
                            ordered=ordered, n_rows=len(a.rows), n_cols=len(a.columns), result_hash=h))

    # dev/test split: keep any existing assignment (so tuning on dev is never invalidated), stratify only NEW ids
    prior = {}
    if OUT.exists():
        prior = {r["id"]: r["split"] for r in map(json.loads, OUT.read_text().splitlines()) if r.get("split")}
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for r in records:
        if r["id"] in prior:
            r["split"] = prior[r["id"]]
        else:
            groups[(r["category"], r["difficulty"])].append(r)
    for key in sorted(groups):
        g = groups[key]
        rng.shuffle(g)
        n_dev = round(len(g) * DEV_FRACTION) if len(g) > 1 else 0
        for j, r in enumerate(g):
            r["split"] = "dev" if j < n_dev else "test"

    records.sort(key=lambda r: r["id"])
    for qid, msg in problems:
        print(f"  [{qid}] {msg}")
    from collections import Counter
    print(f"{len(records)} valid / {len(GOLD)} written; splits={Counter(r['split'] for r in records)}; "
          f"difficulty={Counter(r['difficulty'] for r in records)}")
    if write:
        OUT.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        print(f"wrote {OUT}")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main("--write" in sys.argv) else 0)
