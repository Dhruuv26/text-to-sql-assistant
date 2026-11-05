"""HTTP layer for uploaded files: POST /api/upload, GET/DELETE /api/session, POST /api/session/ask.

Design notes
- The upload body is the raw request body (no multipart parser). A pure-ASGI middleware enforces the byte cap on the declared
  Content-Length and on the bytes actually received, so an oversized or chunked body cannot fill memory or disk.
- The browser holds only an opaque session id in an HttpOnly, SameSite=Lax cookie. SameSite=Lax keeps cross-site POSTs from
  carrying it, which is the CSRF defence for these state-changing routes.
- Single server process assumed: sessions, limiter and the LLM semaphore live in memory.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from guardrails.validator import validate_sql

from .config import Settings
from .ingest import IngestError, IngestLimits, TableMeta
from .intent import write_intent
from .ratelimit import RateLimiter
from .sessions import Session, SessionLimitError, SessionStore
from .sqlnorm import constant_text_only
from .upload_pipeline import UploadQA

log = logging.getLogger("text2sql.upload")
COOKIE = "t2s_session"
UPLOAD_PATH = "/api/upload"
BODY_SLACK = 64 * 1024            # bodies slightly over the file limit still reach ingest for its friendly message
UploadApproach = Literal["plain", "profiled", "profiled_retry"]
DEFAULT_UPLOAD_APPROACH = "profiled_retry"
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class _TooLarge(Exception):
    pass


class BodyLimit:
    """Pure-ASGI request size cap for one path. Checks Content-Length first, then counts the streamed bytes."""

    def __init__(self, app, path: str, max_bytes: int):
        self.app, self.path, self.max_bytes = app, path, max_bytes

    async def _reject(self, send, status: int, message: str):
        body = json.dumps({"detail": message}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != self.path or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        too_big = f"The upload is larger than {self.max_bytes / 1e6:.0f} MB."
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                n = int(declared)
            except ValueError:
                return await self._reject(send, 400, "Invalid Content-Length header.")
            if n < 0:
                return await self._reject(send, 400, "Invalid Content-Length header.")
            if n > self.max_bytes:
                return await self._reject(send, 413, too_big)
        received, started = 0, False

        async def counting_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge
            return msg

        async def tracking_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(send, 413, too_big)


def build_store(st: Settings) -> SessionStore:
    limits = IngestLimits(max_bytes=st.upload_max_bytes)
    return SessionStore(st.session_dir, ttl_s=st.session_ttl_s, max_age_s=st.session_max_age_s,
                        max_sessions=st.max_sessions, limits=limits)


def clean_filename(raw: str) -> str:
    """Keep only a short base name. Used for the table label, never as a filesystem path."""
    name = _CTRL.sub("", str(raw)).replace("\\", "/").split("/")[-1].strip()
    return name[:100] or "upload"


def session_payload(store: SessionStore, s: Session, warnings: list[str] | None = None) -> dict:
    def col(c):
        return {"name": c.name, "label": c.label, "type": c.sqltype, "kind": c.kind, "nulls": c.nulls, "distinct": c.distinct,
                "note": c.note, "samples": [str(v)[:40] if not isinstance(v, (int, float)) else v for v in c.samples[:3]]}

    def tbl(t: TableMeta):
        return {"name": t.name, "label": t.label, "rows": t.rows, "columns": [col(c) for c in t.columns]}

    return {"active": True, "tables": [tbl(t) for t in s.tables], "warnings": list(warnings or []),
            "seconds_left": store.seconds_left(s), "uploads": s.uploads, "max_uploads": store.max_uploads,
            "max_tables": store.max_tables, "limits": {"max_bytes": store.limits.max_bytes, "max_rows": store.limits.max_rows,
                                                       "max_cols": store.limits.max_cols}}


class UploadAskRequest(BaseModel):
    question: str = Field(min_length=3)
    approach: UploadApproach | None = None


def register_upload_routes(app: FastAPI, st: Settings, store: SessionStore, llm, slots, limiter: RateLimiter, client_id,
                           make_response, policy_response) -> None:
    upload_limiter = RateLimiter(st.upload_rate_per_minute, st.upload_rate_per_day)

    def is_https(request: Request) -> bool:
        if request.url.scheme == "https":
            return True
        return st.trust_proxy and request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"

    def set_cookie(resp: JSONResponse, request: Request, sid: str) -> None:
        resp.set_cookie(COOKIE, sid, max_age=int(st.session_max_age_s), path="/", httponly=True, samesite="lax",
                        secure=is_https(request))

    @app.post(UPLOAD_PATH)
    async def upload(request: Request, filename: str = Query(min_length=1, max_length=300)):
        ok, retry = upload_limiter.check(client_id(request))
        if not ok:
            raise HTTPException(429, f"Too many uploads. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
        data = await request.body()                      # bounded by BodyLimit
        s = store.get(request.cookies.get(COOKIE))
        created = s is None
        if created:
            try:
                s = store.create()
            except SessionLimitError as e:
                raise HTTPException(e.status, str(e), headers={"Retry-After": "60"}) from None
        try:
            res = await run_in_threadpool(store.add_upload, s, clean_filename(filename), data)
        except IngestError as e:
            if created:
                store.delete(s.id)
            raise HTTPException(422, str(e)) from None
        except SessionLimitError as e:
            if created:
                store.delete(s.id)
            raise HTTPException(e.status, str(e)) from None
        except Exception:
            if created:
                store.delete(s.id)
            log.exception("upload failed")
            raise HTTPException(500, "The file could not be processed.") from None
        log.info("upload ok tables=%d rows=%d", len(res.tables), sum(t.rows for t in res.tables))
        resp = JSONResponse(session_payload(store, s, res.warnings))
        set_cookie(resp, request, s.id)
        return resp

    @app.get("/api/session")
    def session_status(request: Request):
        s = store.get(request.cookies.get(COOKIE), touch=False)     # polling must not keep the data alive
        if s is None or not s.tables:
            return {"active": False, "limits": {"max_bytes": store.limits.max_bytes, "max_rows": store.limits.max_rows,
                                                "max_cols": store.limits.max_cols}, "ttl_s": int(store.ttl_s)}
        return session_payload(store, s)

    @app.delete("/api/session")
    def session_delete(request: Request):
        deleted = store.delete(request.cookies.get(COOKIE))
        resp = JSONResponse({"deleted": deleted})
        resp.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=is_https(request))
        return resp

    @app.post("/api/session/ask")
    def session_ask(body: UploadAskRequest, request: Request):
        question = " ".join(body.question.split())
        if len(question) > st.max_question_chars:
            raise HTTPException(422, f"Question is too long (limit {st.max_question_chars} characters).")
        ok, retry = limiter.check(client_id(request))
        if not ok:
            raise HTTPException(429, f"Too many requests. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
        s = store.get(request.cookies.get(COOKIE))
        if s is None or not s.tables:
            raise HTTPException(404, "No uploaded data in this session. Upload a CSV or Excel file first.")
        approach = body.approach or DEFAULT_UPLOAD_APPROACH
        t0 = time.perf_counter()
        if write_intent(question):
            return JSONResponse(policy_response(question, approach, st.model, st.row_limit, (time.perf_counter() - t0) * 1000))
        if not slots.acquire(timeout=st.queue_wait_s):
            raise HTTPException(503, "The model is busy with other requests. Please try again in a moment.", headers={"Retry-After": "10"})
        try:
            qa = UploadQA(llm, s.path, list(s.tables), row_limit=st.row_limit, timeout_s=st.query_timeout_s)
            out = qa.ask(question, approach)
        except sqlite3.Error:
            raise HTTPException(410, "Your uploaded data has expired. Upload the file again.") from None
        except RuntimeError:
            log.warning("llm unreachable")
            raise HTTPException(503, "The language model is not reachable right now.") from None
        finally:
            slots.release()
        res, sql = out.result, out.sql
        warnings = ["no_data_source"] if (res.ok and sql and constant_text_only(sql)) else []
        tables = sorted(validate_sql(sql, qa.allowed).tables) if sql else []
        total_ms = (time.perf_counter() - t0) * 1000
        log.info("session_ask approach=%s ok=%s code=%s total_ms=%.0f", approach, res.ok, res.code, total_ms)
        return JSONResponse(make_response(question=question, approach=approach, res=res, sql=sql, tables=tables,
                                          attempts=len(out.attempts), source="upload", model=st.model, row_limit=st.row_limit,
                                          llm_ms=out.llm_latency_ms, total_ms=total_ms, warnings=warnings))

