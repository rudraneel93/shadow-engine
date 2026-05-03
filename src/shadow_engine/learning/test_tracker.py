"""Per-Test-Name Tracking — Deep Feature #2.

Tracks individual test names across sessions, mapping which tests break
when specific files are changed. Enables precise failure prediction:

Example output:
  "Changes to rate_limiter.py break test_rate_limit.py 85% of the time"
  "test_auth_invalid_token fails 60% of the time when auth.py is touched"
"""

from __future__ import annotations

import json
from typing import Any


class TestTracker:
    """Tracks individual test results across sessions for file-level correlation.

    Uses the session_test_results table (already storing JSON) to
    correlate specific test outcomes with file changes across sessions.
    """

    def __init__(self, store: Any):
        self.store = store

    def record_test_results(
        self,
        session_id: str,
        files_changed: list[str],
        test_results: dict[str, Any],
    ) -> None:
        """Store per-test results for a session.

        Args:
            session_id: The session identifier
            files_changed: List of files modified in this session
            test_results: Dict with 'total', 'passed', 'failed', and optional
                         'individual' — a list of {name, passed} objects
        """
        if "individual" not in test_results:
            return  # No per-test data to store

        conn = self.store._get_conn() if hasattr(self.store, '_get_conn') else None
        if conn is None:
            return

        # Store test names in a JSON array alongside existing results
        existing = conn.execute(
            "SELECT results_json FROM session_test_results WHERE session_id=?",
            (session_id,),
        ).fetchone()

        if existing and existing["results_json"]:
            try:
                current = json.loads(existing["results_json"])
            except Exception:
                current = {}
        else:
            current = {}

        # Add per-test results
        current["test_names"] = test_results["individual"]

        conn.execute(
            "INSERT OR REPLACE INTO session_test_results VALUES (?, ?)",
            (session_id, json.dumps(current)),
        )
        conn.commit()

    def get_file_test_failure_rates(
        self,
        file_path: str,
        min_sessions: int = 3,
    ) -> list[dict[str, Any]]:
        """Get test failure rates for a specific file.

        Returns list of {test_name, sessions_touching_file, failure_count, rate}.
        """
        conn = self.store._get_conn() if hasattr(self.store, '_get_conn') else None
        if conn is None:
            return []

        # Find sessions that touched this file
        sessions = conn.execute(
            "SELECT session_id FROM session_files WHERE file_path=?",
            (file_path,),
        ).fetchall()
        session_ids = [r["session_id"] for r in sessions]

        if len(session_ids) < min_sessions:
            return []

        # Collect individual test results across all sessions
        test_failures: dict[str, dict[str, int]] = {}  # test_name → {failures, total}
        for sid in session_ids:
            tr = conn.execute(
                "SELECT results_json FROM session_test_results WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not tr or not tr["results_json"]:
                continue
            try:
                results = json.loads(tr["results_json"])
                test_names = results.get("test_names", [])
                for test in test_names:
                    name = test.get("name", "unknown")
                    passed = test.get("passed", True)
                    if name not in test_failures:
                        test_failures[name] = {"failures": 0, "total": 0}
                    test_failures[name]["total"] += 1
                    if not passed:
                        test_failures[name]["failures"] += 1
            except Exception:
                continue

        # Compute failure rates
        result: list[dict[str, Any]] = []
        for test_name, counts in test_failures.items():
            if counts["total"] >= min_sessions:
                rate = counts["failures"] / counts["total"]
                result.append({
                    "test_name": test_name,
                    "sessions": counts["total"],
                    "failures": counts["failures"],
                    "failure_rate": rate,
                })

        result.sort(key=lambda x: x["failure_rate"], reverse=True)
        return result

    def build_test_risk_context(self, files: list[str]) -> str:
        """Build a context block showing which tests historically break."""
        if not files:
            return ""

        all_risky_tests: list[dict[str, Any]] = []
        seen: set[str] = set()

        for f in files[:3]:  # Top 3 files
            rates = self.get_file_test_failure_rates(f, min_sessions=2)
            for r in rates:
                if r["test_name"] not in seen and r["failure_rate"] >= 0.5:
                    seen.add(r["test_name"])
                    all_risky_tests.append(r)

        if not all_risky_tests:
            return ""

        all_risky_tests.sort(key=lambda x: x["failure_rate"], reverse=True)
        lines = ["### Test Risk by File", ""]

        for rt in all_risky_tests[:5]:
            lines.append(
                f"- `{rt['test_name']}` — fails {rt['failure_rate']:.0%} "
                f"of the time ({rt['failures']}/{rt['sessions']} sessions)"
            )

        lines.append("")
        return "\n".join(lines)