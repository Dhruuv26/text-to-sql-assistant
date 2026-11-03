"""Run the frozen experiment matrix, skipping runs that already exist (safe to stop and resume).

  python -m eval.matrix --split test --models qwen2.5-coder:3b qwen2.5-coder:7b --vote-models qwen2.5-coder:7b
"""
import argparse
import time

from . import runner

APPROACHES = ["zero_shot", "docs", "shots_only", "fewshot", "self_correct"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--models", nargs="+", default=["qwen2.5-coder:3b", "qwen2.5-coder:7b"])
    ap.add_argument("--vote-models", nargs="*", default=["qwen2.5-coder:7b"], help="models to also run the (slow) vote approach on")
    a = ap.parse_args()
    jobs = [(m, ap_) for m in a.models for ap_ in APPROACHES] + [(m, "vote") for m in a.vote_models]
    t0 = time.time()
    for i, (model, approach) in enumerate(jobs, 1):
        name = runner.run_name(approach, model, a.split)
        if (runner.RESULTS / name / "summary.json").exists():
            print(f"[{i}/{len(jobs)}] skip {name} (exists)")
            continue
        print(f"\n[{i}/{len(jobs)}] {name}   (elapsed {(time.time()-t0)/60:.0f} min)")
        runner.run_experiment(model, approach, a.split)
    print("\nmatrix complete. Now: python -m eval.report --split", a.split)


if __name__ == "__main__":
    main()
