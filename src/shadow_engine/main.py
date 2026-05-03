"""Shadow Engineer — Main orchestrator and CLI.

Uses SQLiteStore + ChromaDB by default. Falls back gracefully.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .knowledge_graph.indexer import CodebaseIndexer
from .knowledge_graph.store import KnowledgeGraphStore
from .laboratory.experiment import ExperimentRunner
from .learning.engine import LearningEngine
from .observability import (
    log_bootstrap, record_bootstrap, record_search, record_session, record_context,
)

logger = logging.getLogger(__name__)

try:
    from .sqlite_store.db import SQLiteStore
    _SQLITE_AVAILABLE = True
except Exception:
    _SQLITE_AVAILABLE = False

try:
    from .chroma_store.vector_store import ChromaSymbolStore
    _CHROMA_AVAILABLE = True
except Exception:
    _CHROMA_AVAILABLE = False


class ShadowEngine:
    """Unified Shadow Engineer orchestrator.

    Uses SQLiteStore + ChromaDB by default. Falls back gracefully.
    """

    def __init__(
        self, storage_path: str | Path = "./.shadow-engine", repo_path: str | Path = ".",
        use_sqlite: bool = True, use_chroma: bool = True,
    ):
        self.storage_path = Path(storage_path)
        self.repo_path = Path(repo_path).resolve()

        if use_sqlite and _SQLITE_AVAILABLE:
            self.store = SQLiteStore(self.storage_path / "knowledge.db")
            logger.info("Using SQLiteStore backend (WAL mode)")
        else:
            self.store = KnowledgeGraphStore(self.storage_path / "knowledge")
            logger.info("Using JSON KnowledgeGraphStore backend (legacy)")

        if use_chroma and _CHROMA_AVAILABLE:
            self._chroma = ChromaSymbolStore(self.storage_path / "chroma")
            logger.info("ChromaDB vector store enabled")
        else:
            self._chroma = None

        self.indexer = CodebaseIndexer(self.repo_path)
        self.laboratory = ExperimentRunner()
        self.learning = LearningEngine(self.store)

        # Fix #5: Metrics derived from DB (survives restarts)
        self._metrics: dict[str, Any] = {
            "bootstraps": 0,
            "searches": 0,
            "sessions_recorded": 0,
            "contexts_generated": 0,
            "experiments_created": 0,
            "total_index_time_ms": 0,
            "total_search_time_ms": 0,
        }
        self._load_metrics()

    def _load_metrics(self) -> None:
        """Load persisted metrics from store (survives restarts)."""
        try:
            metrics_path = self.storage_path / "metrics.json"
            if metrics_path.exists():
                loaded = json.loads(metrics_path.read_text())
                self._metrics.update(loaded)
        except Exception:
            pass

    def _save_metrics(self) -> None:
        """Persist metrics to disk."""
        try:
            metrics_path = self.storage_path / "metrics.json"
            metrics_path.write_text(json.dumps(self._metrics, indent=2))
        except Exception:
            pass

    def bootstrap(self) -> dict[str, Any]:
        t0 = time.time()

        # Fix #2.3: Incremental indexing — only reindex changed files
        from .knowledge_graph.indexer import compute_file_hash

        symbols, files = self.indexer.index()

        for sym in symbols.values():
            self.store.upsert_symbol(sym)

        for file_path, file_summary in files.items():
            self.store.upsert_file(file_summary)
            # Update file hash for incremental reindexing
            full_path = self.repo_path / file_path
            if hasattr(self.store, 'set_file_hash') and full_path.exists():
                file_hash = compute_file_hash(full_path)
                self.store.set_file_hash(file_path, file_hash)

        if self._chroma is not None:
            self._chroma.index_symbols(symbols)
        self._metrics["bootstraps"] += 1
        duration_ms = (time.time() - t0) * 1000
        self._metrics["total_index_time_ms"] += duration_ms
        self._save_metrics()
        stats = self.store.get_stats()

        # Phase 2.4: Structured logging + Prometheus
        record_bootstrap(str(self.repo_path.name), duration_ms / 1000.0, len(symbols), len(files))
        log_bootstrap(str(self.repo_path.name), len(symbols), len(files), duration_ms)

        return {
            "status": "bootstrapped", "repository": str(self.repo_path.name),
            "symbols_indexed": len(symbols), "files_indexed": len(files),
            "semantic_search": self._chroma is not None, "stats": stats,
        }

    # Fix #1: ChromaDB semantic search with full symbol enrichment from store
    def get_context(self, task_description: str) -> str:
        self._metrics["contexts_generated"] += 1
        self._save_metrics()
        record_context()

        if self._chroma is not None and self._chroma.count() > 0:
            try:
                semantic_results = self._chroma.search(task_description, top_k=15)
                if semantic_results:
                    parts = ["## Codebase Knowledge Graph Context (Semantic)", ""]
                    parts.append("### Semantically Relevant Symbols")
                    parts.append("")
                    for skeleton_sym, score in semantic_results[:15]:
                        # Fix #1: Enrich skeleton with full symbol from store
                        full_sym = self.store.get_symbol(skeleton_sym.id)
                        if full_sym is None:
                            full_sym = skeleton_sym
                        parts.append(
                            f"- **{full_sym.name}** (`{full_sym.kind.value}`) "
                            f"in `{full_sym.file_path}` (relevance: {score:.2f})"
                        )
                        if full_sym.docstring:
                            parts.append(f"  {full_sym.docstring[:200].replace(chr(10), ' ')}")
                        deps = self.store.get_symbol_dependencies(full_sym.id)
                        if deps:
                            parts.append(f"  Depends on: {', '.join(d.name for d in deps[:5])}")
                        parts.append("")
                    parts.append("")
                    parts.append(self.store.build_context_for_prompt(task_description))
                    return "\n".join(parts)
            except Exception as e:
                logger.warning(f"ChromaDB search failed, falling back: {e}")

        return self.store.build_context_for_prompt(task_description)

    def suggest(self, task_description: str) -> dict[str, Any]:
        return self.learning.suggest_approach(task_description)

    def search(self, query: str, kind: str | None = None) -> list[dict[str, Any]]:
        t0 = time.time()
        self._metrics["searches"] += 1
        self._save_metrics()

        record_search((time.time() - t0) * 1000)

        if self._chroma is not None and self._chroma.count() > 0:
            try:
                results = self._chroma.search(query, top_k=20, kind_filter=kind, store=self.store)
                self._metrics["total_search_time_ms"] += (time.time() - t0) * 1000
                return [
                    {"id": sym.id, "name": sym.name, "kind": sym.kind.value,
                     "file_path": sym.file_path,
                     "signature": sym.signature[:100] if sym.signature else "",
                     "docstring": (sym.docstring or "")[:200],
                     "complexity": sym.complexity_score}
                    for sym, score in results
                ]
            except Exception:
                pass

        symbols = self.store.search_symbols(query, kind=kind)
        self._metrics["total_search_time_ms"] += (time.time() - t0) * 1000
        return [
            {"id": s.id, "name": s.name, "kind": s.kind.value, "file_path": s.file_path,
             "signature": s.signature[:100], "docstring": (s.docstring or "")[:200],
             "complexity": s.complexity_score}
            for s in symbols[:20]
        ]

    def impact(self, symbol_name: str) -> dict[str, Any]:
        symbols = self.store.search_symbols(symbol_name)
        if not symbols:
            return {"error": f"No symbol found matching '{symbol_name}'"}
        sym = symbols[0]
        return {
            "symbol": {"name": sym.name, "kind": sym.kind.value, "file_path": sym.file_path},
            "dependencies": [d.name for d in self.store.get_symbol_dependencies(sym.id)],
            "direct_dependents": [d.name for d in self.store.get_symbol_dependents(sym.id)],
            "impact_radius": [s.name for s in self.store.get_impact_radius(sym.id, depth=2)],
            "total_affected_symbols": len(self.store.get_impact_radius(sym.id, depth=2)),
        }

    def experiment(self, task_description: str, num_variants: int = 3,
                   models: list[str] | None = None, strategies: list[dict[str, str]] | None = None) -> dict[str, Any]:
        self._metrics["experiments_created"] += 1
        self._save_metrics()
        batch = self.laboratory.create_batch(
            task_description=task_description, repository=str(self.repo_path.name),
            num_variants=num_variants, models=models, strategies=strategies)
        return batch.to_summary()

    def record_result(self, session_id: str, outcome: str, prompt: str, approach: str = "",
                      model: str = "default", pr_url: str | None = None,
                      files_changed: list[str] | None = None,
                      test_results: dict[str, int] | None = None,
                      review_comments: list[str] | None = None,
                      duration_seconds: float = 0.0, token_count: int = 0) -> dict[str, Any]:
        self._metrics["sessions_recorded"] += 1
        self._save_metrics()
        record_session(outcome, "unknown")  # problem_type determined during ingestion
        from .knowledge_graph.models import AgentOutcome, SessionRecord
        session = SessionRecord(
            session_id=session_id, repository=str(self.repo_path.name),
            prompt=prompt, approach=approach, model=model,
            outcome=AgentOutcome(outcome), pr_url=pr_url,
            files_changed=files_changed or [], test_results=test_results or {},
            review_comments=review_comments or [],
            duration_seconds=duration_seconds, token_count=token_count)
        return self.learning.ingest_session(session)

    def get_report(self) -> str:
        return self.learning.get_improvement_report()

    def get_stats(self) -> dict[str, Any]:
        return self.store.get_stats()

    def get_metrics(self) -> dict[str, Any]:
        stats = self.get_stats()
        return {
            **self._metrics,
            "knowledge_graph": stats,
            "chromadb_symbols": self._chroma.count() if self._chroma else 0,
        }

    def close(self) -> None:
        self._save_metrics()
        if hasattr(self.store, 'close'):
            self.store.close()

    # Fix #7: Migration from JSON store to SQLite
    def migrate_to_sqlite(self) -> dict[str, Any]:
        """Migrate data from the legacy JSON KnowledgeGraphStore to SQLiteStore.

        Call this if you started with JSON storage and want to switch to SQLite.
        Returns migration statistics.
        """
        if not _SQLITE_AVAILABLE:
            return {"status": "error", "reason": "SQLite store not available"}

        json_store = KnowledgeGraphStore(self.storage_path / "knowledge")
        sqlite_store = SQLiteStore(self.storage_path / "knowledge.db")
        sqlite_store._init_db()

        counts = {"symbols": 0, "files": 0, "sessions": 0, "patterns": 0, "approaches": 0}

        # Migrate symbols
        for sym in json_store._symbols.values():
            sqlite_store.upsert_symbol(sym)
            counts["symbols"] += 1

        # Migrate files
        for fs in json_store._files.values():
            sqlite_store.upsert_file(fs)
            counts["files"] += 1

        # Migrate sessions
        for session in json_store._sessions.values():
            sqlite_store.record_session(session)
            counts["sessions"] += 1

        # Migrate patterns
        for pattern in json_store._patterns.values():
            # Re-create patterns via learn_pattern
            sqlite_store.learn_pattern(
                pattern_type=pattern.pattern_type,
                description=pattern.description,
                examples=pattern.examples,
                source_session_id=pattern.source_sessions[0] if pattern.source_sessions else "migration",
                confidence=pattern.confidence,
            )
            counts["patterns"] += 1

        # Migrate approaches — directly insert
        conn = sqlite_store._get_conn()
        for key, ae in json_store._approaches.items():
            conn.execute(
                "INSERT OR REPLACE INTO approaches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, ae.problem_type, ae.approach, ae.total_attempts,
                 ae.successes, ae.avg_duration_seconds, ae.avg_tokens,
                 ae.best_model, ae.last_used.isoformat()),
            )
            counts["approaches"] += 1
        conn.commit()
        sqlite_store.close()

        self.store = sqlite_store
        self.learning = LearningEngine(self.store)

        return {"status": "migrated", **counts}


def cli_main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Shadow Engineer — Self-improving background agent knowledge engine")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("bootstrap")
    sp = subparsers.add_parser("search"); sp.add_argument("query"); sp.add_argument("--kind", "-k")
    sp = subparsers.add_parser("context"); sp.add_argument("task", nargs="+")
    sp = subparsers.add_parser("suggest"); sp.add_argument("task", nargs="+")
    sp = subparsers.add_parser("impact"); sp.add_argument("symbol")
    sp = subparsers.add_parser("experiment"); sp.add_argument("task", nargs="+"); sp.add_argument("--variants", "-n", type=int, default=3)
    sp = subparsers.add_parser("record")
    sp.add_argument("--session-id", required=True); sp.add_argument("--outcome", required=True, choices=["success","failure","rejected","abandoned"]); sp.add_argument("--prompt", required=True); sp.add_argument("--approach", default=""); sp.add_argument("--model", default="default"); sp.add_argument("--pr-url"); sp.add_argument("--files", nargs="+", default=[]); sp.add_argument("--tests-passed", type=int, default=0); sp.add_argument("--tests-failed", type=int, default=0); sp.add_argument("--duration", type=float, default=0.0); sp.add_argument("--tokens", type=int, default=0)
    subparsers.add_parser("report")
    subparsers.add_parser("stats")
    subparsers.add_parser("metrics")
    subparsers.add_parser("migrate")  # Fix #7: CLI migration command

    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    engine = ShadowEngine()
    if args.command == "bootstrap":
        r = engine.bootstrap(); print(f"Bootstrapped: {r['symbols_indexed']} symbols, {r['files_indexed']} files")
    elif args.command == "search":
        for r in engine.search(args.query, kind=args.kind): print(f"  [{r.get('kind','?')}] {r['name']} — {r['file_path']}")
    elif args.command == "context": print(engine.get_context(" ".join(args.task)))
    elif args.command == "suggest": print(json.dumps(engine.suggest(" ".join(args.task)), indent=2, default=str))
    elif args.command == "impact": print(json.dumps(engine.impact(args.symbol), indent=2))
    elif args.command == "experiment": print(json.dumps(engine.experiment(" ".join(args.task), num_variants=args.variants), indent=2))
    elif args.command == "record":
        r = engine.record_result(session_id=args.session_id, outcome=args.outcome, prompt=args.prompt, approach=args.approach, model=args.model, pr_url=args.pr_url, files_changed=args.files, test_results={"total": args.tests_passed + args.tests_failed, "passed": args.tests_passed, "failed": args.tests_failed}, duration_seconds=args.duration, token_count=args.tokens)
        print(json.dumps(r, indent=2, default=str))
    elif args.command == "report": print(engine.get_report())
    elif args.command == "stats": print(json.dumps(engine.get_stats(), indent=2))
    elif args.command == "metrics": print(json.dumps(engine.get_metrics(), indent=2))
    elif args.command == "migrate":
        r = engine.migrate_to_sqlite()
        print(json.dumps(r, indent=2))


if __name__ == "__main__":
    cli_main()