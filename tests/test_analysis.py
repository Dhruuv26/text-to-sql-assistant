import json

from eval import analysis, results_md


def _write(root, name, model, approach, split, correct_flags, cat="join", diff="easy"):
    d = root / name
    d.mkdir(parents=True)
    recs = [dict(id=f"{split}{i}", correct=c, category=cat, difficulty=diff, exact_match=c, executed_ok=True, failure=None if c else "wrong_filter",
                 latency_ms=100.0, llm_cached=False, attempts=1, split=split, question="q", gold_sql="g", pred_sql="p", error=None, n_rows=1)
            for i, c in enumerate(correct_flags)]
    (d / "predictions.jsonl").write_text("\n".join(json.dumps(r) for r in recs))
    (d / "summary.json").write_text(json.dumps({"model": model, "approach": approach, "split": split}))


def _setup(tmp_path):
    _write(tmp_path, "a_dev", "m", "zero_shot", "dev", [True, False, False])
    _write(tmp_path, "b_dev", "m", "fewshot", "dev", [True, True, False])
    _write(tmp_path, "a_test", "m", "zero_shot", "test", [True, True, False, False])
    _write(tmp_path, "b_test", "m", "fewshot", "test", [True, True, True, False])
    _write(tmp_path, "c_dev", "m", "vote", "dev", [True, True, True])      # exists on dev only


def test_load_splits_and_pooling(tmp_path):
    _setup(tmp_path)
    assert set(analysis.load("test", tmp_path)) == {("m", "zero_shot"), ("m", "fewshot")}
    pooled = analysis.load("pooled", tmp_path)
    assert set(pooled) == {("m", "zero_shot"), ("m", "fewshot")}          # vote has no test run -> excluded
    assert len(pooled[("m", "zero_shot")]) == 7


def test_compare_counts_fixed_and_broke(tmp_path):
    _setup(tmp_path)
    c = analysis.compare(analysis.load("pooled", tmp_path), ("m", "zero_shot"), ("m", "fewshot"))
    assert (c["n"], c["fixed"], c["broke"]) == (7, 2, 0)
    assert analysis.compare({}, ("x", "y"), ("x", "z")) is None


def test_results_markdown_generation(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(analysis.runner, "RESULTS", tmp_path)
    monkeypatch.setattr(results_md, "OUT", tmp_path / "docs" / "RESULTS.md")
    results_md.main()
    text = (tmp_path / "docs" / "RESULTS.md").read_text()
    assert "Held-out test split" in text and "fewshot vs zero_shot" in text and "Dev vs test" in text and "Pooled" in text
