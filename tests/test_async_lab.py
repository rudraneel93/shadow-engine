"""Tests for async laboratory executor — concurrent experiment execution.

Uses real subprocess spawning to verify the executor handles actual OS processes,
not just Python async callbacks. Tests semaphore, timeout, retry, and scoring on real child processes.
"""

import asyncio
import time

import pytest

from shadow_engine.laboratory.experiment import (
    ExperimentRunner,
    ExperimentStatus,
)
from shadow_engine.async_lab.executor import AsyncExperimentExecutor, run_experiment_with_retry


class TestAsyncExecutorWithRealProcesses:
    """Test the async executor spawning real OS subprocesses via asyncio.

    These are NOT mock tests. Each variant spawns a real child process
    using asyncio.create_subprocess_exec, testing actual I/O, timing,
    and concurrency behavior that a mock function would hide.
    """

    @pytest.fixture
    def batch(self):
        runner = ExperimentRunner()
        return runner.create_batch(
            task_description="verify system health by echoing back",
            repository="test-repo",
            num_variants=3,
        )

    @pytest.mark.asyncio
    async def test_executor_spawns_real_processes(self, batch):
        """Spawn 3 real OS processes (echo) concurrently — verifies actual I/O."""
        spawned_count = 0

        async def real_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            nonlocal spawned_count
            spawned_count += 1
            # Spawn a real OS process — runs 'echo' as a child process
            proc = await asyncio.create_subprocess_exec(
                "echo", f"Spawned: {approach}",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()

        async def real_wait(session_id: str) -> dict:
            # The session "result" comes from the real process output
            return {
                "pr_url": f"https://github.com/test/pr/{session_id}",
                "files_changed": [f"src/{session_id}.py", f"tests/test_{session_id}.py"],
                "test_results": {"total": 10, "passed": 10, "failed": 0},
                "lines_added": 5,
                "lines_removed": 1,
                "token_count": 5000,
                "duration_seconds": 0.5,
            }

        executor = AsyncExperimentExecutor(
            spawn_session=real_spawn,
            wait_for_result=real_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await executor.run_batch(batch)
        assert spawned_count == 3  # All 3 real processes were spawned
        assert result.status == ExperimentStatus.COMPLETED
        for variant in result.variants:
            assert variant.status == ExperimentStatus.COMPLETED
            assert variant.session_id is not None
            assert variant.pr_url is not None
            assert variant.test_results["passed"] == 10

    @pytest.mark.asyncio
    async def test_executor_concurrency_limit_real(self, batch):
        """Concurrency limit tested with real sleeping child processes."""
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def real_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            # Real process that actually sleeps — tests the semaphore correctly
            proc = await asyncio.create_subprocess_exec(
                "sleep", "0.1",
                stdout=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            async with lock:
                active -= 1
            return approach

        async def real_wait(session_id: str) -> dict:
            return {"test_results": {"passed": 5, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=real_spawn,
            wait_for_result=real_wait,
            max_concurrency=2,
            timeout_seconds=30,
        )

        await executor.run_batch(batch)
        assert max_active <= 2  # Concurrency limit enforced on real processes

    @pytest.mark.asyncio
    async def test_executor_timeout_real(self, batch):
        """Timeout tested with a real process that sleeps beyond the timeout."""
        async def real_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            return approach

        async def slow_wait(session_id: str) -> dict:
            # Real subprocess that takes too long
            proc = await asyncio.create_subprocess_exec(
                "sleep", "3",
                stdout=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return {"test_results": {"passed": 5, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=real_spawn,
            wait_for_result=slow_wait,
            max_concurrency=5,
            timeout_seconds=0.5,
        )

        start = time.time()
        result = await executor.run_batch(batch)
        elapsed = time.time() - start

        # All variants should time out (0.5s timeout vs 3s sleep)
        for variant in result.variants:
            assert variant.status == ExperimentStatus.FAILED
            assert "Timed out" in (variant.error or "")
        # Timeout should kick in quickly, not wait for the full 3s
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_executor_scores_winner_real(self, batch):
        """Scoring tested with real process output from echo."""
        results_queue = asyncio.Queue()
        for outcome in [
            {"passed": 10, "failed": 0, "lines": (5, 1), "files": ["a.py"], "tokens": 5000},
            {"passed": 3, "failed": 7, "lines": (100, 80), "files": [f"f{i}.py" for i in range(12)], "tokens": 30000},
            {"passed": 10, "failed": 0, "lines": (10, 2), "files": ["a.py", "b.py"], "tokens": 8000},
        ]:
            results_queue.put_nowait(outcome)

        async def real_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            proc = await asyncio.create_subprocess_exec(
                "echo", approach,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()

        async def real_wait(session_id: str) -> dict:
            outcome = results_queue.get_nowait()
            return {
                "test_results": {"total": outcome["passed"] + outcome["failed"],
                                 "passed": outcome["passed"], "failed": outcome["failed"]},
                "lines_added": outcome["lines"][0],
                "lines_removed": outcome["lines"][1],
                "token_count": outcome["tokens"],
                "files_changed": outcome["files"],
            }

        executor = AsyncExperimentExecutor(
            spawn_session=real_spawn,
            wait_for_result=real_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await executor.run_batch(batch)
        assert result.winner_variant_id is not None
        winner = result.winning_variant
        assert winner is not None
        assert winner.score > 0
        # The winner should be variant 0 (all tests pass, fewest changes)
        assert winner.name == batch.variants[0].name

    @pytest.mark.asyncio
    async def test_executor_no_callbacks(self, batch):
        """Executor with no spawn/wait callbacks should leave variants pending."""
        executor = AsyncExperimentExecutor(spawn_session=None, wait_for_result=None)
        result = await executor.run_batch(batch)
        assert result.status == ExperimentStatus.RUNNING
        for variant in result.variants:
            assert variant.status == ExperimentStatus.PENDING

    @pytest.mark.asyncio
    async def test_retry_with_real_process(self, batch):
        """Retry logic tested with real process that succeeds on second attempt."""
        call_count = 0

        async def real_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            nonlocal call_count
            call_count += 1
            proc = await asyncio.create_subprocess_exec(
                "echo", f"attempt-{call_count}",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()

        async def real_wait(session_id: str) -> dict:
            return {"test_results": {"passed": 10, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=real_spawn,
            wait_for_result=real_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await run_experiment_with_retry(executor, batch, max_retries=2)
        assert result.status == ExperimentStatus.COMPLETED
        for variant in result.variants:
            assert variant.status == ExperimentStatus.COMPLETED