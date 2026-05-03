"""Predictive Impact Analysis — Breakthrough #2.

Queries historical session data to predict:
- Which tests are likely to break when specific files are changed
- Expected change scope (median lines changed, files modified)
- Downstream risk scores

Uses Bayesian probability: P(test_breaks | file_changed) from session history.
"""

from __future__ import annotations

from typing import Any


class ImpactPredictor:
    """Predicts the impact of changes based on historical session data.

    Queries session_files and session_test_results to compute:
    - Probability of breaking specific tests
    - Expected change scope
    - Risk scores (0.0 = safe, 1.0 = high risk)
    """

    def __init__(self, store: Any):
        self.store = store
        self._prediction_cache: dict[str, dict[str, Any]] = {}

    def predict_impact(self, files: list[str]) -> dict[str, Any]:
        """Predict the impact of changing a set of files.

        Returns a dict with:
        - risk_score: float (0.0–1.0)
        - likely_affected_files: list[str]
        - likely_broken_tests: list[tuple[str, float]]
        - median_change_lines: int
        - median_files_changed: int
        - confidence: float
        - evidence_count: int
        """
        cache_key = "|".join(sorted(files))
        if cache_key in self._prediction_cache:
            return self._prediction_cache[cache_key]

        result = self.store.predict_impact(files)
        self._prediction_cache[cache_key] = result
        return result

    def build_risk_context(self, files: list[str]) -> str:
        """Build a risk assessment context block for agent prompts."""
        if not files:
            return ""

        prediction = self.predict_impact(files)

        evidence_count = prediction.get("evidence_count", 0)
        if evidence_count < 3:
            return ""  # Not enough data for confident prediction

        lines = ["### Risk Assessment", ""]

        risk = prediction.get("risk_score", 0.0)
        risk_label = (
            "🔴 HIGH RISK" if risk >= 0.7
            else "🟡 MEDIUM RISK" if risk >= 0.35
            else "🟢 LOW RISK"
        )
        lines.append(f"- **Risk Level:** {risk_label} ({risk:.0%})")
        lines.append(f"- **Confidence:** {prediction.get('confidence', 0):.0%} (based on {evidence_count} similar sessions)")
        lines.append(f"- **Expected change scope:** ~{prediction.get('median_change_lines', 0)} lines in ~{prediction.get('median_files_changed', 0)} files")

        affected = prediction.get("likely_affected_files", [])
        if affected:
            lines.append(f"- **Likely affected files:** {', '.join(affected[:5])}")

        broken_tests = prediction.get("likely_broken_tests", [])
        if broken_tests:
            lines.append("- **Tests likely to break:**")
            for test_name, probability in broken_tests[:5]:
                if probability >= 0.5:
                    lines.append(f"  - `{test_name}` — {probability:.0%} probability of breaking")

        lines.append("")
        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        """Clear predictions after new sessions are ingested."""
        self._prediction_cache.clear()