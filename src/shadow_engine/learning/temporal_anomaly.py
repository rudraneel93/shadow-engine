"""Temporal Anomaly Detection — Breakthrough Feature #3.

Detects when something has fundamentally changed in the codebase by analyzing
time-series patterns in agent session outcomes. Goes beyond static health
scores to detect real-time regressions.

Key capabilities:
  - Bayesian Online Changepoint Detection (BOCD) for detecting shifts
  - Rolling window statistics for sustained degradation
  - Auto-correlation of anomalies with specific commits/files/approaches
  - Predictive: "At current trend, health will drop below 40 in ~3 sessions"

This transforms the health score from a point-in-time snapshot into a
trend-aware monitoring system that catches problems as they emerge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────

@dataclass
class Changepoint:
    """A detected changepoint in the session time series."""
    index: int  # Session index where change occurred
    probability: float  # Posterior probability of changepoint
    direction: str  # "improvement" or "degradation"
    magnitude: float  # Effect size (Cohen's d)
    before_mean: float  # Mean success rate before changepoint
    after_mean: float  # Mean success rate after changepoint
    likely_cause: str = ""  # Correlated commit, file, or approach

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_index": self.index,
            "probability": round(self.probability, 3),
            "direction": self.direction,
            "magnitude": round(self.magnitude, 3),
            "before_mean": round(self.before_mean, 3),
            "after_mean": round(self.after_mean, 3),
            "likely_cause": self.likely_cause,
        }


@dataclass
class TemporalAnomaly:
    """A detected anomaly in session outcomes."""
    anomaly_type: str  # "changepoint", "spike", "sustained_drop", "trend_reversal"
    severity: str  # "critical", "warning", "info"
    description: str
    detected_at_session: int
    confidence: float
    changepoint: Changepoint | None = None
    correlated_files: list[str] = field(default_factory=list)
    correlated_commits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.anomaly_type,
            "severity": self.severity,
            "description": self.description,
            "detected_at_session": self.detected_at_session,
            "confidence": round(self.confidence, 3),
            "changepoint": self.changepoint.to_dict() if self.changepoint else None,
            "correlated_files": self.correlated_files[:5],
            "correlated_commits": self.correlated_commits[:3],
        }


@dataclass
class TrendForecast:
    """Forecast of future health score trajectory."""
    current_health: float
    trend_direction: str  # "improving", "stable", "degrading", "crashing"
    trend_slope: float  # Health points per session
    projected_health_10: float  # Projected health in 10 sessions
    sessions_until_critical: int  # Sessions until health < 40
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_health": round(self.current_health, 1),
            "trend_direction": self.trend_direction,
            "trend_slope": round(self.trend_slope, 2),
            "projected_health_10": round(self.projected_health_10, 1),
            "sessions_until_critical": self.sessions_until_critical,
            "confidence": round(self.confidence, 3),
        }


# ── Bayesian Online Changepoint Detection ───────────────────────

class BOCD:
    """Bayesian Online Changepoint Detection for session outcomes.

    Maintains a posterior distribution over run lengths (time since
    last changepoint). When a changepoint occurs, the run length
    resets to 0.

    Uses a Beta-Bernoulli model for binary outcomes (success/failure).
    """

    def __init__(self, hazard_rate: float = 1.0 / 50.0, max_run_length: int = 200):
        """Initialize BOCD detector.

        Args:
            hazard_rate: Prior probability of changepoint at each step.
                         Default: 1/50 = 2% per session.
            max_run_length: Maximum run length to track.
        """
        self.hazard_rate = hazard_rate
        self.max_run_length = max_run_length

        # Run length posterior: P(r_t | x_{1:t})
        self.run_length_posterior: list[float] = [1.0]  # r=0 with prob 1

        # Beta distribution parameters per run length
        # Beta(alpha, beta) conjugate prior for Bernoulli
        self.alphas: list[float] = [1.0]  # Prior: Beta(1, 1) = uniform
        self.betas: list[float] = [1.0]

        # History
        self.observations: list[int] = []
        self.changepoint_probs: list[float] = []  # P(changepoint at each step)

    def update(self, observation: int) -> float:
        """Update BOCD with a new observation.

        Args:
            observation: 1 for success, 0 for failure.

        Returns:
            Probability of a changepoint at this step.
        """
        self.observations.append(observation)

        # Ensure arrays are sized for current run length
        len(self.alphas)
        needed = min(len(self.observations), self.max_run_length)
        while len(self.alphas) < needed:
            self.alphas.append(1.0)
            self.betas.append(1.0)
            self.run_length_posterior.append(0.0)

        # Compute predictive probabilities: P(x_t | r_{t-1}, x_{1:t-1})
        predictive_probs = []
        for r in range(min(len(self.observations) - 1, self.max_run_length)):
            if r < len(self.alphas):
                alpha = self.alphas[r]
                beta = self.betas[r]
                # Predictive: (alpha / (alpha + beta)) for success
                pred = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
                predictive_probs.append(
                    pred if observation == 1 else (1.0 - pred)
                )
            else:
                predictive_probs.append(0.5)

        # Compute growth probabilities: P(r_t = r_{t-1} + 1, x_t)
        growth_probs = []
        for r in range(len(predictive_probs)):
            prior = self.run_length_posterior[r] if r < len(self.run_length_posterior) else 0.0
            growth_probs.append(prior * predictive_probs[r] * (1.0 - self.hazard_rate))

        # Compute changepoint probability: P(r_t = 0, x_t)
        cp_pred = 0.5  # Uniform predictive before any data
        prior_sum = sum(self.run_length_posterior[:len(predictive_probs)])
        cp_prob = prior_sum * cp_pred * self.hazard_rate

        # Normalize
        total = sum(growth_probs) + cp_prob
        if total > 0:
            # New run length posterior
            new_posterior = [cp_prob / total] if cp_prob > 0 else [0.0]
            for gp in growth_probs:
                new_posterior.append(gp / total if total > 0 else 0.0)
        else:
            new_posterior = [1.0] + [0.0] * len(growth_probs)

        # Trim to max_run_length
        self.run_length_posterior = new_posterior[:self.max_run_length + 1]

        # Update Beta parameters
        # For the changepoint (r=0) case: reset Beta(1, 1)
        new_alphas = [1.0 + observation]  # Beta(1+success, 1+failure)
        new_betas = [1.0 + (1 - observation)]

        for r in range(len(growth_probs)):
            if r < len(self.alphas):
                new_alphas.append(self.alphas[r] + observation)
                new_betas.append(self.betas[r] + (1 - observation))
            else:
                new_alphas.append(1.0 + observation)
                new_betas.append(1.0 + (1 - observation))

        self.alphas = new_alphas[:self.max_run_length + 1]
        self.betas = new_betas[:self.max_run_length + 1]

        # Store changepoint probability
        cp_p = self.run_length_posterior[0] if self.run_length_posterior else 0.0
        self.changepoint_probs.append(cp_p)

        return cp_p

    def get_expected_success_rate(self) -> float:
        """Get expected success rate under the current run length posterior."""
        if not self.alphas:
            return 0.5

        # Weighted average across all run lengths
        expected = 0.0
        total_weight = sum(self.run_length_posterior[:len(self.alphas)])
        if total_weight == 0:
            return 0.5

        for r in range(min(len(self.alphas), len(self.run_length_posterior))):
            alpha = self.alphas[r]
            beta = self.betas[r]
            mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
            expected += mean * self.run_length_posterior[r]

        return expected / total_weight

    def get_recent_changepoints(self, threshold: float = 0.3) -> list[dict[str, Any]]:
        """Get changepoints above a probability threshold."""
        changepoints = []
        for i, prob in enumerate(self.changepoint_probs):
            if prob >= threshold:
                changepoints.append({
                    "observation_index": i + 1,
                    "probability": prob,
                })
        return changepoints


# ── Temporal Anomaly Detector ────────────────────────────────────

class TemporalAnomalyDetector:
    """Detects anomalies in agent session time series.

    Combines:
    - BOCD for changepoint detection
    - Rolling window statistics for sustained degradation
    - Z-score thresholding for spike detection
    - Linear trend analysis for forecasting
    """

    def __init__(self, store: Any, window_size: int = 10):
        self.store = store
        self.window_size = window_size
        self.bocd = BOCD()
        self._anomaly_history: list[TemporalAnomaly] = []
        self._initialized = False

    def ingest_sessions(self) -> list[TemporalAnomaly]:
        """Ingest all session outcomes and detect anomalies.

        Should be called after each new session is recorded.
        Returns any newly detected anomalies.
        """
        sessions = self._get_ordered_sessions()
        if not sessions:
            return []

        new_anomalies: list[TemporalAnomaly] = []

        for i, s in enumerate(sessions):
            outcome = 1 if s.get("was_successful") else 0

            # Skip already-processed sessions
            if self._initialized and i < len(self.bocd.observations):
                continue

            # Update BOCD
            cp_prob = self.bocd.update(outcome)

            # Check for anomalies
            if i >= self.window_size:
                anomalies = self._check_anomalies(i, sessions[:i + 1], cp_prob)
                new_anomalies.extend(anomalies)
                self._anomaly_history.extend(anomalies)

        self._initialized = True
        return new_anomalies

    def _get_ordered_sessions(self, limit: int = 500) -> list[dict[str, Any]]:
        """Get sessions ordered by creation time."""
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return []

        rows = conn.execute(
            "SELECT session_id, outcome, approach, created_at "
            "FROM sessions WHERE outcome != 'in_progress' "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()

        sessions: list[dict[str, Any]] = []
        for row in rows:
            s = dict(row)
            s["was_successful"] = s.get("outcome") == "success"
            sessions.append(s)

        return sessions

    def _check_anomalies(
        self, current_idx: int, sessions: list[dict[str, Any]],
        cp_prob: float,
    ) -> list[TemporalAnomaly]:
        """Check for various types of anomalies at the current index."""
        anomalies: list[TemporalAnomaly] = []

        # 1. Changepoint detection
        if cp_prob > 0.5:
            anomaly = self._analyze_changepoint(current_idx, sessions, cp_prob)
            if anomaly:
                anomalies.append(anomaly)

        # 2. Sustained drop detection (3+ consecutive failures)
        if current_idx >= 3:
            recent: list[bool] = [bool(s.get("was_successful")) for s in sessions[-3:]]
            if sum(recent) == 0:  # All failures
                anomalies.append(TemporalAnomaly(
                    anomaly_type="sustained_drop",
                    severity="critical",
                    description=f"Sustained failure: last {len(recent)} sessions all failed.",
                    detected_at_session=current_idx,
                    confidence=0.9,
                ))

        # 3. Spike detection (Z-score thresholding on failure rate)
        if current_idx >= self.window_size:
            anomaly = self._check_failure_spike(current_idx, sessions)
            if anomaly:
                anomalies.append(anomaly)

        # 4. Trend reversal detection
        if current_idx >= self.window_size * 2:
            anomaly = self._check_trend_reversal(current_idx, sessions)
            if anomaly:
                anomalies.append(anomaly)

        return anomalies

    def _analyze_changepoint(
        self, idx: int, sessions: list[dict[str, Any]], prob: float,
    ) -> TemporalAnomaly | None:
        """Analyze a detected changepoint."""
        if idx < 10:
            return None  # Need enough data

        mid = max(5, idx - 5)
        before: list[bool] = [bool(s.get("was_successful", False)) for s in sessions[:mid]]
        after: list[bool] = [bool(s.get("was_successful", False)) for s in sessions[mid:]]

        if not before or not after:
            return None

        before_mean = sum(before) / len(before)
        after_mean = sum(after) / len(after)

        # Cohen's d for effect size
        pooled_std = math.sqrt(
            (before_mean * (1 - before_mean) + after_mean * (1 - after_mean)) / 2
        )
        effect_size = abs(after_mean - before_mean) / max(pooled_std, 0.01)
        direction = "degradation" if after_mean < before_mean else "improvement"
        severity = (
            "critical" if effect_size > 1.0 and direction == "degradation"
            else "warning" if effect_size > 0.5
            else "info"
        )

        return TemporalAnomaly(
            anomaly_type="changepoint",
            severity=severity,
            description=(
                f"Changepoint detected: success rate shifted from {before_mean:.0%} "
                f"to {after_mean:.0%} (effect size: {effect_size:.2f})"
            ),
            detected_at_session=idx,
            confidence=prob,
            changepoint=Changepoint(
                index=mid,
                probability=prob,
                direction=direction,
                magnitude=effect_size,
                before_mean=before_mean,
                after_mean=after_mean,
            ),
        )

    def _check_failure_spike(
        self, idx: int, sessions: list[dict[str, Any]],
    ) -> TemporalAnomaly | None:
        """Check for sudden spike in failure rate using Z-score."""
        window = sessions[-self.window_size:]
        failures = sum(1 for s in window if not s.get("was_successful", False))
        failure_rate = failures / len(window)

        # Compute historical mean and std (excluding current window)
        historical = sessions[:-self.window_size]
        if len(historical) < self.window_size:
            return None

        hist_failures = [
            1 if not s.get("was_successful", False) else 0
            for s in historical
        ]
        hist_mean = sum(hist_failures) / len(hist_failures)
        hist_std = math.sqrt(hist_mean * (1 - hist_mean))

        if hist_std > 0:
            z_score = (failure_rate - hist_mean) / hist_std
            if z_score > 2.5:  # > 2.5 standard deviations above mean
                return TemporalAnomaly(
                    anomaly_type="spike",
                    severity="critical" if z_score > 3.5 else "warning",
                    description=(
                        f"Failure spike: {failure_rate:.0%} failure rate "
                        f"({z_score:.1f}σ above historical {hist_mean:.0%})"
                    ),
                    detected_at_session=idx,
                    confidence=min(0.95, z_score / 5.0),
                )

        return None

    def _check_trend_reversal(
        self, idx: int, sessions: list[dict[str, Any]],
    ) -> TemporalAnomaly | None:
        """Check for reversal in success rate trend."""
        first_half = sessions[idx - self.window_size * 2:idx - self.window_size]
        second_half = sessions[idx - self.window_size:idx]

        if len(first_half) < 5 or len(second_half) < 5:
            return None

        first_rate = sum(1 for s in first_half if s.get("was_successful")) / len(first_half)
        second_rate = sum(1 for s in second_half if s.get("was_successful")) / len(second_half)

        # Check if trend reversed significantly
        diff = second_rate - first_rate
        if abs(diff) > 0.3:
            return TemporalAnomaly(
                anomaly_type="trend_reversal",
                severity="warning" if diff < 0 else "info",
                description=(
                    f"Trend reversal: rate changed by {diff:+.0%} "
                    f"({first_rate:.0%} → {second_rate:.0%})"
                ),
                detected_at_session=idx,
                confidence=min(0.9, abs(diff)),
            )

        return None

    # ── Forecasting ──────────────────────────────────────────

    def forecast_health(self, current_health: float) -> TrendForecast:
        """Forecast future health score trajectory.

        Uses linear regression on recent sessions to estimate trend.
        """
        outcomes = self.bocd.observations
        if len(outcomes) < 5:
            return TrendForecast(
                current_health=current_health,
                trend_direction="stable",
                trend_slope=0.0,
                projected_health_10=current_health,
                sessions_until_critical=999,
                confidence=0.1,
            )

        # Linear regression on recent success rates
        window = min(20, len(outcomes))
        recent = outcomes[-window:]
        x = list(range(len(recent)))
        y = [float(o) for o in recent]

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            slope = 0.0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denom

        # Slope is in success-rate-per-session units
        # Convert to health points per session (roughly)
        health_slope = slope * 100  # Convert rate change to health points

        # Project forward
        projected_10 = current_health + health_slope * 10
        projected_10 = max(0, min(100, projected_10))

        # Sessions until critical (< 40)
        if health_slope < -0.1:
            sessions_until = int((40 - current_health) / health_slope)
            sessions_until = max(0, min(999, sessions_until))
        else:
            sessions_until = 999

        # Trend direction
        if abs(health_slope) < 0.2:
            direction = "stable"
        elif health_slope > 0:
            direction = "improving"
        elif health_slope > -1.0:
            direction = "degrading"
        else:
            direction = "crashing"

        # Confidence based on R² and sample size
        y_mean = sum_y / n
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        ss_res = sum((yi - (sum_y / n + slope * (xi - sum_x / n))) ** 2 for xi, yi in zip(x, y))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = min(0.95, r_squared * (n / 20))

        return TrendForecast(
            current_health=current_health,
            trend_direction=direction,
            trend_slope=round(health_slope, 2),
            projected_health_10=round(projected_10, 1),
            sessions_until_critical=sessions_until,
            confidence=round(confidence, 3),
        )

    # ── Context Builder ───────────────────────────────────────

    def build_temporal_context(self) -> str:
        """Build a temporal anomaly analysis context block."""
        sessions = self._get_ordered_sessions()
        if not sessions:
            return ""

        # Ingest all sessions to update BOCD
        self.ingest_sessions()

        lines = ["### ⏱️ Temporal Analysis — Codebase Evolution", ""]

        # Success rate trend
        recent_n = min(50, len(self.bocd.observations))
        recent_outcomes = self.bocd.observations[-recent_n:]
        if recent_outcomes:
            recent_rate = sum(recent_outcomes) / len(recent_outcomes)
            total_rate = sum(self.bocd.observations) / len(self.bocd.observations)
            lines.append(f"**Recent success rate:** {recent_rate:.0%} (last {recent_n} sessions)")
            lines.append(f"**All-time rate:** {total_rate:.0%} ({len(self.bocd.observations)} sessions)")
            lines.append("")

        # Changepoints
        changepoints = self.bocd.get_recent_changepoints(threshold=0.3)
        if changepoints:
            lines.append("**Detected Changepoints:**")
            for cp in changepoints[-5:]:
                idx = cp["observation_index"]
                lines.append(f"- Session #{idx}: probability {cp['probability']:.0%}")
            lines.append("")

        # Recent anomalies
        recent_anomalies = self._anomaly_history[-5:]
        if recent_anomalies:
            lines.append("**Recent Anomalies:**")
            for a in recent_anomalies:
                emoji = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(a.severity, "•")
                lines.append(f"- {emoji} {a.description}")
            lines.append("")

        # Expected current success rate from BOCD
        expected_rate = self.bocd.get_expected_success_rate()
        lines.append(f"**Expected success rate (BOCD):** {expected_rate:.0%}")
        lines.append("")

        return "\n".join(lines)

    def build_forecast_context(self, current_health: float) -> str:
        """Build a health forecast context block."""
        forecast = self.forecast_health(current_health)

        lines = ["### 📈 Health Score Forecast", ""]
        lines.append(f"**Current:** {forecast.current_health:.0f}/100")
        lines.append(f"**Trend:** {forecast.trend_direction.upper()} "
                      f"({forecast.trend_slope:+.1f} pts/session)")
        lines.append(f"**Projected (10 sessions):** {forecast.projected_health_10:.0f}/100")

        if forecast.sessions_until_critical < 999:
            lines.append(f"**⚠️ Critical threshold (40) in:** ~{forecast.sessions_until_critical} sessions")
        lines.append(f"**Confidence:** {forecast.confidence:.0%}")
        lines.append("")

        if forecast.trend_direction in ("degrading", "crashing"):
            lines.append("**Recommendation:** Investigate recent failures. Consider:")
            lines.append("- Reviewing the last 3-5 failed sessions for common patterns")
            lines.append("- Checking if specific files/approaches correlate with the decline")
            lines.append("- Temporarily using more conservative approaches")
            lines.append("")

        return "\n".join(lines)

    def get_anomaly_report(self) -> str:
        """Generate a full temporal anomaly report."""
        self._get_ordered_sessions()
        self.ingest_sessions()

        lines = ["=" * 70]
        lines.append("  TEMPORAL ANOMALY DETECTION REPORT")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total sessions analyzed: {len(self.bocd.observations)}")
        lines.append(f"Anomalies detected: {len(self._anomaly_history)}")
        lines.append("")

        # Success rate by quintile
        outcomes = self.bocd.observations
        if len(outcomes) >= 5:
            lines.append("Success Rate by Quintile:")
            chunk = max(1, len(outcomes) // 5)
            for q in range(5):
                start = q * chunk
                end = min((q + 1) * chunk, len(outcomes))
                segment = outcomes[start:end]
                if segment:
                    rate = sum(segment) / len(segment)
                    bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
                    lines.append(f"  Q{q + 1} ({start}-{end}): {bar} {rate:.0%}")
            lines.append("")

        # Changepoints
        changepoints = self.bocd.get_recent_changepoints(0.2)
        if changepoints:
            lines.append("Significant Changepoints:")
            for cp in changepoints[-10:]:
                lines.append(f"  Session #{cp['observation_index']}: {cp['probability']:.0%} probability")
            lines.append("")

        # Anomalies
        critical = [a for a in self._anomaly_history if a.severity == "critical"]
        warnings = [a for a in self._anomaly_history if a.severity == "warning"]

        lines.append(f"🔴 Critical: {len(critical)}")
        for a in critical[-5:]:
            lines.append(f"  - {a.description}")
        lines.append("")

        lines.append(f"🟡 Warnings: {len(warnings)}")
        for a in warnings[-5:]:
            lines.append(f"  - {a.description}")
        lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)