# Shadow Engineer API Documentation

**Version:** 0.7.0
**Base URL:** `http://localhost:8000` (or your deployment URL)
**OpenAPI Spec:** `http://localhost:8000/docs` (Swagger UI) | `http://localhost:8000/redoc` (ReDoc)

---

## Authentication

All authenticated endpoints require an `X-API-Key` header. Authentication is optional — if no API key is configured via the `SHADOW_ENGINE_API_KEY` environment variable, all endpoints are publicly accessible.

```bash
export SHADOW_ENGINE_API_KEY="your-secret-key"
```

Then include the header in all requests:
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/bootstrap -X POST
```

---

## Rate Limiting

Default: **100 requests per 60 seconds per client IP**.

Rate limiting uses Redis (configured via `SHADOW_ENGINE_REDIS_URL`) with an in-memory fallback. When exceeded, returns `429 Too Many Requests`.

Configure via environment variables:
```bash
SHADOW_ENGINE_RATE_LIMIT=100      # requests per window
SHADOW_ENGINE_RATE_WINDOW=60      # window in seconds
SHADOW_ENGINE_REDIS_URL=redis://localhost:6379
```

---

## Endpoints

All endpoints are available at both the root path and `/v1/` prefix for API versioning.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/bootstrap` | Index entire codebase into knowledge graph |
| `GET` | `/context?task=...` | Get knowledge graph context for agent prompt |
| `GET` | `/search?query=...` | Search knowledge graph for symbols |
| `GET` | `/impact/{symbol_name}` | Analyze change impact of a symbol |
| `GET` | `/suggest?task=...` | Get best approach suggestion based on history |
| `POST` | `/experiment?task=...` | Create parallel experiment batch |
| `POST` | `/sessions/ingest` | Record completed session for learning |
| `GET` | `/report` | Get improvement report |
| `GET` | `/stats` | Get knowledge graph statistics |
| `GET` | `/metrics` | Get operational metrics |
| `GET` | `/health` | Health check |

---

### `POST /bootstrap`

Index the entire codebase and populate the knowledge graph. This is the first step — call once when setting up Shadow Engineer for a new repository. Idempotent; subsequent calls re-index the codebase.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Path to repository to index |

**Response** (200):

```json
{
  "status": "bootstrapped",
  "repository": "shadow-engine",
  "symbols_indexed": 211,
  "files_indexed": 26,
  "semantic_search": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"bootstrapped"` on success |
| `repository` | string | Repository name |
| `symbols_indexed` | integer | Number of symbols (functions, classes, etc.) extracted |
| `files_indexed` | integer | Number of source files parsed |
| `semantic_search` | boolean | Whether ChromaDB vector search is enabled |

**Example:**
```bash
curl -X POST http://localhost:8000/bootstrap?repo=.

# Index a different repository
curl -X POST http://localhost:8000/bootstrap?repo=/path/to/other/repo
```

---

### `GET /context`

Get a knowledge graph context block to inject into an agent prompt. The context includes six layers of intelligence: problem classification, historical insight, proven fix patterns (deduplicated), code-level diff patterns from git history, test risk by file, Bayesian risk assessment, and semantic symbol context. Uses ChromaDB semantic search when available, falling back to text-based search.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task description the agent will work on |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200):

```json
{
  "context": "## Codebase Knowledge Graph Context (Semantic)\n\n### Semantically Relevant Symbols\n\n- **authenticate_user** (`function`) in `src/auth/service.py` (relevance: 0.89)\n  Authenticate a user from a JWT token.\n  Depends on: UserModel, TokenService, hash_password\n\n..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `context` | string | Natural language context block to prepend to agent prompts |

**Example:**
```bash
curl "http://localhost:8000/context?task=fix+the+login+rate+limiting+bug" | jq -r '.context'
```

---

### `GET /search`

Search the knowledge graph for symbols matching a query. Uses ChromaDB semantic search when available.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query (symbol name, keyword, or concept) |
| `kind` | string | No | Filter by symbol kind: `function`, `method`, `class`, `interface`, `enum`, `type_alias` |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200):

```json
{
  "results": [
    {
      "id": "a1b2c3d4e5f6a7b8",
      "name": "authenticate_user",
      "kind": "function",
      "file_path": "src/auth/service.py",
      "signature": "def authenticate_user(token: str) -> User:",
      "docstring": "Authenticate a user from a JWT token.",
      "complexity": 4.5
    }
  ],
  "total": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | List of matching symbols |
| `results[].id` | string | Unique symbol ID (SHA-256 truncated) |
| `results[].name` | string | Symbol name |
| `results[].kind` | string | Symbol kind (`function`, `class`, `method`, etc.) |
| `results[].file_path` | string | File path relative to repo root |
| `results[].signature` | string | Symbol signature (first 100 characters) |
| `results[].docstring` | string | Documentation string (first 200 characters) |
| `results[].complexity` | number | Cyclomatic complexity score |
| `total` | integer | Total number of matching symbols |

**Example:**
```bash
curl "http://localhost:8000/search?query=authenticate&kind=function" | jq '.'
```

---

### `GET /impact/{symbol_name}`

Analyze the change impact of a symbol. Shows what depends on it, what it depends on, and the full impact radius.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol_name` | string | Name of the symbol to analyze |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "symbol": {
    "name": "UserService",
    "kind": "class",
    "file_path": "src/services/user.py"
  },
  "dependencies": ["Database", "CacheClient", "EmailService"],
  "direct_dependents": ["AuthController", "ProfileController", "AdminController"],
  "impact_radius": ["AuthController", "ProfileController", "AdminController", "LoginWidget", "UserSettingsPage"],
  "total_affected_symbols": 18
}
```

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | object | The matched symbol |
| `dependencies` | array | Symbols this symbol depends on |
| `direct_dependents` | array | Symbols that directly depend on this symbol |
| `impact_radius` | array | All symbols affected by changing this symbol (BFS depth 2) |
| `total_affected_symbols` | integer | Total number of symbols in the impact radius |

**Response** (404):

```json
{
  "detail": "No symbol found matching 'NonExistentSymbol'"
}
```

**Example:**
```bash
curl "http://localhost:8000/impact/authenticate_user" | jq '.'
```

---

### `GET /suggest`

Suggest the best approach and model for a task based on historical learning data. Returns classification confidence and evidence.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task description to classify and suggest approach for |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200):

```json
{
  "problem_type": "bug_fix",
  "classification_confidence": 0.95,
  "recommended_approach": "Targeted Fix",
  "expected_success_rate": 0.85,
  "best_model": "claude-sonnet-4-6",
  "confidence": 0.85
}
```

| Field | Type | Description |
|-------|------|-------------|
| `problem_type` | string | Classified problem type (`bug_fix`, `feature`, `refactor`, `testing`, `migration`, `documentation`, `general`) |
| `classification_confidence` | number | Confidence in the classification (0.0–1.0) |
| `recommended_approach` | string | Best approach based on historical data |
| `expected_success_rate` | number | Expected success rate based on prior attempts (0.0–1.0) |
| `best_model` | string | Model that historically performs best for this approach |
| `confidence` | number | Overall recommendation confidence (0.0–1.0) |

**Response when no historical data:**

```json
{
  "problem_type": "refactor",
  "classification_confidence": 0.75,
  "recommended_approach": "Use a balanced approach following existing codebase conventions.",
  "expected_success_rate": 0.0,
  "best_model": "unknown",
  "confidence": 0.0
}
```

**Example:**
```bash
curl "http://localhost:8000/suggest?task=fix+the+login+rate+limiting+bug" | jq '.'
```

---

### `POST /experiment`

Create a parallel experiment batch. Given a task, creates N parallel variants with different strategies and models. Use this before spawning agent sessions.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | (required) | Task description |
| `variants` | integer | `3` | Number of parallel variants (1–10) |
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "batch_id": "a1b2c3d4e5f6a7b8",
  "task": "fix the login rate limiting bug",
  "total_variants": 3,
  "completed": 0,
  "failed": 0,
  "pending": 3,
  "running": 0,
  "winner": null,
  "variants": [
    {
      "name": "Targeted Fix",
      "approach": "Analyze the error precisely. Find the minimal code change needed...",
      "model": "default",
      "status": "pending",
      "score": 0.0,
      "tests_passed": 0,
      "tests_failed": 0,
      "lines_changed": 0,
      "duration_s": 0.0,
      "tokens": 0,
      "pr_url": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | string | Unique batch identifier (16 hex characters) |
| `task` | string | Task description (first 200 characters) |
| `total_variants` | integer | Total number of variants |
| `completed` | integer | Number of completed variants |
| `failed` | integer | Number of failed variants |
| `pending` | integer | Number of pending variants |
| `running` | integer | Number of currently running variants |
| `winner` | string or null | Winner variant ID (null until scored) |
| `variants` | array | List of experiment variants |
| `variants[].name` | string | Human-readable variant name |
| `variants[].approach` | string | Strategy description for the agent |
| `variants[].model` | string | Model to use for this variant |
| `variants[].status` | string | Current status (`pending`, `running`, `completed`, `failed`) |
| `variants[].score` | number | Computed score (0–100) |
| `variants[].tests_passed` | integer | Number of tests passed |
| `variants[].tests_failed` | integer | Number of tests failed |
| `variants[].lines_changed` | integer | Total lines added + removed |
| `variants[].duration_s` | number | Execution duration in seconds |
| `variants[].tokens` | integer | Token count |
| `variants[].pr_url` | string or null | Pull request URL |

**Example:**
```bash
curl -X POST "http://localhost:8000/experiment?task=refactor+the+billing+module&variants=3" | jq '.'
```

---

### `POST /sessions/ingest`

Record a completed agent session for learning. Call this after every agent session completes (success or failure). Feeds the learning engine.

**Request Body**

<tool_call name="write_to_file">
<path>/Users/rudraneeldas/Desktop/shadow-engine/API_DOCS.md</path>
<content>
# Shadow Engineer API Documentation

**Version:** 1.0.0
**Base URL:** `http://localhost:8000` (or your deployment URL)
**OpenAPI Spec:** `http://localhost:8000/docs` (Swagger UI) | `http://localhost:8000/redoc` (ReDoc)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Rate Limiting](#rate-limiting)
3. [Endpoints](#endpoints)
   - [POST /bootstrap](#post-bootstrap)
   - [GET /context](#get-context)
   - [GET /search](#get-search)
   - [GET /impact/{symbol_name}](#get-impactsymbol_name)
   - [GET /suggest](#get-suggest)
   - [POST /experiment](#post-experiment)
   - [POST /sessions/ingest](#post-sessionsingest)
   - [GET /report](#get-report)
   - [GET /stats](#get-stats)
   - [GET /metrics](#get-metrics)
   - [GET /health](#get-health)
4. [Error Responses](#error-responses)
5. [Integration Guide](#integration-guide)
6. [SDK Examples](#sdk-examples)

---

## Authentication

All authenticated endpoints require an `X-API-Key` header. Authentication is **optional** — if no API key is configured via the `SHADOW_ENGINE_API_KEY` environment variable, all endpoints are publicly accessible.

```bash
export SHADOW_ENGINE_API_KEY="your-secret-key"
```

Include the header in all requests:
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/health
```

If authentication is enabled and the header is missing or incorrect, returns `401 Unauthorized`:
```json
{"detail": "Invalid or missing API key"}
```

---

## Rate Limiting

Default: **100 requests per 60 seconds per client IP**.

Rate limiting uses Redis (configured via `SHADOW_ENGINE_REDIS_URL`) with an in-memory fallback when Redis is unavailable. When exceeded, returns `429 Too Many Requests` with:
```json
{"detail": "Rate limit exceeded. Try again shortly."}
```

Configure via environment variables:
```bash
SHADOW_ENGINE_RATE_LIMIT=100      # requests per window
SHADOW_ENGINE_RATE_WINDOW=60      # window in seconds
SHADOW_ENGINE_REDIS_URL=redis://localhost:6379
```

---

## Endpoints

All endpoints are available at both the root path (`/`) and the versioned prefix (`/v1/`).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/bootstrap` | Index entire codebase into knowledge graph |
| `GET` | `/context?task=...` | Get knowledge graph context for agent prompt |
| `GET` | `/search?query=...` | Search knowledge graph for symbols |
| `GET` | `/impact/{symbol_name}` | Analyze change impact of a symbol |
| `GET` | `/suggest?task=...` | Get best approach suggestion based on history |
| `POST` | `/experiment?task=...` | Create parallel experiment batch |
| `POST` | `/sessions/ingest` | Record completed session for learning |
| `GET` | `/report` | Get improvement report |
| `GET` | `/stats` | Get knowledge graph statistics |
| `GET` | `/metrics` | Get operational metrics |
| `GET` | `/health` | Health check |

---

### `POST /bootstrap`

Index the entire codebase and populate the knowledge graph. Call once when setting up for a new repository. Idempotent — subsequent calls re-index.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Path to repository to index |

**Response** (200):

```json
{
  "status": "bootstrapped",
  "repository": "shadow-engine",
  "symbols_indexed": 211,
  "files_indexed": 26,
  "semantic_search": true
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/bootstrap?repo=.

# Index a different repository
curl -X POST "http://localhost:8000/bootstrap?repo=/path/to/other/repo"
```

---

### `GET /context`

Get a knowledge graph context block to inject into an agent prompt. Uses ChromaDB semantic search when available, falling back to text-based search.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task description for the agent |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200):

```json
{
  "context": "## Codebase Knowledge Graph Context (Semantic)\n\n### Semantically Relevant Symbols\n\n- **authenticate_user** (`function`) in `src/auth/service.py` (relevance: 0.89)\n  Authenticate a user from a JWT token.\n  Depends on: UserModel, TokenService\n\n..."
}
```

**Example:**
```bash
curl "http://localhost:8000/context?task=fix+the+login+rate+limiting+bug" | jq -r '.context'
```

---

### `GET /search`

Search the knowledge graph for symbols. Uses ChromaDB semantic search when available.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `kind` | string | No | Filter by kind: `function`, `method`, `class`, `interface`, `enum`, `type_alias` |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200):

```json
{
  "results": [
    {
      "id": "a1b2c3d4e5f6a7b8",
      "name": "authenticate_user",
      "kind": "function",
      "file_path": "src/auth/service.py",
      "complexity": 4.5
    }
  ],
  "total": 1
}
```

**Example:**
```bash
curl "http://localhost:8000/search?query=authenticate&kind=function" | jq '.'
```

---

### `GET /impact/{symbol_name}`

Analyze the change impact of a symbol — shows what depends on it and what it depends on.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol_name` | string | Name of the symbol to analyze |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "symbol": {"name": "UserService", "kind": "class", "file_path": "src/services/user.py"},
  "dependencies": ["Database", "CacheClient", "EmailService"],
  "direct_dependents": ["AuthController", "ProfileController"],
  "impact_radius": ["AuthController", "ProfileController", "AdminController", "LoginWidget"],
  "total_affected_symbols": 18
}
```

**Response** (404):
```json
{"detail": "No symbol found matching 'NonExistent'"}
```

**Example:**
```bash
curl "http://localhost:8000/impact/authenticate_user" | jq '.'
```

---

### `GET /suggest`

Suggest the best approach and model for a task based on historical learning data.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | Yes | Task description to classify and suggest approach for |
| `repo` | string | No | Repository path (default: current directory) |

**Response** (200) — with historical data:

```json
{
  "problem_type": "bug_fix",
  "classification_confidence": 0.95,
  "recommended_approach": "Targeted Fix",
  "expected_success_rate": 0.85,
  "best_model": "claude-sonnet-4-6",
  "confidence": 0.85
}
```

**Response** (200) — no historical data:

```json
{
  "problem_type": "refactor",
  "classification_confidence": 0.75,
  "recommended_approach": "Use a balanced approach following existing codebase conventions.",
  "expected_success_rate": 0.0,
  "best_model": "unknown",
  "confidence": 0.0
}
```

**Example:**
```bash
curl "http://localhost:8000/suggest?task=fix+the+login+rate+limiting+bug" | jq '.'
```

---

### `POST /experiment`

Create a parallel experiment batch with N variants using different strategies.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | (required) | Task description |
| `variants` | integer | `3` | Number of parallel variants (1–10) |
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "batch_id": "a1b2c3d4e5f6a7b8",
  "task": "fix the login rate limiting bug",
  "total_variants": 3,
  "completed": 0,
  "failed": 0,
  "pending": 3,
  "running": 0,
  "winner": null,
  "variants": [
    {
      "name": "Targeted Fix",
      "approach": "Analyze the error precisely. Find the minimal code change needed...",
      "model": "default",
      "status": "pending",
      "score": 0.0,
      "tests_passed": 0,
      "tests_failed": 0,
      "lines_changed": 0,
      "duration_s": 0.0,
      "tokens": 0,
      "pr_url": null
    },
    {
      "name": "Root Cause + Guard",
      "approach": "Find the root cause of the bug. Fix it, then add input validation...",
      "model": "default",
      "status": "pending",
      "score": 0.0,
      "tests_passed": 0,
      "tests_failed": 0,
      "lines_changed": 0,
      "duration_s": 0.0,
      "tokens": 0,
      "pr_url": null
    },
    {
      "name": "Defense in Depth",
      "approach": "Fix the bug, add comprehensive error handling at every layer...",
      "model": "default",
      "status": "pending",
      "score": 0.0,
      "tests_passed": 0,
      "tests_failed": 0,
      "lines_changed": 0,
      "duration_s": 0.0,
      "tokens": 0,
      "pr_url": null
    }
  ]
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/experiment?task=refactor+the+billing+module&variants=3" | jq '.'
```

---

### `POST /sessions/ingest`

Record a completed agent session for learning. Call after every session completes (success or failure).

**Request Body:**

```json
{
  "session_id": "sess-abc123",
  "outcome": "success",
  "prompt": "fix the login rate-limiting bug",
  "approach": "Targeted Fix",
  "model": "claude-sonnet-4-6",
  "pr_url": "https://github.com/myorg/myrepo/pull/142",
  "files_changed": ["src/auth/service.py", "tests/auth/test_service.py"],
  "tests_passed": 12,
  "tests_failed": 0,
  "review_comments": ["LGTM!", "Clean fix"],
  "duration_seconds": 45.2,
  "token_count": 8500
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Unique session identifier |
| `outcome` | string | Yes | `success`, `failure`, `rejected`, or `abandoned` |
| `prompt` | string | Yes | The task the agent was given |
| `approach` | string | No | Strategy used (default: `""`) |
| `model` | string | No | Model used (default: `"default"`) |
| `pr_url` | string | No | Pull request URL if created |
| `files_changed` | array | No | List of file paths modified |
| `tests_passed` | integer | No | Number of tests passed |
| `tests_failed` | integer | No | Number of tests failed |
| `review_comments` | array | No | Code review comments received |
| `duration_seconds` | number | No | Session wall-clock time |
| `token_count` | integer | No | Total tokens consumed |

**Response** (200):

```json
{
  "status": "ingested",
  "problem_type": "bug_fix",
  "classification_confidence": 0.95,
  "was_successful": true,
  "patterns_learned": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ingested"` on success, `"skipped"` for in-progress sessions |
| `problem_type` | string | Classified problem type |
| `classification_confidence` | number | Confidence in the classification (0.0–1.0) |
| `was_successful` | boolean | Whether the session succeeded |
| `patterns_learned` | integer | Number of codebase patterns extracted |

**Example:**
```bash
curl -X POST http://localhost:8000/sessions/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "outcome": "success",
    "prompt": "fix the login bug",
    "approach": "Targeted Fix",
    "model": "claude-sonnet-4-6",
    "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "tests_passed": 10,
    "tests_failed": 0,
    "duration_seconds": 30.0,
    "token_count": 5000
  }' | jq '.'
```

---

### `GET /report`

Get a comprehensive improvement report showing knowledge graph health, agent performance, and most effective approaches.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Repository path |

**Response** (200, text/plain):

```
============================================================
  SHADOW ENGINEER — IMPROVEMENT REPORT
============================================================

### Knowledge Graph Health
  Total symbols indexed: 211
  Total files indexed:   26
  Patterns learned:      3
  Graph nodes:           211
  Graph edges:           12

### Agent Performance
  Total sessions:        8
  Completed:             8
  Successful:            6
  Overall success rate:  75.0%

### Most Effective Approaches

  1. [bug_fix] Targeted Fix
     Success: 85% (17/20)
     Best model: claude-sonnet-4-6
     Avg duration: 42s

  2. [feature] Extensible Design
     Success: 72% (13/18)
     Best model: claude-opus-4-6
     Avg duration: 68s
============================================================
```

**Example:**
```bash
curl "http://localhost:8000/report"
```

---

### `GET /stats`

Get knowledge graph statistics as JSON.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "total_symbols": 211,
  "total_files": 26,
  "total_sessions": 8,
  "successful_sessions": 6,
  "overall_success_rate": 0.75
}
```

**Example:**
```bash
curl "http://localhost:8000/stats" | jq '.'
```

---

### `GET /metrics`

Get operational metrics including usage counters, timing data, and ChromaDB symbol count.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | `.` | Repository path |

**Response** (200):

```json
{
  "bootstraps": 2,
  "searches": 45,
  "sessions_recorded": 8,
  "contexts_generated": 12,
  "experiments_created": 3,
  "total_index_time_ms": 1234.0,
  "total_search_time_ms": 567.0,
  "knowledge_graph": {
    "total_symbols": 211,
    "total_files": 26,
    "total_patterns": 5,
    "total_sessions": 8,
    "completed_sessions": 8,
    "successful_sessions": 6,
    "overall_success_rate": 0.75,
    "total_approaches_tracked": 12,
    "graph_nodes": 211,
    "graph_edges": 28
  },
  "chromadb_symbols": 211
}
```

**Example:**
```bash
curl "http://localhost:8000/metrics" | jq '.'
```

---

### `GET /health`

Health check endpoint — not rate-limited, no authentication required.

**Response** (200):

```json
{
  "status": "ok",
  "timestamp": "2026-05-03T04:50:00+05:30",
  "version": "1.0.0"
}
```

**Example:**
```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/v1/health"
```

---

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Invalid request (e.g., wrong outcome value) |
| `401` | Missing or invalid API key (when auth is enabled) |
| `404` | Symbol or resource not found |
| `422` | Validation error (e.g., required field missing) |
| `429` | Rate limit exceeded |

---

## Integration Guide

### Integrating with Open-Inspect

Shadow Engineer provides an async bridge for Open-Inspect:

```python
from shadow_engine.integrations.openinspect import OpenInspectBridge

bridge = OpenInspectBridge(repo_path="/path/to/your/repo")
bridge.bootstrap_if_needed()

# Before spawning a session — enrich the prompt
config = {
    "prompt": "fix the login rate-limiting bug",
    "repository": "my-repo",
}
enriched = await bridge.enrich_session_config(config)
# enriched["prompt"] now contains knowledge graph context prepended
# enriched["suggested_approach"] = "Targeted Fix"
# enriched["suggested_model"] = "claude-sonnet-4-6"

# After session completes — ingest the result
result = {
    "session_id": "sess-abc123",
    "outcome": "completed",
    "prompt": "fix the login rate-limiting bug",
    "approach": "Targeted Fix",
    "model": "claude-sonnet-4-6",
    "pr_url": "https://github.com/myorg/myrepo/pull/142",
    "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "tests_passed": 12,
    "tests_failed": 0,
    "duration_seconds": 45.2,
    "token_count": 8500,
}
ingestion = await bridge.ingest_session_result(result)
```

### Typical Workflow

```
1. POST /bootstrap                    # Index the codebase
2. GET  /context?task=...             # Get knowledge graph context
3. GET  /suggest?task=...             # Get approach recommendation
4. POST /experiment?task=...&variants=3  # (optional) Create experiment batch
5. [Agent executes the task in background]
6. POST /sessions/ingest              # Record the result
7. GET  /report                       # View improvement
```

### Python SDK (Minimal)

```python
import httpx

class ShadowEngineClient:
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key} if api_key else {}

    def bootstrap(self, repo: str = ".") -> dict:
        r = httpx.post(f"{self.base_url}/bootstrap", params={"repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def get_context(self, task: str, repo: str = ".") -> str:
        r = httpx.get(f"{self.base_url}/context", params={"task": task, "repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()["context"]

    def search(self, query: str, kind: str | None = None, repo: str = ".") -> dict:
        params = {"query": query, "repo": repo}
        if kind:
            params["kind"] = kind
        r = httpx.get(f"{self.base_url}/search", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def suggest(self, task: str, repo: str = ".") -> dict:
        r = httpx.get(f"{self.base_url}/suggest", params={"task": task, "repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def ingest_session(self, **kwargs) -> dict:
        r = httpx.post(f"{self.base_url}/sessions/ingest", json=kwargs, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def get_report(self, repo: str = ".") -> str:
        r = httpx.get(f"{self.base_url}/report", params={"repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.text

    def health(self) -> dict:
        r = httpx.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()
```

Usage:
```python
client = ShadowEngineClient(api_key="your-secret-key")
client.bootstrap()
context = client.get_context("fix the login rate-limiting bug")
suggestion = client.suggest("fix the login rate-limiting bug")
client.ingest_session(
    session_id="sess-001",
    outcome="success",
    prompt="fix the login bug",
    approach="Targeted Fix",
    model="claude-sonnet-4-6",
    files_changed=["src/auth.py", "tests/test_auth.py"],
    tests_passed=10,
    tests_failed=0,
    duration_seconds=30.0,
    token_count=5000,
)
print(client.get_report())