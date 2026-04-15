"""
Simple in-memory rate limiting helpers for FastAPI endpoints.

Notes:
- Per-process memory store (sufficient for lightweight abuse protection).
- Keyed by client IP and endpoint bucket.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


class _InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            queue = self._events.setdefault(key, deque())
            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit:
                retry_after = max(1, int(window_seconds - (now - queue[0])))
                return False, retry_after

            queue.append(now)
            return True, 0


_limiter = _InMemoryRateLimiter()


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return (request.client.host if request.client else "unknown").strip() or "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    key = f"{bucket}:{get_client_identifier(request)}"
    allowed, retry_after = _limiter.allow(key=key, limit=limit, window_seconds=window_seconds)
    if allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many requests. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )

