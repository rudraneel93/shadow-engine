"""Shared pytest fixtures for shadow-engine tests.

Provides:
- Synthetic session factory for multi-session validation
- Auto-enables experimental engines via SHADOW_EXPERIMENTAL=1
- Shared test repository fixture
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def create_synthetic_sessions(store, count: int = 50) -> int:
    """Populate a store with controlled synthetic session data.

    Creates sessions with known causal relationships:
    - "Targeted Fix" succeeds ~90% of the time
    - "Aggressive Rewrite" succeeds ~20% of the time
    - bug_fix tasks are easier than refactor tasks
    - Files "auth.py", "middleware.py" are high-risk (fail often)
    - Files "utils.py", "helpers.py" are low-risk

    Returns the number of sessions created.
    """
    from datetime import datetime, timezone
    import json

    conn = store._get_conn() if hasattr(store, "_get_conn") else None
    if conn is None:
        return 0

    approaches = ["Targeted Fix", "Root Cause + Guard", "Defense in Depth",
                  "Aggressive Rewrite", "Clean Sweep"]
    problem_types = ["bug_fix", "feature", "refactor", "testing", "general"]
    files_pool = ["src/auth.py", "src/middleware.py", "src/utils.py",
                  "src/helpers.py", "tests/test_auth.py", "tests/test_utils.py",
                  "src/api/routes.py", "src/models/user.py"]

    high_risk_files = {"src/auth.py", "src/middleware.py"}

    created = 0
    for i in range(count):
        session_id = f"synthetic-{i:03d}"
        problem_type = problem_types[i % len(problem_types)]

        # Assign approach with biased success rates
        approach_idx = i % len(approaches)
        approach = approaches[approach_idx]

        # Deterministic success based on approach
        if approach in ("Targeted Fix", "Root Cause + Guard"):
            success = (i % 10 != 0)  # 90% success
        elif approach == "Defense in Depth":
            success = (i % 3 != 0)   # 67% success
        elif approach == "Aggressive Rewrite":
            success = (i % 5 == 0)   # 20% success
        elif approach == "Clean Sweep":
            success = (i % 4 == 0)   # 25% success
        else:
            success = (i % 2 == 0)   # 50%

        outcome = "success" if success else "failure"

        # Assign files — high-risk files more likely with failing approaches
        num_files = 2 if success else (4 if approach == "Aggressive Rewrite" else 3)
        files_changed = []
        for j in range(num_files):
            f = files_pool[(i + j) % len(files_pool)]
            files_changed.append(f)

        # Record session
        conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, repository, prompt, approach, model, outcome, "
            "duration_seconds, token_count, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "test-repo",
             f"{problem_type} task #{i}: fix the {problem_type} issue",
             approach, "test-model", outcome,
             30.0 + i, 5000 + i * 100,
             datetime.now(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat()),
        )

        # Record files
        for f in files_changed:
            conn.execute(
                "INSERT OR REPLACE INTO session_files (session_id, file_path) VALUES (?, ?)",
                (session_id, f),
            )

        # Record test results
        total_tests = 20
        failed_tests = 0 if success else (15 if approach == "Aggressive Rewrite" else 5)
        passed_tests = total_tests - failed_tests
        conn.execute(
            "INSERT OR REPLACE INTO session_test_results "
            "(session_id, results_json) VALUES (?, ?)",
            (session_id, json.dumps({"total": total_tests, "passed": passed_tests, "failed": failed_tests})),
        )

        # Update approach efficacy
        existing = conn.execute(
            "SELECT total_attempts, successes FROM approaches WHERE approach = ? AND problem_type = ?",
            (approach, problem_type),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE approaches SET total_attempts = ?, successes = ?, "
                "avg_duration_seconds = ?, avg_tokens = ?, "
                "best_model = ?, last_used = ? "
                "WHERE approach = ? AND problem_type = ?",
                (existing["total_attempts"] + 1,
                 existing["successes"] + (1 if success else 0),
                 30.0, 5000.0, "test-model",
                 datetime.now(timezone.utc).isoformat(),
                 approach, problem_type),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO approaches "
                "(approach, problem_type, total_attempts, successes, "
                "avg_duration_seconds, avg_tokens, best_model, last_used) "
                "VALUES (?, ?, 1, ?, 30.0, 5000.0, ?, ?)",
                (approach, problem_type, 1 if success else 0,
                 "test-model", datetime.now(timezone.utc).isoformat()),
            )

        created += 1

    conn.commit()
    return created


@pytest.fixture(scope="module")
def populated_store():
    """Create a SQLite store with 50 synthetic sessions."""
    import tempfile
    from shadow_engine.sqlite_store.db import SQLiteStore

    tmpdir = tempfile.mkdtemp()
    store_path = Path(tmpdir) / "test_populated.db"
    store = SQLiteStore(store_path)
    count = create_synthetic_sessions(store, count=50)
    assert count == 50, f"Expected 50 sessions, created {count}"
    yield store

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def test_repo_path():
    """Path to a temporary test repository."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "test_repo"
        repo.mkdir()
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "__init__.py").write_text("")
        (repo / "src" / "math_utils.py").write_text(
            '"""Math utilities."""\n\n'
            "def add(a: int, b: int) -> int:\n    return a + b\n\n"
            "def multiply(a: int, b: int) -> int:\n    return a * b\n"
        )
        yield str(repo)


@pytest.fixture(scope="session")
def shadow_engine_root():
    """Path to the shadow-engine project root."""
    return str(Path(__file__).resolve().parent.parent)


@pytest.fixture(autouse=True)
def enable_experimental():
    """Enable experimental engines for all tests."""
    os.environ["SHADOW_EXPERIMENTAL"] = "1"
    yield