"""Mid-Session Intervention Engine — Breakthrough Feature #4.

Closes the loop between monitoring and action. Instead of just warning about
risky files, the engine actively intervenes in agent sessions when risk
crosses configurable thresholds.

Intervention escalation ladder:
  1. WARN: Inject risk context into agent prompt (non-disruptive)
  2. INTERVENE: Halt session, inject corrective context, resume
  3. ABORT: Kill session, auto-spawn corrective variant via Laboratory
  4. ESCALATE: Notify human operator (future: Slack/email/webhook)

Tracks intervention efficacy to learn which interventions actually improve outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import logging

logger = logging.getLogger(__name__)


class InterventionLevel(str, Enum):
    WARN = "warn"          # Inject risk context silently
    INTERVENE = "intervene"  # Halt + inject corrective prompt
    ABORT = "abort"         # Kill + auto-spawn corrective variant
    ESCALATE = "escalate"    # Notify human


@dataclass
class InterventionEvent:
    session_id: str
    level: InterventionLevel
    triggered_by: str  # What triggered it (file risk, scope expansion, etc.)
    context_injected: str = ""
    was_effective: bool | None = None  # None = not yet known
    session_outcome_after: str = ""


class InterventionEngine:
    """Active supervisor that intervenes in high-risk agent sessions."""

    # Risk thresholds for each intervention level
    THRESHOLDS: dict[InterventionLevel, float] = {
        InterventionLevel.WARN: 0.3,     # >30% risk → warn
        InterventionLevel.INTERVENE: 0.5,  # >50% risk → pause + correct
        InterventionLevel.ABORT: 0.75,     # >75% risk → kill + retry
        InterventionLevel.ESCALATE: 0.9,   # >90% risk → human needed
    }

    def __init__(self, store: Any, live_monitor: Any = None, laboratory: Any = None):
        self.store = store
        self.live_monitor = live_monitor
        self.laboratory = laboratory
        self._interventions: list[InterventionEvent] = []
        self._active_sessions: dict[str, dict[str, Any]] = {}

    def assess_risk(self, files: list[str], approach: str = "",
                    session_id: str = "") -> tuple[float, InterventionLevel | None]:
        """Assess risk and determine if intervention is needed."""
        risk_scores: list[float] = []

        if self.live_monitor:
            try:
                warnings = self.live_monitor.generate_warnings_text(files)
                if "HIGH" in warnings:
                    risk_scores.append(0.8)
                elif "MEDIUM" in warnings:
                    risk_scores.append(0.4)
            except Exception:
                pass

        # File count risk
        if len(files) > 8:
            risk_scores.append(0.7)
        elif len(files) > 5:
            risk_scores.append(0.4)
        elif len(files) > 3:
            risk_scores.append(0.2)

        # Approach risk
        if approach:
            risky_approaches = {"aggressive rewrite", "clean sweep", "ambitious"}
            if any(r in approach.lower() for r in risky_approaches):
                risk_scores.append(0.6)

        # Hot zone risk from DB
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn and files:
            placeholders = ",".join("?" * len(files))
            results = conn.execute(
                f"SELECT file_path, COUNT(*) as cnt FROM session_files "
                f"WHERE file_path IN ({placeholders}) "
                f"GROUP BY file_path",
                files,
            ).fetchall()
            for r in results:
                if r["cnt"] > 5:
                    risk_scores.append(0.5)

        overall_risk = max(risk_scores) if risk_scores else 0.0

        level = None
        for lvl in [InterventionLevel.WARN, InterventionLevel.INTERVENE,
                     InterventionLevel.ABORT, InterventionLevel.ESCALATE]:
            if overall_risk >= self.THRESHOLDS[lvl]:
                level = lvl

        return overall_risk, level

    def build_intervention_context(self, files: list[str], risk_score: float,
                                    level: InterventionLevel) -> str:
        """Build context to inject into agent prompt based on risk level."""
        lines = []

        if level == InterventionLevel.WARN:
            lines.append("### ⚠️ Risk Warning")
            lines.append(f"- {len(files)} files being modified have elevated risk ({risk_score:.0%})")
            lines.append("- Consider using a more targeted approach")
            lines.append("- Ensure all existing tests pass before adding new changes")
        elif level == InterventionLevel.INTERVENE:
            lines.append("### 🛑 INTERVENTION: High Risk Detected")
            lines.append(f"- Risk score: {risk_score:.0%}")
            lines.append("- PAUSE. Review the following before continuing:")
            lines.append("  1. Can you reduce the number of files being changed?")
            lines.append("  2. Have you verified that all existing tests still pass?")
            lines.append("  3. Consider switching to a 'Targeted Fix' approach")
        elif level in (InterventionLevel.ABORT, InterventionLevel.ESCALATE):
            lines.append("### 🚨 CRITICAL: Unsafe to Proceed")
            lines.append(f"- Risk score: {risk_score:.0%} — exceeds safe threshold")
            lines.append("- This session should be aborted and reattempted with safer approach")

        return "\n".join(lines) + "\n"

    def record_intervention(self, event: InterventionEvent) -> None:
        self._interventions.append(event)

    def get_intervention_stats(self) -> dict[str, Any]:
        if not self._interventions:
            return {"total": 0, "effectiveness": 0.0}
        effective = sum(1 for i in self._interventions if i.was_effective is True)
        total_with_outcome = sum(1 for i in self._interventions if i.was_effective is not None)
        return {
            "total": len(self._interventions),
            "by_level": {
                lvl.value: sum(1 for i in self._interventions if i.level == lvl)
                for lvl in InterventionLevel
            },
            "effectiveness": effective / total_with_outcome if total_with_outcome > 0 else 0.0,
        }