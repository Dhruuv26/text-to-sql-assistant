import hashlib
import json
from pathlib import Path

import pytest

from app.llm import FakeLLM
from eval.csvbench import build as cb
from eval.csvbench import fetch as cf
from eval.csvbench import report, run
from eval.csvbench.fetch import FetchError
from guardrails.validator import validate_sql

MINI = (b"name,group,score,note\n"
        b"ann,a,10,x\nbob,a,20,\ncat,b,30,N/A\ndan,b,40,y\neve,b,50,\nfay,c,60,z\n")
GOLD = [
    ("mini", "count", "easy", "How many rows are there?", "SELECT COUNT(*) FROM mini", False, None),
    ("mini", "null", "easy", "How many rows have no note?", "SELECT COUNT(*) FROM mini WHERE note IS NULL", False, None),
    ("mini", "group", "medium", "What is the total score per group?", "SELECT \"group\", SUM(score) FROM mini GROUP BY \"group\"", False, None),
    ("mini", "ranking", "hard", "Who has the highest score, and what is it?",
     "SELECT name, score FROM mini ORDER BY score DESC LIMIT 1", True, 1),
]


def entry(tmp_path, data=MINI, sha=None, name="mini.csv"):
    src = tmp_path / "origin" / name
    src.parent.mkdir(exist_ok=True)
    src.write_bytes(data)
    return {"id": "mini", "file": name, "table": "mini", "url": src.as_uri(),
            "sha256": sha or hashlib.sha256(data).hexdigest()}


@pytest.fixture()
def world(tmp_path):
    e = entry(tmp_path)
    manifest = {"datasets": [e]}
    cache = tmp_path / "cache"
    cf.fetch_all(manifest, cache)
    return manifest, cache, cb.prepare(manifest, cache)


# ------------------------------------------------------------ the committed files
def test_manifest_is_pinned_and_well_formed():
    m = cf.load_manifest()
    assert len(m["datasets"]) == 8 and m["excluded"][0]["file"] == "bad-drivers.csv"
    for e in m["datasets"]:
        assert len(e["commit"]) == 40 and len(e["sha256"]) == 64 and e["commit"] in e["url"]
        assert e["url"].startswith("https://raw.githubusercontent.com/") and e["table"] == e["id"]


def test_committed_questions_are_consistent():
    qs = run.load_questions()
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)) == 80
    manifest_ids = {e["id"] for e in cf.load_manifest()["datasets"]}
    for ds in manifest_ids:
        assert sum(q["dataset"] == ds for q in qs) == 10
    for q in qs:
        assert q["dataset"] in manifest_ids and q["id"].startswith(q["dataset"] + "-") and q["difficulty"] in {"easy", "medium", "hard"}
        v = validate_sql(q["gold_sql"], {q["dataset"]})
        assert v.ok, (q["id"], v.code)
        assert q["n_rows"] >= 1 and len(q["result_hash"]) == 16


def test_gold_source_matches_committed_questions():
    from eval.csvbench.gold_source import GOLD as REAL
    qs = run.load_questions()
    assert [g[3] for g in REAL] == [q["question"] for q in qs] and [g[4] for g in REAL] == [q["gold_sql"] for q in qs]


# ------------------------------------------------------------ fetch
def test_fetch_downloads_verifies_then_uses_cache(tmp_path):
    e = entry(tmp_path)
    cache = tmp_path / "c"
    assert cf.fetch_one(e, cache) == "downloaded" and cf.is_verified(e, cache)
    assert cf.fetch_one(e, cache) == "cached"


def test_fetch_refuses_a_file_whose_hash_changed(tmp_path):
    e = entry(tmp_path, sha="0" * 64)
    with pytest.raises(FetchError, match="SHA-256 mismatch"):
        cf.fetch_one(e, tmp_path / "c")
    assert not cf.raw_path(e, tmp_path / "c").exists()


def test_prepare_refuses_missing_or_tampered_files(tmp_path):
    e = entry(tmp_path)
    cache = tmp_path / "c"
    with pytest.raises(FetchError, match="fetch"):
        cb.prepare({"datasets": [e]}, cache)
    cf.fetch_one(e, cache)
    cf.raw_path(e, cache).write_bytes(MINI + b"tampered,x,1,\n")
    with pytest.raises(FetchError):
        cb.prepare({"datasets": [e]}, cache)


# ------------------------------------------------------------ gold checks
def test_build_accepts_good_gold_and_assigns_ids(world):
    _, _, prepared = world
    records, problems = cb.build(GOLD, prepared)
    assert not problems and [r["id"] for r in records] == ["mini-01", "mini-02", "mini-03", "mini-04"]
    assert records[0]["result_hash"] == cb.build(GOLD, prepared)[0][0]["result_hash"]


@pytest.mark.parametrize("sql,key,why", [
    ("SELECT name FROM mini WHERE score > 999", None, "EMPTY"),
    ("SELECT COUNT(*) FROM mini WHERE score > 999", None, "TRIVIAL"),
    ("SELECT name FROM mini ORDER BY score DESC LIMIT 1", None, "LIMIT without limit_key"),
    ("SELECT name, 5 FROM mini WHERE name <> 'zzz' ORDER BY 2 LIMIT 2", 1, "TIE"),
    ("SELECT nope FROM mini", None, "gold failed"),
    ("SELECT random() FROM mini LIMIT 1", 0, "nondeterministic"),
])
def test_bad_gold_is_rejected(world, sql, key, why):
    _, _, prepared = world
    res, reason = cb.check_gold(prepared["mini"], sql, key)
    assert res is None and why.lower() in reason.lower()


def test_gold_answering_one_is_rejected_as_trivial(world):
    _, _, prepared = world
    _, reason = cb.check_gold(prepared["mini"], "SELECT COUNT(*) FROM mini WHERE name = 'ann'", None)
    assert "TRIVIAL" in reason


# ------------------------------------------------------------ runner self-tests (as for the Chinook harness)
def _questions(prepared):
    records, problems = cb.build(GOLD, prepared)
    assert not problems
    return records


def test_oracle_scores_100_and_constant_model_scores_0(world, tmp_path):
    _, _, prepared = world
    qs = _questions(prepared)
    gold = {q["question"]: q["gold_sql"] for q in qs}
    oracle = FakeLLM(lambda p: gold[" ".join(p.rsplit("Question:", 1)[-1].split("\n")[0].split())])
    for ap in ("plain", "profiled", "profiled_retry"):
        s = run.run_experiment("oracle", ap, questions=qs, prepared=prepared, llm=oracle, results_root=tmp_path / "r", verbose=False)
        assert s["execution_accuracy"] == 100.0 and s["n"] == 4 and set(s["by_dataset"]) == {"mini"}
    s = run.run_experiment("const", "plain", questions=qs, prepared=prepared, llm=FakeLLM("SELECT 5 FROM mini"),
                           results_root=tmp_path / "r", verbose=False)
    assert s["execution_accuracy"] == 0.0


def test_each_configuration_runs_once_unless_forced(world, tmp_path):
    _, _, prepared = world
    qs = _questions(prepared)
    kw = dict(questions=qs, prepared=prepared, llm=FakeLLM("SELECT 5 FROM mini"), results_root=tmp_path / "r", verbose=False)
    run.run_experiment("m", "plain", **kw)
    with pytest.raises(SystemExit, match="already exists"):
        run.run_experiment("m", "plain", **kw)
    run.run_experiment("m", "plain", force=True, **kw)
    with pytest.raises(ValueError):
        run.run_experiment("m", "nope", **kw)


def test_provider_errors_are_recorded_not_fatal(world, tmp_path):
    _, _, prepared = world
    qs = _questions(prepared)

    def boom(_p):
        raise RuntimeError("model down")
    s = run.run_experiment("m", "profiled", questions=qs, prepared=prepared, llm=FakeLLM(boom), results_root=tmp_path / "r", verbose=False)
    assert s["execution_accuracy"] == 0.0 and s["failures"]


def test_profiled_prompt_shows_nulls_that_plain_hides(world):
    _, _, prepared = world
    seen = {}
    qs = _questions(prepared)
    for ap in ("plain", "profiled"):
        run.evaluate(FakeLLM(lambda p, ap=ap: seen.setdefault(ap, p) and "SELECT 1 FROM mini"), ap, qs[:1], prepared, verbose=False)
    assert "NULL of 6" not in seen["plain"] and "3 NULL of 6" in seen["profiled"]


# ------------------------------------------------------------ report
def test_report_renders_tables_and_pairs(world, tmp_path):
    _, _, prepared = world
    qs = _questions(prepared)
    gold = {q["question"]: q["gold_sql"] for q in qs}
    oracle = FakeLLM(lambda p: gold[" ".join(p.rsplit("Question:", 1)[-1].split("\n")[0].split())])
    root = tmp_path / "r"
    for m, llm in (("qwen2.5-coder:3b", FakeLLM("SELECT 5 FROM mini")), ("qwen2.5-coder:7b", oracle)):
        for ap in ("plain", "profiled", "profiled_retry"):
            run.run_experiment(m, ap, questions=qs, prepared=prepared, llm=llm, results_root=root, verbose=False)
    md = report.render(report.load_runs(root))
    for needle in ("CSV generalisation benchmark", "exploratory", "| qwen2.5-coder:7b | profiled | 4/4 | 100.0%", "profiled vs plain",
                   "both models pooled", "By question category", "By dataset", "Failure types"):
        assert needle in md, needle


# ------------------------------------------------------------ real data (skipped unless fetched)
real = pytest.mark.skipif(not all(cf.is_verified(e, cf.CACHE) for e in cf.load_manifest()["datasets"]),
                          reason="run `python -m eval.csvbench.fetch` first")


@real
def test_real_gold_reproduces_the_committed_hashes_and_oracle_is_perfect(tmp_path):
    prepared = cb.prepare()
    records, problems = cb.build(prepared=prepared)
    assert not problems
    committed = {q["id"]: q["result_hash"] for q in run.load_questions()}
    assert {r["id"]: r["result_hash"] for r in records} == committed
    gold = {q["question"]: q["gold_sql"] for q in run.load_questions()}
    oracle = FakeLLM(lambda p: gold[" ".join(p.rsplit("Question:", 1)[-1].split("\n")[0].split())])
    s = run.run_experiment("oracle", "profiled", prepared=prepared, llm=oracle, results_root=tmp_path, verbose=False)
    assert s["execution_accuracy"] == 100.0 and s["n"] == 80
    c = run.run_experiment("const", "profiled", prepared=prepared, llm=FakeLLM("SELECT 1"), results_root=tmp_path, verbose=False)
    assert c["execution_accuracy"] == 0.0


def test_json_helpers_roundtrip():
    assert json.loads(json.dumps({"a": 1})) == {"a": 1} and Path(cf.MANIFEST).exists()
