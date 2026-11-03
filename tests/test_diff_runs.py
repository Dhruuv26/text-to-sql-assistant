
import pytest

from eval.diff_runs import diff
from eval.runs import resolve


def test_diff_lists_only_disagreements():
    a = {"q1": {"correct": True}, "q2": {"correct": False}, "q3": {"correct": True}}
    b = {"q1": {"correct": True}, "q2": {"correct": True}, "q3": {"correct": False}}
    assert diff(a, b) == [("q2", "B_only"), ("q3", "A_only")]


def test_resolve_by_prefix_and_exact(tmp_path):
    (tmp_path / "fewshot__m__dev").mkdir(); (tmp_path / "fewshot__m__test").mkdir()
    assert resolve("fewshot", "dev", tmp_path).name == "fewshot__m__dev"
    assert resolve("fewshot__m__test", "dev", tmp_path).name == "fewshot__m__test"
    with pytest.raises(SystemExit):
        resolve("nope", "dev", tmp_path)
