import re
from types import SimpleNamespace as NS

import pytest

from app.llm import FakeLLM
from eval.metrics import exact_match, normalize_sql, percentile, results_match
from eval.runner import evaluate, load_questions, summarize
from eval.taxonomy import classify_failure

QS = load_questions("all")
GOLD_BY_Q = {q["question"]: q["gold_sql"] for q in QS}


def oracle(prompt: str) -> str:
    return GOLD_BY_Q[re.search(r"Question: (.*)\n", prompt).group(1)]


# ---------------- results_match
def test_match_ignores_row_order_when_unordered():
    assert results_match([(2,), (1,)], [(1,), (2,)], ordered=False)


def test_match_respects_row_order_when_ordered():
    assert not results_match([(2,), (1,)], [(1,), (2,)], ordered=True)
    assert results_match([(1,), (2,)], [(1,), (2,)], ordered=True)


def test_match_float_tolerance_and_int_float():
    assert results_match([(1.00004,)], [(1.0,)])
    assert results_match([(5,)], [(5.0,)])
    assert not results_match([(1.01,)], [(1.0,)])


def test_match_duplicates_matter():
    assert not results_match([(1,), (1,)], [(1,)])


def test_match_column_permutation_allowed_but_extra_columns_not():
    assert results_match([("a", 1)], [(1, "a")])
    assert not results_match([("a", 1, 9)], [("a", 1)])


def test_match_empty_results():
    assert results_match([], [])
    assert not results_match([], [(1,)])


# ---------------- exact match / percentiles
def test_exact_match_normalises_case_whitespace_semicolon():
    assert exact_match("select  name from artist ;", "SELECT Name FROM Artist")
    assert not exact_match("SELECT Name FROM Album", "SELECT Name FROM Artist")
    assert normalize_sql("SELECT (") is None


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 95) == 0
    assert percentile([10], 95) == 10


# ---------------- taxonomy
def _ex(ok=True, cols=("a",), code=None, error=None):
    return NS(ok=ok, columns=list(cols), code=code, error=error)


G = "SELECT COUNT(*) FROM Track WHERE GenreId = 1"
@pytest.mark.parametrize("pred,pe,expected", [
    ("", _ex(False), "empty_output"),
    ("SELECT x FROM Track", _ex(False, code="db_error", error="no such column: x"), "hallucinated_column"),
    ("SELECT 1 FROM Nope", _ex(False, code="forbidden_table", error="Table not allowed"), "hallucinated_table"),
    ("SELECT 1 FROM Nope", _ex(False, code="db_error", error="no such table: Nope"), "hallucinated_table"),
    ("DROP TABLE Track", _ex(False, code="not_select"), "guardrail_blocked"),
    ("SELECT (", _ex(False, code="parse_error"), "syntax_error"),
    ("SELECT 1", _ex(False, code="timeout"), "timeout"),
    ("SELECT Name, COUNT(*) FROM Track", _ex(True, cols=("a", "b")), "wrong_output_columns"),
    ("SELECT COUNT(*) FROM Album", _ex(True), "wrong_join_or_table"),
    ("SELECT SUM(Milliseconds) FROM Track WHERE GenreId = 1", _ex(True), "wrong_aggregation"),
    ("SELECT COUNT(*) FROM Track WHERE GenreId = 2", _ex(True), "wrong_filter"),
    ("SELECT COUNT(*) FROM Track t WHERE t.GenreId = 1", _ex(True), "other_wrong_result"),
])
def test_taxonomy(pred, pe, expected):
    assert classify_failure(pred, G, pe, _ex()) == expected


def test_taxonomy_ordering_limit():
    gold = "SELECT Name FROM Track ORDER BY Milliseconds DESC LIMIT 5"
    pred = "SELECT Name FROM Track ORDER BY Milliseconds ASC LIMIT 5"
    assert classify_failure(pred, gold, _ex(), _ex()) == "wrong_ordering_limit"


# ---------------- end-to-end harness sanity (the important ones)
def test_oracle_model_scores_100_percent():
    recs = evaluate(FakeLLM(oracle), "zero_shot", QS, verbose=False)
    wrong = [r["id"] for r in recs if not r["correct"]]
    assert not wrong, wrong
    s = summarize(recs, {"approach": "zero_shot", "model": "oracle", "split": "all"})
    assert s["execution_accuracy"] == 100.0 and s["exact_match"] == 100.0 and s["failures"] == {}


def test_constant_wrong_model_scores_near_zero_and_is_categorised():
    recs = evaluate(FakeLLM("SELECT 1"), "zero_shot", QS, verbose=False)
    s = summarize(recs, {"approach": "zero_shot", "model": "bad", "split": "all"})
    assert s["execution_accuracy"] < 5
    assert sum(s["failures"].values()) == sum(1 for r in recs if not r["correct"])


def test_malicious_model_is_blocked_and_counted():
    recs = evaluate(FakeLLM("DROP TABLE Artist"), "zero_shot", QS[:10], verbose=False)
    assert all(r["failure"] == "guardrail_blocked" for r in recs)
    assert summarize(recs, {"approach": "x", "model": "y", "split": "all"})["guardrail_block_rate"] == 100.0


def test_provider_errors_do_not_crash_the_run():
    def boom(_p): raise RuntimeError("ollama down")
    recs = evaluate(FakeLLM(boom), "zero_shot", QS[:3], verbose=False)
    assert len(recs) == 3 and not any(r["correct"] for r in recs)
    assert {r["failure"] for r in recs} == {"provider_error"}


def test_normalize_sql_is_shared_with_the_api():
    from app.sqlnorm import normalize_sql as api_norm
    assert api_norm("SELECT  Name FROM Artist;") == normalize_sql("select name from artist")


def test_fingerprint_ignores_column_aliases_and_constant_text_detection():
    from app.sqlnorm import constant_text_only, fingerprint
    assert fingerprint("SELECT Name AS N FROM Artist") == fingerprint("select name from artist")
    assert constant_text_only("SELECT 'hi' AS x") and not constant_text_only("SELECT 1 + 1")
    assert not constant_text_only("SELECT 'x' FROM Artist")
