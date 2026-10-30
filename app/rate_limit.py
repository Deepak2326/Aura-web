"""Simple in-memory sliding-window rate limiter (per client IP).

For a single-process deployment this is sufficient and has zero external
dependencies. For multi-instance deployments swap this for a Redis-backed
limiter — the public interface (`enforce_rate_limit`) stays the same.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, limiter_attr: str) -> None:
    limiter: SlidingWindowRateLimiter = getattr(request.app.state, limiter_attr)
    if not limiter.allow(client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": "Too many requests. Please try again in a few minutes."},
        )
