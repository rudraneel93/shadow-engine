"""Reference Session Replay — Finds similar past sessions and replays outcomes.

When a new task is described, finds the most semantically similar past sessions
and includes their complete outcomes in the context block. Helps new agents learn
from past successes without repeating mistakes.

Uses Jaccard similarity on tokenized task descriptions against the sessions table.
"""

from __future__ import annotations

import re
from typing import Any


class SessionReplay:
    """Finds and replays the most similar past sessions for reference."""

    def __init__(self, store: Any):
        self.store = store

    def find_similar_sessions(
        self,
        task_description: str,
        problem_type: str | None = None,
        min_similarity: float = 0.2,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Find the most similar past sessions to a given task.

        Uses Jaccard similarity on tokenized task descriptions.
        """
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return []

        # Get all completed sessions
        rows = conn.execute(
            "SELECT session_id, prompt, approach, model, outcome, duration_seconds, "
            "token_count FROM sessions WHERE outcome IN ('success', 'failure') "
            "ORDER BY created_at DESC LIMIT 50"
        ).fetchall()

        if not rows:
            return []

        task_tokens = self._tokenize(task_description)
        scored: list[tuple[float, dict[str, Any]]] = []

        for row in rows:
            session_tokens = self._tokenize(row["prompt"])
            similarity = self._jaccard_similarity(task_tokens, session_tokens)

            if similarity >= min_similarity:
                # Get files changed
                files = conn.execute(
                    "SELECT file_path FROM session_files WHERE session_id=?",
                    (row["session_id"],),
                ).fetchall()
                files_list = [f["file_path"] for f in files]

                # Get test results
                test_row = conn.execute(
                    "SELECT results_json FROM session_test_results WHERE session_id=?",
                    (row["session_id"],),
                ).fetchone()

                import json
                test_results = {}
                if test_row and test_row["results_json"]:
                    try:
                        test_results = json.loads(test_row["results_json"])
                    except Exception:
                        pass

                scored.append((similarity, {
                    "session_id": row["session_id"],
                    "prompt": row["prompt"],
                    "approach": row["approach"],
                    "model": row["model"],
                    "outcome": row["outcome"],
                    "duration_seconds": row["duration_seconds"],
                    "token_count": row["token_count"],
                    "files_changed": files_list,
                    "test_results": test_results,
                    "similarity": round(similarity, 2),
                }))

        # Sort by similarity (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Filter by problem type if specified
        if problem_type:
            scored = [
                (s, d) for s, d in scored
                if problem_type in self._infer_type(d["prompt"])
            ]

        return [d for _, d in scored[:limit]]

    def build_replay_context(self, task_description: str) -> str:
        """Build a context block with similar past sessions."""
        similar = self.find_similar_sessions(task_description)
        if not similar:
            return ""

        lines = ["### Reference Sessions (Similar Past Tasks)", ""]

        for i, session in enumerate(similar, 1):
            outcome_emoji = "✅" if session["outcome"] == "success" else "❌"
            lines.append(
                f"**{i}. {outcome_emoji} {session['outcome'].upper()}** "
                f"({session['similarity']:.0%} similarity)"
            )
            lines.append(f"- **Task:** {session['prompt'][:120]}")
            lines.append(f"- **Approach:** {session['approach'] or 'default'}")
            lines.append(f"- **Model:** {session['model']} | Duration: {session['duration_seconds']:.0f}s | Tokens: {session['token_count']}")

            files = session.get("files_changed", [])
            if files:
                lines.append(f"- **Files changed ({len(files)}):** {', '.join(files[:5])}")

            test_results = session.get("test_results", {})
            if test_results:
                passed = test_results.get("passed", 0)
                failed = test_results.get("failed", 0)
                total = test_results.get("total", 0)
                if total > 0:
                    lines.append(f"- **Tests:** {passed}/{total} passed, {failed} failed")

            lines.append("")

        # Add a recommendation based on the most similar successful session
        successful = [s for s in similar if s["outcome"] == "success"]
        if successful:
            best = successful[0]
            lines.append(f"**Recommendation:** Follow the {best['approach']} approach "
                        f"with {best['model']}. Expected duration: ~{best['duration_seconds']:.0f}s.")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into a set of lowercase words."""
        return set(re.findall(r'\b[a-z]{3,}\b', text.lower()))

    @staticmethod
    def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
        """Compute Jaccard similarity between two sets."""
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _infer_type(prompt: str) -> list[str]:
        """Infer problem types from a prompt."""
        types = []
        p = prompt.lower()
        if any(w in p for w in ("bug", "fix", "error", "crash")):
            types.append("bug_fix")
        if any(w in p for w in ("feature", "add", "implement", "create")):
            types.append("feature")
        if any(w in p for w in ("refactor", "clean", "improve")):
            types.append("refactor")
        if any(w in p for w in ("test", "spec", "coverage")):
            types.append("testing")
        return types or ["general"]