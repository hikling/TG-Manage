"""InMemoryRateLimiter 桶清理与基础行为测试"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _limiter():
    from backend.core.rate_limit import InMemoryRateLimiter

    return InMemoryRateLimiter()


def _hit(limiter, scope="auth.login", key="1.2.3.4", max_attempts=5, window=300, block=900):
    return limiter.hit(
        scope=scope,
        key=key,
        max_attempts=max_attempts,
        window_seconds=window,
        block_seconds=block,
        detail="too many",
    )


class TestRateLimiterBasics:
    def test_allow_then_block(self):
        limiter = _limiter()
        for _ in range(5):
            _hit(limiter)  # 前 5 次放行
        with pytest.raises(HTTPException) as exc:
            _hit(limiter)  # 第 6 次触发封锁
        assert exc.value.status_code == 429
        assert exc.value.headers["Retry-After"]

    def test_reset_clears_bucket(self):
        limiter = _limiter()
        for _ in range(6):
            try:
                _hit(limiter)
            except HTTPException:
                pass
        with pytest.raises(HTTPException):
            _hit(limiter)
        limiter.reset("auth.login", "1.2.3.4")
        _hit(limiter)  # 重置后不再封锁

    def test_reset_all_clears_all(self):
        limiter = _limiter()
        _hit(limiter, key="a")
        _hit(limiter, key="b")
        limiter.reset_all()
        assert limiter._attempts == {}
        assert limiter._blocked_until == {}


class TestRateLimiterSweep:
    def test_sweep_removes_stale_attempt_buckets(self):
        limiter = _limiter()
        # 模拟一个 1 小时前有过一次尝试、此后无请求的桶
        stale = time.monotonic() - 7200
        limiter._attempts[("auth.login", "ghost")] = __import__(
            "collections"
        ).deque([stale])
        limiter._hits_since_sweep = limiter._SWEEP_INTERVAL - 1  # 下一次 hit 触发清扫
        _hit(limiter)
        assert ("auth.login", "ghost") not in limiter._attempts

    def test_sweep_keeps_recent_buckets(self):
        limiter = _limiter()
        limiter._attempts[("auth.login", "live")] = __import__(
            "collections"
        ).deque([time.monotonic()])
        limiter._hits_since_sweep = limiter._SWEEP_INTERVAL - 1
        _hit(limiter)
        assert ("auth.login", "live") in limiter._attempts

    def test_sweep_removes_expired_blocks(self):
        limiter = _limiter()
        limiter._blocked_until[("auth.login", "old")] = time.monotonic() - 10
        limiter._blocked_until[("auth.login", "active")] = time.monotonic() + 100
        limiter._hits_since_sweep = limiter._SWEEP_INTERVAL - 1
        _hit(limiter)
        assert ("auth.login", "old") not in limiter._blocked_until
        assert ("auth.login", "active") in limiter._blocked_until

    def test_sweep_runs_only_every_interval(self):
        limiter = _limiter()
        limiter._attempts[("auth.login", "ghost")] = __import__(
            "collections"
        ).deque([time.monotonic() - 7200])
        # 未到间隔：不触发清扫，陈旧桶保留（每次用新 key 避免触发封锁）
        for i in range(limiter._SWEEP_INTERVAL - 1):
            _hit(limiter, key=f"other-{i}")
        assert ("auth.login", "ghost") in limiter._attempts
        # 到达间隔：清扫生效
        _hit(limiter, key="trigger")
        assert ("auth.login", "ghost") not in limiter._attempts


def test_forwarded_headers_cannot_change_rate_limit_identity():
    from backend.core.rate_limit import get_client_identifier

    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.1", "x-real-ip": "203.0.113.2"},
        client=SimpleNamespace(host="192.0.2.10"),
    )
    assert get_client_identifier(request) == "192.0.2.10"
    request.headers["x-forwarded-for"] = "198.51.100.99"
    assert get_client_identifier(request) == "192.0.2.10"


def test_rate_limit_bucket_count_stays_bounded():
    limiter = _limiter()
    limiter._MAX_BUCKETS = 3
    for name in ("a", "b", "c"):
        _hit(limiter, key=name)
    with pytest.raises(HTTPException) as exc:
        _hit(limiter, key="d")
    assert exc.value.status_code == 429
    assert len(limiter._attempts) == 3

    limiter.reset_all()
    for _ in range(6):
        try:
            _hit(limiter, key="blocked")
        except HTTPException:
            pass
    _hit(limiter, key="one")
    _hit(limiter, key="two")
    with pytest.raises(HTTPException):
        _hit(limiter, key="new")
    assert len(limiter._attempts) + len(limiter._blocked_until) == 3
