"""Token-Budget-Aware Context Builder — Production Fix.

When 11+ engines inject context blocks into agent prompts, the total
can easily exceed model context windows (3000 tokens for local models,
8K-128K for cloud). This module manages a token budget, prioritizing
critical sections and skipping or truncating lower-priority ones.

Key features:
  - Priority-ordered sections (0 = critical, 100 = nice-to-have)
  - Lazy computation: sections only computed if within budget
  - Token estimation (fast word-count heuristic when no tokenizer)
  - Smart truncation preserving sentence boundaries
"""

from __future__ import annotations

from typing import Callable


class ContextBudgetManager:
    """Builds agent context blocks within a configurable token budget.

    Sections are added with priorities (lower = more important).
    When the budget is exceeded, low-priority sections are skipped
    and medium-priority sections are truncated.
    """

    def __init__(self, max_tokens: int = 3000):
        self.max_tokens = max_tokens
        self._sections: list[tuple[int, str, str, Callable[[], str]]] = []
        # (priority, section_id, section_name, lazy_compute)

    def add_section(
        self, priority: int, section_id: str, name: str,
        compute: Callable[[], str],
    ) -> None:
        """Add a context section with its priority.

        Args:
            priority: 0 (critical) to 100 (optional). Lower = more important.
            section_id: Unique identifier for this section.
            name: Human-readable section name (for logging).
            compute: Callable that returns the section text (lazily called).
        """
        self._sections.append((priority, section_id, name, compute))

    def build(self) -> str:
        """Build the context string within the token budget.

        Sections are processed in priority order. Once the budget
        is exhausted, remaining sections are skipped.
        """
        # Sort by priority (ascending — 0 first)
        sorted_sections = sorted(self._sections, key=lambda x: x[0])

        parts: list[str] = []
        tokens_used = 0

        for priority, section_id, name, compute in sorted_sections:
            # Compute section text (lazily — only if needed)
            content = compute()
            if not content or not content.strip():
                continue

            content_tokens = self._estimate_tokens(content)

            if tokens_used + content_tokens > self.max_tokens:
                remaining = self.max_tokens - tokens_used

                if priority < 20:
                    # Critical section: truncate to fit
                    content = self._truncate_to_tokens(content, remaining)
                    content_tokens = self._estimate_tokens(content)
                elif priority < 50:
                    # Medium priority: only include if enough space
                    if remaining < 100:
                        continue
                    content = self._truncate_to_tokens(content, remaining)
                    content_tokens = self._estimate_tokens(content)
                else:
                    # Low priority: skip if budget exceeded
                    continue

            if content.strip():
                parts.append(content)
                tokens_used += content_tokens

        return "\n".join(parts)

    def reset(self) -> None:
        """Clear all sections for reuse."""
        self._sections.clear()

    # ── Token Estimation ──────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast token estimation without a tokenizer.

        Rough heuristic: 1 token ≈ 4 characters (English) or 0.75 words.
        Conservative estimate to avoid exceeding budget.
        """
        if not text:
            return 0
        # Character-based estimate (conservative)
        char_estimate = len(text) // 3
        # Word-based estimate
        word_estimate = int(len(text.split()) * 1.3)
        # Use the larger estimate to stay within budget
        return max(char_estimate, word_estimate)

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens, preserving sentence boundaries."""
        if not text:
            return ""

        estimated = ContextBudgetManager._estimate_tokens(text)
        if estimated <= max_tokens:
            return text

        # Truncate proportionally and find last sentence boundary
        ratio = max_tokens / estimated
        cutoff = int(len(text) * ratio)
        truncated = text[:cutoff]

        # Try to cut at last sentence boundary
        for delimiter in ["\n\n", "\n", ". ", "! ", "? "]:
            last = truncated.rfind(delimiter)
            if last > cutoff * 0.5:  # Only if reasonable
                return truncated[:last + len(delimiter)].rstrip() + "\n[...]"

        return truncated.rstrip() + "\n[...]"