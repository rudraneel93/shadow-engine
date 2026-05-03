"""Codebase Hot Zone Detection — Breakthrough Feature.

Automatic identification of files, symbols, and modules that cause
disproportionate failures. Generates a "hot zone score" for every file
based on: modification frequency × failure rate × dependency fanout.

Example output:
  🔴 main.py — 18 modifications, 4 failures (22%)
     Top failure mode: "Tests broke after orchestral changes"
     Recommendation: Add integration tests before refactoring

  🟡 sqlite_store/db.py — 12 modifications, 2 failures (17%)
     Top failure mode: "Schema migration caused data loss"
     Recommendation: Add migration tests + backup verification
"""

from __future__ import annotations

import json
from typing import Any


class HotZoneDetector:
    """Identifies high-risk files and symbols in the codebase.

    Computes a "hot zone score" for every file:
      score = w1 × mod_frequency + w2 × failure_rate + w3 × dependency_fanout

    Where:
      mod_frequency = sessions touching file / total sessions
      failure_rate = failed sessions / sessions touching file
      dependency_fanout = dependents / max_dependents (normalized)
    """

    def __init__(self, store: Any, chroma: Any = None):
        self.store = store
        self._chroma = chroma
        self._weights = (0.4, 0.4, 0.2)  # mod_freq, failure_rate, fanout

    def detect_hot_zones(
        self, min_sessions: int = 2, top_n: int = 10
    ) -> list[dict[str, Any]]:
        """Detect the hottest zones in the codebase.

        Returns list of hot zones sorted by score (highest first).
        """
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return []

        # Get total sessions for normalization
        total_sessions = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions"
        ).fetchone()["cnt"]

        if total_sessions == 0:
            return []

        # Get all files with session counts
        files = conn.execute(
            "SELECT file_path, COUNT(*) as cnt, GROUP_CONCAT(DISTINCT session_id) as sids "
            "FROM session_files GROUP BY file_path HAVING cnt >= ? "
            "ORDER BY cnt DESC",
            (min_sessions,),
        ).fetchall()

        hot_zones: list[dict[str, Any]] = []

        for f in files:
            file_path = f["file_path"]
            mod_count = f["cnt"]
            session_ids = f["sids"].split(",")

            # How many of these sessions failed?
            sid_ph = ",".join("?" * len(session_ids))
            failures = conn.execute(
                f"SELECT COUNT(*) as cnt FROM sessions "
                f"WHERE session_id IN ({sid_ph}) AND outcome != 'success'",
                session_ids,
            ).fetchone()
            fail_count = failures["cnt"] if failures else 0

            # Find what tests typically break when this file changes
            broken_tests: list[str] = []
            for sid in session_ids:
                tr = conn.execute(
                    "SELECT results_json FROM session_test_results WHERE session_id=?",
                    (sid,),
                ).fetchone()
                if tr and tr["results_json"]:
                    try:
                        res = json.loads(tr["results_json"])
                        test_names = res.get("test_names", [])
                        for t in test_names:
                            if not t.get("passed", True):
                                broken_tests.append(t.get("name", "unknown"))
                    except Exception:
                        pass

            from collections import Counter
            top_broken = [name for name, _ in Counter(broken_tests).most_common(3)]

            # Compute scores
            mod_freq = mod_count / total_sessions
            fail_rate = fail_count / mod_count if mod_count > 0 else 0

            # Get dependency fanout for symbols in this file
            symbols = conn.execute(
                "SELECT id, name FROM symbols WHERE file_path=?",
                (file_path,),
            ).fetchall()
            fanout = 0
            for sym in symbols:
                dep_rows = conn.execute(
                    "SELECT COUNT(*) as cnt FROM symbol_deps WHERE dependency_id=?",
                    (sym["id"],),
                ).fetchone()
                fanout += dep_rows["cnt"] if dep_rows else 0

            max_fanout = max(1, max(
                conn.execute(
                    "SELECT COUNT(*) as cnt FROM symbol_deps WHERE dependency_id=?",
                    (s["id"],),
                ).fetchone()["cnt"]
                for s in symbols
            )) if symbols else 1

            fanout_norm = fanout / max_fanout if max_fanout > 0 else 0
            hot_score = (
                self._weights[0] * mod_freq +
                self._weights[1] * fail_rate +
                self._weights[2] * fanout_norm
            )

            # Determine top failure mode
            failure_mode = "No specific pattern — failures distributed across sessions"
            if fail_rate >= 0.5:
                failure_mode = f"High failure rate — {fail_count}/{mod_count} sessions failed when modifying this file"
            elif fail_rate >= 0.2:
                failure_mode = "Moderate failure rate — verify tests pass before committing"
            else:
                failure_mode = "Low failure rate — standard testing should suffice"

            hot_zones.append({
                "file_path": file_path,
                "hot_score": round(hot_score, 3),
                "modification_count": mod_count,
                "failure_count": fail_count,
                "failure_rate": round(fail_rate, 2),
                "symbol_count": len(symbols),
                "fanout": fanout,
                "top_broken_tests": top_broken,
                "failure_mode": failure_mode,
                "recommendation": self._get_recommendation(
                    fail_rate, mod_count, len(symbols), fanout
                ),
            })

        hot_zones.sort(key=lambda x: x["hot_score"], reverse=True)
        return hot_zones[:top_n]

    def generate_hot_zone_report(self) -> str:
        """Generate a human-readable hot zone report."""
        zones = self.detect_hot_zones(min_sessions=2, top_n=8)
        if not zones:
            return "### Codebase Hot Zones\n\nNo session history available yet."

        lines = ["### 🔥 Codebase Hot Zones", ""]
        lines.append("Files that cause disproportionate failures — focus testing here:")
        lines.append("")

        for i, zone in enumerate(zones, 1):
            risk = zone["failure_rate"]
            emoji = "🔴" if risk >= 0.3 else "🟡" if risk >= 0.1 else "🟢"
            lines.append(
                f"{i}. {emoji} `{zone['file_path']}` "
                f"({zone['modification_count']} modifications, "
                f"{zone['failure_count']} failures, {risk:.0%})"
            )
            lines.append(f"   Hot score: {zone['hot_score']:.2f}")
            lines.append(f"   {zone['failure_mode']}")
            lines.append(f"   Recommendation: {zone['recommendation']}")
            if zone["top_broken_tests"]:
                tests_str = ", ".join(f"`{t}`" for t in zone["top_broken_tests"])
                lines.append(f"   Commonly breaks: {tests_str}")
            lines.append("")

        return "\n".join(lines)

    def _get_recommendation(
        self, fail_rate: float, mod_count: int, symbol_count: int, fanout: int
    ) -> str:
        if fail_rate >= 0.3:
            return (
                f"High risk — add integration tests. "
                f"This file has {symbol_count} symbols with {fanout} dependents. "
                f"Changes here ripple broadly."
            )
        elif fail_rate >= 0.1:
            return "Medium risk — add focused unit tests. Verify existing tests pass."
        else:
            return "Low risk — standard testing workflow should suffice."
