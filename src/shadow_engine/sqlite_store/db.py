"""SQLite-backed Knowledge Graph Store with WAL mode for concurrent safety.

Replaces the JSON file store. Uses SQLite in WAL mode so multiple readers
and a single writer can operate concurrently without blocking.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..knowledge_graph.models import (
    AgentOutcome,
    ApproachEfficacy,
    CodePattern,
    FileSummary,
    Symbol,
    SymbolKind,
    SessionRecord,
)


class SQLiteStore:
    """Thread-safe SQLite store for the knowledge graph.

    Uses WAL journal mode for concurrent read/write safety and connection-per-thread
    for thread safety. Designed to scale to 100K+ sessions without data loss.
    """

    SCHEMA = """
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    CREATE TABLE IF NOT EXISTS symbols (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        file_path TEXT NOT NULL,
        line_start INTEGER NOT NULL DEFAULT 0,
        line_end INTEGER NOT NULL DEFAULT 0,
        signature TEXT DEFAULT '',
        docstring TEXT DEFAULT '',
        complexity_score REAL DEFAULT 0.0,
        last_modified TEXT NOT NULL,
        first_seen TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS symbol_deps (
        symbol_id TEXT NOT NULL,
        dependency_id TEXT NOT NULL,
        PRIMARY KEY (symbol_id, dependency_id),
        FOREIGN KEY (symbol_id) REFERENCES symbols(id),
        FOREIGN KEY (dependency_id) REFERENCES symbols(id)
    );

    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        language TEXT NOT NULL,
        summary TEXT DEFAULT '',
        line_count INTEGER DEFAULT 0,
        last_indexed TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS file_imports (
        file_path TEXT NOT NULL,
        import_statement TEXT NOT NULL,
        PRIMARY KEY (file_path, import_statement),
        FOREIGN KEY (file_path) REFERENCES files(path)
    );

    CREATE TABLE IF NOT EXISTS patterns (
        id TEXT PRIMARY KEY,
        pattern_type TEXT NOT NULL,
        description TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pattern_examples (
        pattern_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        FOREIGN KEY (pattern_id) REFERENCES patterns(id)
    );

    CREATE TABLE IF NOT EXISTS pattern_sessions (
        pattern_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        FOREIGN KEY (pattern_id) REFERENCES patterns(id)
    );

    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        repository TEXT NOT NULL,
        prompt TEXT NOT NULL,
        approach TEXT DEFAULT '',
        model TEXT DEFAULT 'unknown',
        outcome TEXT NOT NULL,
        pr_url TEXT,
        duration_seconds REAL DEFAULT 0.0,
        token_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS session_files (
        session_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    );

    CREATE TABLE IF NOT EXISTS session_test_results (
        session_id TEXT PRIMARY KEY,
        results_json TEXT DEFAULT '{}',
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    );

    CREATE TABLE IF NOT EXISTS session_review_comments (
        session_id TEXT NOT NULL,
        comment TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    );

    CREATE TABLE IF NOT EXISTS approaches (
        key TEXT PRIMARY KEY,
        problem_type TEXT NOT NULL,
        approach TEXT NOT NULL,
        total_attempts INTEGER DEFAULT 0,
        successes INTEGER DEFAULT 0,
        avg_duration_seconds REAL DEFAULT 0.0,
        avg_tokens INTEGER DEFAULT 0,
        best_model TEXT DEFAULT 'unknown',
        last_used TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
    CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
    CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
    CREATE INDEX IF NOT EXISTS idx_sessions_outcome ON sessions(outcome);
    CREATE INDEX IF NOT EXISTS idx_approaches_type ON approaches(problem_type);
    CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local connection. Creates one if none exists."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Symbols ────────────────────────────────────────────────

    def upsert_symbol(self, symbol: Symbol) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO symbols
            (id, name, kind, file_path, line_start, line_end, signature, docstring,
             complexity_score, last_modified, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol.id, symbol.name, symbol.kind.value, symbol.file_path,
                symbol.line_start, symbol.line_end, symbol.signature,
                symbol.docstring, symbol.complexity_score,
                symbol.last_modified.isoformat(), symbol.first_seen.isoformat(),
            ),
        )
        conn.execute("DELETE FROM symbol_deps WHERE symbol_id = ?", (symbol.id,))
        for dep_id in symbol.dependencies:
            try:
                conn.execute("INSERT INTO symbol_deps VALUES (?, ?)", (symbol.id, dep_id))
            except sqlite3.IntegrityError:
                # Dependency symbol may not be inserted yet — will resolve on reindex
                pass
        conn.commit()

    # Fix #1: Add upsert_file() method
    def upsert_file(self, file_summary: FileSummary) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO files (path, language, summary, line_count, last_indexed)
            VALUES (?, ?, ?, ?, ?)""",
            (
                file_summary.path, file_summary.language, file_summary.summary,
                file_summary.line_count, file_summary.last_indexed.isoformat(),
            ),
        )
        conn.execute("DELETE FROM file_imports WHERE file_path = ?", (file_summary.path,))
        for imp in file_summary.imports:
            conn.execute("INSERT OR IGNORE INTO file_imports VALUES (?, ?)", (file_summary.path, imp))
        conn.commit()

    def get_file(self, path: str) -> FileSummary | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        imports = conn.execute(
            "SELECT import_statement FROM file_imports WHERE file_path = ?", (path,)
        ).fetchall()
        return FileSummary(
            path=row["path"], language=row["language"], summary=row["summary"] or "",
            line_count=row["line_count"], last_indexed=datetime.fromisoformat(row["last_indexed"]),
            imports=[i[0] for i in imports],
        )

    def get_symbol(self, symbol_id: str) -> Symbol | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
        if not row:
            return None
        return self._row_to_symbol(row)

    def search_symbols(
        self, query: str, kind: str | None = None, file_path: str | None = None
    ) -> list[Symbol]:
        conn = self._get_conn()
        sql = "SELECT * FROM symbols WHERE name LIKE ? OR signature LIKE ? OR docstring LIKE ?"
        params: list[Any] = [f"%{query}%", f"%{query}%", f"%{query}%"]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if file_path:
            sql += " AND file_path LIKE ?"
            params.append(f"%{file_path}%")
        sql += " ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, name LIMIT 50"
        params.append(query)

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_symbol_dependencies(self, symbol_id: str) -> list[Symbol]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT s.* FROM symbols s
            JOIN symbol_deps d ON s.id = d.dependency_id
            WHERE d.symbol_id = ?""",
            (symbol_id,),
        ).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_symbol_dependents(self, symbol_id: str) -> list[Symbol]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT s.* FROM symbols s
            JOIN symbol_deps d ON s.id = d.symbol_id
            WHERE d.dependency_id = ?""",
            (symbol_id,),
        ).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def get_impact_radius(self, symbol_id: str, depth: int = 2) -> list[Symbol]:
        conn = self._get_conn()
        affected: set[str] = {symbol_id}
        current = {symbol_id}
        for _ in range(depth):
            if not current:
                break
            placeholders = ",".join("?" * len(current))
            rows = conn.execute(
                f"SELECT s.id FROM symbols s JOIN symbol_deps d ON s.id = d.symbol_id WHERE d.dependency_id IN ({placeholders})",
                list(current),
            ).fetchall()
            current = {r[0] for r in rows} - affected
            affected.update(current)

        if not affected:
            return []
        placeholders = ",".join("?" * len(affected))
        rows = conn.execute(
            f"SELECT * FROM symbols WHERE id IN ({placeholders})", list(affected)
        ).fetchall()
        return [self._row_to_symbol(r) for r in rows]

    def _row_to_symbol(self, row: sqlite3.Row) -> Symbol:
        conn = self._get_conn()
        dep_rows = conn.execute(
            "SELECT dependency_id FROM symbol_deps WHERE symbol_id = ?", (row["id"],)
        ).fetchall()
        return Symbol(
            id=row["id"],
            name=row["name"],
            kind=SymbolKind(row["kind"]),
            file_path=row["file_path"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            signature=row["signature"],
            docstring=row["docstring"] or "",
            dependencies=[r[0] for r in dep_rows],
            complexity_score=row["complexity_score"],
            last_modified=datetime.fromisoformat(row["last_modified"]),
            first_seen=datetime.fromisoformat(row["first_seen"]),
        )

    # ── Sessions ───────────────────────────────────────────────

    def record_session(self, session: SessionRecord) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO sessions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.session_id, session.repository, session.prompt,
                session.approach, session.model, session.outcome.value,
                session.pr_url, session.duration_seconds, session.token_count,
                session.created_at.isoformat(),
                session.completed_at.isoformat() if session.completed_at else None,
            ),
        )
        conn.execute("DELETE FROM session_files WHERE session_id = ?", (session.session_id,))
        for f in session.files_changed:
            conn.execute("INSERT INTO session_files VALUES (?, ?)", (session.session_id, f))
        conn.execute(
            "INSERT OR REPLACE INTO session_test_results VALUES (?, ?)",
            (session.session_id, json.dumps(session.test_results)),
        )
        conn.execute("DELETE FROM session_review_comments WHERE session_id = ?", (session.session_id,))
        for c in session.review_comments:
            conn.execute("INSERT INTO session_review_comments VALUES (?, ?)", (session.session_id, c))
        conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None

        files = conn.execute(
            "SELECT file_path FROM session_files WHERE session_id = ?", (session_id,)
        ).fetchall()
        test_row = conn.execute(
            "SELECT results_json FROM session_test_results WHERE session_id = ?", (session_id,)
        ).fetchone()
        comments = conn.execute(
            "SELECT comment FROM session_review_comments WHERE session_id = ?", (session_id,)
        ).fetchall()

        return SessionRecord(
            session_id=row["session_id"],
            repository=row["repository"],
            prompt=row["prompt"],
            approach=row["approach"],
            model=row["model"],
            outcome=AgentOutcome(row["outcome"]),
            pr_url=row["pr_url"],
            files_changed=[f[0] for f in files],
            test_results=json.loads(test_row[0]) if test_row else {},
            review_comments=[c[0] for c in comments],
            duration_seconds=row["duration_seconds"],
            token_count=row["token_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    def get_stats(self) -> dict[str, Any]:
        conn = self._get_conn()
        total_symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        total_patterns = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE outcome != ?", (AgentOutcome.IN_PROGRESS.value,)
        ).fetchone()[0]
        successes = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE outcome = ?", (AgentOutcome.SUCCESS.value,)
        ).fetchone()[0]

        return {
            "total_symbols": total_symbols,
            "total_files": total_files,
            "total_patterns": total_patterns,
            "total_sessions": total_sessions,
            "completed_sessions": completed,
            "successful_sessions": successes,
            "overall_success_rate": successes / completed if completed > 0 else 0.0,
            "total_approaches_tracked": conn.execute("SELECT COUNT(*) FROM approaches").fetchone()[0],
            "graph_nodes": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "graph_edges": conn.execute("SELECT COUNT(*) FROM symbol_deps").fetchone()[0],
        }

    def update_approach_efficacy(
        self, problem_type: str, approach: str, was_successful: bool,
        model: str, duration_seconds: float, token_count: int,
    ) -> ApproachEfficacy:
        conn = self._get_conn()
        key = f"{problem_type}:{approach[:100]}"
        existing = conn.execute("SELECT * FROM approaches WHERE key = ?", (key,)).fetchone()

        if existing:
            new_total = existing["total_attempts"] + 1
            new_successes = existing["successes"] + (1 if was_successful else 0)
            new_avg_dur = ((existing["avg_duration_seconds"] * (new_total - 1)) + duration_seconds) / new_total
            new_avg_tok = int(((existing["avg_tokens"] * (new_total - 1)) + token_count) / new_total)
            best_model = model if was_successful else existing["best_model"]
            conn.execute(
                """UPDATE approaches SET total_attempts=?, successes=?, avg_duration_seconds=?,
                avg_tokens=?, best_model=?, last_used=? WHERE key=?""",
                (new_total, new_successes, new_avg_dur, new_avg_tok, best_model, self._now(), key),
            )
            conn.commit()
            return ApproachEfficacy(
                problem_type=problem_type, approach=approach,
                total_attempts=new_total, successes=new_successes,
                avg_duration_seconds=new_avg_dur, avg_tokens=new_avg_tok,
                best_model=best_model,
            )
        else:
            conn.execute(
                """INSERT INTO approaches VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)""",
                (key, problem_type, approach, 1 if was_successful else 0,
                 duration_seconds, token_count, model, self._now()),
            )
            conn.commit()
            return ApproachEfficacy(
                problem_type=problem_type, approach=approach,
                total_attempts=1, successes=1 if was_successful else 0,
                avg_duration_seconds=duration_seconds, avg_tokens=token_count,
                best_model=model,
            )

    def get_best_approaches(
        self, problem_type: str | None = None, min_attempts: int = 3
    ) -> list[ApproachEfficacy]:
        conn = self._get_conn()
        sql = "SELECT * FROM approaches WHERE total_attempts >= ?"
        params: list[Any] = [min_attempts]
        if problem_type:
            sql += " AND problem_type = ?"
            params.append(problem_type)
        sql += " ORDER BY CAST(successes AS REAL) / total_attempts DESC"

        rows = conn.execute(sql, params).fetchall()
        return [
            ApproachEfficacy(
                problem_type=r["problem_type"], approach=r["approach"],
                total_attempts=r["total_attempts"], successes=r["successes"],
                avg_duration_seconds=r["avg_duration_seconds"],
                avg_tokens=r["avg_tokens"], best_model=r["best_model"],
            )
            for r in rows
        ]

    def learn_pattern(
        self, pattern_type: str, description: str, examples: list[str],
        source_session_id: str, confidence: float = 1.0,
    ) -> CodePattern:
        conn = self._get_conn()
        pid = CodePattern.compute_id(pattern_type, description[:100])

        existing = conn.execute("SELECT * FROM patterns WHERE id = ?", (pid,)).fetchone()
        if existing:
            new_conf = min(1.0, existing["confidence"] + 0.1)
            conn.execute("UPDATE patterns SET confidence = ? WHERE id = ?", (new_conf, pid))
        else:
            conn.execute(
                "INSERT INTO patterns VALUES (?, ?, ?, ?, ?)",
                (pid, pattern_type, description, confidence, self._now()),
            )
        conn.execute("DELETE FROM pattern_examples WHERE pattern_id = ?", (pid,))
        for ex in set(examples):
            conn.execute("INSERT INTO pattern_examples VALUES (?, ?)", (pid, ex))
        conn.execute("INSERT OR IGNORE INTO pattern_sessions VALUES (?, ?)", (pid, source_session_id))
        conn.commit()
        return CodePattern(
            id=pid, pattern_type=pattern_type, description=description,
            examples=examples, confidence=existing["confidence"] if existing else confidence,
            source_sessions=[source_session_id],
        )

    def get_patterns_by_type(self, pattern_type: str) -> list[CodePattern]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM patterns WHERE pattern_type = ? ORDER BY confidence DESC", (pattern_type,)
        ).fetchall()
        result: list[CodePattern] = []
        for r in rows:
            exs = conn.execute(
                "SELECT file_path FROM pattern_examples WHERE pattern_id = ?", (r["id"],)
            ).fetchall()
            sess = conn.execute(
                "SELECT session_id FROM pattern_sessions WHERE pattern_id = ?", (r["id"],)
            ).fetchall()
            result.append(CodePattern(
                id=r["id"], pattern_type=r["pattern_type"], description=r["description"],
                examples=[e[0] for e in exs], confidence=r["confidence"],
                source_sessions=[s[0] for s in sess],
            ))
        return result

    def close(self) -> None:
        """Close all thread-local connections. Runs WAL checkpoint to prevent
        unbounded WAL file growth."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def build_context_for_prompt(self, task_description: str) -> str:
        """Build context block — delegates to the JSON store's logic since it's string manipulation."""
        keywords = [w for w in task_description.lower().split() if len(w) > 2]
        parts: list[str] = ["## Codebase Knowledge Graph Context", ""]

        seen: set[str] = set()
        relevant: list[Symbol] = []
        for kw in keywords:
            for sym in self.search_symbols(kw):
                if sym.id not in seen:
                    relevant.append(sym)
                    seen.add(sym.id)

        if relevant:
            parts.append("### Relevant Symbols")
            parts.append("")
            for sym in relevant[:20]:
                parts.append(f"- **{sym.name}** (`{sym.kind.value}`) in `{sym.file_path}`")
                if sym.docstring:
                    parts.append(f"  {sym.docstring[:200].replace(chr(10), ' ')}")
                deps = self.get_symbol_dependencies(sym.id)
                if deps:
                    parts.append(f"  Depends on: {', '.join(d.name for d in deps[:5])}")
                parts.append("")
            parts.append("")

        for ptype in ["testing", "change_scope", "error_handling", "code_quality"]:
            patterns = self.get_patterns_by_type(ptype)
            if patterns:
                parts.append("### Learned Codebase Conventions")
                parts.append("")
                for pat in patterns[:5]:
                    parts.append(f"- **{pat.pattern_type}**: {pat.description}")
                    if pat.examples:
                        parts.append(f"  Examples: {', '.join(pat.examples[:3])}")
                    parts.append("")
                break

        return "\n".join(parts)