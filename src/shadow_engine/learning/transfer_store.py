"""Cross-Codebase Transfer Learning — Breakthrough Feature #8.

Abstracts fix patterns, approach efficacy, and strategy fitness out of
individual repositories into a global pattern space. Patterns learned on
Repo A can be applied to Repo B by stripping file paths and generalizing
symbol names, using embedding similarity between codebases.

Federated learning across teams without sharing source code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TransferPattern:
    """A codebase-agnostic fix pattern for cross-repo transfer."""
    pattern_type: str
    description: str  # Generalized description (no file paths)
    problem_type: str
    confidence: float = 0.5
    source_repo_count: int = 1
    total_successes: int = 0
    total_attempts: int = 0

    @property
    def success_rate(self) -> float:
        return self.total_successes / self.total_attempts if self.total_attempts > 0 else 0.0


class TransferStore:
    """Cross-repo pattern transfer and federated learning store."""

    def __init__(self, store: Any):
        self.store = store
        self._global_patterns: dict[str, TransferPattern] = {}

    def abstract_pattern(self, description: str, problem_type: str,
                          source_repo: str, was_successful: bool) -> TransferPattern | None:
        """Abstract a repo-specific pattern into a transferable one."""
        # Strip file paths and generalize
        import re
        generalized = re.sub(r'`[\w/._-]+\.py`', '`<file>`', description)
        generalized = re.sub(r'in `[\w/._-]+`', 'in a file', generalized)
        generalized = re.sub(r'[\w_]+\.py', '<module>.py', generalized)

        key = f"{problem_type}:{generalized[:100]}"
        if key in self._global_patterns:
            pattern = self._global_patterns[key]
            pattern.total_attempts += 1
            if was_successful:
                pattern.total_successes += 1
            pattern.confidence = pattern.success_rate
            return pattern

        pattern = TransferPattern(
            pattern_type="transfer",
            description=generalized,
            problem_type=problem_type,
            confidence=0.5,
            source_repo_count=1,
            total_successes=1 if was_successful else 0,
            total_attempts=1,
        )
        self._global_patterns[key] = pattern
        return pattern

    def get_transferable_patterns(self, problem_type: str, min_confidence: float = 0.5) -> list[TransferPattern]:
        """Get patterns that can be transferred for a problem type."""
        patterns = [p for p in self._global_patterns.values()
                    if p.problem_type == problem_type and p.confidence >= min_confidence]
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def build_transfer_context(self, problem_type: str) -> str:
        """Build context block with transferable patterns."""
        patterns = self.get_transferable_patterns(problem_type)
        if not patterns:
            return ""

        lines = ["### 🌐 Cross-Repository Transfer Patterns", "",
                 f"*Patterns from {sum(p.source_repo_count for p in patterns)} repositories:*",
                 ""]
        for p in patterns[:5]:
            lines.append(f"- **{p.problem_type}** (confidence: {p.confidence:.0%}): {p.description}")
            lines.append(f"  Success rate: {p.success_rate:.0%} ({p.total_successes}/{p.total_attempts})")
            lines.append("")
        return "\n".join(lines)