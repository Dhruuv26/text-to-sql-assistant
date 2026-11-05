"""Parser-based SQL validation (sqlglot). Allowlist-first: only a single read-only query over allowed tables."""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

MAX_SQL_CHARS = 5000

# Root statement types that are acceptable (everything else is rejected).
_ALLOWED_ROOTS = (exp.Select, exp.SetOperation)  # SetOperation = UNION / INTERSECT / EXCEPT

# Functions that touch the filesystem, load code or allocate unbounded memory.
DENIED_FUNCTIONS = frozenset({
    "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer",
    "zeroblob", "randomblob", "sqlite_compileoption_used", "sqlite_compileoption_get",
})

# Node types that must never appear anywhere in the tree (defence in depth, e.g. writes hidden in CTEs).
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Merge,
    exp.Command, exp.Pragma, exp.Attach, exp.Detach, exp.Transaction, exp.Commit,
    exp.Rollback, exp.Use, exp.Set, exp.Into,
)


@dataclass
class ValidationResult:
    ok: bool
    sql: str | None = None        # normalised SQL when ok
    error: str | None = None
    code: str | None = None       # machine-readable reason, used by the eval failure taxonomy
    tables: frozenset[str] = frozenset()


def _fail(code: str, msg: str) -> ValidationResult:
    return ValidationResult(False, None, msg, code)


def validate_sql(sql: str, allowed_tables: set[str] | frozenset[str]) -> ValidationResult:
    """Never raises: pathological input (e.g. thousands of nested parentheses) is rejected as 'too_complex'."""
    try:
        return _validate(sql, allowed_tables)
    except RecursionError:
        return _fail("too_complex", "The query is too deeply nested.")


def _validate(sql: str, allowed_tables: set[str] | frozenset[str]) -> ValidationResult:
    if not isinstance(sql, str) or not sql.strip():
        return _fail("empty", "Empty query.")
    if len(sql) > MAX_SQL_CHARS:
        return _fail("too_long", f"Query exceeds {MAX_SQL_CHARS} characters.")

    canonical = {t.lower(): t for t in allowed_tables}      # report real table names, match case-insensitively
    allowed = set(canonical)

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except (ParseError, TokenError) as e:
        return _fail("parse_error", f"SQL could not be parsed: {str(e).splitlines()[0]}")

    if len(statements) == 0:
        return _fail("empty", "Empty query.")
    if len(statements) > 1:
        return _fail("multiple_statements", "Only a single statement is allowed.")

    tree = statements[0]
    if not isinstance(tree, _ALLOWED_ROOTS):
        return _fail("not_select", f"Only SELECT queries are allowed (got {type(tree).__name__}).")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return _fail("forbidden_statement", f"Forbidden construct: {type(node).__name__}.")

    # Function denylist (named + anonymous functions).
    for fn in tree.find_all(exp.Func):
        name = (fn.name if isinstance(fn, exp.Anonymous) else fn.sql_name()).lower()
        if name in DENIED_FUNCTIONS:
            return _fail("forbidden_function", f"Function not allowed: {name}.")

    # Table allowlist. CTE aliases are legal references but are not real tables.
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used = set()
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name:  # table-valued function etc.
            return _fail("forbidden_table", "Table-valued functions are not allowed.")
        if t.db or t.args.get("catalog"):
            return _fail("forbidden_table", "Schema-qualified tables are not allowed.")
        if name in cte_names:
            continue
        if name not in allowed:
            return _fail("forbidden_table", f"Table not allowed: {t.name}.")
        used.add(canonical[name])

    # A bare "SELECT 1" is harmless; but anything with a table-less FROM function (e.g. json_each) is caught above.
    return ValidationResult(True, tree.sql(dialect="sqlite"), None, None, frozenset(used))
