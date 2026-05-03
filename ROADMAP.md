# Shadow Engineer — Production Readiness Roadmap

**Current State:** v0.2.2 — 155 tests passing, 0 failures, ~75% coverage
**Target:** v1.0.0 — Production-grade for customer-facing SaaS
**Estimated Timeline:** 3–9 weeks depending on scope

---

## Phase 1: Already Completed ✅

| # | Issue | Status | Commit |
|---|-------|--------|--------|
| 1 | `secrets.compare_digest()` for constant-time API key comparison | ✅ Done | `b7f218f` |
| 2 | WAL checkpoint `TRUNCATE` on SQLite close() | ✅ Done | `b7f218f` |
| 3 | Exponential backoff retry (2^n seconds, max 3) for all LLM providers | ✅ Done | `b7f218f` |
| 4 | `StoreProtocol` completed with `get_patterns_by_type()` | ✅ Done | `b7f218f` |
| 5 | ChromaDB skeleton symbols enriched with full symbol data | ✅ Done | `d4a2c7f` |
| 6 | Incremental indexing — `file_hashes` table + hash storage during bootstrap | ✅ Done | `e6b8f03` |

---

## Phase 2: Remaining Critical (Week 1, ~1 week)

### Story 2.1: Structured Logging & Observability
**Effort:** 1 week  
**Priority:** 🔴 Critical  
**Impact:** No structured logging means operators cannot monitor or debug the system in production.
**Status:** ⏳ Not started

**Implementation:**
1. Add `structlog` dependency for structured JSON logging
2. Add request ID middleware (UUID per request, propagated to all log statements)
3. Add `prometheus_client` dependency — expose `/metrics` in Prometheus format
4. Log key operations: bootstrap (duration, symbol count), search (duration), ingest (outcome)
- **Files:** `api_server/server.py`, `main.py`, new `observability.py`
- **Verification:** `GET /metrics` returns Prometheus-formatted metrics

---

## Phase 3: Important — Improves Quality (Week 3–4, ~1 week)

### Story 3.1: AST-Based Docstring Extraction for Python
**Effort:** 3 days  
**Priority:** 🟡 Important  
**Impact:** Current regex-based extraction misses single-line docstrings, decorators, type annotations. Python's `ast` module gives perfect parsing.

**Implementation:**
1. Import `ast` in `indexer.py` — use `ast.parse(content)` for `.py` files
2. Walk AST for `FunctionDef`, `ClassDef`, `AsyncFunctionDef` nodes
3. Extract docstring: `node.body[0].value.value` when first statement is `Expr(Constant(...))`
4. Extract line numbers from `node.lineno` and `node.end_lineno`
5. Fall back to regex for files that fail AST parsing (syntax errors)
- **Files:** `knowledge_graph/indexer.py`
- **Verification:** Single-line `"""doc"""` test must pass (currently fails)

### Story 3.2: Historical Baseline Comparison in Scoring
**Effort:** 2 days  
**Priority:** 🟡 Important  
**Impact:** Scoring treats each PR in isolation. Adding per-file historical baselines makes winner selection smarter.

**Implementation:**
1. Query `session_files` for all changes to each file
2. Compute median change sizes, test failure rates per file
3. Add "historical alignment" dimension (15% weight) to `ScoringConfig`
4. Score based on closeness to historical norms for each file
- **Files:** `laboratory/experiment.py`, `sqlite_store/db.py`
- **Verification:** PR that matches historical patterns scores higher than outlier

### Story 3.3: Strategy Template Configuration
**Effort:** 1 day  
**Priority:** 🟡 Important  
**Impact:** Hardcoded strategies prevent teams from defining custom approaches.

**Implementation:**
1. Accept JSON/YAML file with `[{name, problem_type, approach}]` definitions
2. Default to built-in strategies if no file provided
3. Add `STRATEGIES_FILE` environment variable in FastAPI
- **Files:** `laboratory/experiment.py`, `api_server/server.py`
- **Verification:** Custom strategy file is loaded and used in experiment creation

---

## Phase 4: Enterprise Features (Week 5–8, ~2 weeks)

### Story 4.1: PostgreSQL Backend
**Effort:** 2 weeks  
**Priority:** 🟡 Important (for SaaS)  
**Impact:** SQLite is single-writer. PostgreSQL enables multi-tenant scale with connection pooling and read replicas.

**Implementation:**
1. Create `PostgresStore` class implementing same interface as `SQLiteStore`
2. Use `asyncpg` for async connections
3. Add Alembic for schema migrations
4. Make `ShadowEngine` backend-aware: `ShadowEngine(backend="postgresql", dsn="...")`
- **Files:** New `postgres_store/db.py`, updated `main.py`
- **Verification:** All 155 tests pass against PostgreSQL backend

### Story 4.2: Multi-Tenant Database Isolation
**Effort:** 1 week  
**Priority:** 🔴 Critical (for SaaS)  
**Impact:** All data currently goes into one database. SaaS requires per-organization isolation.

**Implementation:**
1. Add `tenant_id` column to all tables or use separate databases per tenant
2. Add middleware extracting tenant from API key or subdomain
3. Modify all queries to filter by `tenant_id`
4. Add billing integration for session counting per tenant
- **Files:** `sqlite_store/db.py`, `api_server/server.py`, new `tenants.py`

### Story 4.3: Streaming LLM Responses
**Effort:** 2 days  
**Priority:** 🟢 Nice-to-have  
**Impact:** Enables real-time token streaming to UIs, reducing perceived latency.

**Implementation:**
1. Add `generate_stream()` to `LLMProvider` base class
2. Implement for OpenAI (SSE), Anthropic (streaming events), Ollama (subprocess line-by-line)
3. Expose via WebSocket: `GET /stream?task=...`
- **Files:** `llm/providers.py`, `api_server/server.py`

---

## Phase 5: Long-Term Strategic (Month 2–4, ~6 weeks)

### Story 5.1: Distributed Experiment Execution
**Effort:** 3–4 weeks  
**Impact:** Enables 50+ parallel experiments across multiple machines.

### Story 5.2: Admin Dashboard
**Effort:** 2–3 weeks  
**Impact:** Visual insights: KG health, agent performance trends, experiment success rates.

### Story 5.3: Plugin System
**Effort:** 2 weeks  
**Impact:** Custom indexers, scorers, classifiers, providers via Python entry points.

---

## Timeline Summary

| Phase | Stories | Effort | Cumulative | Milestone |
|-------|---------|--------|-----------|-----------|
| **Done** | 1–6 | — | — | v0.2.2 |
| **Phase 2** | 2.1 (logging) | 1 week | 1 week | v0.3.0 — Internal team ready |
| **Phase 3** | 3.1–3.3 | 1 week | 2 weeks | v0.4.0 — Quality improved |
| **Phase 4** | 4.1–4.3 | 2 weeks | 4 weeks | v1.0.0 — SaaS ready |
| **Phase 5** | 5.1–5.3 | 6 weeks | 10 weeks | v1.x — Enterprise ready |

**After Phase 2: Use internally with confidence.**
**After Phase 4: Offer as SaaS to paying customers.**
**After Phase 5: Sell to enterprises with custom integrations.**
