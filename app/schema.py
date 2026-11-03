"""Schema extraction: tables, columns, PK/FK, row counts, sample values -> prompt-ready text."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "chinook.sqlite"


@dataclass
class Column:
    name: str
    type: str
    pk: bool
    samples: list = field(default_factory=list)


@dataclass
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str


@dataclass
class Table:
    name: str
    columns: list[Column]
    fks: list[ForeignKey]
    row_count: int


def _qi(name: str) -> str:
    """Quote an identifier for use in PRAGMA / SELECT (names come from sqlite_master, not users)."""
    return '"' + name.replace('"', '""') + '"'


def extract_schema(db_path: str | Path = DEFAULT_DB, n_samples: int = 3,
                   max_sample_len: int = 40) -> list[Table]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        tables = []
        for t in names:
            cols = []
            for _cid, cname, ctype, _nn, _dflt, pk in con.execute(f"PRAGMA table_info({_qi(t)})"):
                rows = con.execute(
                    f"SELECT DISTINCT {_qi(cname)} FROM {_qi(t)} "
                    f"WHERE {_qi(cname)} IS NOT NULL LIMIT {n_samples}").fetchall()
                samples = [r[0] if not isinstance(r[0], str) else r[0][:max_sample_len] for r in rows]
                cols.append(Column(cname, ctype or "", bool(pk), samples))
            fks = [ForeignKey(r[3], r[2], r[4]) for r in con.execute(f"PRAGMA foreign_key_list({_qi(t)})")]
            count = con.execute(f"SELECT COUNT(*) FROM {_qi(t)}").fetchone()[0]
            tables.append(Table(t, cols, fks, count))
        return tables
    finally:
        con.close()


def table_names(db_path: str | Path = DEFAULT_DB) -> list[str]:
    return [t.name for t in extract_schema(db_path, n_samples=0)]


def schema_to_prompt(tables: list[Table], with_samples: bool = True, with_counts: bool = False) -> str:
    """Render CREATE-TABLE-like text; compact and LLM friendly."""
    out = []
    for t in tables:
        header = f"TABLE {t.name}" + (f"  -- {t.row_count} rows" if with_counts else "")
        out.append(header)
        for c in t.columns:
            line = f"  {c.name} {c.type}" + (" PRIMARY KEY" if c.pk else "")
            if with_samples and c.samples:
                line += f"  -- e.g. {', '.join(repr(s) for s in c.samples)}"
            out.append(line)
        for fk in t.fks:
            out.append(f"  FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table}({fk.ref_column})")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    print(schema_to_prompt(extract_schema(), with_samples=True, with_counts=True))
