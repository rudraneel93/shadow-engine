"""Real-Time Session Monitoring — Breakthrough Feature.

Watches files being modified during a coding session and provides live risk
warnings based on historical data from prior sessions. Transforms Shadow
Engine from "context provider" into "pair programmer."

Example output:
  WARNING: auth.py was modified in 8 sessions.
    Changes here break test_auth.py 75% of the time (6/8).
    Median safe change: 15 lines. Risk: MEDIUM (0.72 - shrink 40%).

Uses existing session_files, session_test_results, and Bayesian predictions.
Zero new data sources required.
"""

from __future__ import annotations

import json
from typing import Any


class LiveMonitor:
    """Real-time file monitoring with historical risk warnings.

    Queries session_files, session_test_results, and approach_efficacy
    tables to provide live warnings during a coding session.

    Call watch(files) whenever an agent starts modifying files.
    """

    RISK_THRESHOLDS = {
        "HIGH": 0.65,
        "MEDIUM": 0.35,
        "LOW": 0.0,
    }

    def __init__(self, store: Any):
        self.store = store
        self._watched_files: set[str] = set()
        self._warnings_shown: set[str] = set()

    def watch(self, files: list[str]) -> list[dict[str, Any]]:
        """Monitor a set of files and generate risk warnings.

        Args:
            files: List of file paths the agent is about to modify.

        Returns:
            List of warning dicts, one per file that triggered a warning.
        """
        warnings: list[dict[str, Any]] = []

        for file_path in files:
            if file_path in self._warnings_shown:
                continue

            risk = self.check_file(file_path)
            if risk["risk_score"] >= self.RISK_THRESHOLDS["LOW"]:
                self._warnings_shown.add(file_path)
                warnings.append(risk)

        self._watched_files.update(files)
        return warnings

    def check_file(self, file_path: str) -> dict[str, Any]:
        """Analyze a single file's historical risk profile.

        Returns a dict with:
        - file_path: str
        - risk_score: float (0.0-1.0)
        - risk_label: str (HIGH/MEDIUM/LOW)
        - modification_count: int — how many sessions touched this file
        - test_break_rate: float — proportion of sessions where tests broke
        - median_change_lines: int — median lines changed in successful sessions
        - top_broken_tests: list[str] — test names most commonly broken
        - recommendation: str — actionable guidance
        - shrinkage: float — how much the Bayesian prior influenced the estimate
        """
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return self._empty_risk(file_path)

        # How many sessions touched this file?
        sessions = conn.execute(
            "SELECT DISTINCT session_id FROM session_files WHERE file_path=?",
            (file_path,),
        ).fetchall()
        session_ids = [r["session_id"] for r in sessions]
        n = len(session_ids)

        if n < 2:
            return {
                "file_path": file_path,
                "risk_score": 0.25,
                "risk_label": "LOW",
                "modification_count": n,
                "test_break_rate": 0.0,
                "median_change_lines": 0,
                "top_broken_tests": [],
                "recommendation": f"Only {n} prior session(s) — insufficient data for confident risk assessment.",
                "shrinkage": 1.0,
            }

        # Count successes vs failures
        sid_ph = ",".join("?" * len(session_ids))
        outcomes = conn.execute(
            f"SELECT outcome, COUNT(*) as cnt FROM sessions WHERE session_id IN ({sid_ph}) GROUP BY outcome",
            session_ids,
        ).fetchall()

        failures = sum(r["cnt"] for r in outcomes if r["outcome"] != "success")
        successes = n - failures

        # Bayesian risk: Beta(1+successes, 1+failures)
        alpha = 1 + successes
        beta = 1 + failures
        risk_score = beta / (alpha + beta)
        shrinkage = (alpha + beta - 2) / (alpha + beta)

        # Test break rate
        test_sessions = 0
        test_failure_count = 0
        broken_test_names: list[str] = []

        for sid in session_ids:
            tr = conn.execute(
                "SELECT results_json FROM session_test_results WHERE session_id=?",
                (sid,),
            ).fetchone()
            if tr and tr["results_json"]:
                try:
                    res = json.loads(tr["results_json"])
                    if res.get("total", 0) > 0:
                        test_sessions += 1
                        if res.get("failed", 0) > 0:
                            test_failure_count += 1
                            # Look for individual test names
                            test_names = res.get("test_names", [])
                            for t in test_names:
                                if not t.get("passed", True):
                                    broken_test_names.append(t.get("name", "unknown"))
                except Exception:
                    pass

        test_break_rate = test_failure_count / test_sessions if test_sessions > 0 else 0.0

        # Top broken tests (unique, sorted by frequency)
        from collections import Counter
        top_tests = [name for name, _ in Counter(broken_test_names).most_common(5)]

        # Risk label
        risk_label = (
            "HIGH" if risk_score >= self.RISK_THRESHOLDS["HIGH"]
            else "MEDIUM" if risk_score >= self.RISK_THRESHOLDS["MEDIUM"]
            else "LOW"
        )

        # Recommendation
        if risk_label == "HIGH":
            recommendation = (
                f"High risk — run all related tests immediately. "
                f"This file has caused test failures in {test_failure_count}/{test_sessions} sessions ({(test_break_rate * 100):.0f}%)."
            )
        elif risk_label == "MEDIUM":
            recommendation = (
                f"Medium risk — verify tests pass before committing. "
                f"Most failures are in {top_tests[:3] if top_tests else 'related tests'}."
            )
        else:
            recommendation = (
                f"Low risk — standard testing workflow should suffice. "
                f"Only {failures}/{n} sessions failed."
            )

        return {
            "file_path": file_path,
            "risk_score": round(risk_score, 2),
            "risk_label": risk_label,
            "modification_count": n,
            "test_break_rate": round(test_break_rate, 2),
            "median_change_lines": 15,  # Placeholder — needs actual diff data
            "top_broken_tests": top_tests,
            "recommendation": recommendation,
            "shrinkage": round(shrinkage, 2),
            "raw_successes": successes,
            "raw_failures": failures,
        }

    def generate_warnings_text(self, files: list[str]) -> str:
        """Generate human-readable warning text for injection into prompts."""
        warnings = self.watch(files)
        if not warnings:
            return ""

        high = [w for w in warnings if w["risk_label"] == "HIGH"]
        medium = [w for w in warnings if w["risk_label"] == "MEDIUM"]

        lines = ["### ⚠️ Live Risk Warnings", ""]

        for w in high:
            lines.append(f"- 🔴 **HIGH RISK**: `{w['file_path']}`")
            lines.append(f"  Modified in {w['modification_count']} sessions. "
                        f"Tests break {w['test_break_rate']:.0%} of the time "
                        f"({w['raw_failures']}/{w['modification_count']}).")
            if w.get("top_broken_tests"):
                for test in w["top_broken_tests"][:3]:
                    lines.append(f"  ↳ `{test}` commonly breaks")
            lines.append(f"  Recommendation: {w['recommendation']}")
            lines.append("")

        for w in medium:
            lines.append(f"- 🟡 **MEDIUM RISK**: `{w['file_path']}`")
            lines.append(f"  Modified in {w['modification_count']} sessions. "
                        f"Tests break {w['test_break_rate']:.0%} of the time.")
            if w.get("top_broken_tests"):
                tests_str = ", ".join(f"`{t}`" for t in w["top_broken_tests"][:2])
                lines.append(f"  Commonly breaks: {tests_str}")
            lines.append(f"  Recommendation: {w['recommendation']}")
            lines.append("")

        if not high and not medium:
            lines.append("- 🟢 All watched files have low historical risk. Proceed normally.")
            lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset warnings for a new session."""
        self._watched_files.clear()
        self._warnings_shown.clear()

    def _empty_risk(self, file_path: str) -> dict[str, Any]:
        return {
            "file_path": file_path,
            "risk_score": 0.0,
            "risk_label": "UNKNOWN",
            "modification_count": 0,
            "test_break_rate": 0.0,
            "median_change_lines": 0,
            "top_broken_tests": [],
            "recommendation": "No historical data available for this file.",
            "shrinkage": 1.0,
            "raw_successes": 0,
            "raw_failures": 0,
        }