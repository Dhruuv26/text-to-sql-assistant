"""Run the CSV generalisation benchmark.

  python -m eval.csvbench.fetch
  python -m eval.csvbench.run --models qwen2.5-coder:3b qwen2.5-coder:7b          (plain, profiled, profiled_retry)
  python -m eval.csvbench.report

Each (model, approach) is run ONCE: an existing result is skipped, and --force is needed to overwrite it. This benchmark is
exploratory and separate from the held-out Chinook test split; do not tune prompts on it (see eval/PROTOCOL.md, addendum).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.llm import CachedLLM, OllamaClient
from app.upload_pipeline import UPLOAD_APPROACHES, UploadQA
from eval.metrics import exact_match, results_match
from eval.runner import print_summary, summarize
from eval.taxonomy import classify_failure
from guardrails.executor import ExecResult, execute_safe

from .build import QUESTIONS, Prepared, prepare
from .fetch import ROOT

RESULTS = ROOT / "results" / "csvbench"
EVAL_ROW_LIMIT = 100_000
EVAL_TIMEOUT_S = 20.0


def load_questions(path: Path = QUESTIONS, limit: int | None = None) -> list[dict]:
    qs = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return qs[:limit] if limit else qs


def run_name(approach: str, model: str) -> str:
    return f"csv__{approach}__{model.replace(':', '-')}"


def evaluate(llm, approach: str, questions: list[dict], prepared: dict[str, Prepared], verbose: bool = True) -> list[dict]:
    qa = {ds: UploadQA(llm, p.db_path, p.tables, row_limit=EVAL_ROW_LIMIT, timeout_s=EVAL_TIMEOUT_S) for ds, p in prepared.items()}
    out = []
    for i, q in enumerate(questions, 1):
        p = prepared[q["dataset"]]
        gold = execute_safe(p.db_path, q["gold_sql"], p.allowed, EVAL_TIMEOUT_S, EVAL_ROW_LIMIT)
        assert gold.ok, f"gold query for {q['id']} failed: {gold.error}"
        try:
            r = qa[q["dataset"]].ask(q["question"], approach)
            sql, res, llm_ms, cached, attempts = r.sql, r.result, r.llm_latency_ms, r.cached, r.attempts
        except Exception as e:   # provider error: record and keep going
            sql, res, llm_ms, cached, attempts = "", ExecResult(False, error=str(e), code="provider_error"), 0.0, False, []
        correct = res.ok and results_match(res.rows, gold.rows, q["ordered"])
        rec = {"id": q["id"], "dataset": q["dataset"], "category": q["category"], "difficulty": q["difficulty"], "question": q["question"],
               "gold_sql": q["gold_sql"], "pred_sql": sql, "correct": correct,
               "exact_match": exact_match(sql, q["gold_sql"]) if sql else False, "executed_ok": res.ok, "n_rows": len(res.rows),
               "error": res.error, "failure": None if correct else classify_failure(sql, q["gold_sql"], res, gold),
               "latency_ms": round(llm_ms + res.latency_ms, 1), "llm_cached": cached, "attempts": len(attempts) or 1}
        out.append(rec)
        if verbose:
            print(f"[{i}/{len(questions)}] {q['id']:20} {'OK ' if correct else 'BAD'} {rec['latency_ms'] / 1000:.1f}s {rec['failure'] or ''}", flush=True)
    return out


def _by(records, field):
    groups = {}
    for r in records:
        groups.setdefault(r[field], []).append(r)
    return {k: {"n": len(v), "correct": sum(1 for r in v if r["correct"])} for k, v in sorted(groups.items())}


def run_experiment(model: str, approach: str, *, questions: list[dict] | None = None, prepared: dict[str, Prepared] | None = None,
                   llm=None, results_root: Path = RESULTS, force: bool = False, no_cache: bool = False, limit: int | None = None,
                   verbose: bool = True) -> dict:
    if approach not in UPLOAD_APPROACHES:
        raise ValueError(f"unknown approach {approach!r}")
    name = run_name(approach, model)
    done = Path(results_root) / name / "summary.json"
    if done.exists() and not force:
        raise SystemExit(f"{name} already exists. Each configuration is run once; use --force to overwrite.")
    questions = questions if questions is not None else load_questions(limit=limit)
    prepared = prepared or prepare()
    if llm is None:
        llm = OllamaClient(model)
        llm = llm if no_cache else CachedLLM(llm, ROOT / "cache" / "csvbench" / "llm")
    records = evaluate(llm, approach, questions, prepared, verbose)
    summary = summarize(records, {"approach": approach, "model": model, "split": "csvbench"})
    summary["by_dataset"] = _by(records, "dataset")
    summary["by_category_counts"] = _by(records, "category")
    if verbose:
        print_summary(summary)
    d = Path(results_root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "predictions.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    done.write_text(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen2.5-coder:3b", "qwen2.5-coder:7b"])
    ap.add_argument("--approaches", nargs="+", default=list(UPLOAD_APPROACHES), choices=list(UPLOAD_APPROACHES))
    ap.add_argument("--limit", type=int, help="first N questions only (smoke test; write to a throwaway --results-dir)")
    ap.add_argument("--results-dir", type=Path, default=RESULTS)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    prepared = prepare()
    jobs = [(m, ap_) for m in a.models for ap_ in a.approaches]
    t0 = time.time()
    for i, (model, approach) in enumerate(jobs, 1):
        name = run_name(approach, model)
        if (a.results_dir / name / "summary.json").exists() and not a.force:
            print(f"[{i}/{len(jobs)}] skip {name} (exists)")
            continue
        print(f"\n[{i}/{len(jobs)}] {name}   ({(time.time() - t0) / 60:.1f} min elapsed)")
        run_experiment(model, approach, prepared=prepared, results_root=a.results_dir, force=a.force, no_cache=a.no_cache, limit=a.limit)


if __name__ == "__main__":
    main()
