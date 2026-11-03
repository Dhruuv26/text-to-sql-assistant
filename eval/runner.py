"""Run an approach over the gold questions and score it.

  python -m eval.runner --split dev  --approach zero_shot --model qwen2.5-coder:7b
  python -m eval.runner --split test --approach zero_shot --limit 10 --no-cache

Outputs results/<run>/predictions.jsonl and results/<run>/summary.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from app.llm import CachedLLM, LLMClient, OllamaClient
from app.pipeline import Text2SQL
from app.schema import DEFAULT_DB
from guardrails.executor import execute_safe

from .metrics import exact_match, percentile, results_match
from .taxonomy import classify_failure

QUESTIONS = Path(__file__).parent / "questions.jsonl"
RESULTS = Path(__file__).resolve().parent.parent / "results"
EVAL_ROW_LIMIT = 100_000
EVAL_TIMEOUT_S = 20.0
VOTE_TEMPERATURE = 0.6


def load_questions(split: str = "all", limit: int | None = None) -> list[dict]:
    qs = [json.loads(l) for l in QUESTIONS.read_text().splitlines() if l.strip()]
    if split != "all":
        qs = [q for q in qs if q["split"] == split]
    return qs[:limit] if limit else qs


def _rate(items, key=lambda r: r["correct"]):
    return round(100 * sum(1 for r in items if key(r)) / len(items), 1) if items else 0.0


def summarize(records: list[dict], meta: dict) -> dict:
    lat = [r["latency_ms"] for r in records]
    by = lambda field: {k: {"n": len(v), "execution_accuracy": _rate(v)}
                        for k, v in sorted(_group(records, field).items())}
    return {
        **meta,
        "n": len(records),
        "execution_accuracy": _rate(records),
        "exact_match": _rate(records, lambda r: r["exact_match"]),
        "valid_sql_rate": _rate(records, lambda r: r["executed_ok"]),
        "guardrail_block_rate": _rate(records, lambda r: r["failure"] == "guardrail_blocked"),
        "latency_ms": {"mean": round(sum(lat) / len(lat), 1) if lat else 0,
                       "p50": round(percentile(lat, 50), 1), "p95": round(percentile(lat, 95), 1)},
        "by_difficulty": by("difficulty"),
        "by_category": by("category"),
        **_vote_stats(records),
        "failures": dict(Counter(r["failure"] for r in records if not r["correct"]).most_common()),
    }


def _vote_stats(records):
    ag = [r["vote_agreement"] for r in records if r.get("vote_agreement") is not None]
    if not ag:
        return {}
    return {"vote_mean_agreement": round(sum(ag) / len(ag), 3),
            "vote_unanimous_rate": round(100 * sum(1 for a in ag if a == 1.0) / len(ag), 1)}


def _group(records, field):
    g = defaultdict(list)
    for r in records:
        g[r[field]].append(r)
    return g


def evaluate(llm: LLMClient, approach: str, questions: list[dict], db_path=DEFAULT_DB, verbose: bool = True,
             sampler_factory=None) -> list[dict]:
    t2s = Text2SQL(llm, db_path, row_limit=EVAL_ROW_LIMIT, timeout_s=EVAL_TIMEOUT_S, sampler_factory=sampler_factory)
    out = []
    for i, q in enumerate(questions, 1):
        gold = execute_safe(db_path, q["gold_sql"], t2s.allowed, EVAL_TIMEOUT_S, EVAL_ROW_LIMIT)
        assert gold.ok, f"gold query for {q['id']} failed: {gold.error}"
        try:
            p = t2s.ask(q["question"], approach)
            sql, res, llm_ms, cached, attempts, agreement = p.sql, p.result, p.llm_latency_ms, p.cached, p.attempts, p.agreement
        except Exception as e:  # provider/network error: record, keep going
            from guardrails.executor import ExecResult
            sql, res, llm_ms, cached, attempts, agreement = "", ExecResult(False, error=str(e), code="provider_error"), 0.0, False, [], None
        correct = res.ok and results_match(res.rows, gold.rows, q["ordered"])
        rec = {
            "id": q["id"], "split": q["split"], "category": q["category"], "difficulty": q["difficulty"],
            "question": q["question"], "gold_sql": q["gold_sql"], "pred_sql": sql,
            "correct": correct, "exact_match": exact_match(sql, q["gold_sql"]) if sql else False,
            "executed_ok": res.ok, "n_rows": len(res.rows), "error": res.error,
            "failure": None if correct else classify_failure(sql, q["gold_sql"], res, gold),
            "latency_ms": round(llm_ms + res.latency_ms, 1), "llm_cached": cached, "attempts": len(attempts) or 1,
            "vote_agreement": agreement,
        }
        out.append(rec)
        if verbose:
            print(f"[{i}/{len(questions)}] {q['id']} {'OK ' if correct else 'BAD'} "
                  f"{rec['latency_ms']/1000:.1f}s {rec['failure'] or ''}", flush=True)
    return out


def write_run(records, summary, run_name):
    d = RESULTS / run_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "predictions.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    return d


def print_summary(s: dict):
    print(f"\n== {s['approach']} | {s['model']} | split={s['split']} | n={s['n']} ==")
    print(f"execution accuracy {s['execution_accuracy']}%   exact match {s['exact_match']}%   "
          f"valid SQL {s['valid_sql_rate']}%   latency p50 {s['latency_ms']['p50']:.0f} ms / p95 {s['latency_ms']['p95']:.0f} ms")
    print("by difficulty:", {k: f"{v['execution_accuracy']}% (n={v['n']})" for k, v in s["by_difficulty"].items()})
    if "vote_mean_agreement" in s:
        print(f"vote agreement: mean {s['vote_mean_agreement']}, unanimous on {s['vote_unanimous_rate']}% of questions")
    print("failures:", s["failures"])


def run_name(approach: str, model: str, split: str) -> str:
    return f"{approach}__{model.replace(':', '-')}__{split}"


def run_experiment(model: str, approach: str, split: str, *, limit: int | None = None, no_cache: bool = False,
                   name: str | None = None, force: bool = False, llm=None, sampler=None) -> dict:
    """Run + score + save one (model, approach, split). The held-out TEST split refuses to be re-run without force."""
    run = name or run_name(approach, model, split)
    if split == "test" and (RESULTS / run / "summary.json").exists() and not force:
        raise SystemExit(f"{run} already exists. The test split is meant to be run ONCE per approach; use --force to override.")
    if llm is None:
        llm = OllamaClient(model)
        llm = llm if no_cache else CachedLLM(llm)

        def sampler(i):  # i-th sampled candidate for approach "vote": same model, temperature 0.6, seed i
            c = OllamaClient(model, temperature=VOTE_TEMPERATURE, seed=i)
            return c if no_cache else CachedLLM(c)
    records = evaluate(llm, approach, load_questions(split, limit), sampler_factory=sampler)
    summary = summarize(records, {"approach": approach, "model": model, "split": split})
    print_summary(summary)
    print("saved to", write_run(records, summary, run))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--approach", default="zero_shot", choices=["zero_shot", "fewshot", "self_correct", "docs", "shots_only", "vote"])
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing TEST run (avoid: it invalidates the held-out protocol)")
    a = ap.parse_args()
    run_experiment(a.model, a.approach, a.split, limit=a.limit, no_cache=a.no_cache, name=a.name, force=a.force)


if __name__ == "__main__":
    main()
