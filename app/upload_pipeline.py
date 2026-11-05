"""Question answering over a user's uploaded tables (one session database).

Separate from Text2SQL on purpose: the evaluated Chinook pipeline is untouched. This class reuses the shared retry_loop
and the same guardrails; execution is hardened (SQLite resource limits) and retries stop after a rejected write.

Approaches (for the CSV generalisation benchmark):
  plain            names and types only
  profiled         NULL counts, ranges, category values, notes + rules
  profiled_retry   profiled, then error-feedback retries (abort_on_unsafe=True)
"""
from __future__ import annotations

from pathlib import Path

from guardrails.executor import ExecResult, execute_safe

from .ingest import TableMeta
from .llm import LLMClient
from .pipeline import PipelineResult, retry_loop
from .prompts import extract_sql
from .upload_prompts import UPLOAD_SYSTEM, render_schema, upload_prompt

UPLOAD_APPROACHES = ("plain", "profiled", "profiled_retry")


class UploadQA:
    def __init__(self, llm: LLMClient, db_path: str | Path, tables: list[TableMeta], row_limit: int = 200,
                 timeout_s: float = 5.0, harden: bool = True):
        self.llm, self.db_path, self.tables = llm, db_path, tables
        self.row_limit, self.timeout_s, self.harden = row_limit, timeout_s, harden
        self.allowed = {t.name for t in tables}

    def schema_text(self, level: str) -> str:
        return render_schema(self.tables, level)

    def _run(self, sql: str) -> ExecResult:
        return execute_safe(self.db_path, sql, self.allowed, self.timeout_s, self.row_limit, harden=self.harden)

    def _generate(self, prompt: str):
        resp = self.llm.generate(prompt, UPLOAD_SYSTEM)
        return resp, extract_sql(resp.text)

    def ask(self, question: str, approach: str = "profiled_retry") -> PipelineResult:
        if approach not in UPLOAD_APPROACHES:
            raise ValueError(f"unknown approach '{approach}'; choose from {UPLOAD_APPROACHES}")
        level = "plain" if approach == "plain" else "profiled"
        prompt = upload_prompt(question, self.schema_text(level), level)
        resp, sql = self._generate(prompt)
        res = self._run(sql)
        total_ms, all_cached, attempts, raw = resp.latency_ms, resp.cached, [sql], resp.text
        if approach == "profiled_retry":
            sql, res, raw, total_ms, all_cached = retry_loop(
                prompt, sql, res, raw, total_ms, all_cached, attempts, self._generate, self._run, abort_on_unsafe=True)
        return PipelineResult(question, approach, raw, sql, res, total_ms, all_cached, attempts)
