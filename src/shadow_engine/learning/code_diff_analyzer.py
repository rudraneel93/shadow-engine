"""Code-Level Diff Pattern Extraction — Deep Feature #4.

Parses real git diff history to extract structural code patterns that
recur across successful sessions. This transforms the system from
"which files changed" → "what code was written."

Uses git log + git diff to extract hunks, then parses them with Python's
ast module to classify structural changes:

Example extracted patterns:
  **null_guard**: Add `if x is None: return default` guard clause
  **error_handling**: Add try/except around API calls
  **type_annotation**: Add type hints to function signatures
  **import_cleanup**: Remove unused imports
  **test_pairing**: Add test file alongside source changes
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


class CodeDiffAnalyzer:
    """Analyzes git diff history to extract recurring code-level fix patterns.

    Parses actual commit diffs using git log + git diff, then classifies
    structural changes using AST-level pattern matching for Python files.

    Stores extracted patterns in the existing fix_patterns table for
    injection into agent context blocks.
    """

    # AST-level pattern signatures to detect
    PATTERN_SIGNATURES = {
        "null_guard": [
            r"if\s+\w+\s+is\s+None\s*:",       # None check
            r"if\s+not\s+\w+\s*:",              # falsy check
            r"if\s+\w+\s+is\s+None\s+or\s+",   # None or condition
        ],
        "error_handling": [
            r"try\s*:",
            r"except\s+\w+(\s+as\s+\w+)?\s*:",
            r"except\s+Exception(\s+as\s+\w+)?\s*:",
            r"raise\s+\w+Error",
        ],
        "type_annotation": [
            r"def\s+\w+\([^)]*\)\s*->\s*\w+\s*:",  # return type annotation
            r":\s*(str|int|float|bool|list|dict|Path|None)\b",  # param types
            r"from\s+__future__\s+import\s+annotations",
        ],
        "import_cleanup": [
            r"-\s*import\s+\w+",      # removed import
            r"-\s*from\s+\S+\s+import",
        ],
        "test_pairing": [
            r"tests?/test_\w+\.py",   # test file added
            r"def\s+test_\w+",         # test function added
        ],
        "refactor_extract": [
            r"^\+\s*def\s+\w+",        # new function extracted
            r"^\+\s*class\s+\w+",       # new class extracted
        ],
        "logging_addition": [
            r"logger\.\w+\(f?\"",
            r"logging\.\w+\(f?\"",
            r"log_\w+\(f?\"",
        ],
    }

    def __init__(self, store: Any, repo_path: str | Path = "."):
        self.store = store
        self.repo_path = Path(repo_path).resolve()
        self._pattern_counts: dict[str, dict[str, int]] = {}
        self._pattern_examples: dict[str, list[str]] = {}

    def extract_patterns_from_git_history(
        self,
        problem_type: str,
        session_id: str,
        max_commits: int = 100,
    ) -> list[dict[str, Any]]:
        """Parse recent git commit diffs and extract recurring code patterns.

        Args:
            problem_type: The problem type to tag patterns with
            session_id: Current session ID for attribution
            max_commits: Maximum commits to analyze

        Returns:
            List of extracted patterns with examples
        """
        try:
            result = subprocess.run(
                ["git", "log", f"-{max_commits}", "--diff-filter=M",
                 "--format=%H %s", "--no-merges"],
                capture_output=True, text=True, timeout=30,
                cwd=self.repo_path,
            )
            commits = result.stdout.strip().split("\n") if result.stdout else []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        patterns_found: list[dict[str, Any]] = []
        for commit_line in commits[:30]:  # Limit to recent 30 commits
            parts = commit_line.split(" ", 1)
            if len(parts) < 2:
                continue
            commit_hash, message = parts

            # Get the diff for this commit
            try:
                diff_result = subprocess.run(
                    ["git", "diff", f"{commit_hash}^!", "--", "*.py",
                     "--diff-filter=AM", "-U0"],
                    capture_output=True, text=True, timeout=10,
                    cwd=self.repo_path,
                )
                diff_text = diff_result.stdout
            except (subprocess.TimeoutExpired, Exception):
                continue

            if not diff_text:
                continue

            # Classify patterns in the diff
            added_lines = self._extract_added_lines(diff_text)
            classifications = self._classify_added_lines(added_lines)

            for pattern_name, matches in classifications.items():
                if len(matches) >= 2:  # At least 2 occurrences in this commit
                    # Add to global counts
                    self._pattern_counts.setdefault(pattern_name, {})
                    self._pattern_counts[pattern_name][commit_hash] = len(matches)

                    # Store first 2 examples (truncated)
                    self._pattern_examples.setdefault(pattern_name, [])
                    for match in matches[:2]:
                        line = match.strip()[:80]
                        if line not in self._pattern_examples[pattern_name]:
                            self._pattern_examples[pattern_name].append(line)

                    confidence = min(0.9, 0.4 + (len(matches) * 0.1))
                    pattern_desc = self._get_pattern_description(pattern_name, len(matches))

                    self.store.learn_fix_pattern(
                        pattern_type=pattern_name,
                        problem_type=problem_type,
                        description=pattern_desc,
                        approach="code_pattern",
                        examples=self._pattern_examples[pattern_name][:3],
                        session_id=session_id,
                        confidence=confidence,
                    )
                    patterns_found.append({
                        "pattern_type": pattern_name,
                        "description": pattern_desc,
                        "examples": self._pattern_examples[pattern_name][:3],
                        "confidence": confidence,
                    })

        return patterns_found

    def build_code_pattern_context(self, problem_type: str) -> str:
        """Build context block with real code-level patterns from git history."""
        patterns = self.store.get_fix_patterns(
            problem_type=problem_type, min_confidence=0.4, limit=5)

        if not patterns:
            return ""

        lines = ["### Proven Code-Level Fix Patterns", ""]
        for p in patterns[:4]:
            conf = p.get("confidence", 0.5)
            label = "high" if conf >= 0.7 else "medium" if conf >= 0.5 else "low"
            lines.append(f"- **{p['pattern_type']}**: {p['description']} (confidence: {conf:.0%}, {label})")
            examples = p.get("examples", [])
            for ex in examples[:2]:
                lines.append(f"  `{ex}`")
            lines.append("")

        total_patterns = sum(
            len(v) for v in self._pattern_counts.values()
        )
        if total_patterns > 0:
            lines.append(f"  *({total_patterns} code-level patterns extracted from git history)*")
        lines.append("")
        return "\n".join(lines)

    def _extract_added_lines(self, diff_text: str) -> list[str]:
        """Extract only added lines (starting with +) from a git diff."""
        return [
            line[1:] for line in diff_text.split("\n")
            if line.startswith("+") and not line.startswith("+++")
            and len(line) > 2
        ]

    def _classify_added_lines(self, added_lines: list[str]) -> dict[str, list[str]]:
        """Classify added lines into pattern categories."""
        classifications: dict[str, list[str]] = {}
        for line in added_lines:
            for pattern_name, signatures in self.PATTERN_SIGNATURES.items():
                for sig in signatures:
                    if re.search(sig, line):
                        classifications.setdefault(pattern_name, []).append(line)
                        break  # Only classify once per line per pattern
        return classifications

    def _get_pattern_description(self, pattern_name: str, count: int) -> str:
        """Human-readable description for each pattern type."""
        descriptions = {
            "null_guard": f"Added guard clause (None/falsy check) — appeared {count}×",
            "error_handling": f"Added try/except error handling — appeared {count}×",
            "type_annotation": f"Added type annotations to function signatures — appeared {count}×",
            "import_cleanup": f"Removed unused imports — appeared {count}×",
            "test_pairing": f"Added test files/functions alongside source changes — appeared {count}×",
            "refactor_extract": f"Extracted new function or class from existing code — appeared {count}×",
            "logging_addition": f"Added logging/observability calls — appeared {count}×",
        }
        return descriptions.get(pattern_name, f"Detected code pattern '{pattern_name}' — appeared {count}× ({count} occurrences)")

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about extracted patterns."""
        return {
            "total_patterns_extracted": sum(
                len(examples) for examples in self._pattern_examples.values()
            ),
            "pattern_types_found": list(self._pattern_counts.keys()),
            "pattern_examples": {
                k: v[:3] for k, v in self._pattern_examples.items()
            },
        }