import shutil

from app.llm import FakeLLM
from app.schema import DEFAULT_DB
from eval.redteam import PROMPTS, run_redteam


def _db_copy(tmp_path):
    dst = tmp_path / "chinook.sqlite"
    shutil.copy(DEFAULT_DB, dst)
    return dst


def test_hostile_model_output_is_blocked_and_database_never_changes(tmp_path):
    db = _db_copy(tmp_path)
    s = run_redteam(FakeLLM("DROP TABLE Artist"), "zero_shot", db_path=db, verbose=False)
    assert s["n"] == len(PROMPTS) and s["db_modified"] is False
    assert all(r["outcome"] == "blocked" for r in s["rows"]) and not any(r["db_changed"] for r in s["rows"])


def test_system_table_probe_is_blocked(tmp_path):
    s = run_redteam(FakeLLM("SELECT * FROM sqlite_master"), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    assert all(r["outcome"] == "blocked" and r["code"] == "forbidden_table" for r in s["rows"])


def test_out_of_scope_answers_are_counted_as_irrelevant(tmp_path):
    s = run_redteam(FakeLLM("SELECT COUNT(*) FROM Artist"), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    assert s["out_of_scope_irrelevant_answers"] == 8 and s["outcomes_by_kind"]["out_of_scope"] == {"executed": 8}


def test_policy_catches_every_write_prompt_and_stated_sql_injection(tmp_path):
    s = run_redteam(FakeLLM("SELECT 1"), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    refused = {r["id"] for r in s["rows"] if r["policy_refuses"]}
    assert {f"w0{i}" for i in range(1, 9)} <= refused and {"i01", "i04", "i05", "i08"} <= refused
    assert not refused & {f"o0{i}" for i in range(1, 9)}                # no out-of-scope prompt is mistaken for a write


def test_provider_failure_is_recorded_not_raised(tmp_path):
    def boom(_p):
        raise RuntimeError("down")
    s = run_redteam(FakeLLM(boom), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    assert all(r["outcome"] == "provider_error" for r in s["rows"]) and s["db_modified"] is False


def test_show_prints_one_block_per_prompt(tmp_path, capsys):
    from eval.redteam import show
    s = run_redteam(FakeLLM("SELECT COUNT(*) FROM Artist"), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    show(s)
    out = capsys.readouterr().out
    assert out.count("prompt:") == len(PROMPTS) and "policy-refuses" in out and "SELECT COUNT(*) FROM Artist" in out


def test_first_attempt_interception_is_recorded_when_retry_repairs_it(tmp_path):
    llm = FakeLLM(lambda p: "SELECT 1" if "had a problem" in p else "DROP TABLE Artist")
    s = run_redteam(llm, "self_correct", db_path=_db_copy(tmp_path), verbose=False, abort_on_unsafe=False)
    assert s["first_attempt_intercepted_by_guardrail"] == len(PROMPTS) and s["db_modified"] is False
    assert all(r["outcome"] == "executed" and len(r["attempts"]) == 2 for r in s["rows"])


def test_model_written_text_is_counted(tmp_path):
    s = run_redteam(FakeLLM("SELECT 'Test Band' AS ArtistName"), "zero_shot", db_path=_db_copy(tmp_path), verbose=False)
    assert s["literal_text_answers"] == len(PROMPTS) and s["out_of_scope_breakdown"]["model_written_text"] == 8


def test_safe_mode_stops_after_a_rejected_write_instead_of_repairing_it(tmp_path):
    llm = FakeLLM(lambda p: "SELECT 1" if "had a problem" in p else "DROP TABLE Artist")
    s = run_redteam(llm, "self_correct", db_path=_db_copy(tmp_path), verbose=False)       # default: abort_on_unsafe=True
    assert all(r["outcome"] == "blocked" and r["code"] == "not_select" and len(r["attempts"]) == 1 for r in s["rows"])
    assert llm.calls == len(PROMPTS)
