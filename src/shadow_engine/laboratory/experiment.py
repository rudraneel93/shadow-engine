"""Laboratory Engine — Run parallel agent experiments and compare results."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..knowledge_graph.models import AgentOutcome, ApproachEfficacy, SessionRecord


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WinnerSelection(str, Enum):
    FIRST_TO_PASS = "first_to_pass"
    BEST_PERFORMING = "best_performing"
    SMALLEST_CHANGE = "smallest_change"
    FASTEST_EXECUTION = "fastest_execution"


# Fix #9: Configurable scoring weights with sensible defaults
@dataclass
class ScoringConfig:
    """Configurable scoring weights for experiment comparison.

    All weights should sum to 1.0. The normalization functions use smooth
    logistic curves instead of linear cliffs to avoid arbitrary cutoffs.
    """
    test_pass_weight: float = 0.40
    change_size_weight: float = 0.20
    speed_weight: float = 0.15
    token_efficiency_weight: float = 0.10
    file_scope_weight: float = 0.15

    # Tuning parameters for normalization curves
    change_baseline: float = 50.0   # Lines: 50 = neutral, 100 = low
    speed_baseline: float = 60.0    # Seconds: 60 = neutral, 300 = low
    token_baseline: float = 10000.0  # Tokens: 10K = neutral, 50K = low
    file_baseline: float = 5.0       # Files: 5 = neutral, 15 = low

    def __post_init__(self) -> None:
        total = (
            self.test_pass_weight + self.change_size_weight +
            self.speed_weight + self.token_efficiency_weight +
            self.file_scope_weight
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


# Default scoring config
DEFAULT_SCORING = ScoringConfig()


@dataclass
class ExperimentVariant:
    variant_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    approach: str = ""
    model: str = "default"
    prompt: str = ""
    status: ExperimentStatus = ExperimentStatus.PENDING
    session_id: str | None = None
    pr_url: str | None = None
    test_results: dict[str, Any] = field(default_factory=dict)
    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    duration_seconds: float = 0.0
    token_count: int = 0
    error: str | None = None
    score: float = 0.0
    completed_at: datetime | None = None

    def to_session_record(self, repository: str) -> SessionRecord:
        outcome = AgentOutcome.FAILURE
        if self.status == ExperimentStatus.COMPLETED:
            pr_exists = self.pr_url is not None
            tests_pass = self.test_results.get("passed", 0) > 0
            if pr_exists and tests_pass:
                outcome = AgentOutcome.SUCCESS
        return SessionRecord(
            session_id=self.session_id or uuid.uuid4().hex[:12],
            repository=repository, prompt=self.prompt, approach=self.approach,
            model=self.model, outcome=outcome, pr_url=self.pr_url,
            files_changed=self.files_changed, test_results=self.test_results,
            duration_seconds=self.duration_seconds, token_count=self.token_count,
            completed_at=self.completed_at or datetime.now(timezone.utc),
        )


@dataclass
class ExperimentBatch:
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    repository: str = ""
    task_description: str = ""
    problem_type: str = "general"
    variants: list[ExperimentVariant] = field(default_factory=list)
    winner_selection: WinnerSelection = WinnerSelection.BEST_PERFORMING
    status: ExperimentStatus = ExperimentStatus.PENDING
    winner_variant_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    scoring_config: ScoringConfig = field(default_factory=ScoringConfig)

    @property
    def winning_variant(self) -> ExperimentVariant | None:
        if self.winner_variant_id is None:
            return None
        for v in self.variants:
            if v.variant_id == self.winner_variant_id:
                return v
        return None

    def to_summary(self) -> dict[str, Any]:
        completed = [v for v in self.variants if v.status == ExperimentStatus.COMPLETED]
        return {
            "batch_id": self.batch_id,
            "task": self.task_description[:200],
            "total_variants": len(self.variants),
            "completed": len(completed),
            "failed": sum(1 for v in self.variants if v.status == ExperimentStatus.FAILED),
            "pending": sum(1 for v in self.variants if v.status == ExperimentStatus.PENDING),
            "running": sum(1 for v in self.variants if v.status == ExperimentStatus.RUNNING),
            "winner": self.winner_variant_id,
            "variants": [
                {
                    "name": v.name, "approach": v.approach, "model": v.model,
                    "status": v.status.value, "score": v.score,
                    "tests_passed": v.test_results.get("passed", 0),
                    "tests_failed": v.test_results.get("failed", 0),
                    "lines_changed": v.lines_added + v.lines_removed,
                    "duration_s": v.duration_seconds, "tokens": v.token_count,
                    "pr_url": v.pr_url,
                }
                for v in self.variants
            ],
        }


class ExperimentRunner:
    """Orchestrates parallel agent experiments with configurable scoring."""

    STRATEGIES_BY_PROBLEM: dict[str, list[dict[str, str]]] = {
        "bug_fix": [
            {"name": "Targeted Fix", "approach": "Analyze the error precisely. Find the minimal code change needed. Write a focused fix with a regression test. Do not refactor unrelated code."},
            {"name": "Root Cause + Guard", "approach": "Find the root cause of the bug. Fix it, then add input validation or guard clauses to prevent similar bugs. Add both unit and integration tests."},
            {"name": "Defense in Depth", "approach": "Fix the bug, add comprehensive error handling at every layer involved, add logging for observability, and write tests at unit and integration levels."},
        ],
        "feature": [
            {"name": "Minimal Viable", "approach": "Implement the feature with the minimal code necessary. Prioritize simplicity and test coverage over extensibility."},
            {"name": "Extensible Design", "approach": "Implement the feature with a clean interface design. Structure code for future extension. Write thorough tests."},
            {"name": "Full Polish", "approach": "Implement the feature with complete error handling, edge case coverage, logging, and comprehensive tests. Follow existing patterns closely."},
        ],
        "refactor": [
            {"name": "Safe Extract", "approach": "Extract the core logic into smaller, well-named functions. Keep the external API unchanged. Verify with existing tests."},
            {"name": "Pattern Align", "approach": "Refactor to match the prevailing patterns in this codebase. Study similar modules and align structure. Preserve all behavior."},
            {"name": "Clean Sweep", "approach": "Comprehensively refactor: extract functions, improve naming, reduce duplication, add docstrings. Update tests to match new structure."},
        ],
        "general": [
            {"name": "Conservative", "approach": "Make minimal, targeted changes. Prioritize correctness and test coverage. Follow existing codebase conventions strictly."},
            {"name": "Balanced", "approach": "Balance between addressing the core problem and improving surrounding code. Make reasonable refactors to improve clarity while solving the task."},
            {"name": "Ambitious", "approach": "Solve the problem thoroughly and improve related code. Consider edge cases and add comprehensive tests. Document your reasoning."},
        ],
    }

    def __init__(
        self,
        spawn_session: Callable[[str, str, str, str], Awaitable[str]] | None = None,
        scoring_config: ScoringConfig | None = None,
    ):
        self._spawn_session = spawn_session
        self._batches: dict[str, ExperimentBatch] = {}
        self.scoring_config = scoring_config or DEFAULT_SCORING

    def create_batch(
        self, task_description: str, repository: str, num_variants: int = 3,
        models: list[str] | None = None, strategies: list[dict[str, str]] | None = None,
        winner_selection: WinnerSelection = WinnerSelection.BEST_PERFORMING,
        scoring_config: ScoringConfig | None = None,
    ) -> ExperimentBatch:
        problem_type = self._classify_problem(task_description)
        if strategies is None:
            default_strategies = self.STRATEGIES_BY_PROBLEM.get(problem_type, self.STRATEGIES_BY_PROBLEM["general"])
            strategies = default_strategies[:num_variants]

        variants: list[ExperimentVariant] = []
        for i in range(num_variants):
            if i < len(strategies):
                name, approach = strategies[i]["name"], strategies[i]["approach"]
            else:
                name, approach = f"Variant {i + 1}", "Solve the task using a standard approach."
            model = models[i % len(models)] if models else "default"
            variants.append(ExperimentVariant(name=name, approach=approach, model=model, prompt=self._build_prompt(task_description, approach)))

        batch = ExperimentBatch(
            repository=repository, task_description=task_description, problem_type=problem_type,
            variants=variants, winner_selection=winner_selection,
            scoring_config=scoring_config or self.scoring_config,
        )
        self._batches[batch.batch_id] = batch
        return batch

    # Fix #9: Configurable scoring with smooth normalization curves
    def score_variants(self, batch: ExperimentBatch) -> ExperimentBatch:
        cfg = batch.scoring_config
        scored: list[tuple[ExperimentVariant, float]] = []

        for variant in batch.variants:
            if variant.status != ExperimentStatus.COMPLETED:
                variant.score = 0.0
                continue

            # Test pass rate (0-100) — linear
            total_tests = variant.test_results.get("total", 0)
            passed_tests = variant.test_results.get("passed", 0)
            test_score = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0

            # Change size — smooth logistic: smaller = better
            total_changes = variant.lines_added + variant.lines_removed
            change_score = _sigmoid_score(total_changes, cfg.change_baseline, invert=True)

            # Speed — smooth logistic: faster = better
            speed_score = _sigmoid_score(variant.duration_seconds, cfg.speed_baseline, invert=True)

            # Token efficiency — smooth logistic: fewer = better
            token_score = _sigmoid_score(variant.token_count, cfg.token_baseline, invert=True)

            # File scope — smooth logistic: fewer = better
            num_files = len(variant.files_changed)
            scope_score = _sigmoid_score(num_files, cfg.file_baseline, invert=True) if num_files > 0 else 100.0

            final_score = (
                test_score * cfg.test_pass_weight +
                change_score * cfg.change_size_weight +
                speed_score * cfg.speed_weight +
                token_score * cfg.token_efficiency_weight +
                scope_score * cfg.file_scope_weight
            )
            variant.score = round(final_score, 2)
            scored.append((variant, final_score))

        if scored:
            if batch.winner_selection == WinnerSelection.BEST_PERFORMING:
                winner = max(scored, key=lambda x: x[1])
            elif batch.winner_selection == WinnerSelection.FASTEST_EXECUTION:
                winner = min(scored, key=lambda x: x[0].duration_seconds)
            elif batch.winner_selection == WinnerSelection.SMALLEST_CHANGE:
                winner = min(scored, key=lambda x: x[0].lines_added + x[0].lines_removed)
            else:
                winner = max(scored, key=lambda x: x[1])
            batch.winner_variant_id = winner[0].variant_id
        return batch

    def get_comparison_report(self, batch: ExperimentBatch) -> str:
        lines: list[str] = []
        lines.append("=" * 70)
        lines.append("  AGENT LABORATORY — EXPERIMENT COMPARISON REPORT")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Task: {batch.task_description[:150]}")
        lines.append(f"Problem Type: {batch.problem_type}")
        lines.append(f"Variants Run: {len(batch.variants)}")
        lines.append(f"Winner Selection: {batch.winner_selection.value}")
        lines.append("")

        sorted_variants = sorted(batch.variants, key=lambda v: v.score, reverse=True)
        for i, variant in enumerate(sorted_variants):
            is_winner = variant.variant_id == batch.winner_variant_id
            prefix = "🏆 WINNER" if is_winner else f"  #{i + 1}"
            lines.append(f"{prefix} | {variant.name} ({variant.model})")
            lines.append(f"     Approach: {variant.approach[:100]}")
            lines.append(f"     Score: {variant.score:.1f}/100")
            lines.append(f"     Tests: {variant.test_results.get('passed', 0)} passed, {variant.test_results.get('failed', 0)} failed")
            lines.append(f"     Changes: +{variant.lines_added}/-{variant.lines_removed} in {len(variant.files_changed)} files")
            lines.append(f"     Duration: {variant.duration_seconds:.1f}s | Tokens: {variant.token_count}")
            if variant.pr_url:
                lines.append(f"     PR: {variant.pr_url}")
            if variant.error:
                lines.append(f"     Error: {variant.error[:100]}")
            lines.append("")

        lines.append("-" * 70)
        lines.append("  KEY INSIGHTS")
        lines.append("-" * 70)

        pass_rate_by_approach = {}
        for v in sorted_variants:
            total = v.test_results.get("total", 1)
            passed = v.test_results.get("passed", 0)
            pass_rate_by_approach[v.name] = (passed / total * 100) if total > 0 else 0

        best = max(pass_rate_by_approach, key=lambda k: pass_rate_by_approach[k])
        lines.append(f"• Best test pass rate: {best} ({pass_rate_by_approach[best]:.0f}%)")
        lines.append(f"• Most efficient: {min(sorted_variants, key=lambda v: v.token_count).name}")
        lines.append(f"• Fewest changes: {min(sorted_variants, key=lambda v: v.lines_added + v.lines_removed).name}")
        if batch.winning_variant:
            lines.append(f"• Recommended approach: {batch.winning_variant.approach}")
        lines.append("=" * 70)
        return "\n".join(lines)

    @staticmethod
    def _classify_problem(task_description: str) -> str:
        task_lower = task_description.lower()
        if any(w in task_lower for w in ("bug", "fix", "error", "crash", "broken", "failing")):
            return "bug_fix"
        if any(w in task_lower for w in ("feature", "add", "implement", "create", "build", "new")):
            return "feature"
        if any(w in task_lower for w in ("refactor", "clean", "improve", "optimize", "simplify")):
            return "refactor"
        return "general"

    @staticmethod
    def _build_prompt(task: str, approach: str) -> str:
        return (
            f"## Task\n{task}\n\n## Approach\n{approach}\n\n"
            f"## Instructions\n"
            f"1. Understand the existing code thoroughly before making changes\n"
            f"2. Follow the approach strategy above\n"
            f"3. Write tests that verify your changes work correctly\n"
            f"4. Run all existing tests to ensure nothing is broken\n"
            f"5. Keep changes focused and well-documented\n"
        )


# Fix #9: Smooth logistic normalization instead of linear cliffs
def _sigmoid_score(value: float, baseline: float, invert: bool = False) -> float:
    """Smooth scoring function using a logistic curve.

    Maps value → [0, 100] where baseline gives ~50.
    No hard cliffs — graceful degradation.

    Args:
        value: The metric value (lines, seconds, tokens, files)
        baseline: The value that maps to ~50
        invert: If True, lower values score higher (for change size, speed, etc.)
    """
    import math
    # Logistic: 1 / (1 + e^(-k*(x-mid)))
    k = 4.0 / baseline  # Steepness — faster drop for smaller baselines
    mid = baseline * 0.75  # Shift left so baseline maps to ~50
    logistic = 1.0 / (1.0 + math.exp(-k * (value - mid)))
    score = 100.0 * (1.0 - logistic) if invert else 100.0 * logistic
    return max(0.0, min(100.0, score))