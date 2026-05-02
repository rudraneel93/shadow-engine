# Changelog

All notable changes to Shadow Engineer will be documented in this file.

## [1.0.0] — 2026-05-03

### Added
- **Knowledge Graph Engine:** Persistent codebase indexing with symbol extraction for 7 languages (Python, TypeScript/TSX, JavaScript/JSX, Go, Rust)
- **Laboratory Engine:** Parallel experiment runner with 12 problem-type-aware strategy templates, configurable logistic scoring, and 4 winner selection modes
- **Learning Engine:** Cross-session pattern extraction, approach efficacy tracking with running averages, failure analysis, and confidence-weighted classification (6 tiers)
- **SQLite Backend:** WAL-mode storage with 15 normalized tables, 6 indexes, thread-local connections, and `busy_timeout=5000`
- **ChromaDB Vector Store:** Semantic symbol search with 6-layer graceful degradation (embeddings → ChromaDB → SQLite text → JSON text → in-memory text → empty)
- **FastAPI Server:** 11 REST endpoints with optional API key authentication, Redis-backed rate limiting, thread-safe LRU engine registry, and `/v1/` API versioning
- **CLI Interface:** 10 commands (bootstrap, search, context, suggest, impact, experiment, record, report, stats, metrics, migrate)
- **Open-Inspect Bridge:** Async integration layer for enriching sessions with knowledge graph context and ingesting results into the learning engine
- **Docker Deployment:** Production Dockerfile with health checks, non-root user, and docker-compose.yml with Redis service
- **CI/CD Pipeline:** GitHub Actions workflow with test matrix (Python 3.12/3.13), lint (ruff), build verification, and optional Codecov upload
- **Real LLM Pipeline Verified:** Ollama `qwen3:8b` end-to-end test: 211 symbols indexed, ~1,216 tokens generated in 88.6s, session ingested
- **80 Tests:** 33 knowledge graph + 19 laboratory + 12 learning engine + 16 integration (SQLite + pipeline + bridge), 73% code coverage

### Changed
- N/A (initial release)

### Deprecated
- `KnowledgeGraphStore` (JSON backend) — logs deprecation warning on instantiation. Use `SQLiteStore` via `ShadowEngine()`.

### Fixed
- Regex compilation overhead eliminated (pre-compiled patterns at module load time)
- Write amplification in JSON store eliminated (atomic write-then-rename)
- ChronoDB empty embedding bug fixed (graceful fallback to ChromaDB defaults)
- FastAPI route duplication eliminated (single `APIRouter` mounted at root + `/v1`)
- Report UX improved: shows partial data below confidence threshold with ⚠️ warnings
- Classification accuracy improved: priority-ordered keyword rules prevent misclassification

### Security
- Optional API key authentication via `SHADOW_ENGINE_API_KEY` environment variable
- Redis sliding window rate limiting (100 req/min per client, fail-open on Redis down)
- In-memory rate limiting fallback when Redis is unavailable

---

## Version History

| Version | Date | Type | Description |
|---------|------|------|-------------|
| **1.0.0** | 2026-05-03 | Initial | First public release |