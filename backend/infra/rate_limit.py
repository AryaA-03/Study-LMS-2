"""In-memory sliding-window rate limiter for hosted multi-user deployments."""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class SlidingWindowRateLimiter:
    """Thread-safe per-key sliding-window rate limiter with bounded memory eviction."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60, max_keys: int = 10000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def _prune_stale_locked(self, cutoff: float) -> None:
        empty_keys = []
        for k, q in self._buckets.items():
            while q and q[0] <= cutoff:
                q.popleft()
            if not q:
                empty_keys.append(k)
        for k in empty_keys:
            del self._buckets[k]
        # Hard cap safeguard against IP-flood DoS
        if len(self._buckets) > self.max_keys:
            overflow = len(self._buckets) - self.max_keys
            for k in list(self._buckets.keys())[:overflow]:
                del self._buckets[k]

    def allow(self, key: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            self._calls += 1
            if self._calls % 500 == 0 or len(self._buckets) > self.max_keys:
                self._prune_stale_locked(cutoff)
            q = self._buckets[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                return False, retry_after
            q.append(now)
            if len(self._buckets) > self.max_keys:
                self._prune_stale_locked(cutoff)
            return True, 0
