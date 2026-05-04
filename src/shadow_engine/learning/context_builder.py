"""Context Builder — builds agent context by aggregating all learning engines.

Extracted from main.py to reduce the 22KB monolith.
Wires together classification, patterns, causal analysis, debate,
temporal anomaly detection, and knowledge graph context.
"""

from __future__ import annotations

import logging
from typing import Any

from .context_budget import ContextBudgetManager

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Aggregates context from all learning engines into a coherent agent prompt.

    Uses ContextBudgetManager to stay within token limits when multiple
    engines produce large context blocks.
    """

    def __init__(self, engine: Any):
        self.engine = engine  # ShadowEngine reference for all sub-engines

    def build(self, task_description: str, max_tokens: int = 3000) -> str:
        """Build the complete agent context block.

        Args:
            task_description: The task the agent is being asked to perform.
            max_tokens: Maximum estimated tokens for the context block.

        Returns:
            Multi-section context string for injection into agent prompts.
        """
        suggestion = self.engine.suggest(task_description)
        budget = ContextBudgetManager(max_tokens=max_tokens)

        # Priority 0: Classification (must always be included)
        budget.add_section(0, "classification", "Problem Classification",
                           lambda: self._build_classification(suggestion))

        # Priority 10: Historical insight
        budget.add_section(10, "historical", "Historical Insight",
                           lambda: self._build_historical_insight(suggestion))

        # Priority 20: Proven fix patterns (deduplicated)
        budget.add_section(20, "patterns", "Fix Patterns",
                           lambda: self._build_patterns(suggestion, task_description))

        # Priority 30: Code-level diff patterns
        budget.add_section(30, "code_patterns", "Code-Level Patterns",
                           lambda: self._build_code_patterns(suggestion))

        # Priority 40: Causal analysis (if experimental)
        budget.add_section(40, "causal", "Causal Analysis",
                           lambda: self._build_causal_analysis(task_description))

        # Priority 50: Risk warnings + test risk + Bayesian
        budget.add_section(50, "risk", "Risk Assessment",
                           lambda: self._build_risk_assessment(task_description))

        # Priority 60: Temporal analysis
        budget.add_section(60, "temporal", "Temporal Analysis",
                           lambda: self._build_temporal_analysis())

        # Priority 70: Knowledge graph context (large, lower priority)
        budget.add_section(70, "knowledge_graph", "Knowledge Graph",
                           lambda: self._build_knowledge_graph(task_description))

        return budget.build()

    # ── Section Builders ─────────────────────────────────

    def _build_classification(self, suggestion: dict) -> str:
        lines = ["### Problem Classification"]
        lines.append(f"- **Type**: {suggestion['problem_type']} (confidence: {suggestion['classification_confidence']:.2f})")
        lines.append(f"- **Recommended Approach**: {suggestion['recommended_approach']}")
        expected = suggestion.get("expected_success_rate", 0.0)
        if expected > 0:
            lines.append(f"- **Expected Success Rate**: {expected:.0%}")
        lines.append(f"- **Best Model**: {suggestion.get('best_model', 'unknown')}")
        lines.append("")
        return "\n".join(lines)

    def _build_historical_insight(self, suggestion: dict) -> str:
        evidence = suggestion.get("evidence",
            f"Based on {suggestion.get('total_attempts', 0)} tracked sessions, "
            f"'{suggestion['recommended_approach']}' has the highest success rate "
            f"for {suggestion['problem_type']} tasks.")
        lines = ["### Historical Insight", f"- {evidence}", ""]
        return "\n".join(lines)

    def _build_patterns(self, suggestion: dict, task_description: str) -> str:
        try:
            return self.engine.merger.get_merged_context(
                suggestion['problem_type'], task_description)
        except Exception:
            return ""

    def _build_code_patterns(self, suggestion: dict) -> str:
        try:
            return self.engine.diff_analyzer.build_code_pattern_context(
                suggestion['problem_type'])
        except Exception:
            return ""

    def _build_causal_analysis(self, task_description: str) -> str:
        try:
            from .causal_engine import CausalEngine
            from .experimental import is_experimental_enabled
            if not is_experimental_enabled():
                return ""
            causal = CausalEngine(self.engine.store)
            return causal.build_causal_context(task_description)
        except Exception:
            return ""

    def _build_risk_assessment(self, task_description: str) -> str:
        parts: list[str] = []
        semantic_files = self._get_semantic_files(task_description)

        if semantic_files:
            try:
                warnings = self.engine.live_monitor.generate_warnings_text(semantic_files)
                if warnings:
                    parts.append(warnings)
            except Exception:
                pass

            try:
                test_risk = self.engine.test_tracker.build_test_risk_context(semantic_files)
                if test_risk:
                    parts.append(test_risk)
            except Exception:
                pass

            try:
                risk_context = self.engine.bayesian.build_context_bayesian(semantic_files)
                if risk_context:
                    parts.append(risk_context)
            except Exception:
                pass

        return "\n".join(parts)

    def _build_temporal_analysis(self) -> str:
        try:
            from .temporal_anomaly import TemporalAnomalyDetector
            from .experimental import is_experimental_enabled
            if not is_experimental_enabled():
                return ""
            tad = TemporalAnomalyDetector(self.engine.store)
            return tad.build_temporal_context()
        except Exception:
            return ""

    def _build_knowledge_graph(self, task_description: str) -> str:
        parts: list[str] = []
        if self.engine._chroma is not None and self.engine._chroma.count() > 0:
            try:
                results = self.engine._chroma.search(task_description, top_k=15)
                if results:
                    parts.append("### Knowledge Graph Context")
                    parts.append("")
                    parts.append("#### Semantically Relevant Symbols")
                    parts.append("")
                    for sym, score in results[:15]:
                        full_sym = self.engine.store.get_symbol(sym.id) or sym
                        parts.append(
                            f"- **{full_sym.name}** (`{full_sym.kind.value}`) "
                            f"in `{full_sym.file_path}` (relevance: {score:.2f})"
                        )
                        if full_sym.docstring:
                            parts.append(f"  {full_sym.docstring[:200].replace(chr(10), ' ')}")
                        deps = self.engine.store.get_symbol_dependencies(full_sym.id)
                        if deps:
                            parts.append(f"  Depends on: {', '.join(d.name for d in deps[:5])}")
                        parts.append("")
                    parts.append("")
                    parts.append(self.engine.store.build_context_for_prompt(task_description))
            except Exception as e:
                logger.warning(f"KG context failed: {e}")

        if not parts:
            parts.append(self.engine.store.build_context_for_prompt(task_description))
        return "\n".join(parts)

    def _get_semantic_files(self, task_description: str) -> list[str]:
        if self.engine._chroma is None or self.engine._chroma.count() == 0:
            return []
        try:
            results = self.engine._chroma.search(task_description, top_k=5)
            return [s.file_path for s, _ in results[:5]]
        except Exception:
            return []