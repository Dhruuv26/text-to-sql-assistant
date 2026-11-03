import json
import re
from pathlib import Path

import pytest

from app.fewshot_pool import POOL
from app.llm import FakeLLM
from app.pipeline import APPROACHES, Text2SQL
from app.retrieval import ExampleSelector
from app.schema import DEFAULT_DB, table_names
from eval.runner import evaluate, load_questions
from guardrails.executor import execute_safe

GOLD = [json.loads(l) for l in (Path(__file__).parent.parent / "eval" / "questions.jsonl").read_text().splitlines()]
GOOD = "SELECT COUNT(*) FROM Artist"
BAD_COL = "SELECT Nope FROM Artist"
EMPTY = "SELECT Name FROM Artist WHERE Name = 'zzz-nonexistent'"


# ---------- few-shot pool hygiene
def test_pool_examples_execute_and_are_nonempty():
    T = set(table_names())
    for q, s in POOL:
        r = execute_safe(DEFAULT_DB, s, T, 10, 100_000)
        assert r.ok and r.rows, (q, r.error)


def test_pool_has_zero_overlap_with_eval_questions():
    gq = {g["question"].strip().lower() for g in GOLD}
    gs = {" ".join(g["gold_sql"].lower().split()) for g in GOLD}
    for q, s in POOL:
        assert q.strip().lower() not in gq, q
        assert " ".join(s.lower().split()) not in gs, s


# ---------- selector
def test_selector_returns_k_and_is_deterministic():
    sel = ExampleSelector(POOL, k=4)
    a = sel.select("How many tracks per genre including empty genres?")
    assert len(a) == 4 and a == sel.select("How many tracks per genre including empty genres?")


def test_selector_finds_its_own_example_first():
    sel = ExampleSelector(POOL, k=3)
    for q, s in POOL[:8]:
        assert sel.select(q)[0] == (q, s)


# ---------- prompts
def _capture(approach):
    seen = []
    t = Text2SQL(FakeLLM(lambda p: seen.append(p) or GOOD))
    t.ask("Which artist has the most albums?", approach)
    return seen[0]


def test_fewshot_prompt_has_notes_rules_examples_samples_and_question_last():
    p = _capture("fewshot")
    assert "Examples:" in p and "Rules:" in p and "Notes about the data" in p and "-- e.g." in p
    assert p.rstrip().endswith("Question: Which artist has the most albums?\nSQL:")


def test_zero_shot_prompt_stays_minimal():
    p = _capture("zero_shot")
    assert "Examples:" not in p and "Rules:" not in p and "-- e.g." not in p


def test_unknown_approach_rejected():
    with pytest.raises(ValueError):
        Text2SQL(FakeLLM(GOOD)).ask("x", "magic")


# ---------- self-correction loop
def _fixer(first, second):
    return lambda p: second if "had a problem" in p else first


def test_self_correct_fixes_db_error_with_feedback():
    seen = []
    def resp(p):
        seen.append(p)
        return GOOD if "had a problem" in p else BAD_COL
    out = Text2SQL(FakeLLM(resp)).ask("q", "self_correct")
    assert out.result.ok and out.result.rows == [(275,)] and len(out.attempts) == 2
    assert "no such column" in seen[1] and BAD_COL in seen[1]


def test_self_correct_gives_up_after_two_retries():
    llm = FakeLLM(BAD_COL)
    out = Text2SQL(llm).ask("q", "self_correct")
    assert not out.result.ok and len(out.attempts) == 3 and llm.calls == 3


def test_self_correct_does_not_retry_when_first_answer_is_good():
    llm = FakeLLM(GOOD)
    out = Text2SQL(llm).ask("q", "self_correct")
    assert llm.calls == 1 and len(out.attempts) == 1


def test_self_correct_retries_once_on_empty_result():
    llm = FakeLLM(_fixer(EMPTY, GOOD))
    out = Text2SQL(llm).ask("q", "self_correct")
    assert out.result.rows == [(275,)] and llm.calls == 2


def test_failed_retry_never_replaces_an_executable_answer():
    llm = FakeLLM(_fixer(EMPTY, BAD_COL))
    out = Text2SQL(llm).ask("q", "self_correct")
    assert out.result.ok and out.result.rows == [] and out.sql == EMPTY


def test_self_correct_retries_guardrail_blocks_too():
    out = Text2SQL(FakeLLM(_fixer("DROP TABLE Artist", GOOD))).ask("q", "self_correct")
    assert out.result.ok and len(out.attempts) == 2


def test_latency_is_summed_over_attempts():
    out = Text2SQL(FakeLLM(_fixer(BAD_COL, GOOD))).ask("q", "self_correct")
    assert out.llm_latency_ms == 2.0   # FakeLLM reports 1.0 ms per call


# ---------- harness sanity for every approach
GOLD_BY_Q = {g["question"]: g["gold_sql"] for g in GOLD}


def oracle(prompt):
    return GOLD_BY_Q[re.findall(r"Question: (.*)\n", prompt)[-1]]


@pytest.mark.parametrize("approach", APPROACHES)
def test_oracle_scores_100_for_every_approach(approach):
    recs = evaluate(FakeLLM(oracle), approach, load_questions("all"), verbose=False, sampler_factory=lambda i: FakeLLM(oracle))
    assert all(r["correct"] for r in recs), [r["id"] for r in recs if not r["correct"]]
    assert all(r["attempts"] == (5 if approach == "vote" else 1) for r in recs)


# ---------- voting
def _voter(outputs):
    """llm greedy = outputs[0]; sampler i -> outputs[i]"""
    llms = [FakeLLM(o) for o in outputs]
    return llms[0], (lambda i: llms[i])


def _vote(outputs, **kw):
    llm, fac = _voter(outputs)
    return Text2SQL(llm, sampler_factory=fac, n_votes=len(outputs), **kw).ask("q", "vote")


GENRES = "SELECT COUNT(*) FROM Genre"


def test_vote_majority_beats_greedy():
    out = _vote([BAD_COL.replace("Nope", "Name"), GOOD, GOOD, GOOD, "SELECT COUNT(*) FROM Album"])
    assert out.result.rows == [(275,)] and len(out.attempts) == 5


def test_vote_tie_prefers_greedy_candidate():
    out = _vote([GENRES, GOOD, GENRES, GOOD])
    assert out.sql == GENRES


def test_vote_ignores_failing_candidates():
    out = _vote([BAD_COL, BAD_COL, BAD_COL, GOOD, BAD_COL])
    assert out.result.ok and out.result.rows == [(275,)]


def test_vote_all_failing_returns_greedy_error():
    out = _vote([BAD_COL, "DROP TABLE Artist", BAD_COL])
    assert not out.result.ok and out.sql == BAD_COL


def test_vote_empty_results_are_weak_evidence():
    out = _vote([EMPTY, EMPTY, GOOD, GOOD, EMPTY])      # 3 empty = 1.5 weight vs 2 good = 2.0
    assert out.result.rows == [(275,)]


def test_vote_treats_row_order_as_irrelevant_without_order_by():
    a = "SELECT Name FROM Genre WHERE GenreId IN (1, 2)"
    b = "SELECT Name FROM Genre WHERE GenreId IN (2, 1) ORDER BY GenreId DESC"   # same rows, different order, has ORDER BY
    c = "SELECT Name FROM Genre WHERE GenreId IN (1, 2) ORDER BY GenreId"
    out = _vote([a, c, c, b, GOOD])
    assert out.sql in (a, c)


def test_vote_latency_summed_and_needs_factory():
    assert _vote([GOOD] * 5).llm_latency_ms == 5.0
    with pytest.raises(ValueError):
        Text2SQL(FakeLLM(GOOD)).ask("q", "vote")


# ---------- vote diagnostics + test-split guard
def test_vote_reports_agreement():
    out = _vote([GOOD, GOOD, GOOD, GENRES, GOOD])
    assert out.agreement == 0.8
    assert _vote([GOOD] * 5).agreement == 1.0


def test_test_split_run_is_refused_when_it_already_exists(tmp_path, monkeypatch):
    from eval import runner
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    fake = FakeLLM(GOOD)
    runner.run_experiment("fake", "zero_shot", "test", llm=fake, limit=3)
    assert (tmp_path / "zero_shot__fake__test" / "summary.json").exists()
    with pytest.raises(SystemExit):
        runner.run_experiment("fake", "zero_shot", "test", llm=fake, limit=3)
    runner.run_experiment("fake", "zero_shot", "test", llm=fake, limit=3, force=True)   # explicit override allowed
    runner.run_experiment("fake", "zero_shot", "dev", llm=fake, limit=3)
    runner.run_experiment("fake", "zero_shot", "dev", llm=fake, limit=3)                # dev may be re-run freely


def test_vote_summary_contains_agreement():
    from eval.runner import summarize
    recs = evaluate(FakeLLM(GOOD), "vote", load_questions("dev", 4), verbose=False, sampler_factory=lambda i: FakeLLM(GOOD))
    s = summarize(recs, {"approach": "vote", "model": "x", "split": "dev"})
    assert s["vote_mean_agreement"] == 1.0 and s["vote_unanimous_rate"] == 100.0


# ---------- abort_on_unsafe
def _retry_llm(first, second="SELECT 1"):
    return FakeLLM(lambda p: second if "had a problem" in p else first)


def test_abort_on_unsafe_stops_after_a_rejected_write():
    llm = _retry_llm("DELETE FROM Customer")
    out = Text2SQL(llm, abort_on_unsafe=True).ask("q", "self_correct")
    assert not out.result.ok and out.result.code == "not_select" and out.sql == "DELETE FROM Customer"
    assert llm.calls == 1 and len(out.attempts) == 1


def test_default_behaviour_still_retries_after_a_rejected_write():          # what the published evaluation measured
    llm = _retry_llm("DELETE FROM Customer")
    out = Text2SQL(llm).ask("q", "self_correct")
    assert out.result.ok and llm.calls == 2 and len(out.attempts) == 2


def test_abort_on_unsafe_still_retries_invented_tables_and_db_errors():
    for bad in ("SELECT * FROM Weather", BAD_COL):
        llm = _retry_llm(bad, GOOD)
        out = Text2SQL(llm, abort_on_unsafe=True).ask("q", "self_correct")
        assert out.result.ok and out.result.rows == [(275,)] and llm.calls == 2


def test_abort_on_unsafe_blocks_disallowed_functions_without_retry():
    llm = _retry_llm("SELECT readfile('/etc/passwd')")
    out = Text2SQL(llm, abort_on_unsafe=True).ask("q", "self_correct")
    assert out.result.code == "forbidden_function" and llm.calls == 1
