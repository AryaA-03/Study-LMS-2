"""In-memory sliding-window rate limiter for hosted multi-user deployments."""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class SlidingWindowRateLimiter:
    """Thread-safe per-key sliding-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._buckets[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                return False, retry_after
            q.append(now)
            return True, 0
