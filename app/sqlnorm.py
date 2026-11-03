"""SQL normalisation shared by the evaluator (exact match) and the API (copied-example detection)."""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers


def normalize_sql(sql: str) -> str | None:
    """Canonical text: parsed, identifiers lower-cased, no trailing ';', comments dropped. None if unparseable."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
        return normalize_identifiers(tree, dialect="sqlite").sql(dialect="sqlite")
    except Exception:
        return None


def fingerprint(sql: str) -> str | None:
    """Like normalize_sql but also ignores column aliases, so a stored example with renamed output columns still matches."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
        tree = tree.transform(lambda n: n.this if isinstance(n, exp.Alias) else n)
        return normalize_identifiers(tree, dialect="sqlite").sql(dialect="sqlite")
    except Exception:
        return None


def constant_text_only(sql: str) -> bool:
    """True when the query reads no table yet contains a string literal, i.e. the 'result' is text the model wrote."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return False
    if any(True for _ in tree.find_all(exp.Table)):
        return False
    return any(lit.is_string for lit in tree.find_all(exp.Literal))
