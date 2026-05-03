"""Bayesian Probability Engine — Deep Feature #1.

Replaces simple proportions with proper Bayesian inference using Beta distributions.

After N sessions (S successes, F failures):
  Prior: Beta(1, 1) — uniform (maximum uncertainty)
  Posterior: Beta(1 + S, 1 + F)
  Expected probability: (1 + S) / (2 + N)
  95% credible interval: Wilson-style normal approximation

Shrinkage effect: with 0 evidence → 0.5 (maximum uncertainty).
With 5 sessions (4S, 1F) → ~71% (not 80% simple ratio).
Prevents overconfidence on small samples.
"""

from __future__ import annotations

import json
import math
from typing import Any


class BayesianPredictor:
    """Bayesian impact predictor with Beta-Binomial conjugate updating."""

    def __init__(self, store: Any):
        self.store = store
        self._prior_successes = 1.0
        self._prior_failures = 1.0

    def compute_posterior(self, successes: int, failures: int) -> dict[str, float]:
        alpha = self._prior_successes + successes
        beta_p = self._prior_failures + failures
        n = successes + failures
        expected = alpha / (alpha + beta_p) if (alpha + beta_p) > 0 else 0.5
        if n > 0:
            se = math.sqrt(expected * (1 - expected) / (n + 2))
            lower = max(0.0, expected - 1.96 * se)
            upper = min(1.0, expected + 1.96 * se)
        else:
            lower, upper = 0.0, 1.0
        shrinkage = (alpha + beta_p - 2) / (alpha + beta_p) if (alpha + beta_p) > 0 else 0.0
        return {
            "expected": expected, "lower_95": lower, "upper_95": upper,
            "alpha": alpha, "beta_param": beta_p, "effective_sample": n,
            "shrinkage_factor": shrinkage,
        }

    def predict_impact_bayesian(self, files: list[str]) -> dict[str, Any]:
        conn = self.store._get_conn() if hasattr(self.store, '_get_conn') else None
        if conn is None or not files:
            return {"risk_score": 0.5, "risk_ci": "0.00–1.00", "evidence_count": 0,
                    "confidence": "very low — no evidence", "shrinkage": 1.0}
        ph = ",".join("?" * len(files))
        sessions = conn.execute(
            f"SELECT DISTINCT session_id FROM session_files WHERE file_path IN ({ph})", files).fetchall()
        session_ids = [r["session_id"] for r in sessions]
        n = len(session_ids)
        if n == 0:
            return {"risk_score": 0.5, "risk_ci": "0.00–1.00", "evidence_count": 0,
                    "confidence": "very low — no evidence", "shrinkage": 1.0}
        sid_ph = ",".join("?" * len(session_ids))
        outcomes = conn.execute(
            f"SELECT outcome, COUNT(*) as cnt FROM sessions WHERE session_id IN ({sid_ph}) GROUP BY outcome",
            session_ids).fetchall()
        failures = sum(r["cnt"] for r in outcomes if r["outcome"] != "success")
        successes = n - failures
        posterior = self.compute_posterior(successes, failures)
        conf_label = "high" if n >= 20 else "medium" if n >= 8 else "low" if n >= 3 else "very low"
        test_failures = 0
        for sid in session_ids:
            tr = conn.execute("SELECT results_json FROM session_test_results WHERE session_id=?", (sid,)).fetchone()
            if tr and tr["results_json"]:
                try:
                    res = json.loads(tr["results_json"])
                    if res.get("failed", 0) > 0:
                        test_failures += 1
                except Exception:
                    pass
        test_posterior = self.compute_posterior(n - test_failures, test_failures)
        return {
            "risk_score": posterior["expected"],
            "risk_ci": f"{posterior['lower_95']:.2f}–{posterior['upper_95']:.2f}",
            "likelihood_of_failure": posterior["expected"],
            "test_break_likelihood": test_posterior["expected"],
            "test_break_ci": f"{test_posterior['lower_95']:.2f}–{test_posterior['upper_95']:.2f}",
            "evidence_count": n,
            "confidence": conf_label,
            "shrinkage": posterior["shrinkage_factor"],
            "raw_successes": successes, "raw_failures": failures,
        }

    def build_context_bayesian(self, files: list[str]) -> str:
        prediction = self.predict_impact_bayesian(files)
        n = prediction.get("evidence_count", 0)
        if n < 2:
            return ""
        lines = ["### Risk Assessment (Bayesian)", ""]
        risk = prediction.get("risk_score", 0.5)
        risk_label = "🔴 HIGH" if risk >= 0.65 else "🟡 MEDIUM" if risk >= 0.35 else "🟢 LOW"
        lines.append(f"- **Risk:** {risk_label} ({risk:.0%}, 95% CI: {prediction.get('risk_ci', '?')})")
        lines.append(f"- **Test break likelihood:** {prediction.get('test_break_likelihood', 0.5):.0%}")
        lines.append(f"- **Evidence:** {n} sessions ({prediction.get('raw_successes', 0)}✓, {prediction.get('raw_failures', 0)}✗)")
        lines.append(f"- **Confidence:** {prediction.get('confidence', 'unknown')} ({n} sessions)")
        shrinkage = prediction.get("shrinkage", 0)
        if shrinkage > 0.3:
            lines.append(f"- **Note:** Prior significantly influenced estimate ({shrinkage:.0%}) — collect more data")
        lines.append("")
        return "\n".join(lines)