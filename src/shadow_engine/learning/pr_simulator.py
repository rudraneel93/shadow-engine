"""PR Outcome Simulator — Breakthrough Feature #3.

Predicts what would happen if a specific PR were merged BEFORE it's committed.
Uses historical data + Bayesian prediction + Monte Carlo simulation to answer:

  - "This PR modifies 3 files. Predicted: 2/47 tests break, CI +12s."
  - "40% chance of review rejection based on change scope."
  - "67% chance the same files need rework within 3 sessions."

Integrates with RiskGate for pre-commit simulation. Uses Monte Carlo sampling
over empirical distributions from historical session data.

Unlike simple risk scores, this produces full probability distributions:
  P(tests_break = k | files_changed = [f1, f2, f3])
  P(review_rejection | change_scope = 3, approach = "Targeted Fix")
  P(rework_needed | files = [f1, f2])
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────

@dataclass
class SimulationResult:
    """Result of a Monte Carlo PR simulation."""
    files_changed: list[str]
    approach: str
    problem_type: str

    # Test predictions
    expected_tests_broken: float = 0.0
    test_break_probability: float = 0.0  # P(any test breaks)
    broken_test_distribution: dict[int, float] = field(default_factory=dict)  # k → probability

    # Review predictions
    review_rejection_probability: float = 0.0
    expected_review_comments: float = 0.0

    # Rework predictions
    rework_probability: float = 0.0  # P(same file touched within 3 sessions)
    expected_rework_sessions: float = 0.0  # Sessions until rework needed

    # Composite risk
    overall_risk_score: float = 0.0  # 0-100
    risk_breakdown: dict[str, float] = field(default_factory=dict)

    # Confidence
    data_quality: str = "insufficient"  # "strong", "moderate", "weak", "insufficient"
    simulation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_changed": self.files_changed,
            "approach": self.approach,
            "problem_type": self.problem_type,
            "expected_tests_broken": round(self.expected_tests_broken, 1),
            "test_break_probability": round(self.test_break_probability, 3),
            "broken_test_distribution": {
                str(k): round(v, 3)
                for k, v in sorted(self.broken_test_distribution.items())[:10]
            },
            "review_rejection_probability": round(self.review_rejection_probability, 3),
            "expected_review_comments": round(self.expected_review_comments, 1),
            "rework_probability": round(self.rework_probability, 3),
            "expected_rework_sessions": round(self.expected_rework_sessions, 1),
            "overall_risk_score": round(self.overall_risk_score, 1),
            "risk_breakdown": {
                k: round(v, 1) for k, v in self.risk_breakdown.items()
            },
            "data_quality": self.data_quality,
            "simulation_count": self.simulation_count,
        }


# ── PR Outcome Simulator ─────────────────────────────────────────

class PROutcomeSimulator:
    """Monte Carlo simulator for predicting PR outcomes.

    Uses empirical distributions from historical session data to
    simulate thousands of hypothetical PR scenarios and build
    probability distributions for key outcomes.
    """

    DEFAULT_SIMULATION_COUNT = 1000

    def __init__(self, store: Any, bayesian_predictor: Any = None, test_tracker: Any = None):
        self.store = store
        self.bayesian = bayesian_predictor
        self.test_tracker = test_tracker

    def simulate_pr(
        self, files: list[str], approach: str = "", problem_type: str = "general",
        num_simulations: int = DEFAULT_SIMULATION_COUNT,
    ) -> SimulationResult:
        """Run Monte Carlo simulation for a hypothetical PR.

        Args:
            files: List of file paths the PR would modify
            approach: Intended approach/strategy
            problem_type: Classification of the task
            num_simulations: Number of Monte Carlo iterations

        Returns:
            SimulationResult with probability distributions
        """
        sessions = self._get_session_data()
        result = SimulationResult(
            files_changed=files,
            approach=approach or "unknown",
            problem_type=problem_type,
            simulation_count=num_simulations,
        )

        if len(sessions) < 5:
            result.data_quality = "insufficient"
            result.overall_risk_score = 50.0  # Neutral when no data
            return result

        # ── Compute empirical distributions ──────────────────

        # 1. File-level test breakage rates
        file_break_rates = self._compute_file_break_rates(sessions)

        # 2. Per-approach success/rejection rates
        approach_stats = self._compute_approach_stats(sessions)

        # 3. Rework probability per file
        rework_stats = self._compute_rework_stats(sessions)

        # ── Run Monte Carlo simulations ──────────────────────

        broken_tests_per_sim: list[int] = []
        review_rejections = 0
        review_comment_counts: list[int] = []
        rework_events = 0
        rework_session_counts: list[int] = []

        for _ in range(num_simulations):
            # Simulate test breakage
            total_broken = 0
            for f in files:
                break_rate = file_break_rates.get(f, file_break_rates.get("__avg__", 0.1))
                if random.random() < break_rate:
                    # How many tests break? Sample from empirical distribution
                    avg_break_count = self._get_avg_break_count(sessions, f)
                    total_broken += max(0, int(random.gauss(avg_break_count, avg_break_count * 0.5)))
            broken_tests_per_sim.append(total_broken)

            # Simulate review rejection
            rejection_prob = self._estimate_rejection_prob(
                len(files), approach, problem_type, approach_stats)
            if random.random() < rejection_prob:
                review_rejections += 1
                review_comment_counts.append(random.randint(2, 8))  # 2-8 comments on rejection
            else:
                review_comment_counts.append(random.randint(0, 3))  # 0-3 comments on acceptance

            # Simulate rework
            any_rework = False
            rework_sessions = 0
            for f in files:
                rework_rate = rework_stats.get(f, {}).get("rework_rate", 0.1)
                avg_sessions = rework_stats.get(f, {}).get("avg_sessions_to_rework", 5)
                if random.random() < rework_rate:
                    any_rework = True
                    rework_sessions = max(rework_sessions, int(random.gauss(avg_sessions, 2)))
            if any_rework:
                rework_events += 1
                rework_session_counts.append(max(1, rework_sessions))

        # ── Build result distributions ───────────────────────

        # Test breakage distribution
        break_counter = Counter(broken_tests_per_sim)
        result.broken_test_distribution = {
            k: v / num_simulations
            for k, v in sorted(break_counter.items())[:10]
        }
        result.expected_tests_broken = sum(broken_tests_per_sim) / num_simulations
        result.test_break_probability = sum(
            1 for b in broken_tests_per_sim if b > 0
        ) / num_simulations

        # Review predictions
        result.review_rejection_probability = review_rejections / num_simulations
        result.expected_review_comments = (
            sum(review_comment_counts) / num_simulations
            if review_comment_counts else 0
        )

        # Rework predictions
        result.rework_probability = rework_events / num_simulations
        result.expected_rework_sessions = (
            sum(rework_session_counts) / len(rework_session_counts)
            if rework_session_counts else 99  # No rework expected
        )

        # ── Composite risk score ─────────────────────────────

        # Weighted combination
        test_risk = min(100, result.expected_tests_broken * 10)  # 10 pts per broken test
        review_risk = result.review_rejection_probability * 100
        rework_risk = min(100, result.rework_probability * 100)
        scope_risk = min(100, len(files) * 10)  # 10 pts per file
        approach_risk = approach_stats.get(approach, {}).get("failure_rate", 0.3) * 100

        result.risk_breakdown = {
            "test_breakage": round(test_risk, 1),
            "review_rejection": round(review_risk, 1),
            "rework_likelihood": round(rework_risk, 1),
            "change_scope": round(scope_risk, 1),
            "approach_failure": round(approach_risk, 1),
        }

        result.overall_risk_score = (
            test_risk * 0.30 +
            review_risk * 0.25 +
            rework_risk * 0.15 +
            scope_risk * 0.15 +
            approach_risk * 0.15
        )

        # Data quality assessment
        result.data_quality = self._assess_data_quality(
            len(sessions), len(files), len(file_break_rates)
        )

        return result

    def _get_session_data(self, limit: int = 500) -> list[dict[str, Any]]:
        """Get session data for simulation."""
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return []

        rows = conn.execute(
            "SELECT session_id, outcome, approach, duration_seconds, token_count "
            "FROM sessions WHERE outcome != 'in_progress' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        sessions: list[dict[str, Any]] = []
        for row in rows:
            session = dict(row)
            session["was_successful"] = session.get("outcome") == "success"
            session["files_changed"] = []
            session["test_results"] = {}
            session["review_comments"] = []
            sessions.append(session)

        # Get files, test results, review comments from related tables
        for s in sessions:
            sid = s["session_id"]

            # session_files
            files_rows = conn.execute(
                "SELECT file_path FROM session_files WHERE session_id=?",
                (sid,),
            ).fetchall()
            s["files_changed"] = [f["file_path"] for f in files_rows]

            # session_test_results
            tr = conn.execute(
                "SELECT results_json FROM session_test_results WHERE session_id=?",
                (sid,),
            ).fetchone()
            if tr and tr["results_json"]:
                try:
                    import json
                    s["test_results"] = json.loads(tr["results_json"])
                except Exception:
                    pass

            # session_review_comments
            rc = conn.execute(
                "SELECT comment FROM session_review_comments WHERE session_id=?",
                (sid,),
            ).fetchall()
            s["review_comments"] = [r["comment"] for r in rc]

        return sessions

    def _compute_file_break_rates(
        self, sessions: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Compute test breakage probability per file."""
        file_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "breaks": 0})

        for s in sessions:
            had_failures = s.get("test_results", {}).get("failed", 0) > 0
            for f in s.get("files_changed", []):
                file_stats[f]["total"] += 1
                if had_failures:
                    file_stats[f]["breaks"] += 1

        rates: dict[str, float] = {}
        for f, stats in file_stats.items():
            rates[f] = stats["breaks"] / stats["total"] if stats["total"] > 0 else 0.0

        # Global average
        all_breaks = sum(stats["breaks"] for stats in file_stats.values())
        all_total = sum(stats["total"] for stats in file_stats.values())
        rates["__avg__"] = all_breaks / all_total if all_total > 0 else 0.1

        return rates

    def _compute_approach_stats(
        self, sessions: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Compute success/failure rates per approach."""
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "successes": 0, "rejections": 0}
        )

        for s in sessions:
            approach = s.get("approach", "unknown") or "unknown"
            stats[approach]["total"] += 1
            if s.get("was_successful"):
                stats[approach]["successes"] += 1
            if s.get("outcome") == "rejected":
                stats[approach]["rejections"] += 1

        for approach, data in stats.items():
            data["success_rate"] = data["successes"] / data["total"] if data["total"] > 0 else 0.0
            data["failure_rate"] = 1.0 - data["success_rate"]
            data["rejection_rate"] = data["rejections"] / data["total"] if data["total"] > 0 else 0.0

        return dict(stats)

    def _compute_rework_stats(
        self, sessions: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Compute rework probability per file.

        Tracks: when a file is modified, how often is it modified again within 3 sessions?
        """
        # Build file modification timeline
        file_timeline: dict[str, list[int]] = defaultdict(list)
        for idx, s in enumerate(sessions):
            for f in s.get("files_changed", []):
                file_timeline[f].append(idx)

        stats: dict[str, dict[str, Any]] = {}
        for f, indices in file_timeline.items():
            if len(indices) < 2:
                stats[f] = {"rework_rate": 0.0, "avg_sessions_to_rework": 99}
                continue

            rework_events = 0
            rework_gaps: list[int] = []
            for i in range(len(indices) - 1):
                gap = indices[i] - indices[i + 1]
                if gap <= 3:  # Reworked within 3 sessions
                    rework_events += 1
                    rework_gaps.append(gap)

            stats[f] = {
                "rework_rate": rework_events / (len(indices) - 1) if len(indices) > 1 else 0.0,
                "avg_sessions_to_rework": (
                    sum(rework_gaps) / len(rework_gaps) if rework_gaps else 99
                ),
            }

        return stats

    def _get_avg_break_count(
        self, sessions: list[dict[str, Any]], file_path: str,
    ) -> float:
        """Estimate average number of tests broken when this file is modified."""
        break_counts: list[int] = []
        for s in sessions:
            if file_path in s.get("files_changed", []):
                failed = s.get("test_results", {}).get("failed", 0)
                if failed > 0:
                    break_counts.append(failed)

        return sum(break_counts) / len(break_counts) if break_counts else 2.0

    def _estimate_rejection_prob(
        self, num_files: int, approach: str, problem_type: str,
        approach_stats: dict[str, dict[str, Any]],
    ) -> float:
        """Estimate probability of review rejection.

        Uses logistic-regression-like heuristic:
        - More files → higher rejection probability
        - Failed approaches → higher rejection probability
        """
        base_rate = approach_stats.get(approach, {}).get("rejection_rate", 0.15)
        scope_factor = min(1.0, num_files / 10)  # Linear up to 10 files
        return min(0.95, base_rate + scope_factor * 0.3)

    def _assess_data_quality(
        self, total_sessions: int, num_files: int, num_known_files: int,
    ) -> str:
        """Assess the quality of simulation data."""
        if total_sessions < 10:
            return "insufficient"
        if total_sessions < 30:
            return "weak"
        if num_known_files < num_files * 0.5:
            return "weak"  # Many unknown files
        return "moderate" if total_sessions < 100 else "strong"

    # ── Context Builder ───────────────────────────────────────

    def build_simulation_context(self, files: list[str], approach: str = "",
                                  problem_type: str = "general") -> str:
        """Build a simulation prediction context block for agent prompts."""
        if not files:
            return ""

        result = self.simulate_pr(files, approach, problem_type)

        lines = ["### 🔮 PR Outcome Simulation — Before You Commit", ""]

        # Files being changed
        lines.append(f"**Files:** {', '.join(f'`{f}`' for f in files[:8])}")
        if approach:
            lines.append(f"**Approach:** {approach}")
        lines.append(f"**Data quality:** {result.data_quality} ({result.simulation_count} simulations)")
        lines.append("")

        # Test predictions
        lines.append("**Test Predictions:**")
        lines.append(f"- {result.test_break_probability:.0%} chance of breaking at least one test")
        lines.append(f"- Expected broken tests: {result.expected_tests_broken:.1f}")
        if result.broken_test_distribution:
            dist_lines = []
            for k, prob in sorted(result.broken_test_distribution.items())[:5]:
                if prob > 0.01:
                    dist_lines.append(f"  {k} tests broken: {prob:.0%}")
            if dist_lines:
                lines.extend(dist_lines)
        lines.append("")

        # Review predictions
        lines.append("**Review Predictions:**")
        lines.append(f"- {result.review_rejection_probability:.0%} chance of review rejection")
        lines.append(f"- Expected review comments: {result.expected_review_comments:.1f}")
        lines.append("")

        # Rework predictions
        lines.append("**Rework Predictions:**")
        if result.rework_probability > 0:
            lines.append(f"- {result.rework_probability:.0%} chance files need rework within 3 sessions")
            lines.append(f"- Expected sessions until rework: {result.expected_rework_sessions:.0f}")
        else:
            lines.append("- No historical rework pattern for these files")
        lines.append("")

        # Risk score
        risk_emoji = "🟢" if result.overall_risk_score < 30 else "🟡" if result.overall_risk_score < 60 else "🔴"
        lines.append(f"**Overall Risk:** {risk_emoji} {result.overall_risk_score:.0f}/100")
        lines.append(f"- Test breakage: {result.risk_breakdown.get('test_breakage', 0):.0f}")
        lines.append(f"- Review rejection: {result.risk_breakdown.get('review_rejection', 0):.0f}")
        lines.append(f"- Rework likelihood: {result.risk_breakdown.get('rework_likelihood', 0):.0f}")
        lines.append("")

        return "\n".join(lines)