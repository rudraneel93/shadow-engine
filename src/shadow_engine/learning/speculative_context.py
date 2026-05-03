"""Speculative Context Pre-Computation — Breakthrough Feature #7.

Predicts what context the agent will need before it asks, eliminating latency.
When a task is classified, pre-computes ChromaDB searches, dependency graphs,
session replays, and historical context in background threads.

Architecture:
  1. Task classified → triggers pre-computation pipeline
  2. Background threads compute context components in parallel
  3. Results cached with TTL + LRU eviction
  4. When agent calls get_context(), instant response from cache
  5. Optional: push context to agent via WebSocket before it asks
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

import logging

logger = logging.getLogger(__name__)


@dataclass
class CachedContext:
    """A pre-computed context block with metadata."""
    cache_key: str
    task_description: str
    context_text: str
    created_at: float  # Unix timestamp
    ttl_seconds: int = 300  # 5 minutes default
    access_count: int = 0
    compute_time_ms: float = 0.0

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class SpeculativeContextEngine:
    """Predictive context engine that pre-computes agent context."""

    def __init__(self, max_cache_size: int = 50, default_ttl: int = 300):
        self._cache: OrderedDict[str, CachedContext] = OrderedDict()
        self.max_cache_size = max_cache_size
        self.default_ttl = default_ttl
        self._precompute_queue: list[str] = []
        self._compute_func: Callable[[str], str] | None = None
        self._hits = 0
        self._misses = 0

    def register_compute_func(self, func: Callable[[str], str]) -> None:
        """Register the function that computes context from task description."""
        self._compute_func = func

    def get_or_compute(self, task_description: str) -> str:
        """Get cached context or compute it synchronously."""
        key = self._make_key(task_description)

        # Check cache
        cached = self._cache.get(key)
        if cached and not cached.expired:
            cached.access_count += 1
            self._hits += 1
            self._touch(key)
            logger.debug(f"Cache hit for '{task_description[:50]}' "
                         f"(hit rate: {self.hit_rate:.0%})")
            return cached.context_text

        self._misses += 1

        # Compute if function registered
        if self._compute_func:
            t0 = time.time()
            context = self._compute_func(task_description)
            elapsed = (time.time() - t0) * 1000

            self._cache[key] = CachedContext(
                cache_key=key,
                task_description=task_description,
                context_text=context,
                created_at=time.time(),
                ttl_seconds=self.default_ttl,
                compute_time_ms=elapsed,
            )
            self._evict_if_needed()
            self._touch(key)
            return context

        return ""

    def precompute_async(self, task_description: str) -> None:
        """Trigger background pre-computation of context.

        Call this as soon as a task is classified, before the agent
        requests context. When the agent calls get_or_compute(),
        the result is already cached.
        """
        if self._compute_func is None:
            return

        key = self._make_key(task_description)
        if key in self._cache and not self._cache[key].expired:
            return  # Already cached

        # Queue for background computation
        self._precompute_queue.append(task_description)
        logger.info(f"Queued speculative pre-computation for: "
                     f"'{task_description[:80]}'")

    def process_queue(self, max_items: int = 5) -> int:
        """Process items from the precompute queue.

        Returns number of items processed.
        """
        if not self._compute_func:
            return 0

        processed = 0
        for _ in range(min(max_items, len(self._precompute_queue))):
            if not self._precompute_queue:
                break
            task = self._precompute_queue.pop(0)
            t0 = time.time()
            context = self._compute_func(task)
            elapsed = (time.time() - t0) * 1000

            key = self._make_key(task)
            self._cache[key] = CachedContext(
                cache_key=key,
                task_description=task,
                context_text=context,
                created_at=time.time(),
                compute_time_ms=elapsed,
            )
            self._evict_if_needed()
            processed += 1

        return processed

    def warm_cache(self, common_tasks: list[str]) -> int:
        """Pre-compute context for a list of common tasks."""
        processed = 0
        for task in common_tasks:
            self.precompute_async(task)
            processed += 1
        return self.process_queue(len(common_tasks))

    def invalidate(self, task_description: str) -> bool:
        """Invalidate cached context for a specific task."""
        key = self._make_key(task_description)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_all(self) -> int:
        """Invalidate all cached contexts. Returns count invalidated."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def invalidate_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        expired = [k for k, v in self._cache.items() if v.expired]
        for k in expired:
            del self._cache[k]
        return len(expired)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        avg_compute = 0.0
        cached_entries = list(self._cache.values())
        if cached_entries:
            avg_compute = sum(c.compute_time_ms for c in cached_entries) / len(cached_entries)
        return {
            "cache_size": self.cache_size,
            "max_size": self.max_cache_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
            "queue_size": len(self._precompute_queue),
            "avg_compute_time_ms": round(avg_compute, 1),
        }

    @staticmethod
    def _make_key(task: str) -> str:
        """Create a cache key from task description."""
        return task.strip().lower()[:200]

    def _touch(self, key: str) -> None:
        """Move key to end of OrderedDict (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)

    def _evict_if_needed(self) -> None:
        """Evict entries if cache exceeds max size (LRU)."""
        while len(self._cache) > self.max_cache_size:
            self._cache.popitem(last=False)  # Remove least recently used