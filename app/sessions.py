"""Per-session isolated databases for uploaded data.

Isolation model: every session owns ONE SQLite file under a private directory. The only handle a client ever holds is a random
128+ bit id (kept in an HttpOnly cookie). Ids are looked up in an in-memory table before they are ever turned into a path, so a
crafted id can never reach the filesystem. Sessions expire after an idle TTL and an absolute maximum age; expired files are deleted
by a background sweeper, lazily on access, and (as orphans from a previous process) at startup.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .ingest import DEFAULT_LIMITS, IngestLimits, IngestResult, TableMeta, ingest_file

_ID = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


class SessionLimitError(RuntimeError):
    """Too many sessions, tables or uploads. The message is safe to show to the user.
    status: 503 when the whole service is at capacity, 429 when this session hit its own limit."""

    def __init__(self, message: str, status: int = 429):
        super().__init__(message)
        self.status = status


@dataclass
class Session:
    id: str
    path: Path
    created: float
    last_used: float
    tables: list[TableMeta] = field(default_factory=list)
    uploads: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def table_names(self) -> set[str]:
        return {t.name for t in self.tables}


class SessionStore:
    def __init__(self, root: str | Path, ttl_s: float = 1800, max_age_s: float = 7200, max_sessions: int = 50,
                 max_tables: int = 4, max_uploads: int = 6, clock=time.time, limits: IngestLimits = DEFAULT_LIMITS):
        self.root = Path(root)
        self.ttl_s, self.max_age_s, self.max_sessions = ttl_s, max_age_s, max_sessions
        self.max_tables, self.max_uploads, self.limits, self.clock = max_tables, max_uploads, limits, clock
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.root.mkdir(parents=True, exist_ok=True)
        self.purge_orphans()

    # ---- lifecycle
    def purge_orphans(self) -> int:
        """Delete session database files left behind by a previous process (this process starts with no sessions).
        Only files named like a session id are touched, so a misconfigured directory (say, the one holding the sample
        database) is never wiped."""
        n = 0
        for f in self.root.glob("*.sqlite*"):
            stem = f.name.split(".sqlite", 1)[0]
            if not _ID.match(stem):
                continue
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n

    def _expired(self, s: Session, now: float) -> bool:
        return now - s.last_used > self.ttl_s or now - s.created > self.max_age_s

    def _remove(self, s: Session) -> None:
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                Path(str(s.path) + suffix).unlink()
            except OSError:
                pass

    def cleanup(self) -> int:
        """Remove expired sessions and their files. -> number removed."""
        now = self.clock()
        with self._lock:
            dead = [s for s in self._sessions.values() if self._expired(s, now)]
            for s in dead:
                del self._sessions[s.id]
        for s in dead:
            with s.lock:
                self._remove(s)
        return len(dead)

    def start_sweeper(self, interval_s: float = 60.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval_s):
                try:
                    self.cleanup()
                except Exception:  # the sweeper must never die
                    pass

        self._thread = threading.Thread(target=loop, name="session-sweeper", daemon=True)
        self._thread.start()

    def stop_sweeper(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    # ---- sessions
    def create(self) -> Session:
        self.cleanup()
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise SessionLimitError("The service is at capacity for uploaded files right now. Please try again in a few minutes.", status=503)
            sid = secrets.token_urlsafe(24)
            now = self.clock()
            s = Session(sid, self.root / f"{sid}.sqlite", now, now)
            self._sessions[sid] = s
            return s

    def get(self, sid: str | None, touch: bool = True) -> Session | None:
        """Look a session up by id. touch=False (status polling) does not extend the idle timer."""
        if not sid or not _ID.match(sid):
            return None
        now = self.clock()
        with self._lock:
            s = self._sessions.get(sid)
            if s is None:
                return None
            if self._expired(s, now):
                del self._sessions[sid]
            else:
                if touch:
                    s.last_used = now
                return s
        with s.lock:
            self._remove(s)
        return None

    def delete(self, sid: str | None) -> bool:
        if not sid or not _ID.match(sid):
            return False
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s is None:
            return False
        with s.lock:
            self._remove(s)
        return True

    def add_upload(self, s: Session, filename: str, data: bytes) -> IngestResult:
        """Parse the file into the session's database. Raises IngestError / SessionLimitError (both user-safe)."""
        with s.lock:
            if s.uploads >= self.max_uploads:
                raise SessionLimitError(f"At most {self.max_uploads} uploads per session. Remove your data and start again.")
            res = ingest_file(filename, data, s.path, existing_tables=s.table_names, limits=self.limits)
            if len(s.tables) + len(res.tables) > self.max_tables:
                self._drop_tables(s, [t.name for t in res.tables])
                raise SessionLimitError(f"At most {self.max_tables} tables per session. Remove your data and start again.")
            s.tables += res.tables
            s.uploads += 1
            return res

    @staticmethod
    def _drop_tables(s: Session, names: list[str]) -> None:
        import sqlite3
        con = sqlite3.connect(str(s.path))
        try:
            with con:
                for n in names:
                    con.execute(f'DROP TABLE IF EXISTS "{n}"')      # names come from normalize_name, never from the user directly
        finally:
            con.close()

    def seconds_left(self, s: Session) -> int:
        now = self.clock()
        return max(0, int(min(self.ttl_s - (now - s.last_used), self.max_age_s - (now - s.created))))

    def __len__(self) -> int:
        return len(self._sessions)
