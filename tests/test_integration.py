"""Integration tests: Full pipeline from bootstrap through learning.

Covers #6 (SQLite backend tests) and #10 (full integration test).
"""

from pathlib import Path

import pytest

from shadow_engine.main import ShadowEngine
from shadow_engine.knowledge_graph.models import (
    AgentOutcome, Symbol, SymbolKind, SessionRecord,
)
from shadow_engine.knowledge_graph.store import KnowledgeGraphStore
from shadow_engine.learning.engine import LearningEngine

# Try to import SQLite store for backend tests
try:
    from shadow_engine.sqlite_store.db import SQLiteStore
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False


class TestFullPipeline:
    """#10: End-to-end integration test — bootstrap → search → context → record → suggest → report."""

    def test_bootstrap_search_context_flow(self, tmp_path: Path):
        """Create a multi-file project, bootstrap, search, and generate context."""
        # Create a realistic project structure
        (tmp_path / "src" / "auth").mkdir(parents=True)
        (tmp_path / "src" / "billing").mkdir(parents=True)
        (tmp_path / "tests").mkdir(parents=True)

        (tmp_path / "src" / "auth" / "service.py").write_text(
            'def authenticate_user(token: str) -> dict:\n'
            '    """Validate JWT token and return user info."""\n'
            '    return {"id": 1, "role": "admin"}\n\n'
            'class AuthMiddleware:\n'
            '    """Middleware that checks authentication headers."""\n'
            '    def process(self, request):\n'
            '        pass\n'
        )
        (tmp_path / "src" / "billing" / "invoice.py").write_text(
            'def calculate_total(items: list) -> float:\n'
            '    """Sum line items with tax."""\n'
            '    return sum(item.price for item in items) * 1.08\n'
        )
        (tmp_path / "tests" / "test_auth.py").write_text(
            'def test_authenticate_user():\n'
            '    assert authenticate_user("valid") == {"id": 1}\n'
        )

        engine = ShadowEngine(storage_path=tmp_path / ".shadow-engine", repo_path=tmp_path)
        result = engine.bootstrap()

        # Bootstrap succeeded
        assert result["symbols_indexed"] >= 3
        assert result["files_indexed"] >= 3
        assert result["status"] == "bootstrapped"

        # Search finds symbols
        auth_results = engine.search("authenticate")
        assert len(auth_results) >= 1
        assert any(r["name"] == "authenticate_user" for r in auth_results)

        # Context generation
        ctx = engine.get_context("fix the authentication token validation")
        assert "authenticate_user" in ctx
        assert "AuthMiddleware" in ctx

        # Impact analysis
        impact = engine.impact("authenticate_user")
        assert "error" not in impact
        assert impact["symbol"]["name"] == "authenticate_user"

    def test_record_and_learn_flow(self, tmp_path: Path):
        """Record sessions and verify learning compounds."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text(
            'def login(user: str, pwd: str) -> bool:\n'
            '    """Authenticate a user."""\n'
            '    return user == "admin"\n'
        )

        engine = ShadowEngine(storage_path=tmp_path / ".shadow-engine", repo_path=tmp_path)
        engine.bootstrap()

        # Initially no historical data
        suggestion = engine.suggest("fix a login bug")
        assert suggestion["suggestion"] == "no_historical_data"

        # Record successful sessions for bug fixes with "Targeted Fix"
        for i in range(5):
            engine.record_result(
                session_id=f"sess-{i}",
                outcome="success",
                prompt=f"fix login bug #{i}",
                approach="Targeted Fix",
                model="sonnet",
                files_changed=["src/auth.py", "tests/test_auth.py"],
                test_results={"total": 8, "passed": 8, "failed": 0},
                duration_seconds=30.0,
                token_count=5000,
            )

        # Record failures for "Aggressive Rewrite"
        for i in range(3):
            engine.record_result(
                session_id=f"bad-{i}",
                outcome="failure",
                prompt=f"fix login bug #{i}",
                approach="Aggressive Rewrite",
                model="opus",
                files_changed=[f"src/module{i}.py" for i in range(12)],
                test_results={"total": 10, "passed": 4, "failed": 6},
                duration_seconds=120.0,
                token_count=20000,
            )

        # Now suggestion should recommend "Targeted Fix"
        suggestion = engine.suggest("fix the authentication bug")
        assert suggestion["suggestion"] == "historical_best"
        assert suggestion["recommended_approach"] == "Targeted Fix"
        assert suggestion["expected_success_rate"] == 1.0
        assert suggestion["best_model"] == "sonnet"
        assert suggestion["classification_confidence"] > 0.8  # "fix" + "bug" = 0.95

        # Report should reflect the data
        report = engine.get_report()
        assert "75.0%" in report or "83.3%" in report or "success" in report.lower()

        # Stats
        stats = engine.get_stats()
        assert stats["total_sessions"] >= 8
        assert stats["successful_sessions"] >= 5

    def test_experiment_batch_flow(self, tmp_path: Path):
        """Create an experiment batch and verify scoring."""
        engine = ShadowEngine(storage_path=tmp_path / ".shadow-engine", repo_path=tmp_path)

        batch = engine.experiment("fix the login bug", num_variants=3)
        assert batch["total_variants"] == 3
        assert batch["completed"] == 0
        assert len(batch["variants"]) == 3

        # Bug fix should use bug_fix strategies
        names = {v["name"] for v in batch["variants"]}
        assert "Targeted Fix" in names


class TestSQLiteStore:
    """#6: Tests for the production SQLite backend."""

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_store_initialization(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        stats = store.get_stats()
        assert stats["total_symbols"] == 0
        assert stats["total_sessions"] == 0
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_upsert_and_get_symbol(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        sym = Symbol(
            id="test-sym-1", name="hello", kind=SymbolKind.FUNCTION,
            file_path="test.py", line_start=1, line_end=5,
            signature="def hello():", docstring="Say hello.",
        )
        store.upsert_symbol(sym)
        retrieved = store.get_symbol("test-sym-1")
        assert retrieved is not None
        assert retrieved.name == "hello"
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_upsert_file(self, tmp_path: Path):
        """Verify upsert_file works (was the missing method)."""
        from shadow_engine.knowledge_graph.models import FileSummary

        store = SQLiteStore(tmp_path / "test.db")
        fs = FileSummary(path="src/main.py", language=".py", line_count=50,
                        imports=["os", "sys"])
        store.upsert_file(fs)

        retrieved = store.get_file("src/main.py")
        assert retrieved is not None
        assert retrieved.language == ".py"
        assert retrieved.line_count == 50
        assert "os" in retrieved.imports
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_search_symbols(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        for name, kind in [("auth_user", SymbolKind.FUNCTION), ("login", SymbolKind.FUNCTION), ("billing_total", SymbolKind.FUNCTION)]:
            store.upsert_symbol(Symbol(
                id=f"id-{name}", name=name, kind=kind,
                file_path=f"src/{name}.py", line_start=1, line_end=5,
            ))

        results = store.search_symbols("auth")
        assert len(results) == 1
        assert results[0].name == "auth_user"
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_record_and_get_session(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        session = SessionRecord(
            session_id="sess-sqlite-1", repository="test", prompt="Fix bug",
            approach="Targeted", model="sonnet", outcome=AgentOutcome.SUCCESS,
            files_changed=["a.py", "b.py"],
            test_results={"total": 5, "passed": 5, "failed": 0},
            duration_seconds=30.0, token_count=5000,
        )
        store.record_session(session)
        retrieved = store.get_session("sess-sqlite-1")
        assert retrieved is not None
        assert retrieved.was_successful is True
        assert retrieved.files_changed == ["a.py", "b.py"]
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_approach_efficacy_tracking(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        ae = store.update_approach_efficacy(
            problem_type="bug_fix", approach="Targeted", was_successful=True,
            model="sonnet", duration_seconds=30.0, token_count=5000,
        )
        assert ae.success_rate == 1.0

        ae = store.update_approach_efficacy(
            problem_type="bug_fix", approach="Targeted", was_successful=False,
            model="opus", duration_seconds=60.0, token_count=10000,
        )
        assert ae.success_rate == 0.5

        best = store.get_best_approaches(problem_type="bug_fix", min_attempts=1)
        assert len(best) >= 1
        assert best[0].approach == "Targeted"
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_persistence_across_instances(self, tmp_path: Path):
        """Verify data survives store re-creation."""
        db_path = tmp_path / "persist.db"

        store1 = SQLiteStore(db_path)
        sym = Symbol(id="persist-sym", name="persist_me", kind=SymbolKind.FUNCTION,
                    file_path="test.py", line_start=1, line_end=5)
        store1.upsert_symbol(sym)
        store1.close()

        store2 = SQLiteStore(db_path)
        retrieved = store2.get_symbol("persist-sym")
        assert retrieved is not None
        assert retrieved.name == "persist_me"
        store2.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_build_context(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        store.upsert_symbol(Symbol(
            id="ctx-sym", name="authenticate", kind=SymbolKind.FUNCTION,
            file_path="src/auth.py", line_start=1, line_end=10,
            signature="def authenticate(token: str) -> User:",
            docstring="Authenticate a user from a JWT token.",
        ))
        store.learn_pattern(
            pattern_type="error_handling", description="Use 401 for auth failures",
            examples=["src/auth.py"], source_session_id="sess-1",
        )

        ctx = store.build_context_for_prompt("Fix authenticate bug")
        assert "authenticate" in ctx
        assert "Use 401" in ctx
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_learn_patterns(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        store.learn_pattern(
            pattern_type="testing", description="Write tests alongside code",
            examples=["a.py", "b.py"], source_session_id="sess-1",
        )
        patterns = store.get_patterns_by_type("testing")
        assert len(patterns) == 1
        assert patterns[0].description == "Write tests alongside code"
        store.close()

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_impact_radius(self, tmp_path: Path):
        store = SQLiteStore(tmp_path / "test.db")
        sym_a = Symbol(id="a", name="A", kind=SymbolKind.FUNCTION, file_path="a.py", line_start=1, line_end=5, dependencies=[])
        sym_b = Symbol(id="b", name="B", kind=SymbolKind.FUNCTION, file_path="b.py", line_start=1, line_end=5, dependencies=["a"])
        sym_c = Symbol(id="c", name="C", kind=SymbolKind.FUNCTION, file_path="c.py", line_start=1, line_end=5, dependencies=["b"])
        for s in [sym_a, sym_b, sym_c]:
            store.upsert_symbol(s)

        impacted = store.get_impact_radius("a", depth=3)
        names = {s.name for s in impacted}
        assert "A" in names and "B" in names and "C" in names
        store.close()


class TestLearningEngineProtocol:
    """#8: LearningEngine works with both JSON store and SQLite store."""

    def test_engine_with_json_store(self, tmp_path: Path):
        store = KnowledgeGraphStore(tmp_path / "test_json")
        engine = LearningEngine(store)
        session = SessionRecord(
            session_id="sess-protocol", repository="test", prompt="fix bug",
            outcome=AgentOutcome.SUCCESS,
        )
        result = engine.ingest_session(session)
        assert result["status"] == "ingested"
        assert result["problem_type"] == "bug_fix"
        assert result["classification_confidence"] > 0.8

    @pytest.mark.skipif(not SQLITE_AVAILABLE, reason="SQLite store not available")
    def test_engine_with_sqlite_store(self, tmp_path: Path):
        """Verify LearningEngine works with SQLiteStore via duck typing."""
        store = SQLiteStore(tmp_path / "test.db")
        engine = LearningEngine(store)
        session = SessionRecord(
            session_id="sess-sql-protocol", repository="test", prompt="fix error",
            outcome=AgentOutcome.SUCCESS,
        )
        result = engine.ingest_session(session)
        assert result["status"] == "ingested"
        assert result["problem_type"] == "bug_fix"
        store.close()


class TestOpenInspectBridge:
    """#11: Bridge creates and reuses engines properly."""

    def test_bridge_initialization(self, tmp_path: Path):
        """Bridge initializes without error."""
        from shadow_engine.integrations.openinspect import OpenInspectBridge
        bridge = OpenInspectBridge(repo_path=tmp_path, storage_path=tmp_path / ".shadow")
        bridge.bootstrap_if_needed()
        # Bridge stats is sync on the underlying engine
        stats = bridge.engine.get_stats()
        assert "total_symbols" in stats

    def test_create_enrich_ingest_hooks(self, tmp_path: Path):
        """Hook factories return callables."""
        from shadow_engine.integrations.openinspect import create_enrich_hook, create_ingest_hook
        enrich = create_enrich_hook(repo_path=tmp_path)
        ingest = create_ingest_hook(repo_path=tmp_path)
        assert callable(enrich)
        assert callable(ingest)