"""Data models for the persistent codebase knowledge graph."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SymbolKind(str, Enum):
    """Kind of code symbol."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"


class ChangeType(str, Enum):
    """Type of change made by an agent session."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class AgentOutcome(str, Enum):
    """Outcome of an agent session."""
    SUCCESS = "success"          # PR merged
    FAILURE = "failure"          # PR closed without merge
    ABANDONED = "abandoned"      # Session abandoned, no PR created
    REJECTED = "rejected"        # PR explicitly rejected in review
    IN_PROGRESS = "in_progress"  # Session still active


class Symbol(BaseModel):
    """A code symbol (function, class, etc.) tracked in the knowledge graph."""
    id: str = Field(description="Unique symbol ID (hash of path + name)")
    name: str
    kind: SymbolKind
    file_path: str
    line_start: int
    line_end: int
    signature: str = Field(default="", description="Function/method signature or class declaration")
    docstring: str = Field(default="", description="Documentation string")
    dependencies: list[str] = Field(default_factory=list, description="IDs of symbols this symbol calls/imports")
    dependents: list[str] = Field(default_factory=list, description="IDs of symbols that depend on this symbol")
    complexity_score: float = Field(default=0.0, description="Cyclomatic complexity score")
    test_coverage: float | None = Field(default=None, description="Test coverage percentage, if known")
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def compute_id(cls, file_path: str, name: str) -> str:
        """Compute a stable ID for a symbol."""
        raw = f"{file_path}:{name}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FileSummary(BaseModel):
    """Summary of a file's structure and purpose."""
    path: str
    language: str
    summary: str = Field(default="", description="Natural language summary of file purpose")
    symbols: list[str] = Field(default_factory=list, description="Symbol IDs in this file")
    imports: list[str] = Field(default_factory=list, description="Imported modules/files")
    exported_symbols: list[str] = Field(default_factory=list, description="Exported/public symbol names")
    line_count: int = 0
    last_indexed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CodePattern(BaseModel):
    """A learned codebase convention or pattern."""
    id: str
    pattern_type: str = Field(description="e.g., 'error_handling', 'test_structure', 'naming_convention'")
    description: str
    examples: list[str] = Field(default_factory=list, description="File paths demonstrating this pattern")
    confidence: float = Field(default=1.0, description="How confident we are in this pattern (0-1)")
    source_sessions: list[str] = Field(default_factory=list, description="Session IDs that contributed to this pattern")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def compute_id(cls, pattern_type: str, description_hash: str) -> str:
        raw = f"{pattern_type}:{description_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class SessionRecord(BaseModel):
    """Record of a single agent session for learning purposes."""
    session_id: str
    repository: str
    prompt: str
    approach: str = Field(default="", description="Strategy/approach used by the agent")
    model: str = Field(default="unknown")
    outcome: AgentOutcome
    pr_url: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    symbols_modified: list[str] = Field(default_factory=list)
    test_results: dict[str, Any] = Field(default_factory=dict)
    review_comments: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    token_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    @property
    def was_successful(self) -> bool:
        return self.outcome == AgentOutcome.SUCCESS


class ApproachEfficacy(BaseModel):
    """Tracks which approaches work best for specific problem types."""
    problem_type: str = Field(description="Category of problem (bug_fix, feature, refactor, etc.)")
    approach: str = Field(description="Strategy description")
    total_attempts: int = 0
    successes: int = 0
    avg_duration_seconds: float = 0.0
    avg_tokens: int = 0
    best_model: str = Field(default="unknown")
    last_used: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.successes / self.total_attempts


class KnowledgeSnapshot(BaseModel):
    """A point-in-time snapshot of the entire knowledge graph state."""
    snapshot_id: str
    repository: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_symbols: int = 0
    total_files: int = 0
    total_patterns: int = 0
    total_sessions: int = 0
    overall_agent_success_rate: float = 0.0
    most_effective_approaches: list[ApproachEfficacy] = Field(default_factory=list)

    @classmethod
    def compute_id(cls, repository: str, timestamp: datetime) -> str:
        raw = f"{repository}:{timestamp.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]