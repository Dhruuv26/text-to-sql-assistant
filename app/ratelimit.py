"""In-memory sliding-window rate limiter keyed by client id (per-minute and per-day caps)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int, clock=time.time, max_clients: int = 10_000):
        self.per_minute, self.per_day, self.clock, self.max_clients = per_minute, per_day, clock, max_clients
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str) -> tuple[bool, int]:
        """-> (allowed, retry_after_seconds). Records the hit only when allowed."""
        now = self.clock()
        with self._lock:
            if len(self._hits) > self.max_clients:                      # bound memory under scanning/abuse
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 86400]:
                    del self._hits[k]
            q = self._hits[client]
            while q and now - q[0] > 86400:
                q.popleft()
            if len(q) >= self.per_day:
                return False, max(1, int(86400 - (now - q[0])))
            recent = [t for t in q if now - t <= 60]
            if len(recent) >= self.per_minute:
                return False, max(1, int(60 - (now - recent[0])))
            q.append(now)
            return True, 0
