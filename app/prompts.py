"""Prompt builders per approach + SQL extraction from model output."""
from __future__ import annotations

import re

SYSTEM = ("You are an expert SQLite analyst. Reply with exactly one SQLite SELECT query and nothing else. "
          "Never modify data.")


def zero_shot_prompt(question: str, schema_text: str) -> str:
    return (f"Database schema (SQLite):\n{schema_text}\n"
            f"Question: {question}\n"
            "Write one SQLite SELECT query that answers the question.\nSQL:")


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.*?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """Pull SQL out of a model reply: prefer fenced block, else the text from the first SELECT/WITH."""
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\b(select|with)\b", text, re.I)
        if m:
            text = text[m.start():]
    return text.strip().strip("`").strip()


# ---------------------------------------------------------------- approach B / C prompts
DOC_NOTES = """Notes about the data (Chinook digital music store):
- Invoice.Total is the invoice amount; InvoiceLine.UnitPrice * InvoiceLine.Quantity is the line revenue.
- Track.Milliseconds is the track length; Track.UnitPrice is the price.
- Customer.SupportRepId references Employee.EmployeeId; Employee.ReportsTo references Employee.EmployeeId (the manager).
- Dates are text like 'YYYY-MM-DD HH:MM:SS'; use strftime('%Y', col) / strftime('%Y-%m', col) and julianday(). Invoice dates span 2021-2025.
- Track -> Album -> Artist is the chain from tracks to artists (Track.AlbumId, Album.ArtistId).
- Playlists link to tracks only through PlaylistTrack."""

RULES = """Rules:
- Return exactly the columns the question asks for, in the order asked, and no extra columns.
- When joining several one-to-many tables, use COUNT(DISTINCT ...) to avoid double counting.
- Use only tables and columns from the schema above. SQLite syntax only. One SELECT statement."""


def fewshot_prompt(question: str, schema_text: str, examples: list[tuple[str, str]]) -> str:
    """Docs + rules (+ examples when given). With examples=[] this is the 'docs' ablation."""
    head = f"Database schema (SQLite):\n{schema_text}\n{DOC_NOTES}\n\n{RULES}\n\n"
    if examples:
        shots = "\n\n".join(f"Question: {q}\nSQL: {s}" for q, s in examples)
        head += f"Examples:\n\n{shots}\n\n"
    return head + f"Question: {question}\nSQL:"


def shots_only_prompt(question: str, schema_text: str, examples: list[tuple[str, str]]) -> str:
    """Plain schema (no samples/notes/rules) + examples: isolates the effect of the examples."""
    shots = "\n\n".join(f"Question: {q}\nSQL: {s}" for q, s in examples)
    return (f"Database schema (SQLite):\n{schema_text}\nExamples:\n\n{shots}\n\n"
            f"Question: {question}\nSQL:")


def correction_prompt(base_prompt: str, previous_sql: str, problem: str) -> str:
    """base_prompt is the full fewshot prompt (ends with 'SQL:'); append the failed attempt and the feedback."""
    return (f"{base_prompt} {previous_sql}\n\n"
            f"That query had a problem: {problem}\n"
            "Write a corrected SQLite SELECT query that answers the question. Reply with the SQL only.\nSQL:")
