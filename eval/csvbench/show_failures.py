"""List what one approach fixed, broke or left wrong versus another (the questions, gold SQL and predicted SQL).

  python -m eval.csvbench.show_failures qwen2.5-coder:7b profiled plain      (profiled vs plain)
  python -m eval.csvbench.show_failures qwen2.5-coder:7b profiled            (just the questions profiled got wrong)
"""
from __future__ import annotations

import sys
from pathlib import Path

from .report import load_runs
from .run import RESULTS


def classify(a: list[dict], b: list[dict] | None):
    bmap = {r["id"]: r for r in b} if b else {}
    fixed, broken, both_wrong = [], [], []
    for r in a:
        o = bmap.get(r["id"])
        if not r["correct"]:
            (both_wrong if (o is None or not o["correct"]) else broken).append((r, o))
        elif o is not None and not o["correct"]:
            fixed.append((r, o))
    return fixed, broken, both_wrong


def show(title, rows, with_other=False):
    print(f"\n=== {title} ({len(rows)}) ===")
    for r, o in rows:
        print(f"\n[{r['id']}] {r['question']}\n  gold: {r['gold_sql']}\n  pred: {r['pred_sql']}" + (f"\n  error: {r['error']}" if r["error"] else "")
              + (f"\n  failure: {r['failure']}" if r["failure"] else ""))
        if with_other and o:
            print(f"  other approach predicted: {o['pred_sql']}")


def main(argv: list[str], root: Path = RESULTS) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    runs = load_runs(root)
    model, a = argv[0], argv[1]
    b = argv[2] if len(argv) == 3 else None
    for key in [(model, a)] + ([(model, b)] if b else []):
        if key not in runs:
            print(f"no run for {key}; have {sorted(runs)}")
            return 1
    fixed, broken, both_wrong = classify(runs[(model, a)], runs[(model, b)] if b else None)
    if b:
        show(f"{a} RIGHT where {b} was wrong", fixed, True)
        show(f"{a} WRONG where {b} was right", broken, True)
        show("wrong in both", both_wrong)
    else:
        show(f"{a} wrong", both_wrong)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
