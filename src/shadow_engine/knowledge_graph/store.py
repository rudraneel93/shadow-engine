"""Knowledge Graph Store — JSON file backend (legacy fallback).

For production use, prefer SQLiteStore (sqlite_store/db.py) which is wired
as the default backend in ShadowEngine.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from .models import (
    AgentOutcome,
    ApproachEfficacy,
    CodePattern,
    FileSummary,
    Symbol,
    SessionRecord,
    KnowledgeSnapshot,
)

logger = logging.getLogger(__name__)

# Strict ISO 8601 datetime pattern: YYYY-MM-DDTHH:MM:SS
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _datetime_encoder(obj: Any) -> Any:
    """JSON encoder that handles datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _datetime_decoder(dct: dict[str, Any]) -> dict[str, Any]:
    """JSON decoder that parses datetime strings using strict ISO 8601 matching."""
    for key, value in dct.items():
        if isinstance(value, str) and _DATETIME_RE.match(value):
            try:
                dct[key] = datetime.fromisoformat(value)
            except (ValueError, TypeError):
                pass
    return dct


class KnowledgeGraphStore:
    """Persistent store for the codebase knowledge graph (JSON backend).

    DEPRECATED: This is the legacy JSON backend. For production use, prefer
    SQLiteStore which offers WAL-mode concurrency, indexed queries, and
    connection safety. ShadowEngine auto-detects and uses SQLiteStore by default.
    """
    def __init__(self, storage_path: str | Path):
        # Fix #3: Warn if used directly instead of through ShadowEngine
        logger.warning(
            "KnowledgeGraphStore (JSON) is deprecated. "
            "Use ShadowEngine() which defaults to SQLiteStore for production."
        )
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._graph = nx.DiGraph()
        self._symbols: dict[str, Symbol] = {}
        self._files: dict[str, FileSummary] = {}
        self._patterns: dict[str, CodePattern] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._approaches: dict[str, ApproachEfficacy] = {}
        self._dirty: bool = False

        self._load()

    # ── Persistence ────────────────────────────────────────────────

    def _load(self) -> None:
        """Load all data from disk with error recovery per file."""
        for name, target, cls in [
            ("symbols", self._symbols, Symbol),
            ("files", self._files, FileSummary),
            ("patterns", self._patterns, CodePattern),
            ("sessions", self._sessions, SessionRecord),
            ("approaches", self._approaches, ApproachEfficacy),
        ]:
            try:
                self._load_json(name, target, cls)
            except Exception as e:
                logger.error(f"Failed to load {name}.json — starting fresh. Error: {e}")

        try:
            self._load_graph()
        except Exception as e:
            logger.error(f"Failed to load graph.json — starting fresh. Error: {e}")

    def _save(self) -> None:
        """Write all data to disk atomically (per file).

        Uses atomic write-then-rename for each file. In production,
        prefer SQLiteStore which handles writes incrementally via WAL.
        """
        try:
            self._save_json("symbols", self._symbols)
            self._save_json("files", self._files)
            self._save_json("patterns", self._patterns)
            self._save_json("sessions", self._sessions)
            self._save_json("approaches", self._approaches)
            self._save_graph()
        except Exception as e:
            logger.error(f"Failed to save store: {e}")

    def _json_path(self, name: str) -> Path:
        return self.storage_path / f"{name}.json"

    def _save_json(self, name: str, data: dict[str, Any]) -> None:
        path = self._json_path(name)
        tmp_path = path.with_suffix(".tmp")
        serializable = {
            k: v.model_dump() if hasattr(v, "model_dump") else v
            for k, v in data.items()
        }
        content = json.dumps(serializable, indent=2, default=_datetime_encoder)
        # Atomic write: write to temp, then rename
        tmp_path.write_text(content)
        tmp_path.rename(path)

    def _load_json(self, name: str, target: dict[str, Any], model_cls: type) -> None:
        path = self._json_path(name)
        if not path.exists():
            return
        raw = json.loads(path.read_text(), object_hook=_datetime_decoder)
        target.clear()
        target.update({k: model_cls(**v) for k, v in raw.items()})

    def _save_graph(self) -> None:
        graph_data = nx.node_link_data(self._graph)
        path = self.storage_path / "graph.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(graph_data, indent=2, default=_datetime_encoder))
        tmp.rename(path)

    def _load_graph(self) -> None:
        path = self.storage_path / "graph.json"
        if not path.exists():
            return
        graph_data = json.loads(path.read_text(), object_hook=_datetime_decoder)
        self._graph = nx.node_link_graph(graph_data)

    # ── Symbols ────────────────────────────────────────────────────

    def upsert_symbol(self, symbol: Symbol) -> None:
        self._symbols[symbol.id] = symbol
        self._graph.add_node(
            symbol.id,
            type="symbol",
            name=symbol.name,
            kind=symbol.kind.value,
            file_path=symbol.file_path,
            complexity=symbol.complexity_score,
        )
        for dep_id in symbol.dependencies:
            if dep_id in self._symbols:
                self._graph.add_edge(symbol.id, dep_id, relation="depends_on")
        self._save()

    def get_symbol(self, symbol_id: str) -> Symbol | None:
        return self._symbols.get(symbol_id)

    def search_symbols(
        self, query: str, kind: str | None = None, file_path: str | None = None
    ) -> list[Symbol]:
        results: list[Symbol] = []
        query_lower = query.lower()
        for sym in self._symbols.values():
            if query_lower not in sym.name.lower() and query_lower not in sym.signature.lower():
                if query_lower not in (sym.docstring or "").lower():
                    continue
            if kind is not None and sym.kind.value != kind:
                continue
            if file_path is not None and file_path not in sym.file_path:
                continue
            results.append(sym)
        results.sort(key=lambda s: (0 if s.name.lower() == query_lower else 1, s.name))
        return results

    def get_symbol_dependencies(self, symbol_id: str) -> list[Symbol]:
        if symbol_id not in self._symbols:
            return []
        return [self._symbols[n] for n in self._graph.successors(symbol_id) if n in self._symbols]

    def get_symbol_dependents(self, symbol_id: str) -> list[Symbol]:
        if symbol_id not in self._symbols:
            return []
        return [self._symbols[n] for n in self._graph.predecessors(symbol_id) if n in self._symbols]

    def get_impact_radius(self, symbol_id: str, depth: int = 2) -> list[Symbol]:
        if symbol_id not in self._symbols:
            return []
        affected: set[str] = set()
        from collections import deque
        q = deque([(symbol_id, 0)])
        while q:
            current, d = q.popleft()
            if d > depth:
                continue
            affected.add(current)
            for neighbor in self._graph.predecessors(current):
                if neighbor not in affected:
                    q.append((neighbor, d + 1))
        return [self._symbols[sid] for sid in affected if sid in self._symbols]

    # ── Files ──────────────────────────────────────────────────────

    def upsert_file(self, file_summary: FileSummary) -> None:
        self._files[file_summary.path] = file_summary
        self._graph.add_node(
            f"file:{file_summary.path}", type="file", path=file_summary.path,
            language=file_summary.language, line_count=file_summary.line_count,
        )
        self._save()

    def get_file(self, path: str) -> FileSummary | None:
        return self._files.get(path)

    # ── Context ────────────────────────────────────────────────────

    def build_context_for_prompt(
        self, task_description: str, max_symbols: int = 20, max_patterns: int = 5
    ) -> str:
        parts: list[str] = ["## Codebase Knowledge Graph Context", ""]
        keywords = [w for w in task_description.lower().split() if len(w) > 2]
        relevant: list[Symbol] = []
        seen: set[str] = set()
        for kw in keywords:
            for sym in self.search_symbols(kw):
                if sym.id not in seen:
                    relevant.append(sym)
                    seen.add(sym.id)
        if relevant:
            parts.append("### Relevant Symbols")
            parts.append("")
            for sym in relevant[:max_symbols]:
                parts.append(f"- **{sym.name}** (`{sym.kind.value}`) in `{sym.file_path}`")
                if sym.docstring:
                    parts.append(f"  {sym.docstring[:200].replace(chr(10), ' ')}")
                deps = self.get_symbol_dependencies(sym.id)
                if deps:
                    parts.append(f"  Depends on: {', '.join(d.name for d in deps[:5])}")
                parts.append("")
            parts.append("")
        if self._patterns:
            parts.append("### Learned Codebase Conventions")
            parts.append("")
            for pat in sorted(self._patterns.values(), key=lambda p: p.confidence, reverse=True)[:max_patterns]:
                parts.append(f"- **{pat.pattern_type}**: {pat.description}")
                if pat.examples:
                    parts.append(f"  Examples: {', '.join(pat.examples[:3])}")
                parts.append("")
            parts.append("")
        relevant_approaches = self._get_relevant_approaches(task_description)
        if relevant_approaches:
            parts.append("### Historically Effective Approaches")
            parts.append("")
            for ae in relevant_approaches[:3]:
                parts.append(
                    f"- **{ae.approach}**: {ae.success_rate:.0%} success "
                    f"({ae.successes}/{ae.total_attempts}) — best model: {ae.best_model}"
                )
            parts.append("")
        return "\n".join(parts)

    def _get_relevant_approaches(self, task: str) -> list[ApproachEfficacy]:
        pt = "general"
        tl = task.lower()
        if any(w in tl for w in ("bug", "fix", "error", "crash", "broken")): pt = "bug_fix"
        elif any(w in tl for w in ("test", "spec", "coverage")): pt = "testing"
        elif any(w in tl for w in ("refactor", "clean", "improve", "optimize")): pt = "refactor"
        elif any(w in tl for w in ("feature", "add", "implement", "create", "build", "new")): pt = "feature"
        elif any(w in tl for w in ("migrate", "upgrade")): pt = "migration"
        return [a for a in self._approaches.values() if a.problem_type == pt]

    # ── Patterns ───────────────────────────────────────────────────

    def learn_pattern(
        self, pattern_type: str, description: str, examples: list[str],
        source_session_id: str, confidence: float = 1.0,
    ) -> CodePattern:
        pid = CodePattern.compute_id(pattern_type, description[:100])
        if pid in self._patterns:
            existing = self._patterns[pid]
            existing.examples = list(set(existing.examples + examples))
            if source_session_id not in existing.source_sessions:
                existing.source_sessions.append(source_session_id)
            existing.confidence = min(1.0, existing.confidence + 0.1)
        else:
            self._patterns[pid] = CodePattern(
                id=pid, pattern_type=pattern_type, description=description,
                examples=examples, confidence=confidence, source_sessions=[source_session_id],
            )
        self._save()
        return self._patterns[pid]

    def get_patterns_by_type(self, pattern_type: str) -> list[CodePattern]:
        return [p for p in self._patterns.values() if p.pattern_type == pattern_type]

    # ── Sessions ───────────────────────────────────────────────────

    def record_session(self, session: SessionRecord) -> None:
        self._sessions[session.session_id] = session
        self._graph.add_node(
            f"session:{session.session_id}", type="session",
            outcome=session.outcome.value, prompt=session.prompt[:200], model=session.model,
        )
        self._save()

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def update_approach_efficacy(
        self, problem_type: str, approach: str, was_successful: bool,
        model: str, duration_seconds: float, token_count: int,
    ) -> ApproachEfficacy:
        key = f"{problem_type}:{approach[:100]}"
        if key in self._approaches:
            ae = self._approaches[key]
            ae.total_attempts += 1
            if was_successful:
                ae.successes += 1
            ae.avg_duration_seconds = (
                (ae.avg_duration_seconds * (ae.total_attempts - 1) + duration_seconds)
                / ae.total_attempts
            )
            ae.avg_tokens = int(
                (ae.avg_tokens * (ae.total_attempts - 1) + token_count) / ae.total_attempts
            )
            ae.best_model = model if was_successful else ae.best_model
            ae.last_used = datetime.now(timezone.utc)
        else:
            ae = ApproachEfficacy(
                problem_type=problem_type, approach=approach,
                total_attempts=1, successes=1 if was_successful else 0,
                avg_duration_seconds=duration_seconds, avg_tokens=token_count, best_model=model,
            )
        self._approaches[key] = ae
        self._save()
        return ae

    def get_best_approaches(
        self, problem_type: str | None = None, min_attempts: int = 3
    ) -> list[ApproachEfficacy]:
        candidates = [
            a for a in self._approaches.values()
            if (problem_type is None or a.problem_type == problem_type)
            and a.total_attempts >= min_attempts
        ]
        candidates.sort(key=lambda a: a.success_rate, reverse=True)
        return candidates

    # ── Snapshots ──────────────────────────────────────────────────

    def create_snapshot(self, repository: str) -> KnowledgeSnapshot:
        best = self.get_best_approaches()
        snapshot = KnowledgeSnapshot(
            snapshot_id=KnowledgeSnapshot.compute_id(repository, datetime.now(timezone.utc)),
            repository=repository,
            total_symbols=len(self._symbols),
            total_files=len(self._files),
            total_patterns=len(self._patterns),
            total_sessions=len(self._sessions),
            overall_agent_success_rate=self._compute_overall_success_rate(),
            most_effective_approaches=best[:10],
        )
        snap_path = self.storage_path / "snapshots"
        snap_path.mkdir(exist_ok=True)
        (snap_path / f"{snapshot.snapshot_id}.json").write_text(
            json.dumps(snapshot.model_dump(), indent=2, default=_datetime_encoder)
        )
        return snapshot

    def _compute_overall_success_rate(self) -> float:
        completed = [s for s in self._sessions.values() if s.outcome != AgentOutcome.IN_PROGRESS]
        if not completed:
            return 0.0
        return sum(1 for s in completed if s.outcome == AgentOutcome.SUCCESS) / len(completed)

    def get_stats(self) -> dict[str, Any]:
        completed = [s for s in self._sessions.values() if s.outcome != AgentOutcome.IN_PROGRESS]
        return {
            "total_symbols": len(self._symbols),
            "total_files": len(self._files),
            "total_patterns": len(self._patterns),
            "total_sessions": len(self._sessions),
            "completed_sessions": len(completed),
            "successful_sessions": sum(1 for s in completed if s.was_successful),
            "overall_success_rate": self._compute_overall_success_rate(),
            "total_approaches_tracked": len(self._approaches),
            "graph_nodes": self._graph.number_of_nodes(),
            "graph_edges": self._graph.number_of_edges(),
        }