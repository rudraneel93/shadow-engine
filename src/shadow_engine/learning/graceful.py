"""Graceful degradation utilities for shadow-engine.

Provides a declarative way to handle errors across all engines without
boilerplate try/except. Failures are logged and return safe defaults.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def graceful(
    default_value: Any = None,
    log_message: str = "",
    reraise: tuple[type[Exception], ...] = (),
) -> Callable[[F], F]:
    """Decorator for methods that should fail gracefully.

    Args:
        default_value: Value to return on failure.
        log_message: Override log message (default: function name + error).
        reraise: Exception types to NOT catch (will propagate).

    Usage:
        @graceful(default_value="", log_message="Causal analysis failed")
        def build_causal_context(self, task): ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except reraise:
                raise
            except Exception as e:
                msg = log_message or f"{func.__qualname__} failed"
                logger.warning(f"{msg}: {e}", exc_info=True)
                return default_value
        return wrapper  # type: ignore[return-value]
    return decorator


def graceful_default(default_factory: Callable[[], Any]) -> Callable[[F], F]:
    """Decorator that calls a factory to produce the default value on failure.

    Args:
        default_factory: Callable that produces the default return value.

    Usage:
        @graceful_default(lambda: {"error": "unavailable"})
        def query(self, x): ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"{func.__qualname__} failed, returning default: {e}")
                return default_factory()
        return wrapper  # type: ignore[return-value]
    return decorator


class CircuitBreaker:
    """Simple circuit breaker for external calls (LLM APIs, Redis, etc.).

    After `failure_threshold` consecutive failures, opens the circuit.
    After `recovery_timeout` seconds, allows one probe request.
    If probe succeeds, closes circuit. If fails, stays open.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "closed"  # closed | open | half-open
        self._probe_allowed = False

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (requests should be blocked)."""
        import time

        if self._state == "closed":
            return False

        if self._state == "open":
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = "half-open"
                self._probe_allowed = True
                logger.info(f"[{self.name}] Circuit half-open — allowing probe")
                return False  # Allow probe
            return True  # Still open

        # Half-open: allow one probe then decide
        if self._state == "half-open":
            if self._probe_allowed:
                self._probe_allowed = False
                return False  # Allow probe
            return True  # Already probing — block

        return False

    def success(self) -> None:
        """Report a successful call."""
        self._failure_count = 0
        if self._state != "closed":
            logger.info(f"[{self.name}] Circuit closed — recovered")
        self._state = "closed"
        self._probe_allowed = False

    def failure(self) -> None:
        """Report a failed call."""
        import time

        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                f"[{self.name}] Circuit OPEN after {self._failure_count} failures"
            )

    def call(self, func: Callable[[], Any], fallback: Any = None) -> Any:
        """Execute func with circuit breaker protection.

        Args:
            func: Callable to execute (takes no args).
            fallback: Value to return if circuit is open or func fails.

        Returns:
            Result of func() or fallback.
        """
        if self.is_open:
            logger.warning(f"[{self.name}] Circuit open — returning fallback")
            return fallback

        try:
            result = func()
            self.success()
            return result
        except Exception as e:
            self.failure()
            logger.warning(f"[{self.name}] Call failed: {e}")
            return fallback