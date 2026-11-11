"""Process-local metrics for the command center (export to Prometheus/OTel later via the same API)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.counters: dict[str, int] = defaultdict(int)
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))
        self.recent_errors: deque[dict[str, Any]] = deque(maxlen=50)

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            self.latencies[name].append(ms)

    def error(self, where: str, message: str, request_id: str | None = None) -> None:
        with self._lock:
            self.counters["errors"] += 1
            self.recent_errors.appendleft({"at": time.time(), "where": where, "message": message[:300], "request_id": request_id})

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat = {}
            for k, v in self.latencies.items():
                s = sorted(v)
                if s:
                    lat[k] = {"count": len(s), "p50": round(s[len(s) // 2]), "p95": round(s[min(len(s) - 1, int(len(s) * 0.95))])}
            return {
                "uptime_seconds": int(time.time() - self.started_at),
                "counters": dict(self.counters),
                "latency_ms": lat,
                "recent_errors": list(self.recent_errors)[:20],
            }

    def reset(self) -> None:
        with self._lock:
            self.counters.clear()
            self.latencies.clear()
            self.recent_errors.clear()


metrics = Metrics()
