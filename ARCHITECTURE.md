# Shadow Engineer — Architecture Documentation

## System Overview

Shadow Engineer is a Python library that adds persistent, cross-session learning to background coding agents. It sits as a "learning layer" between an agent framework (Open-Inspect, Claude Code, custom) and the codebase being modified.

```
┌──────────────────────────────────────────────────────────────────┐
│                       SHADOW ENGINEER                             │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │  Knowledge   │   │  Laboratory  │   │   Learning Engine    │ │
│  │    Graph     │   │              │   │                      │ │
│  │              │   │ • Experiment │   │ • Pattern extraction │ │
│  │ • Indexer    │   │ • Debate     │   │ • Efficacy tracking  │ │
│  │ • SQLite     │   │ • Scoring    │   │ • Causal reasoning   │ │
│  │ • ChromaDB   │   │              │   │ • Strategy evolution │ │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬───────────┘ │
│         │                  │                       │             │
│         ▼                  ▼                       ▼             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Context Builder                          │ │
│  │  Budget-aware, priority-ordered, multi-engine aggregation   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│                              ▼                                    │
│                    Agent Prompt + Context                         │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Task → Classify → Build Context → Inject into Agent Prompt → Agent Executes
                                                                      │
                                                                      ▼
Next Session ←── Learn Patterns ←── Analyze Outcome ←── Record Result
```

## Component Details

### Knowledge Graph

**Files:** `knowledge_graph/indexer.py`, `knowledge_graph/models.py`, `knowledge_graph/store.py`

- **Indexer:** Parses source files using regex patterns (Python also uses `ast.parse()`). Outputs `Symbol` and `FileSummary` objects.
- **Models:** Pydantic models for `Symbol`, `SymbolKind`, `FileSummary`, `SessionRecord`, `CodePattern`, `ApproachEfficacy`.
- **Store:** Two backends — `SQLiteStore` (production, WAL mode) and `KnowledgeGraphStore` (JSON, deprecated).

### SQLite Backend

**File:** `sqlite_store/db.py`

Tables: `symbols`, `symbol_deps`, `files`, `file_imports`, `file_hashes`, `patterns`, `fix_patterns`, `sessions`, `session_files`, `session_test_results`, `session_review_comments`, `approaches`.

Uses WAL mode for concurrent read/write. Connection per thread via `threading.local()`.

### ChromaDB Vector Store

**File:** `chroma_store/vector_store.py`

Persistent vector embeddings for semantic symbol search. Uses Sentence-Transformers for embedding generation. Falls back gracefully if ChromaDB unavailable.

### Laboratory

**Files:** `laboratory/experiment.py`, `laboratory/debate.py`

- **ExperimentRunner:** Creates batches of parallel agent variants with different strategies. Uses logistic scoring curves (no arbitrary cliffs). Four winner selection modes.
- **DebateEngine:** After variants complete, runs critique rounds where variants evaluate each other on correctness, completeness, test coverage, simplicity, and safety. Generates consensus synthesis.

### Learning Engine

**Files:** `learning/engine.py`, plus 12 submodule files

**Core:** `engine.py` — Session ingestion, problem classification, pattern extraction, approach efficacy tracking.

**Submodules:**
- `bayesian_predictor.py` — Beta-Binomial posterior with shrinkage priors
- `diff_patterns.py` — Git diff pattern extraction
- `code_diff_analyzer.py` — Code-level fix pattern analysis
- `pattern_merger.py` — Jaccard similarity deduplication
- `health_score.py` — Composite 0-100 codebase health metric
- `hot_zones.py` — Weighted file risk scoring
- `live_monitor.py` — Real-time session risk warnings
- `codebase_qa.py` — Natural language codebase queries
- `session_replay.py` — Semantic session similarity search
- `risk_gate.py` — Pre-commit risk assessment
- `causal_engine.py` — Structural Causal Models (SCM) with do-calculus
- `pr_simulator.py` — Monte Carlo PR outcome simulation
- `temporal_anomaly.py` — Bayesian Online Changepoint Detection (BOCD)
- `intervention_engine.py` — WARN→INTERVENE→ABORT→ESCALATE escalation
- `strategy_evolution.py` — Genetic algorithm strategy optimization
- `speculative_context.py` — LRU-cached context pre-computation
- `transfer_store.py` — Cross-codebase pattern abstraction
- `context_budget.py` — Token-budget-aware context builder

### LLM Providers

**File:** `llm/providers.py`

Factory-based provider system with `LLMProvider` base class. Supports:
- **Ollama** — HTTP API `/api/generate` with real token counts
- **OpenAI** — Chat completions API with structured error handling
- **Anthropic** — Messages API with content block parsing

Custom exceptions: `LLMRateLimitError`, `LLMAuthError`, `LLMTimeoutError`, `LLMConnectionError`, `LLMModelNotFoundError`.

### API Server

**File:** `api_server/server.py`

FastAPI application with:
- API key authentication (constant-time comparison)
- Redis-backed rate limiting with in-memory fallback
- LRU `EngineRegistry` for multi-repo support (thread-safe)
- Path sandboxing for security
- Request ID middleware for observability

### 11 REST Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/bootstrap` | Index codebase |
| GET | `/context` | Generate agent context |
| GET | `/search` | Search symbols |
| GET | `/impact/{symbol}` | Analyze dependency impact |
| GET | `/suggest` | Recommend approach |
| POST | `/experiment` | Create experiment batch |
| POST | `/sessions/ingest` | Record session result |
| GET | `/report` | Improvement report |
| GET | `/stats` | Knowledge graph stats |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |

## Extension Points

1. **New Languages:** Add regex patterns + tree-sitter grammar to `knowledge_graph/indexer.py`
2. **New LLM Providers:** Subclass `LLMProvider` in `llm/providers.py`
3. **New Learning Modules:** Add to `learning/` and wire into `main.py::ShadowEngine`
4. **New Storage Backends:** Implement `StoreProtocol` interface
5. **New API Endpoints:** Add routes in `api_server/server.py`

## Design Decisions

### Why SQLite over PostgreSQL initially?
SQLite WAL mode provides sufficient concurrency for single-node deployments with zero setup. PostgreSQL is planned for multi-tenant, horizontally-scaled deployments.

### Why regex + AST (not pure tree-sitter)?
Python already uses `ast.parse()` for accurate parsing. Tree-sitter is declared as a dependency and will replace regex for TypeScript, JavaScript, Go, and Rust. Regex serves as a fast, zero-setup fallback.

### Why ChromaDB over Pinecone/Weaviate?
ChromaDB runs locally without API keys, supports persistent storage, and integrates with Sentence-Transformers for CPU-based embeddings. This keeps the tool free and self-contained.

### Why logistic scoring curves?
The `_sigmoid_score()` function avoids arbitrary cliffs — a 50-line change scores smoothly differently from a 51-line change. This makes experiment comparison fair and tunable.

---

*Last updated: 2026-05-04*