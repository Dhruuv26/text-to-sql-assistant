"""Markdown comparison tables.

python -m eval.report --split test            # held-out
python -m eval.report --split pooled          # dev+test (n=143), exploratory: dev informed the choice of approaches
"""
import argparse

from . import analysis
from .stats import wilson_ci


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test", "pooled"])
    ap.add_argument("--baseline", default="zero_shot")
    a = ap.parse_args()
    group = analysis.load(a.split)
    if not group:
        print("no runs found"); return
    sums = analysis.summarize_group(group, a.split)
    keys = sorted(group, key=lambda k: (k[0], k[1] != a.baseline, k[1]))
    note = "  [exploratory: dev informed the choice of approaches]" if a.split == "pooled" else ""
    print(f"Split: {a.split}{note}  (95% Wilson confidence intervals)\n")
    print("| Model | Approach | n | Exec. acc. | 95% CI | Exact match | Easy | Medium | Hard | p50 (ms) | p95 (ms) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in keys:
        s, recs = sums[k], group[k]
        d = s["by_difficulty"]

        def g(x, d=d):
            return f"{d[x]['execution_accuracy']}%" if x in d else "-"

        lo, hi = wilson_ci(sum(r["correct"] for r in recs), len(recs))
        print(f"| {k[0]} | {k[1]} | {s['n']} | {s['execution_accuracy']}% | {lo}-{hi}% | {s['exact_match']}% | "
              f"{g('easy')} | {g('medium')} | {g('hard')} | {s['latency_ms']['p50']:.0f} | {s['latency_ms']['p95']:.0f} |")

    rows = []
    for model in sorted({k[0] for k in group}):
        base = (model, a.baseline)
        for k in keys:
            if k[0] == model and k != base and (c := analysis.compare(group, base, k)):
                rows.append(f"| {model} | {k[1]} vs {a.baseline} | {c['fixed']} | {c['broke']} | {c['p']} | {analysis.verdict(c['p'])} |")
        for label, ref, new in analysis.TARGETED:
            if (c := analysis.compare(group, (model, ref), (model, new))):
                rows.append(f"| {model} | {new} vs {ref} ({label}) | {c['fixed']} | {c['broke']} | {c['p']} | {analysis.verdict(c['p'])} |")
    models = sorted({k[0] for k in group})
    if len(models) == 2:   # model-size effect: same approach, small -> large model (ordering by name is 3b < 7b)
        for ap_ in sorted({k[1] for k in group}):
            if (c := analysis.compare(group, (models[0], ap_), (models[1], ap_))):
                rows.append(f"| {models[0]} -> {models[1]} | {ap_} (model size) | {c['fixed']} | {c['broke']} | {c['p']} | {analysis.verdict(c['p'])} |")
    if rows:
        print("\nPaired comparisons (exact McNemar on per-question outcomes; Fixed = right in the second run only):\n")
        print("| Model | Comparison | Fixed | Broke | p-value | Verdict |")
        print("|---|---|---|---|---|---|")
        print("\n".join(rows))


if __name__ == "__main__":
    main()
