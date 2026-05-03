"""Pattern Similarity Merging — Deep Feature #3.

Detects when two fix patterns describe the same thing and merges them
into a single higher-confidence pattern. Prevents pattern fragmentation
where 5 entries all say "targeted fix to 1-2 files" but have different IDs.

Uses keyword overlap scoring: Jaccard similarity between tokenized descriptions.
Patterns with ≥0.7 similarity are candidates for merging.
Merged pattern confidence = weighted average of source confidences.
"""

from __future__ import annotations

import re
from typing import Any


class PatternMerger:
    """Merges semantically similar fix patterns to prevent fragmentation."""

    def __init__(self, store: Any):
        self.store = store
        self._merge_threshold = 0.7

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize a description into a set of lowercase words."""
        return set(re.findall(r'\b[a-z]{3,}\b', text.lower()))

    def _jaccard_similarity(self, set_a: set[str], set_b: set[str]) -> float:
        """Compute Jaccard similarity between two sets."""
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def merge_similar_patterns(self, problem_type: str) -> int:
        """Find and merge similar patterns for a given problem type.

        Returns the number of patterns merged.
        """
        patterns = self.store.get_fix_patterns(
            problem_type=problem_type, min_confidence=0.3, limit=50)

        if len(patterns) < 2:
            return 0

        merged_count = 0
        merged_ids: set[str] = set()

        for i, p1 in enumerate(patterns):
            p1_id = p1.get("id", "")
            if p1_id in merged_ids:
                continue

            for j, p2 in enumerate(patterns):
                if i >= j:
                    continue
                p2_id = p2.get("id", "")
                if p2_id in merged_ids:
                    continue

                tokens1 = self._tokenize(p1["description"])
                tokens2 = self._tokenize(p2["description"])
                similarity = self._jaccard_similarity(tokens1, tokens2)

                if similarity >= self._merge_threshold:
                    # Merge: take the higher-confidence description, combine examples
                    if p1["confidence"] >= p2["confidence"]:
                        keeper, discarding = p1, p2
                    else:
                        keeper, discarding = p2, p1

                    new_confidence = (
                        keeper["confidence"] * keeper.get("evidence_count", 1) +
                        discarding["confidence"] * discarding.get("evidence_count", 1)
                    ) / (
                        keeper.get("evidence_count", 1) + discarding.get("evidence_count", 1)
                    )

                    combined_examples = list(set(
                        keeper.get("examples", []) + discarding.get("examples", [])
                    ))[:5]

                    # Re-store merged pattern with higher confidence
                    self.store.learn_fix_pattern(
                        pattern_type=keeper["pattern_type"],
                        problem_type=problem_type,
                        description=keeper["description"],
                        approach=keeper.get("approach", ""),
                        examples=combined_examples,
                        session_id=keeper.get("session_id", "merged"),
                        confidence=min(1.0, new_confidence + 0.05),  # Small merge bonus
                    )

                    merged_ids.add(discarding.get("id", ""))
                    merged_count += 1

        return merged_count

    def get_merged_context(self, problem_type: str, task_description: str,
                           keywords: list[str] | None = None) -> str:
        """Get deduplicated, merged fix pattern context for agent prompts."""
        # Run merge before retrieving
        merged = self.merge_similar_patterns(problem_type)

        patterns = self.store.get_fix_patterns(
            problem_type=problem_type, min_confidence=0.4, limit=5)

        if not patterns:
            return ""

        # Boost by keyword matches
        if keywords:
            for p in patterns:
                desc = p["description"].lower()
                hits = sum(1 for kw in keywords if kw.lower() in desc)
                p["confidence"] = min(1.0, p["confidence"] + hits * 0.05)

        patterns.sort(key=lambda p: p["confidence"], reverse=True)

        lines = ["### Proven Fix Patterns", ""]
        seen: set[str] = set()

        for p in patterns[:4]:
            desc = p["description"]
            if desc in seen:
                continue
            seen.add(desc)
            conf = p["confidence"]
            label = "high" if conf >= 0.7 else "medium" if conf >= 0.5 else "low"
            lines.append(f"- **[{p['pattern_type']}]** {desc} (confidence: {conf:.0%}, {label})")
            if p.get("examples"):
                lines.append(f"  Examples: {', '.join(p['examples'][:3])}")
            if p.get("approach"):
                lines.append(f"  Approach: {p['approach']}")

        if merged > 0:
            lines.append(f"\n  *({merged} duplicate patterns merged — confidence boosted)*")

        lines.append("")
        return "\n".join(lines)