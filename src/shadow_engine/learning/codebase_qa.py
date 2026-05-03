"""Natural Language Codebase Q&A — Breakthrough Feature.

Answers plain-English questions about the codebase using the knowledge graph,
without requiring an LLM call. Generates responses from structured data.

Example queries:
  "How does authentication work?"
  "What's the most dangerous file?"
  "What tests should I run if I change auth.py?"
  "Who depends on UserService?"
  "What files handle rate limiting?"
"""

from __future__ import annotations

import json
import re
from typing import Any


class CodebaseQA:
    """Answers natural language questions about the codebase.

    Uses ChromaDB semantic search, session history, and pattern data
    to generate informative answers from structured data — no LLM required.
    """

    def __init__(self, store: Any, chroma: Any = None):
        self.store = store
        self._chroma = chroma

    def ask(self, question: str, repo_path: str = ".") -> str:
        """Answer a natural language question about the codebase.

        Detects question type and routes to the appropriate answer generator.
        """
        q = question.lower().strip()

        if any(w in q for w in ["how does", "how do", "explain", "what is", "describe"]):
            return self._answer_how_question(question)
        elif any(w in q for w in ["dangerous", "risky", "hot zone", "most changed", "most modified"]):
            return self._answer_danger_question(question)
        elif any(w in q for w in ["test", "tests", "testing", "break", "breaks"]):
            return self._answer_test_question(question)
        elif any(w in q for w in ["depend", "depends", "who uses", "who calls", "impact"]):
            return self._answer_dependency_question(question)
        elif any(w in q for w in ["file", "files", "module", "where is", "which file"]):
            return self._answer_file_question(question)
        elif any(w in q for w in ["pattern", "convention", "style", "approach"]):
            return self._answer_pattern_question(question)
        else:
            return self._answer_general(question)

    def _answer_how_question(self, question: str) -> str:
        """'How does X work?' — explain a topic via relevant symbols."""
        keywords = self._extract_keywords(question)
        if not keywords:
            return "I couldn't identify what you're asking about. Try using specific terms."

        symbols = self._search_symbols(" ".join(keywords), top_k=5)
        if not symbols:
            return f"I couldn't find any symbols related to: {', '.join(keywords)}"

        lines = [f"## How '{' '.join(keywords[:3])}' Works", ""]
        for sym in symbols[:5]:
            lines.append(f"### {sym['name']} (`{sym['kind']}`)")
            lines.append(f"**Location:** `{sym['file_path']}`")
            if sym.get("docstring"):
                lines.append(f"**Description:** {sym['docstring'][:200]}")
            lines.append(f"**Signature:** `{sym.get('signature', 'N/A')[:100]}`")

            deps = self._get_dependencies(sym["id"])
            if deps:
                lines.append(f"**Depends on:** {', '.join(deps[:5])}")

            dependents = self._get_dependents(sym["id"])
            if dependents:
                lines.append(f"**Used by:** {', '.join(dependents[:5])}")

            # Check session history for this symbol's file
            risk = self._get_file_risk(sym["file_path"])
            if risk and risk["modification_count"] >= 3:
                lines.append(f"**Historical note:** Modified in {risk['modification_count']} sessions. "
                           f"Tests break {risk['test_break_rate']:.0%} of the time.")

            lines.append("")

        return "\n".join(lines)

    def _answer_danger_question(self, question: str) -> str:
        """'What's the most dangerous file?' — find high-risk files."""
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return "Cannot access session history."

        # Get files sorted by modification count
        files = conn.execute(
            "SELECT file_path, COUNT(*) as cnt, GROUP_CONCAT(session_id) as sids "
            "FROM session_files GROUP BY file_path ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        if not files:
            return "No session history available yet. Run some coding sessions first."

        lines = ["## 🔴 Codebase Hot Spots", ""]
        lines.append("Files that are most frequently modified and cause failures:")
        lines.append("")

        for i, f in enumerate(files[:8], 1):
            session_ids = f["sids"].split(",")
            n = len(session_ids)
            sid_ph = ",".join("?" * len(session_ids))
            failures = conn.execute(
                f"SELECT COUNT(*) as cnt FROM sessions WHERE session_id IN ({sid_ph}) AND outcome!='success'",
                session_ids,
            ).fetchone()
            fail_count = failures["cnt"] if failures else 0
            risk = fail_count / n if n > 0 else 0
            risk_label = "🔴" if risk >= 0.3 else "🟡" if risk >= 0.1 else "🟢"

            lines.append(f"{i}. {risk_label} `{f['file_path']}` — {n} modifications, {fail_count} failures ({risk:.0%})")

        lines.append("")
        lines.append("**Recommendation:** Focus testing and refactoring on 🔴 files first.")
        return "\n".join(lines)

    def _answer_test_question(self, question: str) -> str:
        """'What tests should I run?' — find tests correlated with files."""
        keywords = self._extract_keywords(question)
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return "Cannot access session history."

        # Find files mentioned in the question
        file_matches = []
        for kw in keywords:
            rows = conn.execute(
                "SELECT DISTINCT file_path FROM session_files WHERE file_path LIKE ?",
                (f"%{kw}%",),
            ).fetchall()
            file_matches.extend(r["file_path"] for r in rows)

        if not file_matches:
            # Try semantic search
            symbols = self._search_symbols(" ".join(keywords), top_k=3)
            file_matches = [s["file_path"] for s in symbols]

        file_matches = list(set(file_matches))[:5]
        if not file_matches:
            return f"I couldn't find any files matching: {', '.join(keywords[:5])}"

        lines = ["## 🧪 Test Recommendations", ""]
        for file_path in file_matches:
            risk = self._get_file_risk(file_path)
            if risk["modification_count"] >= 2:
                lines.append(f"### `{file_path}`")
                lines.append(f"- Modified in {risk['modification_count']} sessions")
                lines.append(f"- Tests break {risk['test_break_rate']:.0%} of the time "
                           f"({risk['test_failure_count']}/{risk['modification_count']} sessions)")
                if risk.get("top_broken_tests"):
                    for test in risk["top_broken_tests"][:3]:
                        lines.append(f"  ↳ Run: `{test}`")
                lines.append(f"- Risk: {risk['risk_label']}")
                lines.append("")

        if len(file_matches) == 1 and risk["modification_count"] < 3:
            lines.append("⚠️ Limited historical data — run the full test suite to be safe.")
        elif not file_matches:
            lines.append("No historical test failure data for these files — run related tests manually.")

        return "\n".join(lines)

    def _answer_dependency_question(self, question: str) -> str:
        """'Who depends on X?' — show dependency graphs."""
        keywords = self._extract_keywords(question)
        symbols = self._search_symbols(" ".join(keywords), top_k=3)
        if not symbols:
            return f"I couldn't find any symbols matching: {', '.join(keywords[:5])}"

        lines = ["## 🔗 Dependency Analysis", ""]
        for sym in symbols[:3]:
            lines.append(f"### {sym['name']} (`{sym['file_path']}`)")
            deps = self._get_dependencies(sym["id"])
            dependents = self._get_dependents(sym["id"])
            if deps:
                lines.append(f"**Depends on:** {', '.join(deps[:10])}")
            if dependents:
                lines.append(f"**Used by:** {', '.join(dependents[:10])}")
            if not deps and not dependents:
                lines.append("No dependencies found.")
            lines.append("")
        return "\n".join(lines)

    def _answer_file_question(self, question: str) -> str:
        """'Which file handles X?' — find files by topic."""
        keywords = self._extract_keywords(question)
        symbols = self._search_symbols(" ".join(keywords), top_k=5)
        if not symbols:
            return f"I couldn't find files matching: {', '.join(keywords[:5])}"

        lines = ["## 📁 File Locations", ""]
        seen_files = set()
        for sym in symbols[:8]:
            if sym["file_path"] not in seen_files:
                seen_files.add(sym["file_path"])
                lines.append(f"- `{sym['file_path']}` — contains `{sym['name']}` ({sym['kind']})")
                if sym.get("docstring"):
                    lines.append(f"  {sym['docstring'][:120]}")
        lines.append("")
        return "\n".join(lines)

    def _answer_pattern_question(self, question: str) -> str:
        """'What conventions does this codebase follow?'"""
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return "Cannot access pattern data."

        patterns = []
        for ptype in ["testing", "change_scope", "error_handling", "code_quality"]:
            rows = conn.execute(
                "SELECT * FROM patterns WHERE pattern_type=? ORDER BY confidence DESC LIMIT 3",
                (ptype,),
            ).fetchall()
            for r in rows:
                patterns.append({"type": r["pattern_type"], "description": r["description"], "confidence": r["confidence"]})

        if not patterns:
            return "No codebase conventions learned yet. Run more sessions to extract patterns."

        lines = ["## 📐 Codebase Conventions", ""]
        for p in patterns[:8]:
            conf = p["confidence"]
            label = "high" if conf >= 0.7 else "medium" if conf >= 0.5 else "low"
            lines.append(f"- [{p['type']}] {p['description']} (confidence: {conf:.0%}, {label})")
        lines.append("")
        return "\n".join(lines)

    def _answer_general(self, question: str) -> str:
        """General question — search for relevant symbols and provide overview."""
        keywords = self._extract_keywords(question)
        symbols = self._search_symbols(" ".join(keywords), top_k=5)
        if not symbols:
            return f"I couldn't find information about: {question[:100]}"

        lines = ["## Search Results", ""]
        for sym in symbols[:5]:
            lines.append(f"- **{sym['name']}** (`{sym['kind']}`) in `{sym['file_path']}`")
            if sym.get("docstring"):
                lines.append(f"  {sym['docstring'][:150]}")
        lines.append("")
        return "\n".join(lines)

    def _search_symbols(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search for symbols in the knowledge graph."""
        if self._chroma and self._chroma.count() > 0:
            try:
                results = self._chroma.search(query, top_k=top_k)
                return [
                    {"id": s.id, "name": s.name, "kind": s.kind.value,
                     "file_path": s.file_path, "docstring": s.docstring,
                     "signature": s.signature}
                    for s, _ in results
                ]
            except Exception:
                pass
        # Fallback to SQLite search
        try:
            symbols = self.store.search_symbols(query)
            return [
                {"id": s.id, "name": s.name, "kind": s.kind.value,
                 "file_path": s.file_path, "docstring": s.docstring,
                 "signature": s.signature}
                for s in symbols[:top_k]
            ]
        except Exception:
            return []

    def _get_dependencies(self, symbol_id: str) -> list[str]:
        try:
            deps = self.store.get_symbol_dependencies(symbol_id)
            return [d.name for d in deps]
        except Exception:
            return []

    def _get_dependents(self, symbol_id: str) -> list[str]:
        try:
            deps = self.store.get_symbol_dependents(symbol_id)
            return [d.name for d in deps]
        except Exception:
            return []

    def _get_file_risk(self, file_path: str) -> dict[str, Any]:
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return {"modification_count": 0, "test_break_rate": 0, "test_failure_count": 0,
                    "risk_label": "UNKNOWN", "top_broken_tests": []}

        sessions = conn.execute(
            "SELECT DISTINCT session_id FROM session_files WHERE file_path=?",
            (file_path,),
        ).fetchall()
        session_ids = [r["session_id"] for r in sessions]
        n = len(session_ids)

        if n < 2:
            return {"modification_count": n, "test_break_rate": 0, "test_failure_count": 0,
                    "risk_label": "LOW", "top_broken_tests": []}

        sid_ph = ",".join("?" * len(session_ids))
        failures = conn.execute(
            f"SELECT COUNT(*) as cnt FROM sessions WHERE session_id IN ({sid_ph}) AND outcome!='success'",
            session_ids,
        ).fetchone()
        fail_count = failures["cnt"] if failures else 0

        # Check test results
        test_failures = 0
        broken_tests = []
        for sid in session_ids:
            tr = conn.execute(
                "SELECT results_json FROM session_test_results WHERE session_id=?",
                (sid,),
            ).fetchone()
            if tr and tr["results_json"]:
                try:
                    res = json.loads(tr["results_json"])
                    if res.get("failed", 0) > 0:
                        test_failures += 1
                        test_names = res.get("test_names", [])
                        for t in test_names:
                            if not t.get("passed", True):
                                broken_tests.append(t.get("name", "unknown"))
                except Exception:
                    pass

        from collections import Counter
        top_tests = [name for name, _ in Counter(broken_tests).most_common(5)]

        break_rate = test_failures / n if n > 0 else 0
        risk_score = fail_count / n if n > 0 else 0
        risk_label = "HIGH" if risk_score >= 0.3 else "MEDIUM" if risk_score >= 0.1 else "LOW"

        return {
            "modification_count": n,
            "test_break_rate": break_rate,
            "test_failure_count": test_failures,
            "risk_label": risk_label,
            "top_broken_tests": top_tests,
        }

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "can", "shall",
                     "to", "of", "in", "for", "on", "with", "at", "by", "from",
                     "and", "or", "not", "this", "that", "it", "its", "we", "you",
                     "they", "he", "she", "me", "him", "her", "us", "them", "my",
                     "your", "our", "their", "how", "does", "what", "which", "who",
                     "where", "when", "why", "file", "files", "test", "tests",
                     "codebase", "work", "tell", "show", "find", "explain",
                     "dangerous", "most", "risk", "change", "about"}
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        return [w for w in words if w not in stopwords][:10]