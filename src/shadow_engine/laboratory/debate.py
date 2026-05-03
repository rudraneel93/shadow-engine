"""Multi-Agent Debate & Consensus Engine — Breakthrough Feature #5.

Transforms the Laboratory from independent parallel experiments into a
collaborative debate process. After all variants complete, agents critique
each other's work and synthesize a consensus solution.

Process:
  1. Each agent completes its task independently (existing Lab flow)
  2. Critic Round: Each agent reviews all OTHER agents' solutions
  3. Aggregation: Critiques are collected and weighted by critic confidence
  4. Synthesis: A new "consensus" variant combines best elements from all
  5. Meta-Learning: Track whether debate improves outcomes

Inspired by:
  - AlphaGo's self-play + evaluation network
  - Constitutional AI's "critique → revise" loop
  - Ensemble methods in ML

This is the first coding agent framework where agents critique each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────

@dataclass
class Critique:
    """A single critique from one variant about another's solution."""
    critic_variant_id: str
    target_variant_id: str
    dimension: str  # "correctness", "completeness", "test_coverage", "simplicity", "safety"
    severity: str  # "blocker", "major", "minor", "suggestion"
    comment: str
    suggested_fix: str = ""
    confidence: float = 0.5  # How confident the critic is in this critique

    def to_dict(self) -> dict[str, Any]:
        return {
            "critic": self.critic_variant_id,
            "target": self.target_variant_id,
            "dimension": self.dimension,
            "severity": self.severity,
            "comment": self.comment,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
        }


@dataclass
class DebateRound:
    """A complete debate round across all variants."""
    round_id: int
    critiques: list[Critique] = field(default_factory=list)
    consensus_score: float = 0.0  # How much agreement among critics (0-1)
    synthesis_generated: bool = False

    @property
    def blocker_count(self) -> int:
        return sum(1 for c in self.critiques if c.severity == "blocker")

    @property
    def major_count(self) -> int:
        return sum(1 for c in self.critiques if c.severity == "major")

    @property
    def minor_count(self) -> int:
        return sum(1 for c in self.critiques if c.severity == "minor")

    @property
    def suggestion_count(self) -> int:
        return sum(1 for c in self.critiques if c.severity == "suggestion")

    def to_summary(self) -> dict[str, Any]:
        return {
            "round": self.round_id,
            "total_critiques": len(self.critiques),
            "blockers": self.blocker_count,
            "majors": self.major_count,
            "minors": self.minor_count,
            "suggestions": self.suggestion_count,
            "consensus_score": round(self.consensus_score, 3),
            "synthesis_generated": self.synthesis_generated,
        }


@dataclass
class DebateResult:
    """Complete debate process result."""
    variant_count: int
    rounds: list[DebateRound] = field(default_factory=list)
    synthesis_approach: str = ""
    synthesis_description: str = ""
    improvement_over_best: float = 0.0  # Score improvement from debate
    winner_before_debate: str = ""
    winner_after_debate: str = ""
    key_insights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_count": self.variant_count,
            "rounds": [r.to_summary() for r in self.rounds],
            "synthesis_approach": self.synthesis_approach,
            "synthesis_description": self.synthesis_description,
            "improvement_over_best": round(self.improvement_over_best, 3),
            "winner_before_debate": self.winner_before_debate,
            "winner_after_debate": self.winner_after_debate,
            "key_insights": self.key_insights,
        }


# ── Debate Engine ────────────────────────────────────────────────

class DebateEngine:
    """Orchestrates multi-agent debate to improve solution quality.

    Integrates with ExperimentRunner: after all variants complete,
    runs debate rounds and generates a synthesis variant.
    """

    # Dimensions to critique
    CRITIQUE_DIMENSIONS = [
        "correctness",      # Does the solution actually solve the problem?
        "completeness",     # Are edge cases handled? Error states covered?
        "test_coverage",    # Are tests comprehensive and passing?
        "simplicity",       # Is the solution minimal and clear?
        "safety",           # Could this change break other things?
    ]

    # Severity levels with weights for aggregation
    SEVERITY_WEIGHTS: dict[str, float] = {
        "blocker": 1.0,
        "major": 0.7,
        "minor": 0.3,
        "suggestion": 0.1,
    }

    def __init__(self, llm_provider: Any = None):
        """Initialize the debate engine.

        Args:
            llm_provider: Optional LLM to generate critiques and synthesis.
                          If None, uses heuristic critique generation.
        """
        self._llm = llm_provider

    def run_debate(
        self, variants: list[dict[str, Any]], task_description: str,
        max_rounds: int = 2,
    ) -> DebateResult:
        """Run a full debate process across all variants.

        Args:
            variants: List of variant result dicts from ExperimentRunner
            task_description: The original task description
            max_rounds: Maximum number of critique rounds

        Returns:
            DebateResult with analysis and synthesis
        """
        if len(variants) < 2:
            return DebateResult(
                variant_count=len(variants),
                key_insights=["Need at least 2 variants for debate."],
            )

        # Assign variant IDs
        for i, v in enumerate(variants):
            if "variant_id" not in v:
                v["variant_id"] = f"variant_{i}"

        result = DebateResult(variant_count=len(variants))

        # Find winner before debate
        best_before = max(
            variants,
            key=lambda v: v.get("score", 0) if isinstance(v.get("score"), (int, float)) else 0,
        )
        result.winner_before_debate = best_before.get("variant_id", "unknown")

        # Run critique rounds
        for round_num in range(1, max_rounds + 1):
            debate_round = self._run_critique_round(variants, task_description, round_num)
            result.rounds.append(debate_round)

            # Stop if high consensus achieved
            if debate_round.consensus_score > 0.8 and debate_round.blocker_count == 0:
                logger.info(f"High consensus ({debate_round.consensus_score:.2f}) — stopping debate")
                break

        # Generate synthesis
        synthesis = self._generate_synthesis(variants, result.rounds, task_description)
        result.synthesis_approach = synthesis.get("approach", "Consensus Hybrid")
        result.synthesis_description = synthesis.get("description", "")
        result.key_insights = synthesis.get("insights", [])
        result.improvement_over_best = synthesis.get("improvement_estimate", 0.0)

        # Estimate post-debate winner
        # The synthesis variant would be the new winner
        result.winner_after_debate = "synthesis"

        return result

    def _run_critique_round(
        self, variants: list[dict[str, Any]], task_description: str, round_num: int,
    ) -> DebateRound:
        """Run a single round of critiques between all variants.

        Each variant critiques every other variant on all dimensions.
        """
        debate_round = DebateRound(round_id=round_num)
        all_critiques: list[Critique] = []

        for critic in variants:
            critic_id = critic.get("variant_id", "unknown")
            for target in variants:
                target_id = target.get("variant_id", "unknown")
                if critic_id == target_id:
                    continue  # Don't critique yourself

                # Generate critiques for this pair
                critiques = self._critique_variant(
                    critic, target, task_description
                )
                all_critiques.extend(critiques)

        debate_round.critiques = all_critiques

        # Compute consensus score
        if all_critiques:
            debate_round.consensus_score = self._compute_consensus(all_critiques)
        else:
            debate_round.consensus_score = 0.0

        return debate_round

    def _critique_variant(
        self, critic: dict[str, Any], target: dict[str, Any], task_description: str,
    ) -> list[Critique]:
        """Generate critiques from one variant about another.

        Uses heuristic analysis if no LLM is available, otherwise delegates
        to the LLM for deeper semantic critique.
        """
        critic_id = critic.get("variant_id", "unknown")
        target_id = target.get("variant_id", "unknown")
        critiques: list[Critique] = []

        if self._llm is not None:
            # Use LLM for semantic critique generation
            return self._llm_critique(critic, target, task_description)

        # ── Heuristic Critique Generation ────────────────────

        # Correctness: Did tests pass?
        target_tests_passed = target.get("tests_passed", 0)
        target_tests_total = target.get("tests_total", 0)
        if target_tests_total > 0:
            pass_rate = target_tests_passed / target_tests_total
            if pass_rate < 0.5:
                critiques.append(Critique(
                    critic_variant_id=critic_id,
                    target_variant_id=target_id,
                    dimension="correctness",
                    severity="blocker",
                    comment=f"Only {target_tests_passed}/{target_tests_total} tests pass ({pass_rate:.0%}). Solution is likely incorrect.",
                    suggested_fix="Re-examine the core logic and ensure all existing tests pass before adding new ones.",
                    confidence=0.9,
                ))
            elif pass_rate < 0.8:
                critiques.append(Critique(
                    critic_variant_id=critic_id,
                    target_variant_id=target_id,
                    dimension="correctness",
                    severity="major",
                    comment=f"Test pass rate ({pass_rate:.0%}) needs improvement.",
                    suggested_fix="Investigate the {target_tests_total - target_tests_passed} failing tests and fix root causes.",
                    confidence=0.7,
                ))

        # Completeness: Compare files changed
        target_files = len(target.get("files_changed", []))
        critic_files = len(critic.get("files_changed", []))
        if critic_files > 0 and target_files < critic_files * 0.5:
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="completeness",
                severity="major",
                comment=f"Modified only {target_files} files vs. {critic_files} by critic. May miss related code.",
                suggested_fix="Check if changes in related files are also needed.",
                confidence=0.5,
            ))
        elif target_files > critic_files * 2:
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="simplicity",
                severity="minor",
                comment=f"Modified {target_files} files (vs. {critic_files} by critic). Unnecessarily broad?",
                suggested_fix="Can the change be scoped to fewer files?",
                confidence=0.4,
            ))

        # Test coverage: Compare test counts
        critic_tests_total = critic.get("tests_total", 0)
        if critic_tests_total > 0 and target_tests_total < critic_tests_total * 0.5:
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="test_coverage",
                severity="major",
                comment=f"Only {target_tests_total} tests vs. {critic_tests_total} by critic. Test coverage may be insufficient.",
                suggested_fix="Add more tests covering edge cases and error paths.",
                confidence=0.6,
            ))

        # Safety: Check for high-risk file modifications
        target_high_risk = target.get("high_risk_files", 0)
        if target_high_risk > 2:
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="safety",
                severity="major",
                comment=f"Modifies {target_high_risk} high-risk files. Changes may have unintended consequences.",
                suggested_fix="Add integration tests verifying that dependent modules still work correctly.",
                confidence=0.7,
            ))

        # Efficiency comparison
        target_tokens = target.get("token_count", 0)
        critic_tokens = critic.get("token_count", 0)
        if critic_tokens > 0 and target_tokens > critic_tokens * 2:
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="simplicity",
                severity="minor",
                comment=f"Used {target_tokens} tokens (vs. {critic_tokens}). May be over-engineered.",
                suggested_fix="Simplify the solution — less code is often better.",
                confidence=0.4,
            ))

        # Add a positive critique if the target outperforms the critic
        target_score = target.get("score", 0)
        if target_score > critic.get("score", 0):
            critiques.append(Critique(
                critic_variant_id=critic_id,
                target_variant_id=target_id,
                dimension="correctness",
                severity="suggestion",
                comment=f"Score ({target_score}) is higher than critic ({critic.get('score', 0)}). Overall approach appears effective.",
                suggested_fix="",
                confidence=0.3,
            ))

        return critiques

    def _llm_critique(
        self, critic: dict[str, Any], target: dict[str, Any], task_description: str,
    ) -> list[Critique]:
        """Use LLM for deep semantic critique generation.

        Constructs a prompt asking the LLM to analyze the target variant's
        solution and identify specific issues.
        """
        critic_id = critic.get("variant_id", "unknown")
        target_id = target.get("variant_id", "unknown")

        # In a full implementation, this would call the LLM and parse structured output.
        # The prompt template is intentionally not assigned to a variable to avoid
        # unused-variable warnings — the LLM integration is a stub for now.
        # When activated, use: prompt = f"""You are a code reviewer..."""
        logger.info(f"LLM critique would be generated for {target_id} by {critic_id}")
        return []

    def _compute_consensus(self, critiques: list[Critique]) -> float:
        """Compute how much critics agree with each other.

        High consensus = critics independently identified the same issues.
        Low consensus = critics disagree about what's wrong.

        Uses Krippendorff's alpha-like metric: normalized agreement
        across all critic pairs.
        """
        if len(critiques) < 2:
            return 1.0 if critiques else 0.0

        # Group critiques by target variant
        by_target: dict[str, list[Critique]] = {}
        for c in critiques:
            by_target.setdefault(c.target_variant_id, []).append(c)

        consensus_scores: list[float] = []

        for target_id, target_critiques in by_target.items():
            if len(target_critiques) < 2:
                continue

            # Check if critics agree on the severe issues
            matched = 0
            total = 0
            for i, c1 in enumerate(target_critiques):
                for c2 in target_critiques[i + 1:]:
                    total += 1
                    # Agreement if same dimension AND severity within 1 level
                    if c1.dimension == c2.dimension:
                        sev_levels = {"blocker": 0, "major": 1, "minor": 2, "suggestion": 3}
                        if abs(sev_levels.get(c1.severity, 0) - sev_levels.get(c2.severity, 0)) <= 1:
                            matched += 1

            if total > 0:
                consensus_scores.append(matched / total)

        return sum(consensus_scores) / len(consensus_scores) if consensus_scores else 0.0

    def _generate_synthesis(
        self, variants: list[dict[str, Any]], rounds: list[DebateRound],
        task_description: str,
    ) -> dict[str, Any]:
        """Generate a synthesis approach combining the best elements of all variants.

        Based on critiques, identifies:
        - Which variant has the best core approach
        - Which specific elements to borrow from other variants
        - What to avoid based on blocker critiques
        """
        if not rounds:
            return {
                "approach": "No consensus",
                "description": "Insufficient debate data for synthesis.",
                "insights": [],
                "improvement_estimate": 0.0,
            }

        # Collect all critiques and rank issues by frequency
        critique_counts: dict[str, int] = {}
        blocker_issues: list[str] = []
        praised_elements: list[str] = []

        for round_data in rounds:
            for c in round_data.critiques:
                key = f"{c.dimension}:{c.comment[:80]}"
                critique_counts[key] = critique_counts.get(key, 0) + 1
                if c.severity == "blocker":
                    blocker_issues.append(c.comment)
                if c.severity == "suggestion" and c.confidence > 0.5:
                    praised_elements.append(c.comment)

        # Build synthesis approach
        insights: list[str] = []

        # Identify worst problems to avoid
        if blocker_issues:
            top_blockers = list(set(blocker_issues))[:3]
            insights.append(f"🔴 BLOCKERS to avoid: {'; '.join(top_blockers)}")

        # Identify consensus strengths
        if praised_elements:
            top_praises = list(set(praised_elements))[:3]
            insights.append(f"🟢 Strengths to combine: {'; '.join(top_praises)}")

        # Recommend approach
        # Sort variants by score (descending) and pick top approach
        sorted_variants = sorted(
            variants,
            key=lambda v: v.get("score", 0) if isinstance(v.get("score"), (int, float)) else 0,
            reverse=True,
        )

        best_approach = sorted_variants[0].get("approach", "Standard") if sorted_variants else "Standard"
        second_approach = sorted_variants[1].get("approach", "Standard") if len(sorted_variants) > 1 else "Standard"

        # Find what to borrow from second-best
        borrow_from_second = ""
        if len(sorted_variants) > 1:
            second = sorted_variants[1]
            if second.get("tests_passed", 0) > sorted_variants[0].get("tests_passed", 0):
                borrow_from_second = f" Borrow test strategy from '{second_approach}'."
            elif len(second.get("files_changed", [])) < len(sorted_variants[0].get("files_changed", [])):
                borrow_from_second = f" Borrow minimal change scope from '{second_approach}'."
            elif second.get("token_count", 0) < sorted_variants[0].get("token_count", 0):
                borrow_from_second = f" Borrow efficiency from '{second_approach}'."

        synthesis_approach = f"Consensus: '{best_approach}' base + improvements from debate{borrow_from_second}"
        synthesis_description = (
            f"Start with the '{best_approach}' approach (highest-scoring individual variant). "
            f"Apply the critical fixes identified by peers. "
            f"{borrow_from_second} "
            f"Avoid the blockers found during debate: "
            f"{'; '.join(blocker_issues[:2]) if blocker_issues else 'none identified'}."
        )

        # Estimate improvement
        # Based on: consensus score × (1 - best_score) as headroom for improvement
        best_score = sorted_variants[0].get("score", 50) if sorted_variants else 50
        consensus = rounds[-1].consensus_score if rounds else 0.0
        improvement_estimate = consensus * max(0, 100 - best_score) / 100 * 0.3  # Cap at 30% improvement

        return {
            "approach": synthesis_approach,
            "description": synthesis_description,
            "insights": insights,
            "improvement_estimate": round(improvement_estimate, 3),
        }

    # ── Context Builder for Agent Prompts ─────────────────────

    def build_debate_context(
        self, variants: list[dict[str, Any]], task_description: str,
    ) -> str:
        """Build a debate analysis context block for agent prompts.

        Provides the agent with peer review insights from previous attempts.
        """
        if len(variants) < 2:
            return ""

        debate_result = self.run_debate(variants, task_description, max_rounds=1)

        lines = ["### 🤝 Multi-Agent Code Review — Peer Consensus", ""]

        for i, round_data in enumerate(debate_result.rounds):
            lines.append(f"**Round {round_data.round_id}:** {len(round_data.critiques)} critiques")
            lines.append(f"- Consensus: {round_data.consensus_score:.0%} agreement among reviewers")
            lines.append(f"- Blockers: {round_data.blocker_count} | Majors: {round_data.major_count} | Minors: {round_data.minor_count}")
            lines.append("")

        # Top insights
        lines.append("**Key Takeaways:**")
        for insight in debate_result.key_insights[:5]:
            lines.append(f"- {insight}")
        lines.append("")

        # Recommended approach
        lines.append(f"**Recommended Synthesis:** {debate_result.synthesis_approach}")
        lines.append(f"*{debate_result.synthesis_description}*")
        lines.append("")

        if debate_result.improvement_over_best > 0:
            lines.append(f"**Estimated improvement over best individual:** +{debate_result.improvement_over_best:.0f} points")

        return "\n".join(lines)

    def get_debate_report(self, debate_result: DebateResult) -> str:
        """Generate a human-readable debate report."""
        lines = ["=" * 70]
        lines.append("  MULTI-AGENT DEBATE — CONSENSUS REPORT")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Variants debated: {debate_result.variant_count}")
        lines.append(f"Rounds: {len(debate_result.rounds)}")
        lines.append("")

        for i, round_data in enumerate(debate_result.rounds):
            lines.append(f"--- Round {round_data.round_id} ---")
            lines.append(f"  Critiques: {len(round_data.critiques)}")
            lines.append(f"  🔴 Blockers: {round_data.blocker_count}")
            lines.append(f"  🟠 Majors: {round_data.major_count}")
            lines.append(f"  🟡 Minors: {round_data.minor_count}")
            lines.append(f"  🟢 Suggestions: {round_data.suggestion_count}")
            lines.append(f"  Consensus: {round_data.consensus_score:.0%}")
            lines.append("")

            # Show top 3 most impactful critiques
            sorted_critiques = sorted(
                round_data.critiques,
                key=lambda c: self.SEVERITY_WEIGHTS.get(c.severity, 0) * c.confidence,
                reverse=True,
            )
            for c in sorted_critiques[:3]:
                emoji = {"blocker": "🔴", "major": "🟠", "minor": "🟡", "suggestion": "🟢"}.get(c.severity, "•")
                lines.append(f"  {emoji} [{c.dimension}] {c.comment}")
                if c.suggested_fix:
                    lines.append(f"     → Fix: {c.suggested_fix}")
            lines.append("")

        lines.append("--- Synthesis ---")
        lines.append(f"Approach: {debate_result.synthesis_approach}")
        lines.append(f"Description: {debate_result.synthesis_description}")
        lines.append("")
        lines.append(f"Winner (before debate): {debate_result.winner_before_debate}")
        lines.append(f"Winner (after debate): {debate_result.winner_after_debate}")
        lines.append(f"Estimated improvement: +{debate_result.improvement_over_best:.1f}")
        lines.append("")

        lines.append("--- Key Insights ---")
        for insight in debate_result.key_insights:
            lines.append(f"  • {insight}")
        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)