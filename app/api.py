"""FastAPI service: POST /api/ask -> SQL + rows, with guardrails, rate limiting and a bounded LLM queue."""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import sqlglot
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from guardrails.executor import execute_safe
from guardrails.validator import validate_sql

from .config import Settings
from .fewshot_pool import POOL
from .intent import MESSAGE as READ_ONLY_MESSAGE
from .intent import write_intent
from .llm import OllamaClient
from .pipeline import Text2SQL
from .ratelimit import RateLimiter
from .sqlnorm import constant_text_only, fingerprint
from .upload_api import UPLOAD_PATH, BodyLimit, build_store, register_upload_routes

log = logging.getLogger("text2sql")
STATIC = Path(__file__).resolve().parent / "static"
Approach = Literal["zero_shot", "fewshot", "self_correct", "docs", "shots_only"]

FALLBACK_EXAMPLES = [
    "How many tracks are in each genre? Return genre name and track count.",
    "Which 5 customers spent the most? Return first name, last name, and total spent.",
    "Which artists have at least 10 albums? Return artist name and album count.",
    "What is the total invoice revenue for each year? Return the year and total.",
    "List the first and last names of employees who report to Nancy Edwards.",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    approach: Approach | None = None


def _norm(q: str) -> str:
    return " ".join(q.lower().split())


def _jsonable(v):
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    return str(v)


def _pretty(sql: str) -> str:
    try:
        return sqlglot.transpile(sql, read="sqlite", write="sqlite", pretty=True)[0]
    except Exception:
        return sql


def _load_demo(path: Path | str) -> list[dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []


def make_response(*, question: str, approach: str, res, sql: str, tables, attempts: int, source: str, model: str, row_limit: int,
                  llm_ms: float = 0.0, total_ms: float = 0.0, warnings=None) -> dict:
    """The JSON shape of /api/ask; shared with the static-site exporter so both render identically."""
    return {
        "ok": res.ok, "question": question, "sql": _pretty(res.sql or sql) if (res.sql or sql) else "", "columns": res.columns,
        "rows": [[_jsonable(v) for v in r] for r in res.rows], "row_count": len(res.rows), "truncated": res.truncated,
        "row_limit": row_limit, "error": res.error, "code": res.code, "tables": list(tables), "approach": approach,
        "attempts": attempts, "source": source, "model": model, "llm_ms": round(llm_ms), "exec_ms": round(res.latency_ms),
        "total_ms": round(total_ms), "warnings": list(warnings or []),
    }


def policy_response(question: str, approach: str, model: str, row_limit: int, total_ms: float = 0.0) -> dict:
    return {"ok": False, "question": question, "sql": "", "columns": [], "rows": [], "row_count": 0, "truncated": False,
            "row_limit": row_limit, "error": READ_ONLY_MESSAGE, "code": "read_only", "tables": [], "approach": approach,
            "attempts": 0, "source": "policy", "model": model, "llm_ms": 0, "exec_ms": 0, "total_ms": round(total_ms), "warnings": []}


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    st = settings or Settings.from_env()
    llm = llm or OllamaClient(st.model, st.ollama_host, timeout=st.llm_timeout_s)
    t2s = Text2SQL(llm, row_limit=st.row_limit, timeout_s=st.query_timeout_s, abort_on_unsafe=st.abort_on_unsafe)
    limiter = RateLimiter(st.rate_per_minute, st.rate_per_day)
    slots = threading.BoundedSemaphore(st.max_concurrent)
    demo = _load_demo(st.demo_answers)
    demo_by_q = {_norm(d["question"]): d for d in demo}
    pool_by_sql = {fingerprint(sql): q for q, sql in POOL}      # to notice when the model copies a stored example

    store = build_store(st) if st.uploads_enabled else None

    @asynccontextmanager
    async def lifespan(_app):
        if store is not None:
            store.start_sweeper()
        try:
            yield
        finally:
            if store is not None:
                store.stop_sweeper()

    app = FastAPI(title="Text-to-SQL Assistant", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    if store is not None:                       # added before the header middleware so a 413 still gets the security headers
        app.add_middleware(BodyLimit, path=UPLOAD_PATH, max_bytes=st.upload_max_bytes + 64 * 1024)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/api/docs"):
            resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'"
        return resp

    def client_id(request: Request) -> str:
        if st.trust_proxy:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @app.get("/api/health")
    def health():
        ping = getattr(llm, "ping", None)
        return {"status": "ok", "model": st.model, "llm_ready": bool(ping()) if ping else True,
                "examples_precomputed": len(demo), "uploads": store is not None}

    @app.get("/api/schema")
    def schema():
        return [{"table": t.name, "rows": t.row_count,
                 "columns": [{"name": c.name, "type": c.type, "pk": c.pk} for c in t.columns],
                 "foreign_keys": [f"{f.column} -> {f.ref_table}.{f.ref_column}" for f in t.fks]} for t in t2s.tables]

    @app.get("/api/examples")
    def examples():
        return [d["question"] for d in demo] or FALLBACK_EXAMPLES

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request):
        question = " ".join(body.question.split())
        if len(question) > st.max_question_chars:
            raise HTTPException(422, f"Question is too long (limit {st.max_question_chars} characters).")
        ok, retry = limiter.check(client_id(request))
        if not ok:
            raise HTTPException(429, f"Too many requests. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})

        approach = body.approach or st.default_approach
        t0 = time.perf_counter()
        verb = write_intent(question)
        if verb:                                                   # clear refusal; the model is never called
            log.info("ask refused read_only verb=%s", verb)
            return JSONResponse(policy_response(question, approach, st.model, st.row_limit, (time.perf_counter() - t0) * 1000))
        warnings: list[str] = []
        pre = demo_by_q.get(_norm(question))
        if pre:                                                    # saved, verified answer: SQL still runs through the guardrails
            res = execute_safe(t2s.db_path, pre["sql"], t2s.allowed, st.query_timeout_s, st.row_limit)
            sql, attempts, llm_ms, source = pre["sql"], 1, 0.0, "saved"
        else:
            if not slots.acquire(timeout=st.queue_wait_s):
                raise HTTPException(503, "The model is busy with other requests. Please try again in a moment.",
                                    headers={"Retry-After": "10"})
            try:
                out = t2s.ask(question, approach)
            except RuntimeError as e:
                log.warning("llm unreachable: %s", e)
                msg = "The language model is not reachable right now."
                if demo:
                    msg += " The example questions still work."
                raise HTTPException(503, msg) from None
            finally:
                slots.release()
            res, sql, attempts, llm_ms, source = out.result, out.sql, len(out.attempts), out.llm_latency_ms, "model"
            copied_from = pool_by_sql.get(fingerprint(sql)) if sql else None
            if copied_from and _norm(copied_from) != _norm(question):
                warnings.append("copied_example")
            if res.ok and sql and constant_text_only(sql):
                warnings.append("no_data_source")

        tables = sorted(validate_sql(sql, t2s.allowed).tables) if sql else []
        total_ms = (time.perf_counter() - t0) * 1000
        log.info("ask approach=%s source=%s ok=%s code=%s total_ms=%.0f", approach, source, res.ok, res.code, total_ms)
        return JSONResponse(make_response(question=question, approach=approach, res=res, sql=sql, tables=tables, attempts=attempts,
                                          source=source, model=st.model, row_limit=st.row_limit, llm_ms=llm_ms, total_ms=total_ms,
                                          warnings=warnings))

    if store is not None:
        register_upload_routes(app, st, store, llm, slots, limiter, client_id, make_response, policy_response)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
