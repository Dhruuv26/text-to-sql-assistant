"""Small-sample statistics so the comparison table doesn't over-claim."""
from __future__ import annotations

from math import comb, sqrt


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n, returned as percentages."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * max(0.0, centre - half), 1), round(100 * min(1.0, centre + half), 1))


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from discordant pair counts (A right/B wrong, B right/A wrong)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_compare(pred_a: dict[str, bool], pred_b: dict[str, bool]) -> dict:
    """pred_*: question id -> correct. Only questions present in both runs are compared."""
    ids = sorted(set(pred_a) & set(pred_b))
    only_a = sum(1 for i in ids if pred_a[i] and not pred_b[i])
    only_b = sum(1 for i in ids if pred_b[i] and not pred_a[i])
    return {"n": len(ids), "only_a": only_a, "only_b": only_b, "p_value": round(mcnemar_exact(only_a, only_b), 4)}
