"""Harvest verified-correct answers from saved evaluation runs for the demo's example chips.

  python -m eval.export_demo --model qwen2.5-coder:7b --approach self_correct --n 8

Writes app/demo_answers.json. Only predictions the harness scored as CORRECT are exported, and the API still runs
each saved SQL through the guardrails at request time. No model call is needed to show these examples.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import RESULTS, run_name

OUT = Path(__file__).resolve().parent.parent / "app" / "demo_answers.json"
MAX_QUESTION_CHARS = 150


def pick_examples(records: list[dict], n: int = 8) -> list[dict]:
    """One correct, readable, small-result question per category first (variety), then fill by difficulty."""
    good = [r for r in records if r["correct"] and 1 <= r["n_rows"] <= 25 and len(r["question"]) <= MAX_QUESTION_CHARS
            and r["pred_sql"].strip()]
    order = {"medium": 0, "hard": 1, "easy": 2}
    good.sort(key=lambda r: (order.get(r["difficulty"], 3), len(r["question"]), r["id"]))
    chosen, seen_cat = [], set()
    for r in good:
        if r["category"] not in seen_cat:
            chosen.append(r)
            seen_cat.add(r["category"])
    chosen = sorted(chosen, key=lambda r: (order.get(r["difficulty"], 3), len(r["question"])))[:n]
    return [{"question": r["question"], "sql": r["pred_sql"], "category": r["category"], "difficulty": r["difficulty"]} for r in chosen]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--approach", default="self_correct")
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    records = []
    for split in ("test", "dev"):
        p = RESULTS / run_name(a.approach, a.model, split) / "predictions.jsonl"
        if p.exists():
            records += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    if not records:
        raise SystemExit("no saved runs found for that model/approach; run the evaluation first")
    picked = pick_examples(records, a.n)
    OUT.write_text(json.dumps(picked, indent=2))
    print(f"wrote {len(picked)} verified examples to {OUT}")
    for p in picked:
        print(" -", p["question"])


if __name__ == "__main__":
    main()
