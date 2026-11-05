import pytest

from app.schema import DEFAULT_DB, extract_schema, schema_to_prompt, table_names
from guardrails.executor import execute_safe
from guardrails.validator import validate_sql

TABLES = set(table_names())

VALID = [
    "SELECT * FROM Artist",
    "select Name from Artist where ArtistId = 1",
    "SELECT COUNT(*) FROM Track",
    "SELECT a.Name, COUNT(*) FROM Artist a JOIN Album b ON a.ArtistId = b.ArtistId GROUP BY a.Name",
    "WITH t AS (SELECT * FROM Track) SELECT COUNT(*) FROM t",
    "SELECT Name FROM Artist UNION SELECT Title FROM Album",
    "SELECT * FROM Track WHERE AlbumId IN (SELECT AlbumId FROM Album WHERE ArtistId = 1)",
    "SELECT 1",
    "SELECT Name FROM Artist; ",                       # trailing semicolon is fine
    "SELECT strftime('%Y', InvoiceDate) FROM Invoice",
]

# (sql, expected code)
INVALID = [
    ("", "empty"),
    ("   ", "empty"),
    ("DROP TABLE Artist", "not_select"),
    ("DELETE FROM Artist", "not_select"),
    ("UPDATE Artist SET Name='x'", "not_select"),
    ("INSERT INTO Artist(Name) VALUES ('x')", "not_select"),
    ("CREATE TABLE x(a)", "not_select"),
    ("ALTER TABLE Artist ADD COLUMN z", "not_select"),
    ("PRAGMA table_info(Artist)", "not_select"),
    ("ATTACH DATABASE 'x.db' AS x", "not_select"),
    ("VACUUM", "not_select"),
    ("SELECT 1; DROP TABLE Artist", "multiple_statements"),
    ("SELECT 1; SELECT 2", "multiple_statements"),
    ("SELECT * FROM sqlite_master", "forbidden_table"),
    ("SELECT * FROM main.Artist", "forbidden_table"),
    ("SELECT * FROM Secrets", "forbidden_table"),
    ("SELECT * FROM Artist, users", "forbidden_table"),
    ("SELECT * FROM Artist WHERE ArtistId IN (SELECT id FROM users)", "forbidden_table"),
    ("WITH x AS (SELECT * FROM users) SELECT * FROM x", "forbidden_table"),
    ("SELECT * FROM json_each('[1,2]')", "forbidden_table"),
    ("SELECT load_extension('evil.so')", "forbidden_function"),
    ("SELECT readfile('/etc/passwd')", "forbidden_function"),
    ("SELECT zeroblob(1000000000)", "forbidden_function"),
    ("SELECT Name FROM Artist WHERE (", "parse_error"),
    ("SELECT" + " 1," * 3000 + " 1", "too_long"),
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_queries_pass(sql):
    r = validate_sql(sql, TABLES)
    assert r.ok, r.error


@pytest.mark.parametrize("sql,code", INVALID)
def test_invalid_queries_blocked(sql, code):
    r = validate_sql(sql, TABLES)
    assert not r.ok
    assert r.code == code, (r.code, r.error)


def test_comment_hidden_statement_blocked():
    assert not validate_sql("SELECT 1 /* ok */; DROP TABLE Artist -- bye", TABLES).ok


def test_case_insensitive_allowlist():
    assert validate_sql("SELECT * FROM aRtIsT", TABLES).ok


def test_cte_name_shadowing_real_denied_table_still_checked():
    # CTE named like a real table is allowed by name, but its body is still validated
    assert not validate_sql("WITH sqlite_master AS (SELECT * FROM users) SELECT * FROM sqlite_master", TABLES).ok


# ---- executor -------------------------------------------------------------

def test_executes_and_returns_rows():
    r = execute_safe(DEFAULT_DB, "SELECT Name FROM Artist ORDER BY ArtistId LIMIT 2", TABLES)
    assert r.ok and r.columns == ["Name"] and r.rows == [("AC/DC",), ("Accept",)]


def test_row_limit_truncates():
    r = execute_safe(DEFAULT_DB, "SELECT * FROM Track", TABLES, row_limit=10)
    assert r.ok and len(r.rows) == 10 and r.truncated


def test_row_limit_not_truncated_when_exact():
    r = execute_safe(DEFAULT_DB, "SELECT * FROM Genre LIMIT 5", TABLES, row_limit=5)
    assert r.ok and len(r.rows) == 5 and not r.truncated


def test_timeout_enforced():
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c"
    r = execute_safe(DEFAULT_DB, sql, TABLES, timeout_s=0.3)
    assert not r.ok and r.code == "timeout" and r.latency_ms < 3000


def test_db_error_reported_for_hallucinated_column():
    r = execute_safe(DEFAULT_DB, "SELECT Nonexistent FROM Artist", TABLES)
    assert not r.ok and r.code == "db_error" and "no such column" in r.error.lower()


def test_blocked_query_never_touches_db():
    r = execute_safe(DEFAULT_DB, "DROP TABLE Artist", TABLES)
    assert not r.ok and r.code == "not_select"
    assert execute_safe(DEFAULT_DB, "SELECT COUNT(*) FROM Artist", TABLES).rows == [(275,)]


def test_connection_is_physically_read_only():
    import sqlite3

    from guardrails.executor import connect_readonly
    con = connect_readonly(DEFAULT_DB, TABLES)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM Artist")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("SELECT * FROM sqlite_master").fetchall()


# ---- schema ---------------------------------------------------------------

def test_schema_extraction_shape():
    tables = {t.name: t for t in extract_schema()}
    assert len(tables) == 11
    assert tables["Track"].row_count == 3503
    assert any(fk.ref_table == "Album" for fk in tables["Track"].fks)
    text = schema_to_prompt(list(tables.values()))
    assert "FOREIGN KEY (AlbumId) REFERENCES Album(AlbumId)" in text


def test_validator_reports_canonical_table_names():
    r = validate_sql("select * from aRtIsT join ALBUM on artist.artistid = album.artistid", TABLES)
    assert r.ok and r.tables == frozenset({"Artist", "Album"})


@pytest.mark.parametrize("n", [500, 1200, 2400])
def test_deeply_nested_sql_is_rejected_not_a_crash(n):
    r = validate_sql("SELECT " + "(" * n + "1" + ")" * n, TABLES)
    assert not r.ok and r.code in ("too_complex", "too_long")


def test_executor_survives_deeply_nested_sql():
    r = execute_safe(DEFAULT_DB, "SELECT " + "(" * 2400 + "1" + ")" * 2400, TABLES)
    assert not r.ok and r.code == "too_complex"
