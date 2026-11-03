"""Print the wrong predictions of a run.

python -m eval.show_failures zero_shot__qwen2.5-coder-7b__test
python -m eval.show_failures zero_shot --split test --difficulty easy
"""
import argparse
import json

from .runs import RESULTS, resolve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    ap.add_argument("--category")
    a = ap.parse_args()
    d = resolve(a.name, a.split) if a.name else max(RESULTS.glob("*/"), key=lambda p: (p / "summary.json").stat().st_mtime)
    n = 0
    for r in map(json.loads, (d / "predictions.jsonl").read_text().splitlines()):
        if r["correct"] or (a.difficulty and r["difficulty"] != a.difficulty) or (a.category and r["category"] != a.category):
            continue
        n += 1
        print(f"--- {r['id']} [{r['difficulty']}/{r['category']}] {r['failure']}  (attempts={r['attempts']})")
        print("Q   :", r["question"])
        print("GOLD:", r["gold_sql"])
        print("PRED:", r["pred_sql"])
        if r["error"]:
            print("ERR :", r["error"])
        print()
    print(f"{n} failures shown; run: {d.name}")


if __name__ == "__main__":
    main()
