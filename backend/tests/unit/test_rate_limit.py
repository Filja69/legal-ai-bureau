"""In-process rate limiter — Phase 9 audit §15. No DB needed: exercises the
limiter directly rather than through a live endpoint.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.security.rate_limit import rate_limit_by_client_ip, reset_rate_limits


def _fake_request(host: str = "1.2.3.4"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


@pytest.mark.asyncio
async def test_allows_requests_under_the_limit():
    reset_rate_limits()
    dep = rate_limit_by_client_ip("test_scope", limit_per_minute=3)
    for _ in range(3):
        await dep(_fake_request())  # must not raise


@pytest.mark.asyncio
async def test_blocks_requests_over_the_limit():
    reset_rate_limits()
    dep = rate_limit_by_client_ip("test_scope", limit_per_minute=2)
    await dep(_fake_request())
    await dep(_fake_request())
    with pytest.raises(HTTPException) as exc_info:
        await dep(_fake_request())
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_limits_are_independent_per_client_ip():
    reset_rate_limits()
    dep = rate_limit_by_client_ip("test_scope", limit_per_minute=1)
    await dep(_fake_request("1.1.1.1"))
    await dep(_fake_request("2.2.2.2"))  # different IP — must not raise


@pytest.mark.asyncio
async def test_limits_are_independent_per_scope():
    reset_rate_limits()
    dep_a = rate_limit_by_client_ip("scope_a", limit_per_minute=1)
    dep_b = rate_limit_by_client_ip("scope_b", limit_per_minute=1)
    await dep_a(_fake_request("9.9.9.9"))
    await dep_b(_fake_request("9.9.9.9"))  # different scope, same IP — must not raise
