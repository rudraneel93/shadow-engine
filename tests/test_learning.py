"""Tests for Learning Engine — session ingestion, pattern extraction, efficacy tracking."""

import tempfile
from pathlib import Path

from shadow_engine.knowledge_graph.models import (
    AgentOutcome,
    SessionRecord,
)
from shadow_engine.knowledge_graph.store import KnowledgeGraphStore
from shadow_engine.learning.engine import LearningEngine


class TestLearningEngine:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = KnowledgeGraphStore(Path(self.tmpdir) / "test_learn")
        self.engine = LearningEngine(self.store)

    def test_ingest_successful_session(self):
        session = SessionRecord(
            session_id="sess-001",
            repository="test",
            prompt="fix the login bug in auth service",
            approach="Targeted Fix",
            model="claude-sonnet",
            outcome=AgentOutcome.SUCCESS,
            files_changed=["src/auth.py", "tests/test_auth.py"],
            test_results={"total": 8, "passed": 8, "failed": 0},
            duration_seconds=45.0,
            token_count=7000,
        )
        result = self.engine.ingest_session(session)
        assert result["status"] == "ingested"
        assert result["problem_type"] == "bug_fix"
        assert result["was_successful"] is True
        assert len(result["patterns_learned"]) >= 1

    def test_ingest_failed_session(self):
        session = SessionRecord(
            session_id="sess-002",
            repository="test",
            prompt="refactor the entire billing system",
            approach="Clean Sweep",
            model="claude-opus",
            outcome=AgentOutcome.FAILURE,
            files_changed=[f"src/billing/{i}.py" for i in range(15)],
            test_results={"total": 20, "passed": 8, "failed": 12},
            duration_seconds=300.0,
            token_count=25000,
        )
        result = self.engine.ingest_session(session)
        assert result["status"] == "ingested"
        assert result["was_successful"] is False
        assert "failure_analysis" in result
        assert len(result["failure_analysis"]["potential_reasons"]) >= 1

    def test_ingest_rejected_session(self):
        session = SessionRecord(
            session_id="sess-003",
            repository="test",
            prompt="add caching layer",
            approach="Extensible Design",
            model="sonnet",
            outcome=AgentOutcome.REJECTED,
            review_comments=["This doesn't follow our patterns", "Needs better error handling"],
        )
        result = self.engine.ingest_session(session)
        assert result["status"] == "ingested"
        assert "failure_analysis" in result

    def test_ingest_in_progress_skipped(self):
        session = SessionRecord(
            session_id="sess-004",
            repository="test",
            prompt="still working",
            outcome=AgentOutcome.IN_PROGRESS,
        )
        result = self.engine.ingest_session(session)
        assert result["status"] == "skipped"

    def test_problem_type_classification(self):
        tests = [
            ("fix the bug in auth", "bug_fix"),
            ("error crashing on login", "bug_fix"),
            ("add a search feature", "feature"),
            ("implement new endpoint", "feature"),
            ("create the dashboard widget", "feature"),
            ("refactor the billing module", "refactor"),
            ("clean up old code", "refactor"),
            ("improve performance of queries", "refactor"),
            ("write tests for auth service", "testing"),
            ("add test coverage for billing", "testing"),
            ("migrate from flask to fastapi", "migration"),
            ("upgrade django to 5.0", "migration"),
            ("document the API endpoints", "documentation"),
            ("add comments to complex functions", "documentation"),
            ("investigate something weird", "general"),
        ]
        for prompt, expected in tests:
            result_type, confidence = self.engine._classify_problem_type(prompt)
            assert result_type == expected, \
                f"Expected '{prompt}' -> '{expected}', got '{result_type}' (confidence: {confidence:.2f})"
            assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range"

    def test_approach_suggestion_no_data(self):
        result = self.engine.suggest_approach("fix a bug")
        assert result["problem_type"] == "bug_fix"
        assert result["suggestion"] == "no_historical_data"
        assert result["confidence"] == 0.0

    def test_approach_suggestion_with_data(self):
        # Feed in several successful sessions for bug fixes with a specific approach
        for i in range(5):
            session = SessionRecord(
                session_id=f"sess-bug-{i}",
                repository="test",
                prompt=f"fix bug #{i}",
                approach="Targeted Fix",
                model="sonnet",
                outcome=AgentOutcome.SUCCESS,
                duration_seconds=30.0,
                token_count=5000,
            )
            self.engine.ingest_session(session)

        # Feed in some failures with a different approach
        for i in range(3):
            session = SessionRecord(
                session_id=f"sess-bad-{i}",
                repository="test",
                prompt=f"fix bug #{i}",
                approach="Aggressive Rewrite",
                model="opus",
                outcome=AgentOutcome.FAILURE,
                duration_seconds=120.0,
                token_count=15000,
            )
            self.engine.ingest_session(session)

        result = self.engine.suggest_approach("fix the authentication bug")
        assert result["problem_type"] == "bug_fix"
        assert result["suggestion"] == "historical_best"
        assert result["recommended_approach"] == "Targeted Fix"
        assert result["expected_success_rate"] == 1.0
        assert result["best_model"] == "sonnet"

    def test_improvement_report(self):
        # Feed in sessions, then generate a report
        for i in range(3):
            session = SessionRecord(
                session_id=f"sess-rpt-{i}",
                repository="test",
                prompt="add feature",
                approach="Extensible Design",
                outcome=AgentOutcome.SUCCESS if i < 2 else AgentOutcome.FAILURE,
            )
            self.engine.ingest_session(session)

        report = self.engine.get_improvement_report()
        assert "SHADOW ENGINEER" in report
        assert "Knowledge Graph Health" in report
        assert "Agent Performance" in report

    def test_pattern_extraction_from_sessions(self):
        session = SessionRecord(
            session_id="sess-pat",
            repository="test",
            prompt="fix the login bug",
            approach="Targeted Fix",
            outcome=AgentOutcome.SUCCESS,
            files_changed=["src/auth.py", "tests/test_auth.py"],
            test_results={"total": 10, "passed": 10, "failed": 0},
            review_comments=["LGTM! Clean PR."],
        )
        result = self.engine.ingest_session(session)
        pattern_types = {p["type"] for p in result["patterns_learned"]}
        assert "testing" in pattern_types
        assert "change_scope" in pattern_types

    def test_batch_ingestion(self):
        variants = [
            {
                "session_id": "batch-1",
                "prompt": "fix auth bug",
                "approach": "Targeted Fix",
                "model": "sonnet",
                "outcome": "success",
                "files_changed": ["auth.py", "test_auth.py"],
                "test_results": {"passed": 10, "failed": 0},
                "duration_seconds": 30.0,
                "token_count": 5000,
            },
            {
                "session_id": "batch-2",
                "prompt": "fix auth bug",
                "approach": "Defense in Depth",
                "model": "opus",
                "outcome": "success",
                "files_changed": ["auth.py", "middleware.py", "test_auth.py"],
                "test_results": {"passed": 10, "failed": 0},
                "duration_seconds": 60.0,
                "token_count": 9000,
            },
        ]

        result = self.engine.ingest_batch_results("batch-001", variants, "my-repo")
        assert result["variants_ingested"] == 2