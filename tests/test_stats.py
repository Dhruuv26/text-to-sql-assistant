from eval.stats import mcnemar_exact, paired_compare, wilson_ci


def test_wilson_known_values():
    lo, hi = wilson_ci(95, 100)
    assert 88.0 < lo < 89.5 and 97.5 < hi < 99.0
    assert wilson_ci(0, 0) == (0.0, 0.0)
    assert wilson_ci(10, 10)[1] == 100.0


def test_mcnemar_exact():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0
    assert abs(mcnemar_exact(0, 10) - 2 / 1024) < 1e-9
    assert mcnemar_exact(1, 2) > 0.05


def test_paired_compare_only_common_ids():
    c = paired_compare({"a": True, "b": False, "c": True}, {"a": True, "b": True, "z": True})
    assert c["n"] == 2 and c["only_a"] == 0 and c["only_b"] == 1
