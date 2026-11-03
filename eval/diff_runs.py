"""Show questions where two runs disagree.  python -m eval.diff_runs zero_shot fewshot [--split dev]"""
import argparse
import json

from .runs import resolve


def load(d):
    return {r["id"]: r for r in map(json.loads, (d / "predictions.jsonl").read_text().splitlines())}


def diff(a: dict, b: dict) -> list[tuple[str, str]]:
    """-> [(id, 'A_only'|'B_only')] for questions on which exactly one run is correct."""
    out = []
    for i in sorted(set(a) & set(b)):
        if a[i]["correct"] != b[i]["correct"]:
            out.append((i, "A_only" if a[i]["correct"] else "B_only"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("--split", default="dev")
    x = ap.parse_args()
    da, db = resolve(x.a, x.split), resolve(x.b, x.split)
    A, B = load(da), load(db)
    d = diff(A, B)
    print(f"A = {da.name}\nB = {db.name}\n{len(d)} questions differ\n")
    for i, who in d:
        wrong, right = (B[i], A[i]) if who == "A_only" else (A[i], B[i])
        print(f"--- {i} [{right['difficulty']}/{right['category']}]  correct in {'A' if who=='A_only' else 'B'} only")
        print("Q      :", right["question"])
        print("GOLD   :", right["gold_sql"])
        print("RIGHT  :", right["pred_sql"])
        print("WRONG  :", wrong["pred_sql"], f"   <- {wrong['failure']}")
        print()


if __name__ == "__main__":
    main()
