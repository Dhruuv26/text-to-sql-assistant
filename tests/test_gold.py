import json
from collections import Counter
from pathlib import Path

import pytest

from app.schema import DEFAULT_DB, table_names
from eval.build_gold import norm_rows
from guardrails.executor import execute_safe

Q = [json.loads(l) for l in (Path(__file__).parent.parent / "eval" / "questions.jsonl").read_text().splitlines()]
TABLES = set(table_names())


def test_size_and_split():
    assert len(Q) >= 100
    c = Counter(r["split"] for r in Q)
    assert c["dev"] >= 30 and c["test"] >= 60
    assert len({r["id"] for r in Q}) == len(Q)
    assert len({r["question"] for r in Q}) == len(Q), "duplicate question text"


def test_covers_difficulty_levels_and_categories():
    assert {r["difficulty"] for r in Q} == {"easy", "medium", "hard"}
    assert len({r["category"] for r in Q}) >= 10


@pytest.mark.parametrize("r", Q, ids=[r["id"] for r in Q])
def test_gold_sql_runs_and_matches_recorded_result(r):
    res = execute_safe(DEFAULT_DB, r["gold_sql"], TABLES, timeout_s=20, row_limit=100_000)
    assert res.ok, res.error
    assert len(res.rows) == r["n_rows"] and len(norm_rows(res.rows)) > 0
