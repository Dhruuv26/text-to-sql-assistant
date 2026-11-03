"""Heuristic failure taxonomy for INCORRECT predictions. Rule-based on the SQL ASTs + execution outcome.

Order of checks matters (first match wins): execution failures first, then output shape, then structural
differences from the gold query (tables/joins -> aggregation -> ordering/limit -> filter), else 'other'.
This is a diagnostic aid, not ground truth: a query can be wrong in several ways; we report the first one found.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .metrics import _ast_tables

FAILURE_TYPES = [
    "empty_output", "guardrail_blocked", "timeout", "syntax_error", "hallucinated_column",
    "hallucinated_table", "ambiguous_column", "db_error_other", "wrong_output_columns",
    "wrong_join_or_table", "wrong_aggregation", "wrong_ordering_limit", "wrong_filter", "other_wrong_result", "provider_error",
]

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def _parse(sql):
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None


def _aggs(tree) -> set[str]:
    return {type(n).__name__ for n in tree.find_all(*_AGGS)}


def _strip(node) -> str:
    if node is None:
        return ""
    node = node.copy()
    for c in node.find_all(exp.Column):
        c.set("table", None)
    return node.sql(dialect="sqlite").lower().replace(" ", "")


def _order_limit(tree):
    order = tree.args.get("order")
    lim = tree.args.get("limit")
    dirs = [bool(o.args.get("desc")) for o in order.expressions] if order else []
    return (bool(order), tuple(dirs), lim.expression.sql() if lim else None)


def classify_failure(pred_sql: str, gold_sql: str, pred_exec, gold_exec) -> str:
    if getattr(pred_exec, "code", None) == "provider_error":
        return "provider_error"
    if not pred_sql or not pred_sql.strip():
        return "empty_output"
    if not pred_exec.ok:
        code, msg = pred_exec.code, (pred_exec.error or "").lower()
        if code == "provider_error":
            return "provider_error"
        if code == "timeout":
            return "timeout"
        if code == "parse_error" or "syntax error" in msg:
            return "syntax_error"
        if code in ("not_select", "forbidden_statement", "forbidden_function", "multiple_statements", "too_long", "empty"):
            return "guardrail_blocked"
        if code == "forbidden_table":
            return "hallucinated_table"
        if "no such column" in msg:
            return "hallucinated_column"
        if "no such table" in msg:
            return "hallucinated_table"
        if "ambiguous column" in msg:
            return "ambiguous_column"
        return "db_error_other"

    # executed fine but result differs from gold
    p_cols = len(pred_exec.columns)
    g_cols = len(gold_exec.columns)
    if p_cols != g_cols:
        return "wrong_output_columns"
    pt, gt = _parse(pred_sql), _parse(gold_sql)
    if pt is None or gt is None:
        return "other_wrong_result"
    if _ast_tables(pt) != _ast_tables(gt):
        return "wrong_join_or_table"
    if _aggs(pt) != _aggs(gt) or bool(pt.args.get("group")) != bool(gt.args.get("group")):
        return "wrong_aggregation"
    if _order_limit(pt) != _order_limit(gt):
        return "wrong_ordering_limit"
    if _strip(pt.args.get("where")) != _strip(gt.args.get("where")) or _strip(pt.args.get("having")) != _strip(gt.args.get("having")):
        return "wrong_filter"
    return "other_wrong_result"
