"""Turn an uploaded CSV / TSV / XLSX file into typed SQLite tables, defensively.

Everything that comes from the file (headers, sheet names, cell text) is untrusted. This module therefore
  * never uses file-supplied text as an SQL identifier without normalising it to [a-z0-9_] (see normalize_name),
  * binds cell values as parameters (never string-formats them into SQL),
  * enforces byte / row / column / sheet limits and rejects (instead of truncating) files that exceed them,
  * records per-column metadata (type, nulls, distinct values, samples) used later to build the model prompt.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


class IngestError(ValueError):
    """Raised with a message that is safe to show to the user."""


@dataclass(frozen=True)
class IngestLimits:
    max_bytes: int = 5_000_000
    max_rows: int = 20_000
    max_cols: int = 60
    max_sheets: int = 4
    max_uncompressed: int = 50_000_000      # xlsx is a zip: cap the expanded size
    max_ratio: int = 120                    # ... and the per-entry compression ratio
    max_cell_chars: int = 2_000


DEFAULT_LIMITS = IngestLimits()


@dataclass
class ColumnMeta:
    name: str                               # normalised SQL identifier
    label: str                              # original header text (display only, never put in prompts)
    sqltype: str                            # INTEGER | REAL | TEXT
    kind: str                               # integer | real | text | date | currency | percent
    nulls: int = 0
    distinct: int = 0
    samples: list = field(default_factory=list)      # most frequent values first
    categories: list | None = None                   # all distinct values when there are few
    min: Any = None
    max: Any = None
    note: str = ""


@dataclass
class TableMeta:
    name: str
    label: str
    rows: int
    columns: list[ColumnMeta]


@dataclass
class IngestResult:
    tables: list[TableMeta]
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- names
_RESERVED = set("""abort action add after all alter always analyze and as asc attach autoincrement before begin between by cascade case
cast check collate column commit conflict constraint create cross current current_date current_time current_timestamp database default
deferrable deferred delete desc detach distinct do drop each else end escape except exclude exclusive exists explain fail filter first
following for foreign from full generated glob group groups having if ignore immediate in index indexed initially inner insert instead
intersect into is isnull join key last left like limit match materialized natural no not nothing notnull null nulls of offset on or order
others outer over partition plan pragma preceding primary query raise range recursive references regexp reindex release rename replace
restrict returning right rollback row rows savepoint select set table temp temporary then ties to transaction trigger unbounded union
unique update using vacuum values view virtual when where window with without""".split())
_SYMBOLS = {"%": " pct ", "#": " num ", "&": " and ", "$": " usd ", "@": " at ", "€": " eur ", "£": " gbp "}
MAX_NAME = 40


def normalize_name(raw: Any, taken: set[str], fallback: str) -> str:
    """'Total Revenue ($)' -> 'total_revenue_usd'. Always [a-z][a-z0-9_]*, unique within `taken`, never a reserved word."""
    s = "" if raw is None else str(raw)
    for sym, word in _SYMBOLS.items():
        s = s.replace(sym, word)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:MAX_NAME].strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = "c_" + s
    if s in _RESERVED or s.startswith("sqlite_"):
        s += "_"
    base, n = s, 2
    while s in taken:
        suffix = f"_{n}"
        s = base[: MAX_NAME - len(suffix)] + suffix
        n += 1
    taken.add(s)
    return s


# --------------------------------------------------------------------------- cell cleaning
NULL_TOKENS = {"", "na", "n/a", "#n/a", "n.a.", "null", "none", "nan", "nil", "-", "--", "?", "missing"}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060\ufeff]")


def clean_cell(v: Any, max_chars: int) -> Any:
    """Strings are stripped / de-controlled and mapped to None for missing-value tokens; other types pass through."""
    if v is None:
        return None
    if isinstance(v, str):
        s = _CTRL.sub("", v.replace("\xa0", " ")).strip()
        if s.lower() in NULL_TOKENS:
            return None
        return s[:max_chars]
    return v


# --------------------------------------------------------------------------- numbers
_NUM = re.compile(r"^(?P<s1>[-+\u2212])?\s*(?P<cur>[$€£¥₹])?\s*(?P<s2>[-+\u2212])?\s*"
                  r"(?P<body>\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)\s*(?P<pct>%)?$")


def parse_number(s: str):
    """-> (value, family) with family in plain|grouped|currency|percent, or None. IDs like '007' are deliberately NOT numbers."""
    t = s.strip()
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    m = _NUM.match(t)
    if not m:
        return None
    if m["s1"] and m["s2"]:
        return None                                   # "--5", "-$-5"
    body = m["body"]
    digits = body.replace(",", "")
    whole = digits.split(".")[0]
    if (len(whole) > 1 and whole.startswith("0") and "." not in digits) or len(whole) > 15:
        return None                                   # leading-zero identifiers and very long digit strings stay text
    val: int | float = float(digits) if "." in digits else int(digits)
    if "\u2212" in (m["s1"] or "") + (m["s2"] or "") or "-" in (m["s1"] or "") + (m["s2"] or ""):
        neg = not neg if neg else True
    family = "percent" if m["pct"] else "currency" if m["cur"] else "grouped" if "," in body else "plain"
    return (-val if neg else val), family


# --------------------------------------------------------------------------- dates
_MONTHS = {m: i + 1 for i, names in enumerate(
    ["jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august", "sep sept september",
     "oct october", "nov november", "dec december"]) for m in names.split()}
_TIME = r"(?:[ T](?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2})(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?"
_D_ISO = re.compile(rf"^(?P<y>\d{{4}})-(?P<m>\d{{1,2}})-(?P<d>\d{{1,2}}){_TIME}$")
_D_YMD = re.compile(rf"^(?P<y>\d{{4}})[/.](?P<m>\d{{1,2}})[/.](?P<d>\d{{1,2}}){_TIME}$")
_D_DMONY = re.compile(r"^(?P<d>\d{1,2})[- ](?P<mon>[A-Za-z]{3,9})\.?[- ,]+(?P<y>\d{4})$")
_D_MONDY = re.compile(r"^(?P<mon>[A-Za-z]{3,9})\.? (?P<d>\d{1,2}),? (?P<y>\d{4})$")
_D_NUM = re.compile(rf"^(?P<a>\d{{1,2}})[/.-](?P<b>\d{{1,2}})[/.-](?P<y>\d{{4}}){_TIME}$")


def _mk(y, m, d, h=None, mi=None, s=None) -> str | None:
    try:
        dt = datetime(int(y), int(m), int(d), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_date_column(values: list[str]) -> tuple[list[str] | None, str]:
    """All values must belong to ONE date family. -> (iso strings, note). (None, note) when not a date column."""
    out: list[str] = []
    fams = [(_D_ISO, "ymd"), (_D_YMD, "ymd"), (_D_DMONY, "dmony"), (_D_MONDY, "mondy"), (_D_NUM, "num")]
    for rx, fam in fams:
        ms = [rx.match(v) for v in values]
        if not all(ms):
            continue
        if fam == "num":
            first_gt12 = any(int(m["a"]) > 12 for m in ms)
            second_gt12 = any(int(m["b"]) > 12 for m in ms)
            if first_gt12 and second_gt12:
                return None, ""
            if not first_gt12 and not second_gt12:
                return None, "dates like 03/04/2020 are ambiguous (day/month order), so the column was kept as text"
            dmy = first_gt12
            out = [_mk(m["y"], m["b"] if dmy else m["a"], m["a"] if dmy else m["b"], m["h"], m["mi"], m["s"]) for m in ms]
        elif fam == "ymd":
            out = [_mk(m["y"], m["m"], m["d"], m["h"], m["mi"], m["s"]) for m in ms]
        else:
            mons = [_MONTHS.get(m["mon"].lower()) for m in ms]
            if not all(mons):
                continue
            out = [_mk(m["y"], mo, m["d"]) for m, mo in zip(ms, mons, strict=True)]
        if any(o is None for o in out):
            return None, ""
        if all(o.endswith("00:00:00") for o in out):
            out = [o[:10] for o in out]
        return out, ""
    return None, ""


# --------------------------------------------------------------------------- column typing
def infer_column(raw: list[Any]) -> tuple[list[Any], str, str, str]:
    """-> (stored values, sqltype, kind, note). `raw` holds cleaned cells (None = missing)."""
    non = [v for v in raw if v is not None]
    if not non:
        return raw, "TEXT", "text", ""
    if all(isinstance(v, bool) for v in non):
        return [None if v is None else int(v) for v in raw], "INTEGER", "integer", ""
    if all(isinstance(v, (datetime, date)) for v in non):
        def iso(v):
            if v is None:
                return None
            return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v.strftime("%Y-%m-%d 00:00:00")
        vals = [iso(v) for v in raw]
        if all(v is None or v.endswith("00:00:00") for v in vals):
            vals = [None if v is None else v[:10] for v in vals]
        return vals, "TEXT", "date", ""
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non):
        if all(float(v).is_integer() for v in non):
            return [None if v is None else int(v) for v in raw], "INTEGER", "integer", ""
        return raw, "REAL", "real", ""
    # anything non-string left over (time objects, mixed Excel types) becomes text
    strs = [None if v is None else (v if isinstance(v, str) else str(v)) for v in raw]
    sn = [v for v in strs if v is not None]

    parsed = [parse_number(v) for v in sn]
    if all(p is not None for p in parsed):
        fams = {p[1] for p in parsed}
        if "percent" in fams and fams != {"percent"}:
            return strs, "TEXT", "text", "mixed percent and plain numbers, kept as text"
        it = iter(parsed)
        vals = [None if v is None else next(it)[0] for v in strs]
        has_dot = any("." in v for v in sn)
        integral = all(float(p[0]).is_integer() for p in parsed) and not has_dot
        kind = "percent" if fams == {"percent"} else "currency" if "currency" in fams else "integer" if integral else "real"
        note = {"percent": "stored as a number in percent units (12.5 means 12.5%)",
                "currency": "currency symbols and thousands separators were removed"}.get(kind, "")
        if kind in ("integer", "real") and "grouped" in fams:
            note = "thousands separators were removed"
        return ([None if v is None else (int(v) if integral else float(v)) for v in vals],
                "INTEGER" if integral else "REAL", kind, note)

    dates, note = parse_date_column(sn)
    if dates is not None:
        it = iter(dates)
        return [None if v is None else next(it) for v in strs], "TEXT", "date", "dates normalised to YYYY-MM-DD"
    return strs, "TEXT", "text", note


def _profile(values: list[Any], kind: str) -> dict:
    non = [v for v in values if v is not None]
    cnt = Counter(non)
    order = {v: i for i, v in enumerate(dict.fromkeys(non))}
    top = sorted(cnt, key=lambda v: (-cnt[v], order[v]))
    out = {"nulls": len(values) - len(non), "distinct": len(cnt), "samples": top[:4]}
    if len(cnt) <= 12 and kind in ("text",) and cnt:
        out["categories"] = sorted(cnt, key=lambda v: order[v])
    if non and kind in ("integer", "real", "currency", "percent", "date"):
        out["min"], out["max"] = min(non), max(non)
    return out


# --------------------------------------------------------------------------- reading files
_DELIMS = [",", ";", "\t", "|"]


def _decode(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise IngestError("This does not look like a text file. Upload a .csv, .tsv or .xlsx file.")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _sniff(text: str) -> str:
    lines = [ln for ln in text.splitlines()[:30] if ln.strip()]
    best, best_score = ",", -1.0
    for d in _DELIMS:
        counts = [len(next(csv.reader([ln], delimiter=d))) for ln in lines] if lines else [1]
        mode = Counter(counts).most_common(1)[0][0]
        score = (mode > 1) * (counts.count(mode) / len(counts)) * (1 + 0.01 * min(mode, 50))
        if score > best_score:
            best, best_score = d, score
    return best


def read_csv_rows(data: bytes, lim: IngestLimits) -> tuple[list[list[Any]], list[str]]:
    text = _decode(data)
    delim = _sniff(text)
    csv.field_size_limit(max(lim.max_cell_chars * 20, 100_000))
    rows: list[list[Any]] = []
    try:
        for row in csv.reader(io.StringIO(text), delimiter=delim):
            if not any(c.strip() for c in row):
                continue
            rows.append(row)
            if len(rows) > lim.max_rows + 1:
                raise IngestError(f"The file has more than {lim.max_rows:,} rows. Upload a smaller file.")
    except csv.Error as e:
        raise IngestError(f"The file could not be read as CSV ({str(e)[:80]}).") from None
    return rows, []


def read_xlsx_sheets(data: bytes, lim: IngestLimits) -> tuple[list[tuple[str, list[list[Any]]]], list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise IngestError("This is not a valid .xlsx file.") from None
    total = 0
    for info in zf.infolist():
        total += info.file_size
        if total > lim.max_uncompressed or (info.compress_size and info.file_size / info.compress_size > lim.max_ratio
                                           and info.file_size > 1_000_000):
            raise IngestError("The Excel file expands to an unreasonable size and was rejected.")
    names = set(zf.namelist())
    if "xl/vbaProject.bin" in names:
        raise IngestError("Excel files with macros are not accepted. Save a copy as .xlsx without macros.")
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise IngestError("The Excel file could not be read.") from None
    sheets, warnings = [], []
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            rows: list[list[Any]] = []
            for r in ws.iter_rows(values_only=True):
                if r is None or not any(c is not None and str(c).strip() for c in r):
                    continue
                rows.append(list(r))
                if len(rows) > lim.max_rows + 1:
                    raise IngestError(f"Sheet '{str(ws.title)[:40]}' has more than {lim.max_rows:,} rows. Upload a smaller file.")
            if rows:
                sheets.append((str(ws.title), rows))
            if len(sheets) > lim.max_sheets:
                raise IngestError(f"The workbook has more than {lim.max_sheets} non-empty sheets.")
    finally:
        wb.close()
    if not sheets:
        raise IngestError("The workbook has no data.")
    return sheets, warnings


# --------------------------------------------------------------------------- building tables
def _is_numberish(v: Any) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    return isinstance(v, str) and parse_number(v) is not None


def build_table(rows: list[list[Any]], label: str, taken_tables: set[str], lim: IngestLimits) -> tuple[TableMeta, list[list[Any]], list[str]]:
    warnings: list[str] = []
    first_raw = rows[0]
    header_like = sum(1 for c in first_raw if c is not None and str(c).strip() and not _is_numberish(c))
    filled = sum(1 for c in first_raw if c is not None and str(c).strip())
    has_header = filled > 0 and header_like >= max(1, 0.6 * filled)
    width = len(first_raw) if has_header else max(len(r) for r in rows)      # cells beyond the header are trimmed (and counted below)
    if width > lim.max_cols + 40:
        raise IngestError(f"The file has more than {lim.max_cols} columns.")
    norm = [(list(r) + [None] * (width - len(r)))[:width] for r in rows]
    if has_header:
        headers, body = [("" if c is None else str(c)) for c in norm[0]], norm[1:]
    else:
        headers, body = [""] * width, norm
        warnings.append(f"'{label[:40]}': no header row was found, columns were named col_1, col_2, ...")
    if not body:
        raise IngestError(f"'{label[:40]}' has a header but no data rows.")

    cleaned = [[clean_cell(c, lim.max_cell_chars) for c in r] for r in body]
    keep = [j for j in range(width) if headers[j].strip() or any(r[j] is not None for r in cleaned)]
    if not keep:
        raise IngestError(f"'{label[:40]}' has no usable columns.")
    if len(keep) > lim.max_cols:
        raise IngestError(f"The file has {len(keep)} columns; the limit is {lim.max_cols}.")
    ragged = sum(1 for r in rows if len(r) != width)
    if ragged:
        warnings.append(f"'{label[:40]}': {ragged} rows had a different number of cells than the header and were padded or trimmed")

    taken_cols: set[str] = set()
    metas, columns = [], []
    for j in keep:
        raw_col = [r[j] for r in cleaned]
        vals, sqltype, kind, note = infer_column(raw_col)
        name = normalize_name(headers[j], taken_cols, f"col_{j + 1}")
        prof = _profile(vals, kind)
        metas.append(ColumnMeta(name=name, label=headers[j].strip()[:80] or f"column {j + 1}", sqltype=sqltype, kind=kind, note=note, **prof))
        columns.append(vals)
    tname = normalize_name(label, taken_tables, "data")
    table = TableMeta(name=tname, label=label[:80], rows=len(cleaned), columns=metas)
    return table, [list(r) for r in zip(*columns, strict=True)], warnings


def write_tables(db_path: str | Path, built: list[tuple[TableMeta, list[list[Any]]]]) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA synchronous=OFF")
        with con:
            for table, rows in built:
                cols = ", ".join(f'"{c.name}" {c.sqltype}' for c in table.columns)
                con.execute(f'CREATE TABLE "{table.name}" ({cols})')            # names are normalised identifiers, never raw text
                marks = ", ".join("?" for _ in table.columns)
                con.executemany(f'INSERT INTO "{table.name}" VALUES ({marks})', rows)    # values are always bound parameters
    finally:
        con.close()


def ingest_file(filename: str, data: bytes, db_path: str | Path, existing_tables: set[str] | None = None,
                limits: IngestLimits = DEFAULT_LIMITS) -> IngestResult:
    """Parse `data` and add its table(s) to the SQLite file at db_path. Raises IngestError with a user-safe message."""
    if len(data) > limits.max_bytes:
        raise IngestError(f"The file is larger than {limits.max_bytes / 1e6:.0f} MB.")
    if not data.strip():
        raise IngestError("The file is empty.")
    name = Path(str(filename).replace("\\", "/")).name
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    taken = set(existing_tables or set())
    warnings: list[str] = []
    built: list[tuple[TableMeta, list[list[Any]]]] = []

    if ext in (".csv", ".tsv", ".txt"):
        rows, w = read_csv_rows(data, limits)
        if not rows:
            raise IngestError("The file has no data.")
        t, body, w2 = build_table(rows, stem or "data", taken, limits)
        built.append((t, body))
        warnings += w + w2
    elif ext in (".xlsx",):
        sheets, w = read_xlsx_sheets(data, limits)
        warnings += w
        for title, rows in sheets:
            label = f"{stem}_{title}" if len(sheets) > 1 else (stem or title)
            t, body, w2 = build_table(rows, label, taken, limits)
            built.append((t, body))
            warnings += w2
    elif ext == ".xls":
        raise IngestError("Old .xls files are not supported. Save the file as .xlsx or .csv and upload that.")
    else:
        raise IngestError("Only .csv, .tsv and .xlsx files are supported.")

    write_tables(db_path, built)
    return IngestResult([t for t, _ in built], warnings)


_ = time  # (datetime.time objects from Excel are stringified in infer_column)
