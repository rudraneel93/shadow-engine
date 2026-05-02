"""Async Laboratory Executor — Real parallel agent session spawning with asyncio.

Handles concurrent execution of multiple experiment variants, progress tracking,
timeout management, and result aggregation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..laboratory.experiment import (
    ExperimentBatch,
    ExperimentRunner,
    ExperimentStatus,
    ExperimentVariant,
)

logger = logging.getLogger(__name__)


# Type for session spawn callback:
#   (repository, prompt, approach, model) -> session_id
SessionSpawner = Callable[[str, str, str, str], Awaitable[str]]

# Type for waiting for a session result:
#   (session_id) -> {outcome, pr_url, files_changed, test_results, lines_added, lines_removed, token_count}
SessionWaiter = Callable[[str], Awaitable[dict[str, Any]]]


class AsyncExperimentExecutor:
    """Async executor for running experiment batches with real concurrency.

    Usage:
        async def my_spawn(repo, prompt, approach, model):
            # Call Open-Inspect API or any agent backend
            return await api.create_session(repo, prompt)

        async def my_wait(session_id):
            # Poll for session completion
            return await api.get_session_result(session_id)

        executor = AsyncExperimentExecutor(
            spawn_session=my_spawn,
            wait_for_result=my_wait,
            max_concurrency=5,
            timeout_seconds=600,
        )

        results = await executor.run_batch(batch)
    """

    def __init__(
        self,
        spawn_session: SessionSpawner | None = None,
        wait_for_result: SessionWaiter | None = None,
        max_concurrency: int = 5,
        timeout_seconds: float = 600.0,
    ):
        self._spawn = spawn_session
        self._wait = wait_for_result
        self.max_concurrency = max_concurrency
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run_batch(
        self,
        batch: ExperimentBatch,
        poll_interval: float = 2.0,
        on_progress: Callable[[ExperimentVariant], Awaitable[None]] | None = None,
    ) -> ExperimentBatch:
        """Run all variants in a batch concurrently.

        Args:
            batch: The experiment batch to execute
            poll_interval: Seconds between status checks per session
            on_progress: Optional callback invoked when a variant transitions status

        Returns:
            The updated batch with all variant results populated
        """
        batch.status = ExperimentStatus.RUNNING

        if self._spawn is None:
            # Simulation mode — no real spawning
            logger.info("No session spawner configured — running in simulation mode")
            return batch

        # Spawn all variants concurrently
        spawn_tasks = []
        for variant in batch.variants:
            task = asyncio.create_task(self._run_variant(variant, batch.repository))
            spawn_tasks.append(task)

        # Wait for all variants to complete (or fail)
        results = await asyncio.gather(*spawn_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                batch.variants[i].status = ExperimentStatus.FAILED
                batch.variants[i].error = str(result)
                logger.error(f"Variant {batch.variants[i].name} failed: {result}")

        batch.completed_at = datetime.now(timezone.utc)

        # Score variants and pick winner
        runner = ExperimentRunner()
        batch = runner.score_variants(batch)
        batch.status = ExperimentStatus.COMPLETED

        return batch

    async def _run_variant(self, variant: ExperimentVariant, repository: str) -> None:
        """Run a single experiment variant."""
        async with self._semaphore:
            variant.status = ExperimentStatus.RUNNING
            start_time = datetime.now(timezone.utc)

            try:
                # Spawn the session
                assert self._spawn is not None
                session_id = await self._spawn(
                    repository, variant.prompt, variant.approach, variant.model
                )
                variant.session_id = session_id

                # Wait for completion
                if self._wait is not None:
                    result = await asyncio.wait_for(
                        self._wait(session_id),
                        timeout=self.timeout_seconds,
                    )
                    await self._apply_result(variant, result)
                else:
                    variant.status = ExperimentStatus.COMPLETED
                    variant.completed_at = datetime.now(timezone.utc)

            except asyncio.TimeoutError:
                variant.status = ExperimentStatus.FAILED
                variant.error = f"Timed out after {self.timeout_seconds}s"
                logger.warning(f"Variant {variant.name} timed out")
            except Exception as e:
                variant.status = ExperimentStatus.FAILED
                variant.error = str(e)
                logger.error(f"Variant {variant.name} error: {e}")
            finally:
                variant.duration_seconds = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

    async def _apply_result(
        self, variant: ExperimentVariant, result: dict[str, Any]
    ) -> None:
        """Apply a completed session's result to the variant."""
        variant.status = ExperimentStatus.COMPLETED
        variant.completed_at = datetime.now(timezone.utc)
        variant.pr_url = result.get("pr_url")
        variant.files_changed = result.get("files_changed", [])
        variant.test_results = result.get("test_results", {})
        variant.lines_added = result.get("lines_added", 0)
        variant.lines_removed = result.get("lines_removed", 0)
        variant.token_count = result.get("token_count", 0)
        variant.error = result.get("error")


async def run_experiment_with_retry(
    executor: AsyncExperimentExecutor,
    batch: ExperimentBatch,
    max_retries: int = 2,
) -> ExperimentBatch:
    """Run an experiment batch with retry logic for failed variants.

    Failed variants are retried up to max_retries times before giving up.
    """
    for attempt in range(max_retries + 1):
        pending = [
            v for v in batch.variants
            if v.status in (ExperimentStatus.PENDING, ExperimentStatus.FAILED)
        ]

        if not pending:
            break

        if attempt > 0:
            logger.info(f"Retry attempt {attempt}/{max_retries} for {len(pending)} variants")
            # Reset failed variants to pending
            for v in pending:
                v.status = ExperimentStatus.PENDING
                v.error = None
                v.session_id = None

        batch = await executor.run_batch(batch)

    return batch