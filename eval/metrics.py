"""Scoring: execution accuracy (result-set equivalence), normalised exact match, latency percentiles."""
from __future__ import annotations

from collections import Counter
from itertools import permutations

from sqlglot import exp

from app.sqlnorm import normalize_sql

FLOAT_DIGITS = 4
MAX_PERMUTE_COLS = 6


def _norm_val(v):
    if isinstance(v, float):
        return round(v, FLOAT_DIGITS)
    return v


def _norm_rows(rows):
    return [tuple(_norm_val(v) for v in r) for r in rows]


def _same(a: list[tuple], b: list[tuple], ordered: bool) -> bool:
    return a == b if ordered else Counter(a) == Counter(b)


def results_match(pred_rows, gold_rows, ordered: bool = False) -> bool:
    """Execution-accuracy comparison.

    * values: floats rounded to 4 dp (5 == 5.0)
    * ordered=False -> multiset of rows (duplicates matter, order does not)
    * ordered=True  -> exact row order
    * column ORDER is ignored (we try column permutations, up to 6 columns); column NAMES are ignored.
      Extra or missing columns are always a mismatch.
    """
    p, g = _norm_rows(pred_rows), _norm_rows(gold_rows)
    if len(p) != len(g):
        return False
    if not g:
        return True
    ncol = len(g[0])
    if len(p[0]) != ncol:
        return False
    if _same(p, g, ordered):
        return True
    if 1 < ncol <= MAX_PERMUTE_COLS:
        for perm in permutations(range(ncol)):
            if _same([tuple(r[i] for i in perm) for r in p], g, ordered):
                return True
    return False


def exact_match(pred_sql: str, gold_sql: str) -> bool:
    a, b = normalize_sql(pred_sql), normalize_sql(gold_sql)
    return a is not None and a == b


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _ast_tables(tree: exp.Expression) -> set[str]:
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return {t.name.lower() for t in tree.find_all(exp.Table) if t.name.lower() not in ctes}
