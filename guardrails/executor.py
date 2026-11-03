"""Safe execution: read-only connection, authorizer, wall-clock timeout, row cap."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .validator import DENIED_FUNCTIONS, ValidationResult, validate_sql

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_ROW_LIMIT = 200
_PROGRESS_OPS = 10_000  # VM instructions between timeout checks


@dataclass
class ExecResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    code: str | None = None       # validation code | "timeout" | "db_error"
    sql: str | None = None        # normalised SQL that actually ran
    latency_ms: float = 0.0


_SYSTEM_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema", "sqlite_sequence", "sqlite_stat1"}


def _make_authorizer(denied_tables: set[str]):
    """Deny reads of real-but-not-allowed tables. CTE names are not real tables, so they pass
    (the parser-level validator already enforces the allowlist; this is defence in depth)."""
    ok_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                  sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorizer(action, arg1, arg2, _db, _src):
        if action not in ok_actions:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower() in denied_tables:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and arg2 and arg2.lower() in DENIED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorizer


def connect_readonly(db_path: str | Path, allowed_tables: set[str]) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    con.execute("PRAGMA query_only = ON")
    allowed = {t.lower() for t in allowed_tables}
    real = {r[0].lower() for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    con.set_authorizer(_make_authorizer((real | _SYSTEM_TABLES) - allowed))
    return con


def execute_safe(db_path: str | Path, sql: str, allowed_tables: set[str],
                 timeout_s: float = DEFAULT_TIMEOUT_S, row_limit: int = DEFAULT_ROW_LIMIT) -> ExecResult:
    """Validate then execute. Never raises for bad SQL; returns ExecResult with code/error."""
    v: ValidationResult = validate_sql(sql, allowed_tables)
    if not v.ok:
        return ExecResult(False, error=v.error, code=v.code)

    con = connect_readonly(db_path, allowed_tables)
    deadline = time.monotonic() + timeout_s
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, _PROGRESS_OPS)
    t0 = time.perf_counter()
    try:
        cur = con.execute(v.sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(row_limit + 1)
        truncated = len(rows) > row_limit
        return ExecResult(True, cols, rows[:row_limit], truncated, sql=v.sql,
                          latency_ms=(time.perf_counter() - t0) * 1000)
    except sqlite3.OperationalError as e:
        msg = str(e)
        code = "timeout" if "interrupted" in msg.lower() else "db_error"
        if code == "timeout":
            msg = f"Query exceeded {timeout_s}s time limit."
        return ExecResult(False, error=msg, code=code, sql=v.sql,
                          latency_ms=(time.perf_counter() - t0) * 1000)
    except sqlite3.DatabaseError as e:
        return ExecResult(False, error=str(e), code="db_error", sql=v.sql,
                          latency_ms=(time.perf_counter() - t0) * 1000)
    finally:
        con.close()
