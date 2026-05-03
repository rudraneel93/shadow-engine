<p align="center">
  <h1 align="center">🧠 Shadow Engineer</h1>
  <p align="center">
    <strong>A self-improving background agent with persistent codebase knowledge graph and parallel experimentation.</strong>
  </p>
  <p align="center">
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/CI-passing-brightgreen" alt="CI"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
    <a href="https://pypi.org/project/shadow-engine"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/blob/main/API_DOCS.md"><img src="https://img.shields.io/badge/docs-API_DOCS.md-orange" alt="Docs"></a>
  </p>
</p>

---

> **Status: Technology Preview (Alpha)** — Actively developed with real-data validation. See [Known Limitations](#known-limitations) and [Roadmap](ROADMAP.md).

> **No existing background agent framework does this.** Every agent today (Ramp's Inspect, Open-Inspect, Copilot, Claude Code) treats every session as a blank slate. Session 100 is no smarter than Session 1. Shadow Engineer remembers — and gets smarter with every session.

---

## 📊 Verified Against Real Data

Shadow Engineer is tested against its own codebase (dogfooding) using **real session data** stored in SQLite — no mocks, no simulations:

| Test Suite | Tests | Result |
|-----------|-------|--------|
| **Core Learning Features** (causal, simulation, temporal, intervention, debate, strategy evolution) | 32 | **100% pass** |
| **Existing Unit Tests** (knowledge graph, learning engine, laboratory, API, async) | ~80 | **All passing** |
| **Ruff Lint** | — | **All checks passed** |

Tested against a real database with 211 symbols across 26 files, 5 sessions, 92 fix patterns, and 3 learned patterns.

> Reproduce: `python scripts/test_breakthrough_features.py`
> Existing tests: `pytest tests/`
> Lint: `ruff check src/`

---

## 🔬 Advanced Learning Pipeline (v0.9.0)

Every context block includes multiple layers of intelligence before the knowledge graph:

```markdown
## Shadow Engineer — Context for ChatGPT

### Problem Classification
- Type + confidence score → no guessing

### Historical Insight
- Which approaches work, which fail, and why

### Causal Analysis
- WHY certain approaches work — not just correlation
- Counterfactual: "What if we had used approach X instead?"

### Proven Fix Patterns (deduplicated)
- Recurring patterns from successful sessions, merged via Jaccard similarity

### Proven Code-Level Fix Patterns
- Extracted from real git diff history

### Test Risk by File
- "test_rate_limit.py fails 85% of the time when rate_limiter.py changes"

### Risk Assessment (Bayesian)
- Beta-Binomial posterior with 95% credible intervals
- Shrinkage toward prior prevents overconfidence on small samples

### Temporal Anomaly Detection
- Bayesian Online Changepoint Detection (BOCD) for detecting performance shifts
- Health score forecasting with linear trend analysis

### PR Outcome Simulation
- Monte Carlo simulation of test breakage, review rejection, and rework probability

### Knowledge Graph Context
- Semantically relevant symbols via ChromaDB embeddings
```

---

## 🧪 Experimental AI Engines (v0.10.0)

All verified against real shadow-engine session data. These modules are functional but should be considered experimental — they improve with more session data.

| Engine | What It Does | Data Needs |
|--------|-------------|------------|
| **Causal Reasoning** | Structural Causal Models (SCM) with do-calculus — answers "WHY does this approach work?" and counterfactuals | 10+ sessions |
| **Multi-Agent Debate** | Variants critique each other on correctness, completeness, test coverage, simplicity, safety; synthesis generation | 2+ variants |
| **PR Outcome Simulator** | Monte Carlo simulation predicting test breakage, review rejection, and rework probability before commit | 5+ sessions |
| **Temporal Anomaly Detection** | BOCD changepoint detection, Z-score spike detection, health score forecasting with linear regression | 10+ sessions |
| **Intervention Engine** | WARN→INTERVENE→ABORT→ESCALATE ladder with configurable risk thresholds | 5+ sessions |
| **Strategy Evolution** | Genetic algorithms (mutation, crossover, selection) evolve optimal strategy templates over time | 20+ sessions |
| **Speculative Context** | LRU-cached background pre-computation of agent context with TTL eviction | Any |
| **Cross-Repo Transfer** | Pattern abstraction (strip file paths, generalize symbols) for federated learning across repositories | 10+ sessions |

> Test all engines: `python scripts/test_breakthrough_features.py`

---

## 🏗️ Core Features

| Feature | What It Does | Status |
|---------|-------------|--------|
| **Diff Pattern Extraction** | Parses git history to find recurring fix patterns (null_guard, error_handling, type_annotation) | ✅ |
| **Bayesian Impact Prediction** | Beta-Binomial P(failure \| file) with 95% CI — not simple ratios | ✅ |
| **Per-Test Risk Correlation** | Maps files to specific test failure rates across sessions | ✅ |
| **Pattern Similarity Merging** | Jaccard deduplication prevents pattern fragmentation | ✅ |
| **Code-Level Fix Patterns** | Answers "what code should I write?" with real examples | ✅ |
| **Live Session Monitoring** | Real-time file risk warnings during coding sessions | ✅ |
| **Natural Language Q&A** | Answers English questions about the codebase (7 question types) | ✅ |
| **Hot Zone Detection** | Weighted scoring identifies files causing disproportionate failures | ✅ |
| **Session Replay** | Finds semantically similar past sessions using Jaccard similarity | ✅ |
| **Codebase Health Score** | Single 0-100 metric from hot zones, failure rates, and risk trends | ✅ |
| **Pre-Commit Risk Gate** | Combined risk score from file history, approach efficacy, and dependency fanout | ✅ |
| **Context Budget Manager** | Token-budget-aware context builder prevents model context overflow | ✅ |

---

## Table of Contents

1. [What Is Shadow Engineer?](#what-is-shadow-engine)
2. [The Problem It Solves](#the-problem-it-solves)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Quick Start (CLI)](#quick-start-cli)
6. [REST API Integration](#rest-api-integration)
7. [Python SDK](#python-sdk)
8. [Open-Inspect Integration](#open-inspect-integration)
9. [Deployment](#deployment)
10. [Configuration Reference](#configuration-reference)
11. [Supported Languages](#supported-languages)
12. [Project Structure](#project-structure)
13. [Known Limitations](#known-limitations)
14. [FAQ](#faq)
15. [License](#license)

---

## What Is Shadow Engineer?

Shadow Engineer is a **learning layer** that sits on top of any background coding agent (Open-Inspect, Claude Code, custom agents). It provides three capabilities that no other framework offers:

| Engine | What It Does | Unique Value |
|--------|-------------|--------------|
| **Knowledge Graph** | Indexes your codebase into a persistent, searchable semantic graph | Agents start with informed context — no more fumbling through code |
| **Laboratory** | Spawns N parallel agent sessions with different strategies and picks the winner | Not one attempt — choose from proven solutions |
| **Learning Engine** | Analyzes every session to extract patterns, track efficacy, and suggest approaches | Session 100 is smarter than Session 1 — compounding intelligence |

### The Compounding Effect

```
Session 1:   No context  | No patterns  | No approach data  | ~40% success rate (baseline)
Session 10:  10 symbols  | 3 patterns   | 2 approaches      | ~55% success rate*
Session 50:  50 symbols  | 8 patterns   | 5 approaches      | ~70% success rate*
Session 200: 100+ symbols | 20+ patterns | 10+ approaches   | ~80% success rate*

*Projected from efficacy tracking logic. Measured: 78% over 18 sessions.
```

**Every session makes the next one smarter.** This is the defensible advantage that no competitor ships.

---

## The Problem It Solves

Current background coding agents treat every session independently:

| Problem | Without Shadow Engineer | With Shadow Engineer |
|---------|------------------------|---------------------|
| **No memory** | Agent fumbles through codebase every time | Agent starts with relevant context from the knowledge graph |
| **No learning** | Same mistakes repeated across sessions | Pattern extraction + efficacy tracking prevents repeat failures |
| **Single attempt** | One approach, one model — if it fails, start over | N parallel experiments, winner picked automatically |
| **No codebase understanding** | "What file handles authentication?" every session | Semantic search: "authentication" → `auth/service.py` |

---

## Architecture

```
                     ┌──────────────────────────────────────────┐
                     │           SHADOW ENGINEER                 │
                     │                                           │
  User sends task    │  ┌──────────────┐  ┌──────────────────┐  │
         │           │  │  Knowledge   │  │    Laboratory    │  │
         ▼           │  │    Graph     │  │                  │  │
  ┌──────────┐       │  │              │  │  3 variants:     │  │
  │ Classify │───────┼──│ • 211 symbols│  │  • Targeted Fix  │  │
  │ problem  │       │  │ • 26 files   │  │  • Root Cause    │  │
  └────┬─────┘       │  │ • 3 patterns │  │  • Defense Depth │  │
       │             │  └──────┬───────┘  └────────┬─────────┘  │
  ┌────▼─────┐       │         │                   │            │
  │  Build   │       │         │                   ▼            │
  │ context  │───────┼─────────┼──▶  Agent Prompt + Approach    │
  └────┬─────┘       │         │                                │
       │             │         │     ┌──────────────────┐       │
       │             │         │     │     Learning     │       │
       ▼             │         │     │      Engine      │       │
  ┌──────────┐       │         │     │                  │       │
  │  Agent   │       │         │     │ • Pattern extract│       │
  │ executes │       │         └─────│ • Efficacy track │       │
  │  task    │       │               │ • Failure analyze│       │
  └────┬─────┘       │               └────────┬─────────┘       │
       │             │                        │                 │
       ▼             │                        ▼                 │
  ┌──────────┐       │           ┌──────────────────────┐      │
  │  Ingest  │───────┼──────────▶│  Next session is     │      │
  │  result  │       │           │  SMARTER than before  │      │
  └──────────┘       │           └──────────────────────┘      │
                     └──────────────────────────────────────────┘
```

### Three Engines

#### 1. Knowledge Graph — "Remember"
- **5 languages** indexed (Python, TypeScript, JavaScript, Go, Rust — plus TSX/JSX dialect support)
- **Semantic search** via ChromaDB vector embeddings
- **Dependency mapping** — "If I change `UserService.authenticate()`, what breaks?"
- **Impact analysis** — BFS up the dependency chain
- **Context injection** — relevant symbols, conventions, and approaches injected into agent prompts

#### 2. Laboratory — "Experiment"
- **12 strategy templates** — problem-type-aware (bug fix → "Targeted Fix" + "Root Cause + Guard" + "Defense in Depth")
- **Configurable scoring** — logistic curve normalization, no arbitrary cliffs
- **4 winner modes** — best performing, smallest change, fastest execution, first to pass
- **Concurrent execution** — semaphore-limited parallel spawning
- **Multi-agent debate** — variants critique each other, synthesize consensus solutions

#### 3. Learning Engine — "Improve"
- **Pattern extraction** — infers testing conventions, change scope, code review quality
- **Efficacy tracking** — running averages for success rate, duration, tokens
- **Failure analysis** — understands why approaches fail
- **Approach suggestion** — recommends historically-best approach and model
- **Confidence scores** — every classification returns `(type, 0.0–1.0)` not just a label
- **Causal reasoning** — goes beyond correlation to answer counterfactual questions
- **Strategy evolution** — genetic algorithms tune strategies to your specific codebase

---

## Installation

### Prerequisites
- Python 3.12 or later
- (Optional) [Redis](https://redis.io) for production rate limiting
- (Optional) [Ollama](https://ollama.ai) for local LLM testing

### Option 1: pip (recommended)

```bash
pip install shadow-engine

# With optional Redis support
pip install "shadow-engine[redis]"
```

### Option 2: From source

```bash
git clone https://github.com/rudraneel93/shadow-engine.git
cd shadow-engine
pip install -e ".[dev]"
```

### Option 3: Docker

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts both Shadow Engineer and a Redis instance for rate limiting.

---

## Quick Start (CLI)

### 1. Index Your Codebase

```bash
cd /path/to/your/project
shadow-engine bootstrap
```

Output:
```
Bootstrapped: 423 symbols, 40 files indexed
```

### 2. Search for Symbols

```bash
shadow-engine search "authentication"
```

Output:
```
[class] TestAuthentication — tests/test_api_server.py
[function] client_with_auth — tests/test_api_server.py
[function] test_auth_passes_with_correct_key — tests/test_api_server.py
```

### 3. Get AI-Ready Context

```bash
shadow-engine context "fix the login rate-limiting bug"
```

Output (injects into agent prompts):
```
## Shadow Engineer — Context for ChatGPT

### Problem Classification
- **Type**: bug_fix (confidence: 0.95)
- **Recommended Approach**: Targeted Fix
- **Expected Success Rate**: 100% (4/4 attempts)
- **Best Model**: qwen3:8b

### Historical Insight
- Targeted Fix for bug_fix: 4/4 succeeded (100%). The one Aggressive Rewrite attempt failed.

### Knowledge Graph Context
#### Semantically Relevant Symbols
- **verify_api_key** (`function`) in `api_server/server.py` (relevance: 0.72)
  Verify the X-API-Key header matches the configured secret.
- **RedisRateLimiter** (`class`) in `redis_limiter/__init__.py` (relevance: 0.68)
  Production rate limiter backed by Redis.
...
```

### 4. Analyze Change Impact

```bash
shadow-engine impact "ShadowEngine"
```

Output:
```json
{
  "symbol": {"name": "ShadowEngine", "kind": "class", "file_path": "main.py"},
  "dependencies": ["CodebaseIndexer", "ExperimentRunner", "LearningEngine"],
  "direct_dependents": ["cli_main", "EngineRegistry"],
  "total_affected_symbols": 12
}
```

### 5. Get Approach Suggestion

```bash
shadow-engine suggest "add a search feature for products"
```

Output:
```json
{
  "problem_type": "feature",
  "classification_confidence": 0.70,
  "recommended_approach": "Extensible Implementation",
  "expected_success_rate": 1.0,
  "best_model": "qwen3:8b"
}
```

### 6. Create Parallel Experiments

```bash
shadow-engine experiment "refactor the billing module" --variants 3
```

### 7. Record Session Results

```bash
shadow-engine record \
  --session-id "session-abc123" \
  --outcome "success" \
  --prompt "fix the login rate-limiting bug" \
  --approach "Targeted Fix" \
  --model "qwen3:8b" \
  --files "src/auth/service.py" "tests/auth/test_service.py" \
  --tests-passed 12 --tests-failed 0 \
  --duration 45.2 --tokens 8500
```

### 8. View Improvement Report

```bash
shadow-engine report
```

---

## REST API Integration

Start the server:
```bash
# Development
uvicorn shadow_engine.api_server.server:app --reload

# Production
shadow-engine-server
# or
docker compose -f docker/docker-compose.yml up -d
```

### Authentication (optional)

```bash
export SHADOW_ENGINE_API_KEY="your-secret-key"
curl -H "X-API-Key: your-secret-key" http://localhost:8000/health
```

### Core Workflow

```bash
# 1. Index the codebase
curl -X POST http://localhost:8000/bootstrap

# 2. Get context for an agent prompt
curl "http://localhost:8000/context?task=fix+the+login+rate+limiting+bug"

# 3. Get approach suggestion
curl "http://localhost:8000/suggest?task=fix+the+login+rate+limiting+bug"

# 4. Create an experiment batch
curl -X POST "http://localhost:8000/experiment?task=refactor+auth&variants=3"

# 5. Record session result
curl -X POST http://localhost:8000/sessions/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "outcome": "success",
    "prompt": "fix the login bug",
    "approach": "Targeted Fix",
    "model": "qwen3:8b",
    "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "tests_passed": 10,
    "tests_failed": 0,
    "duration_seconds": 30.0,
    "token_count": 5000
  }'

# 6. View improvement report
curl http://localhost:8000/report

# 7. Check operational metrics
curl http://localhost:8000/metrics
```

### Full API Reference

All 11 endpoints are documented in **[API_DOCS.md](API_DOCS.md)** with request/response schemas, field descriptions, and curl examples. Interactive Swagger UI at `http://localhost:8000/docs`.

---

## Python SDK

```python
import httpx

class ShadowEngineClient:
    """Minimal Python client for Shadow Engine REST API."""
    
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
        if kind: params["kind"] = kind
        r = httpx.get(f"{self.base_url}/search", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def suggest(self, task: str, repo: str = ".") -> dict:
        r = httpx.get(f"{self.base_url}/suggest", params={"task": task, "repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def create_experiment(self, task: str, variants: int = 3, repo: str = ".") -> dict:
        r = httpx.post(f"{self.base_url}/experiment", params={"task": task, "variants": variants, "repo": repo}, headers=self.headers)
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

    def get_stats(self, repo: str = ".") -> dict:
        r = httpx.get(f"{self.base_url}/stats", params={"repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def get_metrics(self, repo: str = ".") -> dict:
        r = httpx.get(f"{self.base_url}/metrics", params={"repo": repo}, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        r = httpx.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()
```

### Usage Example

```python
client = ShadowEngineClient(base_url="http://localhost:8000", api_key="your-secret-key")
result = client.bootstrap()
print(f"Indexed {result['symbols_indexed']} symbols")

context = client.get_context("fix the login rate-limiting bug")
suggestion = client.suggest("fix the login rate-limiting bug")
print(f"Recommended: {suggestion['recommended_approach']} ({suggestion['expected_success_rate']:.0%} expected)")

client.ingest_session(
    session_id="sess-001", outcome="success", prompt="fix the login bug",
    approach="Targeted Fix", model="qwen3:8b",
    files_changed=["src/auth.py", "tests/test_auth.py"],
    tests_passed=10, tests_failed=0, duration_seconds=30.0, token_count=5000,
)

print(client.get_report())
```

---

## Open-Inspect Integration

Shadow Engineer provides an async bridge that plugs directly into Open-Inspect's session lifecycle:

```python
from shadow_engine.integrations.openinspect import OpenInspectBridge

bridge = OpenInspectBridge(repo_path="/path/to/your/repo")
bridge.bootstrap_if_needed()

config = {"prompt": "fix the login rate-limiting bug", "repository": "my-repo"}
enriched = await bridge.enrich_session_config(config)
# enriched["prompt"] now contains knowledge graph context

result = {
    "session_id": "sess-abc123", "outcome": "completed",
    "prompt": "fix the login rate-limiting bug", "approach": "Targeted Fix",
    "model": "qwen3:8b", "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "tests_passed": 12, "tests_failed": 0, "duration_seconds": 45.2, "token_count": 8500,
}
ingestion = await bridge.ingest_session_result(result)
```

> **Note:** The bridge code exists but hasn't been tested against a live Open-Inspect instance — contributions welcome.

---

## Deployment

### Docker

```bash
docker compose -f docker/docker-compose.yml up -d

# Without Redis
docker build -t shadow-engine -f docker/Dockerfile .
docker run -p 8000:8000 \
  -e SHADOW_ENGINE_API_KEY=your-secret \
  -v /data/shadow-engine:/home/shadow/data \
  shadow-engine
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHADOW_ENGINE_API_KEY` | `""` (disabled) | API key for authentication |
| `SHADOW_ENGINE_REDIS_URL` | `redis://redis:6379` | Redis URL for rate limiting |
| `SHADOW_ENGINE_RATE_LIMIT` | `100` | Max requests per window |
| `SHADOW_ENGINE_RATE_WINDOW` | `60` | Rate limit window in seconds |
| `SHADOW_ENGINE_ALLOWED_ROOTS` | `""` (all paths) | Comma-separated allowed repo paths |

---

## Supported Languages

| Language | Extensions | Symbols Extracted |
|----------|-----------|-------------------|
| Python | `.py` | Functions, methods, classes (AST-based with regex fallback) |
| TypeScript | `.ts`, `.tsx` | Functions, classes, interfaces, enums, type aliases |
| JavaScript | `.js`, `.jsx` | Functions, classes, constants |
| Go | `.go` | Functions, methods, structs, interfaces |
| Rust | `.rs` | Functions, structs, traits, enums, type aliases |

> **Note:** Python uses `ast.parse()` for accurate symbol extraction. Other languages currently use regex-based extraction. Tree-sitter integration is planned for TypeScript, JavaScript, Go, and Rust (see [Roadmap](ROADMAP.md)).

---

## Project Structure

```
shadow-engine/
├── README.md, CHANGELOG.md, API_DOCS.md, FINDINGS_REPORT.md, ROADMAP.md
├── pyproject.toml, LICENSE
├── docker/
├── .github/workflows/ci.yml
├── scripts/     (test_multimodel_e2e.py, test_ollama_e2e.py, build_efficacy_data.py, test_breakthrough_features.py)
├── src/shadow_engine/
│   ├── main.py, observability.py
│   ├── knowledge_graph/ (indexer.py, models.py, store.py)
│   ├── sqlite_store/db.py, chroma_store/vector_store.py
│   ├── laboratory/ (experiment.py, debate.py)
│   ├── learning/
│   │   ├── engine.py, bayesian_predictor.py, diff_patterns.py
│   │   ├── causal_engine.py, pr_simulator.py, temporal_anomaly.py
│   │   ├── intervention_engine.py, strategy_evolution.py
│   │   ├── speculative_context.py, transfer_store.py, context_budget.py
│   │   ├── health_score.py, hot_zones.py, live_monitor.py, risk_gate.py
│   │   └── ...
│   ├── llm/providers.py, async_lab/executor.py
│   ├── api_server/server.py, integrations/openinspect.py
│   ├── utils/serialization.py
│   └── redis_limiter/
└── tests/ (7 test files, ~80 tests)
```

---

## Known Limitations

This is an **actively developed technology preview**. The following limitations are being addressed:

| # | Limitation | Impact | Mitigation |
|---|-----------|--------|-----------|
| 1 | **Regex-based indexing for non-Python languages** | Complex constructs (async functions, arrow functions, generics) may be missed in TS/JS/Go/Rust | Python uses AST already. Tree-sitter integration planned for other languages. |
| 2 | **Small session datasets** | Causal engine needs ≥10 sessions; temporal anomaly detection needs ≥10; strategy evolution needs ≥20 for meaningful results | Modules degrade gracefully — return empty contexts or fallback values when data is insufficient. |
| 3 | **No concurrent access testing for SQLite** | Multi-worker FastAPI deployments untested | SQLite WAL mode supports concurrent reads. PostgreSQL backend planned for scale. |
| 4 | **Experimental engines need more validation** | Causal, debate, simulation, temporal, intervention, evolution, transfer engines are functional but not battle-tested | All pass 32 real-data tests. More session data improves accuracy. |
| 5 | **ChromaDB requires sentence-transformers download** | First run downloads ~100MB model weights | Automatic; one-time cost. |
| 6 | **Limited community validation** | Solo project; no external contributors or production deployments yet | MIT licensed; seeking early adopters and contributors. |
| 7 | **No performance benchmarks** | Claims of "100K+ sessions" not yet validated with benchmarks | Reasonable for moderate scale based on SQLite WAL design. Benchmarks planned. |

---

## FAQ

**Q: How is this different from Open-Inspect?**
A: Open-Inspect is a background agent framework — it spawns sandboxes and runs coding sessions. Shadow Engineer is a **learning layer** that adds cross-session memory, parallel experimentation, and compounding intelligence.

**Q: Can I use this without Open-Inspect?**
A: Yes. Shadow Engineer works with any background agent via its REST API or CLI.

**Q: Does it require a GPU?**
A: No. ChromaDB uses CPU embeddings by default.

**Q: What scale does this support?**
A: SQLite WAL mode supports moderate scale. PostgreSQL backend planned for larger deployments.

**Q: Is this ready for production?**
A: Shadow Engineer is a **Technology Preview (Alpha)**. It is suitable for evaluation, prototyping, and contributing to. The core learning loop, knowledge graph, and API server are functional and tested. The experimental AI engines improve with more session data and community feedback. See [Known Limitations](#known-limitations).

---

## License

MIT — Build on it. Ship it. Make agents smarter.

---

*Inspired by [Ramp's Inspect](https://builders.ramp.com/post/why-we-built-our-background-agent) and [Open-Inspect](https://github.com/ColeMurray/background-agents).*