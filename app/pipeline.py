"""question -> prompt -> LLM -> extract -> validate -> execute. One entry point used by CLI, API and eval harness.

Approaches:
  zero_shot     A: schema only
  fewshot       B: schema + sample values + data notes + rules + 4 dynamically retrieved examples (TF-IDF)
  self_correct  C: B, then up to 2 retries feeding back DB/guardrail errors (and one retry on empty results)
  vote          D: zero_shot prompt, N_VOTES candidates (1 greedy + sampled), execute all, majority vote on result sets
Ablations of B:
  docs          sample values + data notes + rules, NO examples
  shots_only    plain schema + retrieved examples, NO samples/notes/rules
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from guardrails.executor import ExecResult, execute_safe

from .fewshot_pool import POOL
from .llm import LLMClient
from .prompts import SYSTEM, correction_prompt, extract_sql, fewshot_prompt, shots_only_prompt, zero_shot_prompt
from .retrieval import ExampleSelector
from .schema import DEFAULT_DB, extract_schema, schema_to_prompt

UNSAFE_CODES = frozenset({"not_select", "forbidden_statement", "forbidden_function", "multiple_statements"})
APPROACHES = ("zero_shot", "fewshot", "self_correct", "docs", "shots_only", "vote")
N_VOTES = 5
MAX_RETRIES = 2


@dataclass
class PipelineResult:
    question: str
    approach: str
    raw_output: str
    sql: str
    result: ExecResult
    llm_latency_ms: float
    cached: bool
    attempts: list[str] = field(default_factory=list)   # SQL per attempt
    agreement: float | None = None                       # vote only: share of candidates whose result equals the chosen one


class Text2SQL:
    def __init__(self, llm: LLMClient, db_path: str | Path = DEFAULT_DB, row_limit: int = 200,
                 timeout_s: float = 5.0, n_shots: int = 4, pool=POOL, sampler_factory=None, n_votes: int = N_VOTES,
                 abort_on_unsafe: bool = False):
        # sampler_factory(i) -> LLMClient producing the i-th (sampled, i>=1) candidate; required for approach "vote"
        self.llm, self.db_path = llm, db_path
        self.sampler_factory, self.n_votes = sampler_factory, n_votes
        # When True, self_correct never retries after the guardrail rejects a write/disallowed function: it stops and reports
        # the block. Off in the evaluation runs (published numbers), on in the API.
        self.abort_on_unsafe = abort_on_unsafe
        self.row_limit, self.timeout_s = row_limit, timeout_s
        self.tables = extract_schema(db_path)
        self.allowed = {t.name for t in self.tables}
        self.selector = ExampleSelector(pool, k=n_shots)
        self._schema_cache: dict[tuple, str] = {}

    def schema_text(self, with_samples: bool = False) -> str:
        key = (with_samples,)
        if key not in self._schema_cache:
            self._schema_cache[key] = schema_to_prompt(self.tables, with_samples=with_samples)
        return self._schema_cache[key]

    # -- helpers
    def _run(self, sql: str) -> ExecResult:
        return execute_safe(self.db_path, sql, self.allowed, self.timeout_s, self.row_limit)

    def _generate(self, prompt: str):
        resp = self.llm.generate(prompt, SYSTEM)
        return resp, extract_sql(resp.text)

    @staticmethod
    def _problem(res: ExecResult) -> str | None:
        """Feedback message for a retry, or None if the result is acceptable."""
        if not res.ok:
            return {"timeout": "the query took too long; simplify it.",
                    "parse_error": f"it could not be parsed ({res.error}).",
                    }.get(res.code, f"it failed with: {res.error}")
        if not res.rows:
            return "it returned no rows. Re-check the filters, joins and literal values against the schema notes."
        return None

    @staticmethod
    def _result_key(sql: str, res: ExecResult):
        rows = [tuple(round(v, 4) if isinstance(v, float) else v for v in r) for r in res.rows]
        if not re.search(r"\border\s+by\b", sql, re.I):
            rows = sorted(rows, key=repr)
        return (len(res.columns), tuple(rows))

    def _vote(self, question: str) -> PipelineResult:
        if self.sampler_factory is None:
            raise ValueError("approach 'vote' needs sampler_factory (see eval.runner)")
        prompt = zero_shot_prompt(question, self.schema_text(with_samples=False))
        llms = [self.llm] + [self.sampler_factory(i) for i in range(1, self.n_votes)]
        cands = []
        for l in llms:
            resp = l.generate(prompt, SYSTEM)
            sql = extract_sql(resp.text)
            cands.append((sql, self._run(sql), resp))
        groups: dict = {}
        for idx, (sql, res, _) in enumerate(cands):
            if res.ok:
                g = groups.setdefault(self._result_key(sql, res), {"w": 0.0, "first": idx})
                g["w"] += 1.0 if res.rows else 0.5       # empty results are weak evidence
        if groups:
            chosen = cands[max(groups.values(), key=lambda g: (g["w"], -g["first"]))["first"]]
        else:
            chosen = cands[0]                            # nothing executed: surface the greedy candidate's error
        sql, res, resp = chosen
        chosen_key = self._result_key(sql, res) if res.ok else None
        agree = sum(1 for c in cands if c[1].ok and chosen_key is not None and self._result_key(c[0], c[1]) == chosen_key)
        return PipelineResult(question, "vote", resp.text, sql, res, sum(c[2].latency_ms for c in cands),
                              all(c[2].cached for c in cands), [c[0] for c in cands], agree / len(cands))

    # -- main entry
    def ask(self, question: str, approach: str = "zero_shot") -> PipelineResult:
        if approach not in APPROACHES:
            raise ValueError(f"unknown approach '{approach}'; choose from {APPROACHES}")
        if approach == "vote":
            return self._vote(question)
        if approach == "zero_shot":
            prompt = zero_shot_prompt(question, self.schema_text(with_samples=False))
        elif approach == "docs":
            prompt = fewshot_prompt(question, self.schema_text(with_samples=True), [])
        elif approach == "shots_only":
            prompt = shots_only_prompt(question, self.schema_text(with_samples=False), self.selector.select(question))
        else:
            prompt = fewshot_prompt(question, self.schema_text(with_samples=True), self.selector.select(question))

        resp, sql = self._generate(prompt)
        res = self._run(sql)
        total_ms, all_cached, attempts, raw = resp.latency_ms, resp.cached, [sql], resp.text

        if approach == "self_correct":
            best_ok = res if res.ok else None            # remember last executable (even if empty) answer
            best_sql = sql if res.ok else None
            empty_retry_used = False
            for _ in range(MAX_RETRIES):
                if self.abort_on_unsafe and res.code in UNSAFE_CODES:
                    break
                problem = self._problem(res)
                if problem is None:
                    break
                if res.ok:                                # only the empty-result case reaches here
                    if empty_retry_used:
                        break
                    empty_retry_used = True
                resp, new_sql = self._generate(correction_prompt(prompt, sql, problem))
                total_ms += resp.latency_ms
                all_cached = all_cached and resp.cached
                attempts.append(new_sql)
                sql, res, raw = new_sql, self._run(new_sql), resp.text
                if res.ok and res.rows:
                    break
                if res.ok:
                    best_ok, best_sql = res, sql
            if not (res.ok and res.rows) and best_ok is not None and not res.ok:
                res, sql = best_ok, best_sql             # a failed retry must not replace an executable answer
        return PipelineResult(question, approach, raw, sql, res, total_ms, all_cached, attempts)
