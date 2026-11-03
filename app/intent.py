"""Read-only policy check on the QUESTION text (a UX layer; the parser guardrails remain the actual security boundary).

Refuses requests that clearly ask to change data, so the user gets a clear message instead of an unrelated query.
Deliberately narrow: only imperative write verbs at the start of the request, or SQL write statements anywhere.
"""
from __future__ import annotations

import re

_LEAD = r"^\s*(?:(?:please|kindly)\s+)?(?:(?:can|could|would)\s+you\s+)?(?:(?:please)\s+)?"
_VERBS = r"(?:delete|drop|truncate|erase|wipe|destroy|remove|insert|update|alter|modify|overwrite|rename)\b"
_LEADING_WRITE = re.compile(_LEAD + r"(" + _VERBS + r")", re.I)
_SQL_WRITE = re.compile(
    r"\b(drop\s+(?:table|database|index|view)|truncate\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|alter\s+table|"
    r"create\s+(?:table|index|view)|attach\s+database|pragma\s+\w+)\b", re.I)

MESSAGE = ("This assistant only reads data. It cannot delete, change or create anything. "
           "Ask a question about what is in the database instead, for example: How many customers are there?")


def write_intent(question: str) -> str | None:
    """-> the offending verb/statement, or None when the question looks like an ordinary read request."""
    m = _SQL_WRITE.search(question)
    if m:
        return " ".join(m.group(1).lower().split())
    m = _LEADING_WRITE.match(question)
    return m.group(1).lower() if m else None
