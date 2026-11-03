"""Resolve run folders by approach prefix:  resolve('fewshot', 'dev') -> results/fewshot__<model>__dev"""
from __future__ import annotations

from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


def resolve(name: str, split: str = "dev", root: Path = RESULTS) -> Path:
    if (root / name).is_dir():
        return root / name
    hits = sorted(root.glob(f"{name}__*__{split}"))
    if not hits:
        raise SystemExit(f"no run matching '{name}' for split '{split}' in {root}")
    if len(hits) > 1:
        print(f"note: {len(hits)} runs match '{name}'; using {hits[0].name}")
    return hits[0]
