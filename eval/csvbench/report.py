"""Summarise the CSV benchmark runs into docs/CSV_RESULTS.md.   python -m eval.csvbench.report"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.stats import paired_compare, wilson_ci

from .fetch import ROOT
from .run import RESULTS

OUT = ROOT / "docs" / "CSV_RESULTS.md"
ORDER = ["plain", "profiled", "profiled_retry"]

CAVEATS = """**How to read this.** This is a small, exploratory benchmark (80 hand-written questions, 8 public CSV files) reported separately from the
143-question Chinook benchmark and its held-out test split. Questions were written after looking at each file's schema and value profile, and
before any model output. Prompts were frozen before the files were chosen and were not tuned on these results. Questions within a file are not
independent, so the intervals below are optimistic. One more public file (`bad-drivers.csv`) was left out because its long headers collapse to
near-identical column names; see the manifest."""


def load_runs(root: Path = RESULTS) -> dict[tuple[str, str], list[dict]]:
    runs = {}
    for d in sorted(Path(root).glob("csv__*")):
        if (d / "summary.json").exists():
            s = json.loads((d / "summary.json").read_text())
            runs[(s["model"], s["approach"])] = [json.loads(l) for l in (d / "predictions.jsonl").read_text().splitlines() if l.strip()]
    return runs


def _acc(recs):
    k = sum(r["correct"] for r in recs)
    lo, hi = wilson_ci(k, len(recs))
    return k, len(recs), round(100 * k / len(recs), 1) if recs else 0.0, lo, hi


def _p50(recs):
    v = sorted(r["latency_ms"] for r in recs)
    return v[len(v) // 2] / 1000 if v else 0.0


def _paired(a: list[dict], b: list[dict]) -> dict:
    return paired_compare({r["id"]: r["correct"] for r in a}, {r["id"]: r["correct"] for r in b})


def render(runs: dict[tuple[str, str], list[dict]]) -> str:
    models = sorted({m for m, _ in runs})
    L = ["# CSV generalisation benchmark (exploratory)", "", CAVEATS, ""]
    L += ["## Execution accuracy", "", "| Model | Approach | Correct | Accuracy | 95% CI | p50 latency |", "|---|---|---|---|---|---|"]
    for m in models:
        for ap in ORDER:
            if (m, ap) in runs:
                k, n, a, lo, hi = _acc(runs[(m, ap)])
                L.append(f"| {m} | {ap} | {k}/{n} | {a}% | {lo} to {hi}% | {_p50(runs[(m, ap)]):.1f} s |")
    L += ["", "## Paired comparisons (exact McNemar; each row compares the same questions)", "",
          "| Model | A vs B | A only right | B only right | p |", "|---|---|---|---|---|"]
    pairs = [("profiled", "plain"), ("profiled_retry", "profiled"), ("profiled_retry", "plain")]
    for m in models + ["both models pooled"]:
        for a, b in pairs:
            ra, rb = ([], [])
            for mm in (models if m == "both models pooled" else [m]):
                if (mm, a) in runs and (mm, b) in runs:
                    ra += [{**r, "id": f"{mm}/{r['id']}"} for r in runs[(mm, a)]]
                    rb += [{**r, "id": f"{mm}/{r['id']}"} for r in runs[(mm, b)]]
            if ra:
                c = _paired(ra, rb)
                L.append(f"| {m} | {a} vs {b} | {c['only_a']} | {c['only_b']} | {c['p_value']} |")
    for title, field in (("By question category", "category"), ("By dataset", "dataset"), ("By difficulty", "difficulty")):
        keys = sorted({r[field] for recs in runs.values() for r in recs})
        L += ["", f"## {title} (correct/total)", "", "| " + field + " | " + " | ".join(f"{m.split(':')[-1]} {a}" for m in models for a in ORDER) + " |",
              "|---|" + "---|" * (len(models) * len(ORDER))]
        for key in keys:
            cells = []
            for m in models:
                for a in ORDER:
                    sub = [r for r in runs.get((m, a), []) if r[field] == key]
                    cells.append(f"{sum(r['correct'] for r in sub)}/{len(sub)}" if sub else "-")
            L.append(f"| {key} | " + " | ".join(cells) + " |")
    L += ["", "## Failure types (wrong answers)", ""]
    for (m, a), recs in sorted(runs.items()):
        f = {}
        for r in recs:
            if not r["correct"]:
                f[r["failure"]] = f.get(r["failure"], 0) + 1
        L.append(f"- **{m} / {a}**: " + (", ".join(f"{k} {v}" for k, v in sorted(f.items(), key=lambda kv: -kv[1])) or "none"))
    return "\n".join(L) + "\n"


def main() -> int:
    runs = load_runs()
    if not runs:
        print("No results yet. Run: python -m eval.csvbench.run")
        return 1
    OUT.write_text(render(runs))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
