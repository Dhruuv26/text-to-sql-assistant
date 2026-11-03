from eval.export_demo import pick_examples


def rec(i, cat, diff="medium", correct=True, rows=3, q=None, sql="SELECT 1"):
    return dict(id=f"q{i}", category=cat, difficulty=diff, correct=correct, n_rows=rows, question=q or f"Question {i}?", pred_sql=sql)


def test_only_correct_small_readable_examples_are_exported_one_per_category():
    recs = [rec(1, "join"), rec(2, "join"), rec(3, "group"), rec(4, "topn", correct=False), rec(5, "date", rows=500),
            rec(6, "string", q="x" * 200), rec(7, "negation", sql="  "), rec(8, "window", rows=0), rec(9, "setop", diff="easy")]
    out = pick_examples(recs, n=10)
    assert [o["category"] for o in out] == ["join", "group", "setop"]
    assert all(set(o) == {"question", "sql", "category", "difficulty"} for o in out)


def test_respects_n_and_prefers_medium_before_easy():
    recs = [rec(i, f"c{i}", diff=("easy" if i < 3 else "medium")) for i in range(6)]
    out = pick_examples(recs, n=2)
    assert len(out) == 2 and all(o["difficulty"] == "medium" for o in out)
