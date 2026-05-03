"""Pre-Commit Risk Gate — Combined risk score before every commit.

Combines Live Monitor file risk + approach efficacy + dependency fanout
into a single 0.0-1.0 risk score. If score > 0.7, recommends alternative approach.

Uses Bayesian Beta-Binomial risk from LiveMonitor, success rates from
approach efficacy tracking, and dependency fanout from HotZoneDetector.
"""

from __future__ import annotations

from typing import Any


class RiskGate:
    """Pre-commit risk gate combining file risk, approach risk, and fanout risk."""

    def __init__(self, store: Any, live_monitor: Any = None, hot_zones: Any = None):
        self.store = store
        self._live_monitor = live_monitor
        self._hot_zones = hot_zones

    def gate(
        self,
        files: list[str],
        approach: str,
        model: str = "default",
    ) -> dict[str, Any]:
        """Compute a combined risk score for a planned commit.

        Returns:
        - risk_score: float (0.0-1.0)
        - file_risk: float — average Bayesian risk across files
        - approach_risk: float — 1 - (success rate for this approach)
        - fanout_risk: float — normalized dependency fanout risk
        - recommendation: str — what to do if risk is high
        """
        file_risk = 0.0
        approach_risk = 0.0
        fanout_risk = 0.0

        # 1. File-level Bayesian risk (weight: 0.5)
        if self._live_monitor and files:
            risks = []
            for f in files:
                r = self._live_monitor.check_file(f)
                risks.append(r["risk_score"])
            file_risk = sum(risks) / len(risks) if risks else 0.5

        # 2. Approach success rate (weight: 0.35)
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn and approach:
            # Find this approach's success rate across all problem types
            approach_row = conn.execute(
                "SELECT SUM(total_attempts) as total, SUM(successes) as successes "
                "FROM approaches WHERE approach=?",
                (approach,),
            ).fetchone()
            if approach_row and approach_row["total"] and approach_row["total"] > 0:
                success_rate = approach_row["successes"] / approach_row["total"]
                approach_risk = 1.0 - success_rate
            else:
                approach_risk = 0.5  # Unknown approach

        # 3. Dependency fanout risk (weight: 0.15)
        if self._hot_zones and files:
            zones = self._hot_zones.detect_hot_zones(min_sessions=1, top_n=50)
            fanout_scores = []
            for f in files:
                matching = [z for z in zones if z["file_path"] == f]
                if matching:
                    fanout_scores.append(matching[0]["hot_score"])
            if fanout_scores:
                fanout_risk = min(1.0, sum(fanout_scores) / len(fanout_scores))

        # Compute combined risk
        risk_score = (file_risk * 0.5) + (approach_risk * 0.35) + (fanout_risk * 0.15)

        # Find better alternative approach if risk is high
        alternative = None
        if risk_score > 0.5 and conn:
            best = conn.execute(
                "SELECT approach, CAST(successes AS REAL)/total_attempts as rate "
                "FROM approaches WHERE total_attempts >= 1 "
                "ORDER BY rate DESC LIMIT 3"
            ).fetchall()
            for row in best:
                if row["approach"] != approach and row["rate"] > (1 - approach_risk + 0.1):
                    alternative = {
                        "approach": row["approach"],
                        "success_rate": round(row["rate"], 2),
                        "estimated_risk": round(
                            (file_risk * 0.5) + ((1 - row["rate"]) * 0.35) + (fanout_risk * 0.15), 2
                        ),
                    }
                    break

        return {
            "risk_score": round(risk_score, 2),
            "risk_label": (
                "🔴 HIGH" if risk_score >= 0.7
                else "🟡 MEDIUM" if risk_score >= 0.35
                else "🟢 LOW"
            ),
            "file_risk": round(file_risk, 2),
            "approach_risk": round(approach_risk, 2),
            "fanout_risk": round(fanout_risk, 2),
            "alternative": alternative,
            "recommendation": (
                f"Switch to '{alternative['approach']}' — estimated risk drops to {alternative['estimated_risk']:.0%}"
                if alternative and alternative["estimated_risk"] < risk_score
                else "Proceed with caution — verify tests pass before committing"
            ),
        }

    def build_gate_context(
        self, files: list[str], approach: str, model: str = "default"
    ) -> str:
        """Build a pre-commit risk gate context block."""
        result = self.gate(files, approach, model)

        lines = ["### ⚠️ Pre-Commit Risk Assessment", ""]
        lines.append(f"**Risk Score:** {result['risk_label']} ({result['risk_score']:.0%})")
        lines.append("")
        lines.append("**Component Breakdown:**")
        lines.append(f"- File Risk: {result['file_risk']:.0%} (weight: 50%)")
        lines.append(f"- Approach Risk: {result['approach_risk']:.0%} (weight: 35%)")
        lines.append(f"- Fanout Risk: {result['fanout_risk']:.0%} (weight: 15%)")
        lines.append("")

        if result.get("alternative"):
            alt = result["alternative"]
            lines.append(f"**Alternative Approach:** '{alt['approach']}' "
                        f"(success rate: {alt['success_rate']:.0%}, "
                        f"estimated risk: {alt['estimated_risk']:.0%})")
            lines.append("")

        lines.append(f"**Recommendation:** {result['recommendation']}")
        lines.append("")
        return "\n".join(lines)