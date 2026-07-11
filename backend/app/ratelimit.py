"""Minimal per-IP sliding-window rate limiter for abuse-prone endpoints.

In-memory and per-process — the right weight for a single-API demo deployment.
At real scale this moves to the gateway (nginx `limit_req`) or Redis; the
interface (a FastAPI dependency) stays the same.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_s: float):
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        # Behind a proxy (Render/Railway) the client is in X-Forwarded-For.
        fwd = request.headers.get("x-forwarded-for")
        ip = (fwd.split(",")[0].strip() if fwd else None) or (
            request.client.host if request.client else "unknown"
        )
        now = time.monotonic()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.max_requests:
                retry = int(self.window_s - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit: {self.max_requests} uploads per "
                    f"{int(self.window_s)}s. Retry in ~{retry}s.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)


# 10 uploads/minute per IP: generous for humans, blocks accidental loops/scripts.
upload_rate_limit = RateLimiter(max_requests=10, window_s=60.0)
