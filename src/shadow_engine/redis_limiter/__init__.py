"""Redis-backed rate limiter for production deployments.

Requires: pip install redis
If Redis is unavailable, falls back to in-memory rate limiting.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict

try:
    import redis as _redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisRateLimiter:
    """Production rate limiter backed by Redis (shared across all workers).

    Falls back to in-memory rate limiting if Redis is unavailable.

    Usage:
        limiter = RedisRateLimiter(
            redis_url="redis://localhost:6379",
            max_requests=100,
            window_seconds=60,
        )

        if limiter.is_allowed("192.168.1.1"):
            # process request
            pass
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_requests: int = 100,
        window_seconds: int = 60,
        namespace: str = "shadow_engine:ratelimit",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.namespace = namespace

        if REDIS_AVAILABLE:
            try:
                self._redis = _redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                self._use_redis = True
            except Exception:
                self._redis = None
                self._use_redis = False
        else:
            self._redis = None
            self._use_redis = False

        # In-memory fallback
        if not self._use_redis:
            self._fallback: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if the client is allowed to make a request.

        Args:
            client_id: Client identifier (IP address, API key, etc.)

        Returns:
            True if the request is allowed, False if rate limited
        """
        if self._use_redis and self._redis is not None:
            return self._redis_check(client_id)
        return self._fallback_check(client_id)

    def _redis_check(self, client_id: str) -> bool:
        """Redis-backed sliding window rate limit check."""
        key = f"{self.namespace}:{client_id}"
        now = _time.time()
        window_start = now - self.window_seconds

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)  # Remove expired entries
            pipe.zcard(key)  # Count current entries
            _, count = pipe.execute()

            if isinstance(count, int) and count < self.max_requests:
                self._redis.zadd(key, {str(now): now})
                self._redis.expire(key, self.window_seconds + 10)
                return True
            return False
        except Exception:
            return True  # Fail open if Redis is down

    def _fallback_check(self, client_id: str) -> bool:
        """In-memory fallback rate limit check."""
        now = _time.time()
        self._fallback[client_id] = [
            t for t in self._fallback[client_id]
            if now - t < self.window_seconds
        ]
        if len(self._fallback[client_id]) >= self.max_requests:
            return False
        self._fallback[client_id].append(now)
        return True