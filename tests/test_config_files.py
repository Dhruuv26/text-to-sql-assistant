"""Catch broken YAML locally (GitHub Actions only reports it after a push)."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted([*ROOT.glob(".github/workflows/*.yml"), ROOT / "docker-compose.yml"])


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_yaml_parses(path):
    assert isinstance(yaml.safe_load(path.read_text()), dict)


def test_workflow_has_the_expected_jobs_and_steps():
    wf = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert set(wf["jobs"]) == {"test", "docker"} and wf["jobs"]["docker"]["needs"] == "test"
    steps = [s.get("name", s.get("uses", "")) for s in wf["jobs"]["test"]["steps"]]
    assert "Lint" in steps and any("Tests" in s for s in steps)
