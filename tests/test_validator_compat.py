"""Regression suite: valid, commonly-LLM-generated SQLite must NOT be rejected by the guardrails (false positives cost accuracy)."""
import pytest

from app.schema import table_names
from guardrails.validator import validate_sql

T = set(table_names())

VALID_SQLITE = [
    "SELECT Name FROM Artist ORDER BY Name LIMIT 1 OFFSET 2",
    "SELECT Name FROM Artist ORDER BY Name LIMIT 2, 3",
    "SELECT Name FROM Artist LIMIT (SELECT COUNT(*) FROM Genre)",
    "SELECT Name FROM Artist LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM Artist)",
    "SELECT GROUP_CONCAT(Name, ', ') FROM Genre",
    "SELECT CAST(Milliseconds AS REAL)/60000 FROM Track",
    "SELECT IIF(Total > 5, 'hi', 'lo') FROM Invoice",
    "SELECT date('now')",
    "SELECT julianday('now') - julianday(HireDate) FROM Employee",
    "SELECT FirstName || ' ' || LastName FROM Customer",
    "SELECT SUM(Total) OVER (ORDER BY InvoiceDate ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) FROM Invoice",
    "SELECT COALESCE(Company, 'none') FROM Customer",
    "SELECT Name FROM Artist WHERE Name GLOB 'A*'",
    "SELECT printf('%.2f', Total) FROM Invoice",
    "SELECT IFNULL(State,'-') FROM Customer",
    'SELECT "Name" FROM "Artist"',
    "SELECT [Name] FROM [Artist]",
    "SELECT substr(Name,1,3) FROM Artist",
    "SELECT strftime('%w', InvoiceDate) FROM Invoice",
    "WITH a AS (SELECT 1 x), b AS (SELECT x+1 y FROM a) SELECT * FROM b",
    "SELECT * FROM (VALUES (1),(2))",
    "SELECT TOTAL(Total), SUM(Total) FROM Invoice",
    "SELECT ROUND(AVG(Total),2) FROM Invoice",
    "SELECT Name FROM Artist a WHERE EXISTS (SELECT 1 FROM Album b WHERE b.ArtistId=a.ArtistId)",
    "SELECT a.Name, COUNT(b.AlbumId) FROM Artist a LEFT JOIN Album b ON a.ArtistId=b.ArtistId GROUP BY a.ArtistId",
    "SELECT * FROM Album JOIN Artist USING (ArtistId) LIMIT 1",
    "SELECT * FROM Album NATURAL JOIN Artist LIMIT 1",
    "SELECT COUNT(*) FROM Genre CROSS JOIN MediaType",
    "SELECT Name FROM Genre UNION ALL SELECT Name FROM MediaType ORDER BY 1",
    "SELECT 1 -- trailing comment",
    "SELECT Name n FROM Artist a",
    "SELECT Name FROM Artist ORDER BY RANDOM() LIMIT 1",
    "SELECT (SELECT COUNT(*) FROM Artist) % 2",
]


@pytest.mark.parametrize("sql", VALID_SQLITE)
def test_valid_sqlite_is_accepted(sql):
    r = validate_sql(sql, T)
    assert r.ok, r.error


@pytest.mark.xfail(strict=True, reason="Known limitation: sqlglot fails to parse LIMIT <arith with subquery and %> OFFSET")
def test_known_limitation_limit_expression_with_modulo_and_offset():
    assert validate_sql("SELECT Name FROM Artist LIMIT 2 - (SELECT COUNT(*) FROM Genre) % 2 OFFSET 1", T).ok
