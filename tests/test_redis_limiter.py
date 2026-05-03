"""Tests for Redis rate limiter — sliding window, fallback, and fail-open behavior."""

import time

from shadow_engine.redis_limiter import RedisRateLimiter


class TestRedisRateLimiter:
    """Test the rate limiter (in-memory fallback mode when Redis is unavailable)."""

    def test_allows_first_request(self):
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=5, window_seconds=60)
        assert limiter.is_allowed("client-1") is True

    def test_blocks_after_limit(self):
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is False

    def test_different_clients_have_separate_limits(self):
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed("client-A") is True
        # Client A is now blocked
        assert limiter.is_allowed("client-A") is False
        # Client B is still allowed
        assert limiter.is_allowed("client-B") is True

    def test_window_expiry(self):
        """Requests older than window_seconds should be pruned."""
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=3, window_seconds=1)
        for _ in range(3):
            assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is False

        # Wait for window to expire
        time.sleep(1.1)
        assert limiter.is_allowed("client-1") is True

    def test_namespace_isolation(self):
        """Different namespaces should not share limits."""
        limiter1 = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=2, window_seconds=60, namespace="ns1")
        limiter2 = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=2, window_seconds=60, namespace="ns2")

        for _ in range(2):
            assert limiter1.is_allowed("client-1") is True
        # ns1 is at limit for client-1
        assert limiter1.is_allowed("client-1") is False
        # ns2 is independent
        assert limiter2.is_allowed("client-1") is True

    def test_custom_max_requests(self):
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=10, window_seconds=60)
        for _ in range(10):
            assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is False

    def test_custom_window(self):
        limiter = RedisRateLimiter(redis_url="redis://nonexistent:9999", max_requests=2, window_seconds=1)
        for _ in range(2):
            assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is False
        time.sleep(1.1)
        assert limiter.is_allowed("client-1") is True