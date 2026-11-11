"""In-process sliding-window rate limiter.

Good for a single API instance. For horizontally scaled deployments swap for a Redis-backed
implementation with the same `hit()` signature (see docs/SECURITY.md).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> tuple[bool, float]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False, max(0.0, q[0] + window_seconds - now)
            q.append(now)
            if len(self._hits) > 50_000:  # bound memory under key-spray
                self._evict(now - window_seconds)
            return True, 0.0

    def _evict(self, cutoff: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or q[-1] < cutoff]:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
