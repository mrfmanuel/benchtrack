"""In-memory sliding-window rate limiter (spec §9.14).

Single-process only: each replica keeps its own counters (v1 runs one replica).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0  # whole seconds, ≥ 1 when not allowed


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateLimitResult:
        """Record a request for `key` if under the limit. Rejected requests are not counted."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - now))
                return RateLimitResult(allowed=False, retry_after=retry_after)
            hits.append(now)
            self._prune(now)
            return RateLimitResult(allowed=True)

    def _prune(self, now: float) -> None:
        """Drop keys whose newest hit left the window, so memory stays bounded."""
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]
        for key in stale:
            del self._hits[key]
