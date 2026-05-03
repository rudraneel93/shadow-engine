"""Learning Engine — Cross-session pattern extraction and compounding intelligence.

This module analyzes completed agent sessions to extract:
1. Codebase conventions (patterns observed in successful PRs)
2. Approach efficacy (which strategies work for which problem types)
3. Codebase hot spots (files/symbols that change frequently)
4. Improvement signals (how the knowledge graph evolves over time)
"""

from __future__ import annotations

from typing import Any, Protocol

from ..knowledge_graph.models import (
    AgentOutcome, ApproachEfficacy, CodePattern, SessionRecord,
)

# Fix #6: Store protocol for duck typing (SQLiteStore + KnowledgeGraphStore)
class StoreProtocol(Protocol):
    def record_session(self, session: SessionRecord) -> None: ...
    def get_stats(self) -> dict[str, Any]: ...
    def update_approach_efficacy(self, problem_type: str, approach: str, was_successful: bool, model: str, duration_seconds: float, token_count: int) -> ApproachEfficacy: ...
    def get_best_approaches(self, problem_type: str | None = None, min_attempts: int = 3) -> list[ApproachEfficacy]: ...
    def learn_pattern(self, pattern_type: str, description: str, examples: list[str], source_session_id: str, confidence: float = 1.0) -> CodePattern: ...
    def get_patterns_by_type(self, pattern_type: str) -> list[CodePattern]: ...


class LearningEngine:
    """Cross-session learning engine that makes the agent smarter over time."""

    # Fix #6: Accept any store that satisfies the protocol
    def __init__(self, store: StoreProtocol):
        self.store = store

    def ingest_session(self, session: SessionRecord) -> dict[str, Any]:
        if session.outcome == AgentOutcome.IN_PROGRESS:
            return {"status": "skipped", "reason": "session still in progress"}

        self.store.record_session(session)
        problem_type, confidence = self._classify_problem_type(session.prompt)

        efficacy = self.store.update_approach_efficacy(
            problem_type=problem_type, approach=session.approach or "default",
            was_successful=session.was_successful, model=session.model,
            duration_seconds=session.duration_seconds, token_count=session.token_count,
        )

        results: dict[str, Any] = {
            "status": "ingested", "problem_type": problem_type,
            "classification_confidence": confidence,
            "approach": session.approach or "default",
            "was_successful": session.was_successful,
            "efficacy": {"success_rate": efficacy.success_rate, "total_attempts": efficacy.total_attempts, "best_model": efficacy.best_model},
            "patterns_learned": [],
        }

        if session.was_successful:
            patterns = self._extract_patterns_from_session(session)
            results["patterns_learned"] = [{"type": p.pattern_type, "description": p.description, "confidence": p.confidence} for p in patterns]

        if not session.was_successful and session.outcome != AgentOutcome.ABANDONED:
            results["failure_analysis"] = self._analyze_failure(session)

        return results

    def ingest_batch_results(self, batch_id: str, variants: list[dict[str, Any]], repository: str) -> dict[str, Any]:
        results: dict[str, Any] = {"batch_id": batch_id, "variants_ingested": 0, "winner_approach": None, "learned": []}
        for vdata in variants:
            self.ingest_session(SessionRecord(
                session_id=vdata.get("session_id", ""), repository=repository,
                prompt=vdata.get("prompt", ""), approach=vdata.get("approach", ""),
                model=vdata.get("model", "default"), outcome=AgentOutcome(vdata.get("outcome", "failure")),
                pr_url=vdata.get("pr_url"), files_changed=vdata.get("files_changed", []),
                test_results=vdata.get("test_results", {}),
                duration_seconds=vdata.get("duration_seconds", 0.0), token_count=vdata.get("token_count", 0),
            ))
            results["variants_ingested"] += 1
        return results

    def get_improvement_report(self) -> str:
        stats = self.store.get_stats()
        best_approaches = self.store.get_best_approaches()
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  SHADOW ENGINEER — IMPROVEMENT REPORT")
        lines.append("=" * 60)
        lines.append("")
        lines.append("### Knowledge Graph Health")
        lines.append(f"  Total symbols indexed: {stats['total_symbols']}")
        lines.append(f"  Total files indexed:   {stats['total_files']}")
        lines.append(f"  Patterns learned:      {stats['total_patterns']}")
        lines.append(f"  Graph nodes:           {stats.get('graph_nodes', 0)}")
        lines.append(f"  Graph edges:           {stats.get('graph_edges', 0)}")
        lines.append("")
        lines.append("### Agent Performance")
        total = stats["total_sessions"]
        completed = stats["completed_sessions"]
        successes = stats["successful_sessions"]
        lines.append(f"  Total sessions:        {total}")
        lines.append(f"  Completed:             {completed}")
        lines.append(f"  Successful:            {successes}")
        lines.append(f"  Overall success rate:  {stats['overall_success_rate']:.1%}")
        lines.append("")
        lines.append("### Most Effective Approaches")
        lines.append("")

        if not best_approaches:
            # Fix #3: Show partial data below threshold instead of "no data"
            all_approaches = self.store.get_best_approaches(min_attempts=1)
            if all_approaches:
                lines.append("  (Showing all approaches — need ≥3 attempts for confident recommendations)")
                lines.append("")
                for i, ae in enumerate(all_approaches[:5], 1):
                    lines.append(f"  {i}. [{ae.problem_type}] {ae.approach[:80]}")
                    lines.append(f"     Success: {ae.success_rate:.0%} ({ae.successes}/{ae.total_attempts})")
                    if ae.total_attempts < 3:
                        lines.append(f"     ⚠️  Low confidence — only {ae.total_attempts} attempt(s)")
                    lines.append(f"     Best model: {ae.best_model}")
                    lines.append(f"     Avg duration: {ae.avg_duration_seconds:.0f}s")
                    lines.append("")
            elif total == 0:
                lines.append("  (No sessions recorded yet — run your first agent to start learning!)")
            else:
                lines.append(f"  ({total} session(s) recorded. Keep using the agent to build confidence!)")
        else:
            for i, ae in enumerate(best_approaches[:5], 1):
                lines.append(f"  {i}. [{ae.problem_type}] {ae.approach[:80]}")
                lines.append(f"     Success: {ae.success_rate:.0%} ({ae.successes}/{ae.total_attempts})")
                lines.append(f"     Best model: {ae.best_model}")
                lines.append(f"     Avg duration: {ae.avg_duration_seconds:.0f}s")
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def suggest_approach(self, task_description: str) -> dict[str, Any]:
        problem_type, class_confidence = self._classify_problem_type(task_description)
        best_approaches = self.store.get_best_approaches(problem_type=problem_type)
        if not best_approaches:
            return {
                "problem_type": problem_type, "classification_confidence": class_confidence,
                "suggestion": "no_historical_data",
                "recommended_approach": "Use a balanced approach following existing codebase conventions.",
                "confidence": 0.0,
            }
        top = best_approaches[0]
        return {
            "problem_type": problem_type, "classification_confidence": class_confidence,
            "suggestion": "historical_best", "recommended_approach": top.approach,
            "expected_success_rate": top.success_rate, "best_model": top.best_model,
            "confidence": min(1.0, top.success_rate * (top.total_attempts / 10)),
            "evidence": f"Based on {top.total_attempts} previous attempts, this approach succeeds {top.success_rate:.0%} of the time with model {top.best_model}.",
        }

    _CLASSIFICATION_RULES: list[tuple[tuple[str, ...], str, float]] = [
        (("bug", "fix", "error", "crash", "broken", "failing"), "bug_fix", 0.9),
        (("test", "spec", "coverage", "tester"), "testing", 0.85),
        (("migrate", "upgrade", "update dependency", "bump"), "migration", 0.9),
        (("doc", "document", "readme", "comment"), "documentation", 0.85),
        (("refactor", "clean", "improve", "optimize", "simplify"), "refactor", 0.75),
        (("feature", "add", "implement", "create", "build", "new"), "feature", 0.7),
    ]

    @staticmethod
    def _classify_problem_type(prompt: str) -> tuple[str, float]:
        p = prompt.lower()
        for keywords, ptype, base_conf in LearningEngine._CLASSIFICATION_RULES:
            matches = sum(1 for kw in keywords if kw in p)
            if matches > 0:
                return ptype, min(1.0, base_conf + (matches - 1) * 0.05)
        return "general", 0.3

    def _extract_patterns_from_session(self, session: SessionRecord) -> list[CodePattern]:
        patterns: list[CodePattern] = []
        if session.files_changed:
            cf = session.files_changed
            test_files = [f for f in cf if "test" in f.lower() or f.endswith("_test.py") or ".test." in f]
            non_test = [f for f in cf if f not in test_files]
            if test_files and non_test:
                patterns.append(self.store.learn_pattern("testing", f"Agent writes tests alongside code changes. Modified {len(non_test)} source files and {len(test_files)} test files.", cf[:5], session.session_id, 0.9))
            if len(cf) <= 3 and len(non_test) <= 2:
                patterns.append(self.store.learn_pattern("change_scope", "Successful sessions tend to modify few files. Targeted, minimal changes are more likely to succeed.", cf, session.session_id, 0.8))
        if session.test_results:
            total = session.test_results.get("total", 0)
            passed = session.test_results.get("passed", 0)
            if total > 0 and (passed / total) == 1.0:
                patterns.append(self.store.learn_pattern("testing", "All tests pass on first attempt when changes are targeted and test coverage is maintained.", session.files_changed[:3], session.session_id, 0.7))
        if session.review_comments:
            negative = [c for c in session.review_comments if any(w in c.lower() for w in ("change", "fix", "revert", "wrong", "incorrect"))]
            if not negative:
                patterns.append(self.store.learn_pattern("code_quality", "Clean PRs with no requested changes follow existing codebase conventions closely.", session.files_changed[:3], session.session_id, 0.75))
        return patterns

    @staticmethod
    def _analyze_failure(session: SessionRecord) -> dict[str, Any]:
        analysis: dict[str, Any] = {"outcome": session.outcome.value, "potential_reasons": []}
        if session.outcome == AgentOutcome.REJECTED:
            analysis["potential_reasons"].append("PR was rejected in code review. Check review comments for specific issues.")
            if session.review_comments: analysis["review_feedback"] = session.review_comments[:5]
        elif session.outcome == AgentOutcome.FAILURE:
            if session.test_results:
                passed, failed = session.test_results.get("passed", 0), session.test_results.get("failed", 0)
                if failed > 0: analysis["potential_reasons"].append(f"{failed} tests failed out of {passed + failed}. Agent changes broke existing functionality.")
            if len(session.files_changed) > 10: analysis["potential_reasons"].append(f"Agent modified {len(session.files_changed)} files — changes were too broad and likely introduced risk.")
            if session.duration_seconds < 10: analysis["potential_reasons"].append("Session completed very quickly — may not have been thorough enough.")
        return analysis