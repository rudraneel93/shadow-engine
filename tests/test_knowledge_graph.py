"""Tests for Knowledge Graph — models, indexer, and store."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shadow_engine.knowledge_graph.models import (
    AgentOutcome,
    ApproachEfficacy,
    CodePattern,
    FileSummary,
    KnowledgeSnapshot,
    SessionRecord,
    Symbol,
    SymbolKind,
)
from shadow_engine.knowledge_graph.indexer import (
    CodebaseIndexer,
    _COMPILED_PATTERNS,
    SUPPORTED_EXTENSIONS,
    compute_file_hash,
)
from shadow_engine.knowledge_graph.store import KnowledgeGraphStore


# ── Models Tests ──────────────────────────────────────────────────

class TestSymbolModel:
    def test_symbol_creation(self):
        sym = Symbol(
            id="abc123",
            name="test_function",
            kind=SymbolKind.FUNCTION,
            file_path="src/test.py",
            line_start=10,
            line_end=25,
        )
        assert sym.name == "test_function"
        assert sym.kind == SymbolKind.FUNCTION
        assert sym.dependencies == []
        assert sym.complexity_score == 0.0

    def test_symbol_id_computation(self):
        sid = Symbol.compute_id("src/auth.py", "login")
        assert len(sid) == 16
        # Same inputs = same ID (deterministic)
        sid2 = Symbol.compute_id("src/auth.py", "login")
        assert sid == sid2
        # Different inputs = different ID
        sid3 = Symbol.compute_id("src/auth.py", "logout")
        assert sid != sid3

    def test_symbol_with_dependencies(self):
        sym = Symbol(
            id="dep123",
            name="ServiceClass",
            kind=SymbolKind.CLASS,
            file_path="src/service.py",
            line_start=1,
            line_end=50,
            dependencies=["abc123", "def456"],
            dependents=["ghi789"],
            complexity_score=12.5,
        )
        assert len(sym.dependencies) == 2
        assert sym.complexity_score == 12.5


class TestFileSummaryModel:
    def test_file_summary_defaults(self):
        fs = FileSummary(path="src/main.py", language=".py")
        assert fs.summary == ""
        assert fs.symbols == []
        assert fs.line_count == 0

    def test_file_summary_with_symbols(self):
        fs = FileSummary(
            path="src/main.py",
            language=".py",
            symbols=["sym1", "sym2"],
            line_count=100,
            exported_symbols=["public_func"],
        )
        assert len(fs.symbols) == 2
        assert fs.exported_symbols == ["public_func"]


class TestSessionRecordModel:
    def test_session_success(self):
        s = SessionRecord(
            session_id="sess-001",
            repository="my-repo",
            prompt="Fix bug",
            approach="Targeted Fix",
            model="claude-sonnet",
            outcome=AgentOutcome.SUCCESS,
        )
        assert s.was_successful is True

    def test_session_failure(self):
        s = SessionRecord(
            session_id="sess-002",
            repository="my-repo",
            prompt="Add feature",
            outcome=AgentOutcome.FAILURE,
        )
        assert s.was_successful is False

    def test_session_in_progress(self):
        s = SessionRecord(
            session_id="sess-003",
            repository="my-repo",
            prompt="Refactor",
            outcome=AgentOutcome.IN_PROGRESS,
        )
        assert s.was_successful is False


class TestApproachEfficacy:
    def test_new_approach_zero_attempts(self):
        ae = ApproachEfficacy(
            problem_type="bug_fix",
            approach="Targeted Fix",
        )
        assert ae.success_rate == 0.0
        assert ae.total_attempts == 0

    def test_approach_with_data(self):
        ae = ApproachEfficacy(
            problem_type="feature",
            approach="Extensible Design",
            total_attempts=10,
            successes=8,
        )
        assert ae.success_rate == 0.8


class TestCodePattern:
    def test_pattern_compute_id(self):
        pid = CodePattern.compute_id("error_handling", "auth errors return 401")
        assert len(pid) == 16


class TestKnowledgeSnapshot:
    def test_snapshot_compute_id(self):
        dt = datetime(2026, 5, 3, tzinfo=timezone.utc)
        sid = KnowledgeSnapshot.compute_id("my-repo", dt)
        assert len(sid) == 16


# ── Indexer Tests ──────────────────────────────────────────────────

class TestCodebaseIndexer:
    def test_supported_extensions(self):
        """Verify we support all expected languages."""
        assert ".py" in SUPPORTED_EXTENSIONS
        assert ".py" in _COMPILED_PATTERNS
        assert ".ts" in SUPPORTED_EXTENSIONS
        assert ".tsx" in SUPPORTED_EXTENSIONS
        assert ".js" in SUPPORTED_EXTENSIONS
        assert ".go" in SUPPORTED_EXTENSIONS
        assert ".rs" in SUPPORTED_EXTENSIONS

    def test_index_python_file(self, tmp_path: Path):
        """Index a simple Python file and verify symbol extraction."""
        py_file = tmp_path / "test_module.py"
        py_file.write_text('''
def hello_world():
    """Say hello to the world."""
    return "Hello, World!"

class Calculator:
    """A simple calculator class."""
    
    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
''')

        indexer = CodebaseIndexer(tmp_path)
        symbols, files = indexer.index()

        # Should find 3 symbols: hello_world (function), Calculator (class), add (method)
        assert len(symbols) >= 3, f"Expected >= 3 symbols, got {len(symbols)}"

        # Check specific symbols
        symbol_names = {s.name for s in symbols.values()}
        assert "hello_world" in symbol_names
        assert "Calculator" in symbol_names
        assert "add" in symbol_names

        # Verify file was indexed
        assert "test_module.py" in files

    def test_index_typescript_file(self, tmp_path: Path):
        """Index a TypeScript file."""
        ts_file = tmp_path / "component.ts"
        ts_file.write_text('''
export function formatDate(date: Date): string {
    return date.toISOString();
}

export interface UserData {
    id: string;
    name: string;
}

export class UserService {
    async getUser(id: string): Promise<UserData> {
        return { id, name: "test" };
    }
}
''')

        indexer = CodebaseIndexer(tmp_path)
        symbols, files = indexer.index()

        symbol_names = {s.name for s in symbols.values()}
        assert "formatDate" in symbol_names
        assert "UserData" in symbol_names
        assert "UserService" in symbol_names

    def test_skips_node_modules(self, tmp_path: Path):
        """Verify node_modules and other skip dirs are excluded."""
        nm_dir = tmp_path / "node_modules" / "lib"
        nm_dir.mkdir(parents=True)
        (nm_dir / "skipped.ts").write_text("export const x = 1;")

        real_file = tmp_path / "real.py"
        real_file.write_text("def foo(): pass")

        indexer = CodebaseIndexer(tmp_path)
        _, files = indexer.index()

        file_paths = list(files.keys())
        assert "real.py" in file_paths
        # node_modules files should not appear
        assert not any("node_modules" in f for f in file_paths)

    def test_skips_non_code_files(self, tmp_path: Path):
        """Verify images, lock files, etc. are skipped."""
        (tmp_path / "image.png").write_text("fake png")
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "real.py").write_text("def foo(): pass")

        indexer = CodebaseIndexer(tmp_path)
        _, files = indexer.index()

        file_paths = list(files.keys())
        assert "real.py" in file_paths
        assert "image.png" not in file_paths
        # .json is not in supported extensions
        assert "data.json" not in file_paths

    def test_compute_file_hash(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        h1 = compute_file_hash(f)
        assert len(h1) == 64  # SHA-256

        # Same content = same hash
        f.write_text("print('hello')")
        h2 = compute_file_hash(f)
        assert h1 == h2

        # Different content = different hash
        f.write_text("print('world')")
        h3 = compute_file_hash(f)
        assert h1 != h3

    def test_index_go_file(self, tmp_path: Path):
        go_file = tmp_path / "main.go"
        go_file.write_text('''
package main

type Server struct {
    Port int
}

func (s *Server) Start() error {
    return nil
}

type Handler interface {
    Handle(req Request) Response
}
''')

        indexer = CodebaseIndexer(tmp_path)
        symbols, _ = indexer.index()

        names = {s.name for s in symbols.values()}
        assert len(names) >= 2

    def test_index_rust_file(self, tmp_path: Path):
        rs_file = tmp_path / "lib.rs"
        rs_file.write_text('''
pub fn calculate_score(metrics: &Metrics) -> f64 {
    metrics.sum() / metrics.count() as f64
}

pub struct Config {
    pub port: u16,
    pub workers: u32,
}

pub trait Service {
    fn start(&self) -> Result<(), Error>;
}
''')

        indexer = CodebaseIndexer(tmp_path)
        symbols, _ = indexer.index()

        names = {s.name for s in symbols.values()}
        assert len(names) >= 3


# ── Store Tests ────────────────────────────────────────────────────

class TestKnowledgeGraphStore:
    @pytest.fixture
    def store(self, tmp_path: Path):
        """Create a temporary store for testing."""
        store = KnowledgeGraphStore(tmp_path / "test_store")
        yield store
        # Cleanup
        import shutil
        if (tmp_path / "test_store").exists():
            shutil.rmtree(tmp_path / "test_store", ignore_errors=True)

    def test_store_initialization(self, store: KnowledgeGraphStore):
        stats = store.get_stats()
        assert stats["total_symbols"] == 0
        assert stats["total_files"] == 0
        assert stats["total_sessions"] == 0

    def test_upsert_and_get_symbol(self, store: KnowledgeGraphStore):
        sym = Symbol(
            id="test-sym-1",
            name="hello",
            kind=SymbolKind.FUNCTION,
            file_path="test.py",
            line_start=1,
            line_end=5,
            signature="def hello():",
            docstring="Say hello.",
        )
        store.upsert_symbol(sym)

        retrieved = store.get_symbol("test-sym-1")
        assert retrieved is not None
        assert retrieved.name == "hello"
        assert retrieved.docstring == "Say hello."

    def test_search_symbols(self, store: KnowledgeGraphStore):
        sym1 = Symbol(id="s1", name="authenticate_user", kind=SymbolKind.FUNCTION, file_path="auth.py", line_start=1, line_end=10)
        sym2 = Symbol(id="s2", name="login_handler", kind=SymbolKind.FUNCTION, file_path="views.py", line_start=1, line_end=10)
        sym3 = Symbol(id="s3", name="calculate_tax", kind=SymbolKind.FUNCTION, file_path="billing.py", line_start=1, line_end=10)

        for sym in [sym1, sym2, sym3]:
            store.upsert_symbol(sym)

        # Search by name
        results = store.search_symbols("authenticate")
        assert len(results) == 1
        assert results[0].name == "authenticate_user"

        # Search by docstring (sym1 has none, so only name match)
        results = store.search_symbols("login")
        assert len(results) >= 1

        # Filter by kind
        results = store.search_symbols("calculate", kind="function")
        assert len(results) == 1
        assert results[0].name == "calculate_tax"

    def test_symbol_dependencies(self, store: KnowledgeGraphStore):
        sym_a = Symbol(id="a", name="A", kind=SymbolKind.FUNCTION, file_path="a.py", line_start=1, line_end=5, dependencies=["b"])
        sym_b = Symbol(id="b", name="B", kind=SymbolKind.FUNCTION, file_path="b.py", line_start=1, line_end=5)

        store.upsert_symbol(sym_b)
        store.upsert_symbol(sym_a)

        deps = store.get_symbol_dependencies("a")
        assert len(deps) == 1
        assert deps[0].name == "B"

        dependents = store.get_symbol_dependents("b")
        assert len(dependents) == 1
        assert dependents[0].name == "A"

    def test_impact_radius(self, store: KnowledgeGraphStore):
        # Build: C depends on B depends on A
        sym_a = Symbol(id="a", name="A", kind=SymbolKind.FUNCTION, file_path="a.py", line_start=1, line_end=5, dependencies=[])
        sym_b = Symbol(id="b", name="B", kind=SymbolKind.FUNCTION, file_path="b.py", line_start=1, line_end=5, dependencies=["a"])
        sym_c = Symbol(id="c", name="C", kind=SymbolKind.FUNCTION, file_path="c.py", line_start=1, line_end=5, dependencies=["b"])

        for sym in [sym_a, sym_b, sym_c]:
            store.upsert_symbol(sym)

        # Changing A should impact B and C
        impacted = store.get_impact_radius("a", depth=3)
        impacted_names = {s.name for s in impacted}
        assert "A" in impacted_names
        assert "B" in impacted_names
        assert "C" in impacted_names

    def test_record_and_retrieve_session(self, store: KnowledgeGraphStore):
        session = SessionRecord(
            session_id="sess-test-1",
            repository="my-repo",
            prompt="Fix login bug",
            approach="Targeted Fix",
            model="claude-sonnet-4-6",
            outcome=AgentOutcome.SUCCESS,
            files_changed=["src/auth.py", "tests/test_auth.py"],
            test_results={"total": 10, "passed": 10, "failed": 0},
            duration_seconds=45.0,
            token_count=8500,
        )
        store.record_session(session)

        retrieved = store.get_session("sess-test-1")
        assert retrieved is not None
        assert retrieved.was_successful is True
        assert retrieved.files_changed == ["src/auth.py", "tests/test_auth.py"]

    def test_approach_efficacy_tracking(self, store: KnowledgeGraphStore):
        ae = store.update_approach_efficacy(
            problem_type="bug_fix",
            approach="Targeted Fix",
            was_successful=True,
            model="claude-sonnet",
            duration_seconds=30.0,
            token_count=5000,
        )
        assert ae.success_rate == 1.0
        assert ae.total_attempts == 1

        # Second attempt — failure
        ae = store.update_approach_efficacy(
            problem_type="bug_fix",
            approach="Targeted Fix",
            was_successful=False,
            model="claude-opus",
            duration_seconds=60.0,
            token_count=10000,
        )
        assert ae.success_rate == 0.5
        assert ae.total_attempts == 2

    def test_get_best_approaches(self, store: KnowledgeGraphStore):
        for _ in range(4):
            store.update_approach_efficacy(
                problem_type="bug_fix", approach="Good", was_successful=True,
                model="sonnet", duration_seconds=10, token_count=100,
            )
        for _ in range(4):
            store.update_approach_efficacy(
                problem_type="bug_fix", approach="Bad", was_successful=False,
                model="sonnet", duration_seconds=10, token_count=100,
            )

        best = store.get_best_approaches(problem_type="bug_fix", min_attempts=3)
        assert len(best) == 2
        # Good should be first (higher success rate)
        assert best[0].approach == "Good"
        assert best[0].success_rate == 1.0

    def test_learn_and_retrieve_patterns(self, store: KnowledgeGraphStore):
        pattern = store.learn_pattern(
            pattern_type="error_handling",
            description="Auth errors use 401 with JSON body",
            examples=["src/auth.py", "src/middleware.py"],
            source_session_id="sess-001",
        )
        assert pattern.confidence == 1.0

        patterns = store.get_patterns_by_type("error_handling")
        assert len(patterns) == 1
        assert patterns[0].description == "Auth errors use 401 with JSON body"

    def test_build_context_for_prompt(self, store: KnowledgeGraphStore):
        # Index some symbols
        sym = Symbol(
            id="auth-sym",
            name="authenticate",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth.py",
            line_start=1, line_end=10,
            signature="def authenticate(token: str) -> User:",
            docstring="Authenticate a user from a JWT token.",
        )
        store.upsert_symbol(sym)

        # Learn a pattern
        store.learn_pattern(
            pattern_type="error_handling",
            description="Auth returns 401",
            examples=["src/auth.py"],
            source_session_id="sess-001",
        )

        context = store.build_context_for_prompt("Fix the authentication bug")
        assert "authenticate" in context
        assert "Auth returns 401" in context

    def test_create_snapshot(self, store: KnowledgeGraphStore):
        snap = store.create_snapshot("test-repo")
        assert snap.snapshot_id is not None
        assert snap.repository == "test-repo"
        assert snap.total_symbols == 0

    def test_persistence(self, tmp_path: Path):
        """Verify data survives store re-creation."""
        store_path = tmp_path / "persist_test"

        # Create, add data, save
        store1 = KnowledgeGraphStore(store_path)
        sym = Symbol(id="persist-sym", name="persist_me", kind=SymbolKind.FUNCTION, file_path="test.py", line_start=1, line_end=5)
        store1.upsert_symbol(sym)

        # Re-create store — should load persisted data
        store2 = KnowledgeGraphStore(store_path)
        retrieved = store2.get_symbol("persist-sym")
        assert retrieved is not None
        assert retrieved.name == "persist_me"

    def test_session_persistence(self, tmp_path: Path):
        store_path = tmp_path / "sess_persist"

        store1 = KnowledgeGraphStore(store_path)
        session = SessionRecord(
            session_id="persist-sess",
            repository="test",
            prompt="test",
            outcome=AgentOutcome.SUCCESS,
        )
        store1.record_session(session)

        store2 = KnowledgeGraphStore(store_path)
        retrieved = store2.get_session("persist-sess")
        assert retrieved is not None
        assert retrieved.outcome == AgentOutcome.SUCCESS