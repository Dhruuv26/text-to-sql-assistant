import pytest

from app.llm import CachedLLM, FakeLLM
from app.pipeline import Text2SQL
from app.prompts import extract_sql


@pytest.mark.parametrize("raw,expected", [
    ("SELECT 1", "SELECT 1"),
    ("```sql\nSELECT COUNT(*) FROM Artist;\n```", "SELECT COUNT(*) FROM Artist;"),
    ("Here you go:\n```\nSELECT 2\n```\nHope it helps", "SELECT 2"),
    ("Sure! The query is SELECT Name FROM Artist", "SELECT Name FROM Artist"),
    ("  with t as (select 1) select * from t  ", "with t as (select 1) select * from t"),
])
def test_extract_sql(raw, expected):
    assert extract_sql(raw) == expected


def test_cache_hits_and_preserves_latency(tmp_path):
    fake = FakeLLM("SELECT 1")
    llm = CachedLLM(fake, tmp_path)
    a, b = llm.generate("p", "s"), llm.generate("p", "s")
    assert fake.calls == 1 and not a.cached and b.cached and a.latency_ms == b.latency_ms
    llm.generate("different", "s")
    assert fake.calls == 2 and (llm.hits, llm.misses) == (1, 2)


def test_cache_key_depends_on_model_name(tmp_path):
    f1, f2 = FakeLLM("SELECT 1", name="m1"), FakeLLM("SELECT 1", name="m2")
    CachedLLM(f1, tmp_path).generate("p"); CachedLLM(f2, tmp_path).generate("p")
    assert f1.calls == 1 and f2.calls == 1


def test_pipeline_happy_path():
    t2s = Text2SQL(FakeLLM("```sql\nSELECT COUNT(*) FROM Artist\n```"))
    out = t2s.ask("How many artists?")
    assert out.result.ok and out.result.rows == [(275,)]


def test_pipeline_blocks_malicious_model_output():
    out = Text2SQL(FakeLLM("DROP TABLE Artist")).ask("anything")
    assert not out.result.ok and out.result.code == "not_select"


def test_pipeline_surfaces_db_errors():
    out = Text2SQL(FakeLLM("SELECT Nope FROM Artist")).ask("x")
    assert not out.result.ok and out.result.code == "db_error"


def test_prompt_contains_schema_and_question():
    seen = {}
    t2s = Text2SQL(FakeLLM(lambda p: seen.setdefault("p", p) and "SELECT 1"))
    t2s.ask("Which artist has most albums?")
    assert "TABLE Album" in seen["p"] and "Which artist has most albums?" in seen["p"]
