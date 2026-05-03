"""Tests for async laboratory executor — concurrent experiment execution."""

import asyncio
from pathlib import Path

import pytest

from shadow_engine.laboratory.experiment import (
    ExperimentRunner,
    ExperimentStatus,
    ExperimentVariant,
    ExperimentBatch,
    WinnerSelection,
)
from shadow_engine.async_lab.executor import AsyncExperimentExecutor, run_experiment_with_retry


class TestAsyncExperimentExecutor:
    """Test the async experiment executor with mock spawn/wait callbacks."""

    @pytest.fixture
    def batch(self):
        """Create a test batch with 3 variants."""
        runner = ExperimentRunner()
        return runner.create_batch(
            task_description="fix the login bug",
            repository="test-repo",
            num_variants=3,
        )

    @pytest.mark.asyncio
    async def test_executor_spawns_all_variants(self, batch):
        """Verify all variants are spawned and completed."""
        spawned_ids: list[str] = []

        async def mock_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            sid = f"sess-{len(spawned_ids)}"
            spawned_ids.append(sid)
            return sid

        async def mock_wait(session_id: str) -> dict:
            return {
                "pr_url": f"https://github.com/test/pull/{session_id}",
                "files_changed": ["src/auth.py", "tests/test_auth.py"],
                "test_results": {"total": 10, "passed": 10, "failed": 0},
                "lines_added": 5,
                "lines_removed": 1,
                "token_count": 5000,
            }

        executor = AsyncExperimentExecutor(
            spawn_session=mock_spawn,
            wait_for_result=mock_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await executor.run_batch(batch)
        assert len(spawned_ids) == 3
        assert result.status == ExperimentStatus.COMPLETED
        for variant in result.variants:
            assert variant.status == ExperimentStatus.COMPLETED
            assert variant.session_id is not None
            assert variant.pr_url is not None
            assert variant.test_results["passed"] == 10
            assert variant.files_changed == ["src/auth.py", "tests/test_auth.py"]

    @pytest.mark.asyncio
    async def test_executor_concurrency_limit(self, batch):
        """Verify max_concurrency is respected."""
        active = 0
        max_active = 0

        async def mock_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1
            return f"sess-{active}"

        async def mock_wait(session_id: str) -> dict:
            return {"test_results": {"passed": 5, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=mock_spawn,
            wait_for_result=mock_wait,
            max_concurrency=2,
            timeout_seconds=30,
        )

        await executor.run_batch(batch)
        assert max_active <= 2  # Should never exceed concurrency limit

    @pytest.mark.asyncio
    async def test_executor_timeout(self, batch):
        """Verify timeout handling — variant that hangs gets marked as failed."""
        async def mock_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            return f"sess-{approach}"

        async def mock_wait(session_id: str) -> dict:
            await asyncio.sleep(5)  # Simulate very slow work
            return {"test_results": {"passed": 5, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=mock_spawn,
            wait_for_result=mock_wait,
            max_concurrency=5,
            timeout_seconds=0.1,  # Very short timeout
        )

        result = await executor.run_batch(batch)
        for variant in result.variants:
            assert variant.status == ExperimentStatus.FAILED
            assert "Timed out" in (variant.error or "")

    @pytest.mark.asyncio
    async def test_executor_scores_winner(self, batch):
        """Verify that the executor correctly scores variants and picks a winner."""
        results = [
            {"test_results": {"total": 10, "passed": 10, "failed": 0}, "lines_added": 5, "lines_removed": 1, "token_count": 5000, "files_changed": ["a.py"]},
            {"test_results": {"total": 10, "passed": 3, "failed": 7}, "lines_added": 100, "lines_removed": 80, "token_count": 30000, "files_changed": [f"f{i}.py" for i in range(12)]},
            {"test_results": {"total": 10, "passed": 10, "failed": 0}, "lines_added": 10, "lines_removed": 2, "token_count": 8000, "files_changed": ["a.py", "b.py"]},
        ]

        async def mock_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            return f"sess-{approach}"

        async def mock_wait(session_id: str) -> dict:
            return results.pop(0)

        executor = AsyncExperimentExecutor(
            spawn_session=mock_spawn,
            wait_for_result=mock_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await executor.run_batch(batch)
        assert result.winner_variant_id is not None
        winner = result.winning_variant
        assert winner is not None
        assert winner.score > 0

    @pytest.mark.asyncio
    async def test_executor_no_spawn_callback(self, batch):
        """Executor with no spawn callback should not modify batch."""
        executor = AsyncExperimentExecutor(spawn_session=None)
        result = await executor.run_batch(batch)
        assert result.status == ExperimentStatus.RUNNING  # Unchanged
        for variant in result.variants:
            assert variant.status == ExperimentStatus.PENDING

    @pytest.mark.asyncio
    async def test_run_experiment_with_retry(self, batch):
        """Test retry logic for failed variants."""
        call_count = 0

        async def mock_spawn(repo: str, prompt: str, approach: str, model: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"sess-{call_count}"

        async def mock_wait(session_id: str) -> dict:
            return {"test_results": {"passed": 10, "failed": 0}}

        executor = AsyncExperimentExecutor(
            spawn_session=mock_spawn,
            wait_for_result=mock_wait,
            max_concurrency=5,
            timeout_seconds=30,
        )

        result = await run_experiment_with_retry(executor, batch, max_retries=2)
        assert result.status == ExperimentStatus.COMPLETED
        for variant in result.variants:
            assert variant.status == ExperimentStatus.COMPLETED