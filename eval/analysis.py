"""Load saved runs and compute grouped / paired views. Used by report.py and results_md.py."""
from __future__ import annotations

import json
from pathlib import Path

from . import runner
from .stats import paired_compare


def load(split: str, root: Path | None = None) -> dict[tuple[str, str], list[dict]]:
    """-> {(model, approach): [records]}.  split in dev | test | pooled (dev+test, only runs that exist in both)."""
    root = Path(root) if root else runner.RESULTS
    by_split: dict[str, dict] = {}
    for d in sorted(root.glob("*/")):
        sp = d / "summary.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        recs = [json.loads(l) for l in (d / "predictions.jsonl").read_text().splitlines() if l.strip()]
        by_split.setdefault(s["split"], {})[(s["model"], s["approach"])] = recs
    if split != "pooled":
        return by_split.get(split, {})
    dev, test = by_split.get("dev", {}), by_split.get("test", {})
    return {k: dev[k] + test[k] for k in dev if k in test}


def summarize_group(group: dict, split: str) -> dict[tuple[str, str], dict]:
    return {k: runner.summarize(v, {"model": k[0], "approach": k[1], "split": split}) for k, v in group.items()}


def preds(records: list[dict]) -> dict[str, bool]:
    return {r["id"]: r["correct"] for r in records}


def compare(group: dict, a: tuple[str, str], b: tuple[str, str]) -> dict | None:
    """Paired comparison of run b relative to run a (a = reference). 'fixed' = right in b, wrong in a."""
    if a not in group or b not in group:
        return None
    c = paired_compare(preds(group[a]), preds(group[b]))
    return {"n": c["n"], "fixed": c["only_b"], "broke": c["only_a"], "p": c["p_value"]}


def verdict(p: float) -> str:
    return "significant (p<0.05)" if p < 0.05 else "not significant"


# comparisons beyond "everything vs zero_shot": (label, reference approach, tested approach)
TARGETED = [("retry loop on top of few-shot", "fewshot", "self_correct"),
            ("docs on top of examples", "shots_only", "fewshot"),
            ("examples on top of docs", "docs", "fewshot")]
