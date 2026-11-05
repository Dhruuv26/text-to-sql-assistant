"""Sanitise untrusted text (cell values, headers) before it is shown to the model.

This is a seatbelt, not the security boundary: the boundary is the SQL parser plus the read-only, per-session database,
so a successful injection can still only yield a SELECT over the user's own file. Here we remove the cheap attacks and
stop values from being read as instructions.
"""
from __future__ import annotations

import re

MAX_VALUE_CHARS = 40
OMITTED = "[text omitted: looks like an instruction]"

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_WS = re.compile(r"\s+")
_SUSPICIOUS = re.compile(
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)|disregard|forget\s+(all|everything|the)"
    r"|new\s+instructions?|(^|\W)system\s*:|(^|\W)assistant\s*:|(^|\W)user\s*:|you\s+are\s+now|act\s+as|pretend\s+to"
    r"|\[/?inst\]|<\|?\s*(im_start|im_end|system|endoftext)|</?\s*(schema|system|instructions?)\s*>"
    r"|```|\b(select|insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum)\b[^.]{0,80}\b(from|into|table|set|database|where|values)\b"
    r"|\b(readfile|writefile|load_extension|sqlite_master|sqlite_schema)\b|--|/\*|;\s*\w",
    re.I)


def clean_text(value, max_chars: int = MAX_VALUE_CHARS) -> str:
    """Control characters out, whitespace collapsed, truncated. No instruction detection."""
    s = _CONTROL.sub("", str(value))
    s = _WS.sub(" ", s).strip()
    return s if len(s) <= max_chars else s[: max_chars - 1].rstrip() + "…"


def is_suspicious(value) -> bool:
    return bool(_SUSPICIOUS.search(_CONTROL.sub("", str(value))))


def safe_text(value, max_chars: int = MAX_VALUE_CHARS) -> str:
    """Cleaned text, or the omission marker when it looks like an instruction (checked before truncation)."""
    if is_suspicious(value):
        return OMITTED
    return clean_text(value, max_chars)


def sql_literal(value, max_chars: int = MAX_VALUE_CHARS) -> str:
    """Render a value as a quoted SQL literal so the model sees it as data: 'text', 12, 3.5, NULL."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    t = safe_text(value, max_chars)
    return "'" + t.replace("'", "''") + "'"


def safe_label(raw, fallback: str = "column") -> str:
    """Original header text for display in a note: sanitised and short."""
    t = safe_text(raw, 30)
    return t if t and t != OMITTED else fallback
