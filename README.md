<p align="center">
  <h1 align="center">🧠 Shadow Engineer</h1>
  <p align="center">
    <strong>A self-improving background agent with persistent codebase knowledge graph and parallel experimentation.</strong>
  </p>
  <p align="center">
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/CI-passing-brightgreen" alt="CI"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/tests-241-brightgreen" alt="Tests"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/coverage-≥60%25-yellow" alt="Coverage"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
    <a href="https://pypi.org/project/shadow-engine"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/blob/main/API_DOCS.md"><img src="https://img.shields.io/badge/docs-API_DOCS.md-orange" alt="Docs"></a>
  </p>
</p>

---

> **Status: Alpha → Strong Beta Candidate** — 241 tests passing with CI coverage enforcement (≥60%). See [Known Limitations](#known-limitations) and [Roadmap](ROADMAP.md).

> **No existing background agent framework does this.** Every agent today (Ramp's Inspect, Open-Inspect, Copilot, Claude Code) treats every session as a blank slate. Session 100 is no smarter than Session 1. Shadow Engineer remembers — and gets smarter with every session.

---

## 📊 Verified Test Results

Shadow Engineer is tested against its own codebase (dogfooding) using **real SQLite session data** and **50 synthetic sessions** for operational validation:

| Test Suite | Tests | Result | Description |
|-----------|-------|--------|-------------|
| **Experimental Engines** (causal, debate, simulation, temporal, intervention, strategy evolution) | 36 | **100% pass** | Includes 6 operational validation tests against 50 sessions with known causal relationships |
| **API Integration** (full workflow + security) | 14 | **100% pass** | bootstrap→context→search→suggest→experiment→ingest→report + auth/path traversal |
| **LLM Providers** (mocked HTTP) | 20 | **100% pass** | Ollama, OpenAI, Anthropic — success paths, auth errors, rate limits, timeouts |
| **Sandbox Execution** (adversarial) | 16 | **100% pass** | Infinite loops, memory limits, syntax errors, null bytes, Unicode bidi, eval/exec detection |
| **Knowledge Graph** (incl. Go/Rust tree-sitter) | 33 | **100% pass** | Symbol extraction, dependency resolution, impact analysis, CRUD |
| **Learning, API, Async, Redis** | 122 | **100% pass** | Session ingestion, pattern extraction, efficacy tracking, rate limiting |
| **Total** | **241** | **100% pass** | CI enforces ≥60% coverage with `--cov-fail-under=60` |
| **Docker Sandbox** | 10/10 | **Verified** | Network isolation, read-only FS, tmpfs, memory cgroups, PID limits, capability drop |
| **Ruff Lint** | — | **All checks passed** | Zero lint errors across entire codebase |

> Reproduce: `pytest tests/ -v`
> Sandbox: `bash scripts/test_docker_sandbox.sh`
> Lint: `ruff check src/`

---

## 🧪 Docker Sandbox Infrastructure

Shadow Engineer includes a full Docker-based sandbox for safe Laboratory code execution:

| Feature | Implementation |
|---------|---------------|
| **Network Isolation** | `--network=none` — no external access |
| **Filesystem Protection** | `--read-only` root filesystem, writable `/tmp` via tmpfs |
| **Memory Limits** | Docker cgroups with `--memory=128m` |
| **PID Limits** | `--pids-limit=50` — prevents fork bombs |
| **Capability Drop** | `--cap-drop=ALL` — minimal privileges |
| **Container Timeout** | `--timeout` flag for execution time limits |
| **Adversarial Testing** | Null bytes, Unicode bidi, very long lines, eval/exec detection |

> Run sandbox tests: `bash scripts/test_docker_sandbox.sh`
> Docker Compose integration: `docker compose -f docker/docker-compose.test.yml up -d`

---

## 🔬 Advanced Learning Pipeline

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

### Code-Level Fix Patterns
- Extracted from real git diff history

### Test Risk by File
- Per-file test failure correlation across sessions

### Risk Assessment (Bayesian)
- Beta-Binomial posterior with 95% credible intervals
- Shrinkage toward prior prevents overconfidence on small samples

### Temporal Anomaly Detection
- Bayesian Online Changepoint Detection (BOCD)
- Health score forecasting with linear regression

### PR Outcome Simulation
- Monte Carlo simulation of test breakage, review rejection, and rework

### Multi-Agent Debate
- Variant peer review with consensus synthesis

### Knowledge Graph Context
- Semantically relevant symbols via ChromaDB embeddings
```

---

## 🧪 Experimental AI Engines

All verified against 50 synthetic sessions with known causal relationships (Targeted Fix = ~90% success, Aggressive Rewrite = ~20% success). Feature-flagged behind `SHADOW_EXPERIMENTAL=1`.

| Engine | What It Does | Validated With | Key Finding |
|--------|-------------|---------------|-------------|
| **Causal Reasoning** | Structural Causal Models (SCM) with do-calculus — answers counterfactuals | 50 sessions | ATE > 0 (positive causal effect for Targeted Fix) |
| **Multi-Agent Debate** | Variants critique each other, synthesize consensus solutions | 5 variants | Synthesis generation works with diverse inputs |
| **PR Outcome Simulator** | Monte Carlo simulation of test breakage, review rejection, rework | 50 sessions | Risky files score higher than safe files |
| **Temporal Anomaly** | BOCD changepoint detection, Z-score spikes, health forecasting | 50 observations | Expected rate correctly tracked |
| **Intervention Engine** | WARN→INTERVENE→ABORT→ESCALATE ladder | Real files | Risk assessment functional |
| **Strategy Evolution** | Genetic algorithms evolve optimal strategies | 2 generations | Best strategy favors successful approaches |
| **Speculative Context** | LRU-cached pre-computation with TTL eviction | Any | Cache hit/miss + queue processing verified |
| **Cross-Repo Transfer** | Pattern abstraction for federated learning | 1+ repos | Pattern generalization works |

> Test all engines: `pytest tests/test_experimental_engines.py -v`

---

## 🏗️ Core Features

| Feature | What It Does | Implementation |
|---------|-------------|---------------|
| **Tree-Sitter Indexing** | Accurate AST parsing for TS/JS/Go/Rust (Python uses `ast.parse()`) | `knowledge_graph/indexer.py` |
| **Bayesian Impact Prediction** | Beta-Binomial P(failure \| file) with 95% CI | `learning/bayesian_predictor.py` |
| **Pattern Similarity Merging** | Jaccard deduplication prevents pattern fragmentation | `learning/pattern_merger.py` |
| **Hot Zone Detection** | Weighted scoring for files causing disproportionate failures | `learning/hot_zones.py` |
| **Codebase Health Score** | Single 0-100 metric from hot zones, failure rates, risk trends | `learning/health_score.py` |
| **Context Budget Manager** | Token-budget-aware builder prevents model overflow | `learning/context_budget.py` |
| **Graceful Error Handling** | @graceful decorator + CircuitBreaker for LLM calls | `learning/graceful.py` |
| **LLM Provider Abstraction** | Ollama (HTTP API), OpenAI, Anthropic with structured error handling | `llm/providers.py` |
| **Centralized Serialization** | JSON helpers with atomic writes | `utils/serialization.py` |
| **Experimental Feature-Flag** | `SHADOW_EXPERIMENTAL=1` gates optional engines | `learning/experimental.py` |

---

## Table of Contents

1. [What Is Shadow Engineer?](#what-is-shadow-engine)
2. [The Problem It Solves](#the-problem-it-solves)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Quick Start (CLI)](#quick-start-cli)
6. [REST API Integration](#rest-api-integration)
7. [Python SDK](#python-sdk)
8. [Docker Sandbox](#docker-sandbox)
9. [Deployment](#deployment)
10. [Configuration Reference](#configuration-reference)
11. [Supported Languages](#supported-languages)
12. [Project Structure](#project-structure)
13. [Known Limitations](#known-limitations)
14. [FAQ](#faq)
15. [License](#license)

---

## What Is Shadow Engineer?

Shadow Engineer is a **learning layer** that sits on top of any background coding agent (Open-Inspect, Claude Code, custom agents). It provides three capabilities:

| Engine | What It Does | Unique Value |
|--------|-------------|--------------|
| **Knowledge Graph** | Indexes your codebase into a persistent, searchable semantic graph | Agents start with informed context |
| **Laboratory** | Spawns N parallel agent experiments with different strategies | Choose from proven solutions |
| **Learning Engine** | Analyzes every session to extract patterns, track efficacy, and suggest approaches | Session 100 is smarter than Session 1 |

---

## The Problem It Solves

| Problem | Without Shadow Engineer | With Shadow Engineer |
|---------|------------------------|---------------------|
| **No memory** | Agent fumbles through codebase every time | Agent starts with relevant KG context |
| **No learning** | Same mistakes repeated across sessions | Pattern extraction + efficacy tracking |
| **Single attempt** | One approach — if it fails, start over | N parallel experiments, winner picked automatically |
| **No understanding** | "What file handles auth?" every session | Semantic search: "authentication" → `auth/service.py` |

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
  │ Classify │───────┼──│ • Tree-sitter│  │  • Targeted Fix  │  │
  │ problem  │       │  │ • SQLite     │  │  • Root Cause    │  │
  └────┬─────┘       │  │ • ChromaDB   │  │  • Defense Depth │  │
       │             │  └──────┬───────┘  └────────┬─────────┘  │
  ┌────▼─────┐       │         │                   │            │
  │  Build   │       │         │                   ▼            │
  │ context  │───────┼─────────┼──▶  Agent Prompt + Approach    │
  │ (budget) │       │         │                                │
  └────┬─────┘       │         │     ┌──────────────────┐       │
       │             │         │     │     Learning     │       │
       ▼             │         │     │      Engine      │       │
  ┌──────────┐       │         │     │                  │       │
  │  Agent   │       │         │     │ • Causal analysis│       │
  │ executes │       │         └─────│ • Strategy evolve│       │
  │ (Docker  │       │               │ • Temporal detect│       │
  │  sandbox)│       │               └────────┬─────────┘       │
  └────┬─────┘       │                        │                 │
       ▼             │                        ▼                 │
  ┌──────────┐       │           ┌──────────────────────┐      │
  │  Ingest  │───────┼──────────▶│  Next session is     │      │
  │  result  │       │           │  SMARTER than before  │      │
  └──────────┘       │           └──────────────────────┘      │
                     └──────────────────────────────────────────┘
```

---

## Installation

### Prerequisites
- Python 3.12 or later
- (Optional) [Redis](https://redis.io) for production rate limiting
- (Optional) [Docker](https://docker.com) for sandboxed code execution
- (Optional) [Ollama](https://ollama.ai) for local LLM testing

### pip (recommended)

```bash
pip install shadow-engine
pip install "shadow-engine[dev]"     # For development
pip install "shadow-engine[redis]"   # For Redis rate limiting
pip install "shadow-engine[tree-sitter-langs]"  # For tree-sitter parsers
```

### From source

```bash
git clone https://github.com/rudraneel93/shadow-engine.git
cd shadow-engine
pip install -e ".[dev]"
shadow-engine bootstrap
```

---

## Quick Start (CLI)

```bash
cd /path/to/your/project
shadow-engine bootstrap          # Index codebase
shadow-engine search "auth"      # Search symbols
shadow-engine context "fix bug"  # Get AI-ready context
shadow-engine suggest "add feature"  # Get approach recommendation
shadow-engine experiment "refactor billing" --variants 3  # Parallel experiments
shadow-engine record --session-id "sess-001" --outcome "success" --prompt "fix bug" --approach "Targeted Fix" --files "src/auth.py" --tests-passed 10 --tests-failed 0 --duration 30 --tokens 5000
shadow-engine report             # View improvement report
```

---

## REST API Integration

```bash
# Start server
uvicorn shadow_engine.api_server.server:app --reload

# Auth (optional)
export SHADOW_ENGINE_API_KEY="your-secret-key"

# Core workflow
curl -X POST http://localhost:8000/bootstrap
curl "http://localhost:8000/context?task=fix+login+bug"
curl "http://localhost:8000/suggest?task=fix+login+bug"
curl -X POST "http://localhost:8000/experiment?task=refactor+auth&variants=3"
curl -X POST http://localhost:8000/sessions/ingest -H "Content-Type: application/json" -d '{...}'
curl http://localhost:8000/report
curl http://localhost:8000/health
```

Full API reference: **[API_DOCS.md](API_DOCS.md)** — Swagger UI at `http://localhost:8000/docs`

---

## Docker Sandbox

Shadow Engineer includes a Docker-based sandbox for safe code execution in the Laboratory:

```bash
# Run sandbox verification (10 isolation tests)
bash scripts/test_docker_sandbox.sh

# Start full integration test environment
docker compose -f docker/docker-compose.test.yml up -d
# API available at http://localhost:18000
# Redis available at localhost:16379
```

Sandbox features: network isolation, read-only filesystem, memory/PID limits, capability dropping, container timeouts. Supports adversarial testing with null bytes, Unicode bidi, fork bombs, and resource exhaustion.

---

## Deployment

```bash
# Docker
docker compose -f docker/docker-compose.yml up -d

# Without Redis
docker build -t shadow-engine -f docker/Dockerfile .
docker run -p 8000:8000 -e SHADOW_ENGINE_API_KEY=your-secret shadow-engine
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHADOW_ENGINE_API_KEY` | `""` (disabled) | API key for authentication |
| `SHADOW_ENGINE_REDIS_URL` | `redis://redis:6379` | Redis URL for rate limiting |
| `SHADOW_ENGINE_RATE_LIMIT` | `100` | Max requests per window |
| `SHADOW_ENGINE_ALLOWED_ROOTS` | `""` (all paths) | Comma-separated allowed repo paths |
| `SHADOW_EXPERIMENTAL` | `""` (disabled) | Set to `1` to enable experimental AI engines |

---

## Supported Languages

| Language | Extensions | Parser | Accuracy |
|----------|-----------|--------|----------|
| Python | `.py` | `ast.parse()` (stdlib) | ✅ Excellent |
| TypeScript | `.ts`, `.tsx` | tree-sitter + regex fallback | ✅ Good |
| JavaScript | `.js`, `.jsx` | tree-sitter + regex fallback | ✅ Good |
| Go | `.go` | tree-sitter + regex fallback | ✅ Good |
| Rust | `.rs` | tree-sitter + regex fallback | ✅ Good |

---

## Project Structure

```
shadow-engine/
├── README.md, ARCHITECTURE.md, API_DOCS.md, ROADMAP.md
├── CHANGELOG.md, CONTRIBUTING.md, FINDINGS_REPORT.md
├── pyproject.toml, LICENSE
├── docker/                    (Dockerfile, docker-compose.yml, docker-compose.test.yml)
├── .github/workflows/ci.yml   (CI with coverage enforcement)
├── scripts/
│   ├── test_docker_sandbox.sh    (10 Docker isolation tests)
│   ├── benchmark.py              (Performance benchmarks)
│   └── test_breakthrough_features.py
├── src/shadow_engine/
│   ├── main.py, observability.py
│   ├── knowledge_graph/ (indexer.py [tree-sitter], models.py, store.py)
│   ├── sqlite_store/db.py, chroma_store/vector_store.py
│   ├── laboratory/ (experiment.py, debate.py)
│   ├── learning/
│   │   ├── engine.py, causal_engine.py, pr_simulator.py
│   │   ├── temporal_anomaly.py, intervention_engine.py
│   │   ├── strategy_evolution.py, speculative_context.py
│   │   ├── transfer_store.py, context_budget.py
│   │   ├── graceful.py (error handling), experimental.py (feature flag)
│   │   └── ...  (bayesian_predictor, diff_patterns, hot_zones, risk_gate, etc.)
│   ├── llm/providers.py, async_lab/executor.py
│   ├── api_server/server.py, integrations/openinspect.py
│   ├── utils/serialization.py
│   └── redis_limiter/
└── tests/
    ├── test_experimental_engines.py (36 tests with operational validation)
    ├── test_api_integration.py (14 tests: full pipeline + security)
    ├── test_providers.py (20 tests: mocked HTTP)
    ├── test_sandbox_execution.py (16 tests: adversarial)
    ├── test_knowledge_graph.py (33 tests)
    ├── test_learning.py, test_api_server.py, test_integration.py
    └── conftest.py (synthetic session factory, 50 sessions)
```

---

## Known Limitations

This is an **actively developed alpha-stage project**. The following limitations are documented transparently:

| # | Limitation | Status | Mitigation |
|---|-----------|--------|-----------|
| 1 | **Single-file core** (main.py is 22KB) | ⚠️ Target for refactoring | Monolithic `ShadowEngine` class to be decomposed into focused modules |
| 2 | **Experimental engines need scale validation** | ⚠️ Validated with 50 synthetic sessions | Operational validation tests passing; needs 100+ real sessions for full confidence |
| 3 | **PostgreSQL backend not yet implemented** | ⚠️ Planned (B1 milestone) | SQLite WAL mode sufficient for single-node; PostgresStore on roadmap |
| 4 | **Docker sandbox not in pytest** | ⚠️ Standalone Bash script | Integration via `testcontainers-python` planned |
| 5 | **No community adoption** | ⚠️ Solo project | MIT licensed; seeking early adopters and contributors |
| 6 | **Performance benchmarks not CI-automated** | ⚠️ Script exists | CI integration planned |

---

## FAQ

**Q: How is this different from Open-Inspect?**
A: Open-Inspect provides sandboxed agent infrastructure. Shadow Engineer adds persistent cross-session memory and learning — a complementary layer.

**Q: Is this ready for production?**
A: Strong Alpha candidate approaching Beta. 241 tests pass with CI coverage enforcement. See [Known Limitations](#known-limitations).

**Q: What scale does this support?**
A: SQLite WAL mode supports moderate single-node scale. PostgreSQL backend planned for multi-tenant deployments.

**Q: Does it require a GPU?**
A: No. ChromaDB uses CPU embeddings by default. LLM calls are delegated to external providers (Ollama, OpenAI, Anthropic).

---

## License

MIT — Build on it. Ship it. Make agents smarter.

---

*Inspired by [Ramp's Inspect](https://builders.ramp.com/post/why-we-built-our-background-agent) and [Open-Inspect](https://github.com/ColeMurray/background-agents).*