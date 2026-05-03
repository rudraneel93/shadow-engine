"""Codebase Health Score — Single metric from 0-100 summarizing codebase health.

Computed from:
- Hot zones: how many files are in the danger zone
- Failure rate: what percentage of sessions fail
- Risk trend: is the failure rate increasing or decreasing
- Approach efficacy: how effective are the best approaches

Formula:
  Health = 100 - (hz_penalty × 30) - (failure_penalty × 40) - (trend_penalty × 30)
"""

from __future__ import annotations

from typing import Any


class HealthScorer:
    """Computes a single 0-100 health score for the codebase."""

    def __init__(self, store: Any, hot_zones: Any = None):
        self.store = store
        self._hot_zones = hot_zones

    def compute(self) -> dict[str, Any]:
        """Compute the codebase health score and its components.

        Returns a dict with:
        - overall_score: int (0-100)
        - hot_zone_score: int (0-100)
        - failure_rate_score: int (0-100)
        - trend_score: int (0-100)
        - components: dict with detailed breakdown
        """
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return {"overall_score": 50, "error": "No database connection"}

        # 1. Hot zone score: how many files are high-risk?
        hz_score = 100
        if self._hot_zones:
            zones = self._hot_zones.detect_hot_zones(min_sessions=1, top_n=50)
            if zones:
                high_risk = sum(1 for z in zones if z["failure_rate"] >= 0.3)
                medium_risk = sum(1 for z in zones if 0.1 <= z["failure_rate"] < 0.3)
                # Penalty: 10 points per high-risk file, 5 per medium-risk
                hz_score = max(0, 100 - (high_risk * 10) - (medium_risk * 5))

        # 2. Failure rate score
        total = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE outcome != 'in_progress'").fetchone()["cnt"]
        if total > 0:
            failures = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE outcome = 'failure'").fetchone()["cnt"]
            failure_rate = failures / total
            # Penalty: linear from 0-100 based on failure rate
            failure_score = max(0, 100 - int(failure_rate * 100))
        else:
            failure_score = 100

        # 3. Risk trend: is failure rate increasing?
        # Compare first half of sessions vs second half
        sessions = conn.execute(
            "SELECT outcome FROM sessions WHERE outcome IN ('success', 'failure') "
            "ORDER BY created_at ASC"
        ).fetchall()

        trend_score = 100
        if len(sessions) >= 6:
            mid = len(sessions) // 2
            first_half = sessions[:mid]
            second_half = sessions[mid:]
            first_rate = sum(1 for s in first_half if s["outcome"] == "failure") / len(first_half)
            second_rate = sum(1 for s in second_half if s["outcome"] == "failure") / len(second_half)
            if second_rate > first_rate + 0.1:
                # Getting worse
                trend_score = max(0, 100 - int((second_rate - first_rate) * 200))
            elif second_rate < first_rate - 0.1:
                # Getting better — bonus
                trend_score = min(100, 100 + int(abs(second_rate - first_rate) * 100))

        # 4. Compute overall
        overall = int((hz_score * 0.3) + (failure_score * 0.4) + (trend_score * 0.3))

        return {
            "overall_score": overall,
            "hot_zone_score": hz_score,
            "failure_rate_score": failure_score,
            "trend_score": trend_score,
            "total_sessions": total,
            "failure_rate": round(failures / total * 100, 1) if total > 0 and 'failures' in dir() else 0,
            "components": {
                "hot_zones": {"score": hz_score, "weight": 0.3},
                "failure_rate": {"score": failure_score, "weight": 0.4},
                "trend": {"score": trend_score, "weight": 0.3},
            },
            "grade": self._grade(overall),
        }

    def build_health_context(self) -> str:
        """Build a health score context block."""
        health = self.compute()

        lines = [
            "### Codebase Health Score",
            "",
            f"**Overall:** {health['overall_score']}/100 — {health['grade']}",
            "",
            "**Component Breakdown:**",
            f"- Hot Zones: {health['hot_zone_score']}/100",
            f"- Failure Rate: {health['failure_rate_score']}/100",
            f"- Risk Trend: {health['trend_score']}/100",
            "",
            f"Based on {health['total_sessions']} sessions ({health['failure_rate']}% failure rate).",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 90:
            return "🟢 Excellent"
        elif score >= 75:
            return "🟢 Good"
        elif score >= 60:
            return "🟡 Fair"
        elif score >= 40:
            return "🟠 Needs Attention"
        else:
            return "🔴 Critical"