"""In-process rate limiting — Phase 9 audit §15: `POST /auth/token` (brute
force) and the LLM-cost endpoints (`POST /research`, `POST
/contracts/{id}/analyze`) had zero abuse protection.

Deliberately in-memory, not Redis-backed: Redis is a declared dependency
(`app/config/settings.py`) but has zero actual usage anywhere in this
codebase today (Phase 9 audit §15/§27 — "do not introduce infrastructure
without a concrete need"). A single-process in-memory limiter is the
correct-sized fix for the current single-instance deployment; swapping to a
Redis-backed limiter is the natural follow-up the moment this app actually
runs as more than one process, not before.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.security.deps import get_workspace_id

# key -> deque of monotonic timestamps within the current window
_hits: dict[str, deque[float]] = defaultdict(deque)
_WINDOW_SECONDS = 60.0


def _check(key: str, limit_per_minute: int) -> None:
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > _WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded — try again shortly")
    hits.append(now)


def rate_limit_by_client_ip(scope: str, limit_per_minute: int):
    """Dependency factory keyed on the caller's IP — for unauthenticated or
    pre-authentication endpoints (`POST /auth/token`) where there's no
    workspace/user identity yet to key on.
    """

    async def _dep(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        _check(f"{scope}:ip:{client_host}", limit_per_minute)

    return _dep


def rate_limit_by_workspace(scope: str, limit_per_minute: int):
    """Dependency factory keyed on the already-authorized workspace — for
    endpoints that call a paid LLM/embedding API per request, so cost abuse
    is bounded per-tenant rather than per-process-wide.
    """

    async def _dep(workspace_id: uuid.UUID = Depends(get_workspace_id)) -> uuid.UUID:
        _check(f"{scope}:workspace:{workspace_id}", limit_per_minute)
        return workspace_id

    return _dep


def reset_rate_limits() -> None:
    """Test-only — clears all in-memory rate-limit state between tests."""
    _hits.clear()
