"""Structured logging and metrics for Shadow Engineer.

Provides structured JSON logging via structlog and Prometheus metrics.
Falls back to standard logging if structlog/prometheus_client are not installed.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextvars import ContextVar

# ── Request ID tracking ───────────────────────────────────────────

_request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request-id")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return _request_id_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set the current request ID. Generates a UUIDv4 if none provided."""
    rid = request_id or uuid.uuid4().hex[:12]
    _request_id_var.set(rid)
    return rid


# ── Prometheus Metrics ────────────────────────────────────────────

_metrics_available = False
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
    _metrics_available = True
except ImportError:
    pass

if _metrics_available:
    BOOTSTRAP_COUNTER = Counter(
        "shadow_engine_bootstrap_total", "Number of bootstraps", ["repository"]
    )
    BOOTSTRAP_DURATION = Histogram(
        "shadow_engine_bootstrap_duration_seconds", "Bootstrap duration",
        ["repository"], buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
    )
    SEARCH_COUNTER = Counter(
        "shadow_engine_search_total", "Number of searches"
    )
    SEARCH_DURATION = Histogram(
        "shadow_engine_search_duration_seconds", "Search duration",
        buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1]
    )
    SESSION_COUNTER = Counter(
        "shadow_engine_sessions_total", "Number of sessions recorded",
        ["outcome", "problem_type"]
    )
    CONTEXT_COUNTER = Counter(
        "shadow_engine_context_total", "Number of context generations"
    )
    SYMBOL_GAUGE = Gauge(
        "shadow_engine_symbols_total", "Total indexed symbols"
    )
    SESSION_SUCCESS_GAUGE = Gauge(
        "shadow_engine_session_success_rate", "Overall session success rate"
    )
    CHROMADB_SYMBOLS_GAUGE = Gauge(
        "shadow_engine_chromadb_symbols", "ChromaDB indexed symbol count"
    )

    def get_prometheus_metrics() -> bytes:
        """Generate Prometheus metrics text."""
        return generate_latest(REGISTRY)
else:
    def get_prometheus_metrics() -> bytes:
        return b"# Prometheus client not installed\n"


def record_bootstrap(repository: str, duration_s: float, symbol_count: int, file_count: int) -> None:
    """Record a bootstrap operation."""
    if _metrics_available:
        BOOTSTRAP_COUNTER.labels(repository=repository).inc()
        BOOTSTRAP_DURATION.labels(repository=repository).observe(duration_s)
        SYMBOL_GAUGE.set(symbol_count)


def record_search(duration_ms: float) -> None:
    """Record a search operation."""
    if _metrics_available:
        SEARCH_COUNTER.inc()
        SEARCH_DURATION.observe(duration_ms / 1000.0)


def record_session(outcome: str, problem_type: str) -> None:
    """Record a session ingestion."""
    if _metrics_available:
        SESSION_COUNTER.labels(outcome=outcome, problem_type=problem_type).inc()


def record_context() -> None:
    """Record a context generation."""
    if _metrics_available:
        CONTEXT_COUNTER.inc()


def update_knowledge_graph_stats(symbol_count: int, success_rate: float, chromadb_count: int = 0) -> None:
    """Update gauges with knowledge graph stats."""
    if _metrics_available:
        SYMBOL_GAUGE.set(symbol_count)
        SESSION_SUCCESS_GAUGE.set(success_rate)
        CHROMADB_SYMBOLS_GAUGE.set(chromadb_count)


# ── Structured Logging ────────────────────────────────────────────

_structlog_available = False
try:
    import structlog
    _structlog_available = True
except ImportError:
    pass

if _structlog_available:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if os.environ.get("SHADOW_ENGINE_LOG_FORMAT", "json") == "console"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _logger = structlog.get_logger("shadow_engine")
else:
    _logger = logging.getLogger("shadow_engine")


def get_logger():
    """Get the structured logger."""
    return _logger


def log_bootstrap(repository: str, symbols: int, files: int, duration_ms: float) -> None:
    """Log a bootstrap operation with structured data."""
    _logger.info(
        "codebase_bootstrapped",
        repository=repository,
        symbols_indexed=symbols,
        files_indexed=files,
        duration_ms=duration_ms,
        request_id=get_request_id(),
    )


def log_search(query: str, results: int, duration_ms: float) -> None:
    """Log a search operation."""
    _logger.info(
        "search_performed",
        query=query[:100],
        result_count=results,
        duration_ms=duration_ms,
        request_id=get_request_id(),
    )


def log_ingest(session_id: str, outcome: str, problem_type: str, patterns: int) -> None:
    """Log a session ingestion."""
    _logger.info(
        "session_ingested",
        session_id=session_id,
        outcome=outcome,
        problem_type=problem_type,
        patterns_learned=patterns,
        request_id=get_request_id(),
    )


def log_error(operation: str, error: str) -> None:
    """Log an error with context."""
    _logger.error(
        "operation_failed",
        operation=operation,
        error=str(error)[:500],
        request_id=get_request_id(),
    )