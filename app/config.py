"""Runtime settings, read from environment variables (12-factor)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    model: str = "qwen2.5-coder:7b"
    ollama_host: str = "http://localhost:11434"
    default_approach: str = "self_correct"
    llm_timeout_s: float = 90.0
    row_limit: int = 200
    query_timeout_s: float = 5.0
    max_question_chars: int = 400
    rate_per_minute: int = 10
    rate_per_day: int = 300
    max_concurrent: int = 1          # simultaneous LLM calls; the rest wait up to queue_wait_s
    queue_wait_s: float = 25.0
    abort_on_unsafe: bool = True     # do not let the retry loop 'repair' a rejected write into an unrelated answer
    trust_proxy: bool = False        # read the client IP from X-Forwarded-For (set when behind a reverse proxy)
    demo_answers: Path = ROOT / "demo_answers.json"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            model=os.environ.get("MODEL", d.model),
            ollama_host=os.environ.get("OLLAMA_HOST", d.ollama_host),
            default_approach=os.environ.get("DEFAULT_APPROACH", d.default_approach),
            llm_timeout_s=float(os.environ.get("LLM_TIMEOUT_S", d.llm_timeout_s)),
            row_limit=_int("ROW_LIMIT", d.row_limit),
            query_timeout_s=float(os.environ.get("QUERY_TIMEOUT_S", d.query_timeout_s)),
            max_question_chars=_int("MAX_QUESTION_CHARS", d.max_question_chars),
            rate_per_minute=_int("RATE_PER_MINUTE", d.rate_per_minute),
            rate_per_day=_int("RATE_PER_DAY", d.rate_per_day),
            max_concurrent=_int("MAX_CONCURRENT", d.max_concurrent),
            queue_wait_s=float(os.environ.get("QUEUE_WAIT_S", d.queue_wait_s)),
            abort_on_unsafe=os.environ.get("ABORT_ON_UNSAFE", "1") == "1",
            trust_proxy=os.environ.get("TRUST_PROXY", "0") == "1",
            demo_answers=Path(os.environ.get("DEMO_ANSWERS", d.demo_answers)),
        )
