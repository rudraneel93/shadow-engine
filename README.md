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

> **No existing background agent framework does this.** Every agent today (Ramp's Inspect, Open-Inspect, Copilot, Claude Code) treats every session as a blank slate. Session 100 is no smarter than Session 1. Shadow Engineer remembers — and gets smarter with every session.

---

## 📊 Real-World E2E Verified

Shadow Engineer was tested end-to-end with **Ollama qwen3:8b (5.2 GB local LLM)** on its own codebase (dogfooding). The full pipeline — bootstrap → classify → context → LLM → analyze → ingest:

| Metric | Result | Grade |
|--------|--------|-------|
| **Classification accuracy** | 3/3 tasks correctly classified (bug_fix, feature, refactor) | **A** |
| **Context generation** | 123–129 lines per task, ~35 real symbol references | **A** |
| **LLM response quality** | qwen3:8b reasoned from context, produced 9K–11K char responses | **B** |
| **File identification** | 83% avg match (2/3 at 100%, 1/3 at 50%) | **A** |
| **Cross-session learning** | 6 patterns extracted from 3 sessions | **A** |
| **Pipeline latency** | 130s avg per task (local 5.2 GB model) | **B** |
| **Total cost** | $0.00 (free local model, no API keys) | **A+** |

**Overall grade: 3.7/4.0.**

The same 3 tasks were tested across **3 different local models** to validate consistency:

| Model | Size | File Match | Success | Tokens | Total Time | Avg Latency | Cost |
|-------|------|-----------|---------|--------|-----------|------------|------|
| **qwen3:8b** | 5.2 GB local | **83%** | 100% | ~5,954 | 420s | 140s | $0.00 |
| **qwen3-coder:480b-cloud** | Cloud | **83%** | 100% | ~1,653 | 221s | 74s | $0.00 |
| **gpt-oss:120b-cloud** | Cloud | **83%** | 100% | ~6,239 | 94s | 31s | $0.00 |

**Key finding:** All 3 models achieved identical 83% file match accuracy. The knowledge graph (not the model) drives codebase understanding — the model just needs to be capable of reading the provided context and reasoning from it. **Any local LLM works.**

> Reproduce: `python scripts/test_multimodel_e2e.py` (requires Ollama + the models above)
> Single-model test: `python scripts/test_ollama_e2e.py`

---

## 🧠 Meta-Reasoning Engine (v0.4.0)

Shadow Engineer doesn't just dump your codebase into a prompt. It provides **meta-reasoning priors** — classification, strategy recommendation, and historical efficacy data — before the knowledge graph context:

```markdown
## Shadow Engineer — Context for ChatGPT

### Problem Classification
- **Type**: bug_fix (confidence: 0.95)
- **Recommended Approach**: Targeted Fix
- **Expected Success Rate**: 100% (4/4 attempts)
- **Last Successful Model**: qwen3:8b

### Historical Insight
- Targeted Fix for bug_fix: 4/4 succeeded (100%). Avoid Aggressive Rewrite — 0/1 succeeded for bug_fix.
- TDD First for testing: 3/3 succeeded (100%). Avoid Full Coverage — 0/1 succeeded.
- Extensible Implementation for feature: 3/3 succeeded (100%). Avoid Clean Sweep — 0/1 succeeded.
*Rates from 18 ingested sessions. Small sample — more sessions increase confidence.

### Knowledge Graph Context
#### Semantically Relevant Symbols
- **ChromaSymbolStore** (`class`) in `chroma_store/vector_store.py` (relevance: 0.89)
  Vector-backed symbol search using ChromaDB...
```

**Pipeline: Task → Classification → Strategy → Context → Prompt**

| Problem Type | Best Approach | Success Rate* | Last Successful Model |
|-------------|--------------|-------------|-----------------------|
| bug_fix | Targeted Fix | 100% (4/4) | qwen3:8b |
| feature | Extensible Implementation | 100% (3/3) | qwen3:8b |
| testing | TDD First | 100% (3/3) | qwen3:8b |
| refactor | Incremental Rewrite | 100% (3/3) | qwen3:8b |
| bug_fix (avoid) | Aggressive Rewrite | 0% (0/1) | — |
| feature (avoid) | Clean Sweep | 0% (0/1) | — |

\* *Rates from 18 ingested sessions. Small sample — more sessions increase confidence.*

> Build real efficacy data: `python scripts/build_efficacy_data.py`

---

## 🔬 Deep Learning Pipeline (v0.7.0)

Every context block now includes six layers of intelligence before the knowledge graph:

```markdown
## Shadow Engineer — Context for ChatGPT

### Problem Classification
- Type + confidence score → no guessing

### Historical Insight
- Which approaches work, which fail, and why

### Proven Fix Patterns (deduplicated)
- Recurring patterns from successful sessions, merged via Jaccard similarity

### Proven Code-Level Fix Patterns
- Extracted from real git diff history:
  null_guard (90%), error_handling (90%), type_annotation (90%)

### Test Risk by File
- "test_rate_limit.py fails 85% of the time when rate_limiter.py changes"

### Risk Assessment (Bayesian)
- Beta-Binomial posterior with 95% credible intervals
- Shrinkage toward prior prevents overconfidence on small samples

### Knowledge Graph Context
- Semantically relevant symbols via ChromaDB embeddings
```

| Deep Feature | What It Does | Status |
|-------------|-------------|--------|
| **Diff Pattern Extraction** | Parses git history to find recurring fix patterns (null_guard, error_handling, type_annotation) | ✅ v0.7.0 |
| **Bayesian Impact Prediction** | Beta-Binomial P(failure \| file) with 95% CI — not simple ratios | ✅ v0.7.0 |
| **Per-Test Risk Correlation** | Maps files to specific test failure rates across sessions | ✅ v0.7.0 |
| **Pattern Similarity Merging** | Jaccard deduplication prevents pattern fragmentation | ✅ v0.7.0 |
| **Code-Level Fix Patterns** | Answers "what code should I write?" with real examples | ✅ v0.7.0 |
| **Live Session Monitoring** | Real-time file risk warnings during coding sessions | ✅ v0.8.0 |
| **Natural Language Q&A** | Answers English questions about the codebase (7 question types) | ✅ v0.8.0 |
| **Hot Zone Detection** | Weighted scoring identifies files causing disproportionate failures | ✅ v0.8.0 |

> Reproduce: `python scripts/build_efficacy_data.py` then `shadow-engine context "your task"`

---

## 🚀 New Capabilities (v0.8.0)

Tested against 18 real sessions with 490 symbols (155 pytest suite passing).

| Test Area | Result |
|-----------|--------|
| **CodebaseQA** | 6/7 question types returned real data |
| **Hot Zone Detection** | 12 files scored — store.py highest risk (100% failure) |
| **Live Monitor** | 6/6 files analyzed with session data |
| **get_context() layers** | 6/8 layers active |
| **pytest suite** | 155 passed, 0 failures |

### Live Session Monitoring
Real-time risk warnings during coding sessions. When an agent starts modifying files, Shadow Engineer provides live, data-driven risk assessment:

| File | Risk | Mods | Break Rate | Shrinkage |
|------|------|------|-----------|-----------|
| `knowledge_graph/store.py` | 🔴 HIGH | 2 | 100% | 50% |
| `main.py` | 🟡 MEDIUM | 6 | 33% | 75% |
| `sqlite_store/db.py` | 🟡 MEDIUM | 5 | 40% | 71% |
| `knowledge_graph/indexer.py` | 🟢 LOW | 4 | 25% | 67% |

### Natural Language Codebase Q&A
Ask plain-English questions. Zero LLM calls — answers from structured data:

```
Q: "What's the most dangerous file?"
A: main.py — 6 modifications, 2 failures (33%)
   sqlite_store/db.py — 5 modifications, 2 failures (40%)

Q: "Who depends on ShadowEngine?"
A: get_engine() → used by get_context, search, impact, suggest, experiment...
   ShadowEngine → used by cli_main
```

### Hot Zone Detection
Weighted composite scoring (mod_freq × 40% + failure_rate × 40% + fanout × 20%) identifies files that cause disproportionate failures. 12 hot zones detected from 18 real sessions.

> Comprehensive test: `python scripts/test_breakthroughs.py`

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
13. [FAQ](#faq)
14. [License](#license)

---

## What Is Shadow Engineer?

Shadow Engineer is a **learning layer** that sits on top of any background coding agent (Open-Inspect, Claude Code, custom agents). It provides three capabilities that no other framework offers:

| Engine | What It Does | Unique Value |
|--------|-------------|--------------|
| **Knowledge Graph** | Indexes your codebase into a persistent, searchable semantic graph | Agents start with informed context — no more fumbling through code |
| **Laboratory** | Spawns N parallel agent sessions with different strategies and picks the winner | Not one attempt — choose from proven solutions |
| **Learning Engine** | Analyzes every session to extract patterns, track efficacy, and suggest approaches | Session 100 is smarter than Session 1 — compounding intelligence |

### The Compounding Moat

```
Session 1:   No context  | No patterns  | No approach data  | ~40% success rate (baseline)
Session 10:  10 symbols  | 3 patterns   | 2 approaches      | ~55% success rate*
Session 50:  50 symbols  | 8 patterns   | 5 approaches      | ~70% success rate*
Session 200: 100+ symbols | 20+ patterns | 10+ approaches   | ~80% success rate*

*Projected from efficacy tracking logic. Measured: 78% over 18 sessions.
```

**Every session makes the next one smarter.** This is the defensible moat that no competitor ships.

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

#### 3. Learning Engine — "Improve"
- **Pattern extraction** — infers testing conventions, change scope, code review quality
- **Efficacy tracking** — running averages for success rate, duration, tokens
- **Failure analysis** — understands why approaches fail
- **Approach suggestion** — recommends historically-best approach and model
- **Confidence scores** — every classification returns `(type, 0.0–1.0)` not just a label

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

### 3. Get AI-Ready Context (Meta-Reasoning)

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
- **Last Successful Model**: qwen3:8b

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
  "last_successful_model": "qwen3:8b"
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

### Docker (Production)

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
| Python | `.py` | Functions, methods, classes |
| TypeScript | `.ts`, `.tsx` | Functions, classes, interfaces, enums, type aliases |
| JavaScript | `.js`, `.jsx` | Functions, classes, constants |
| Go | `.go` | Functions, methods, structs, interfaces |
| Rust | `.rs` | Functions, structs, traits, enums, type aliases |

---

## Project Structure

```
shadow-engine/
├── README.md, CHANGELOG.md, API_DOCS.md, FINDINGS_REPORT.md, ROADMAP.md
├── pyproject.toml, LICENSE
├── docker/
├── .github/workflows/ci.yml
├── scripts/     (test_multimodel_e2e.py, test_ollama_e2e.py, build_efficacy_data.py, ...)
├── src/shadow_engine/
│   ├── main.py, observability.py
│   ├── knowledge_graph/ (indexer.py, models.py, store.py)
│   ├── sqlite_store/db.py, chroma_store/vector_store.py
│   ├── laboratory/experiment.py, learning/engine.py
│   ├── llm/providers.py, async_lab/executor.py
│   ├── api_server/server.py, integrations/openinspect.py
│   └── redis_limiter/
└── tests/ (7 test files, 155 tests)
```

---

## FAQ

**Q: How is this different from Open-Inspect?**
A: Open-Inspect is a background agent framework — it spawns sandboxes and runs coding sessions. Shadow Engineer is a **learning layer** that adds cross-session memory, parallel experimentation, and compounding intelligence.

**Q: Can I use this without Open-Inspect?**
A: Yes. Shadow Engineer works with any background agent via its REST API or CLI.

**Q: Does it require a GPU?**
A: No. ChromaDB uses CPU embeddings by default.

**Q: What scale does this support?**
A: SQLite WAL mode supports 100K+ sessions. PostgreSQL backend planned for larger scale.

**Q: Is this ready for production?**
A: Ready for internal team deployment. See [ROADMAP.md](ROADMAP.md) for GA timeline.

---

## License

MIT — Build on it. Ship it. Make agents smarter.

---

*Inspired by [Ramp's Inspect](https://builders.ramp.com/post/why-we-built-our-background-agent) and [Open-Inspect](https://github.com/ColeMurray/background-agents).*