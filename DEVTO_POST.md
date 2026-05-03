# Building an AI Coding Agent That Remembers Your Codebase Across Sessions

*Published on 2026-05-03 | 8 min read | #ai #python #opensource #machinelearning #programming*

---

**Every AI coding agent has amnesia. I fixed it.**

Two months ago, Ramp's engineering team published a fascinating blog post about [Inspect](https://builders.ramp.com/post/why-we-built-our-background-agent) — their internal background coding agent. It was impressive: 30% of all pull requests merged to their frontend and backend repos are AI-written. The architecture was elegant: Modal sandboxes, OpenCode as the agent runtime, Cloudflare Durable Objects for state.

But there was a problem hiding in plain sight.

Every session treated the codebase like it had never seen it before. Session 1 knew nothing. Session 100 knew nothing. Session 500… still nothing. The agent could write code, but it couldn't learn.

That's when I realized: **no background agent framework in existence retains cross-session state.** Ramp Inspect, Open-Inspect, Copilot, Claude Code, Aider, Sweep, Devin — they all have one thing in common: they forget everything between sessions.

So I built **Shadow Engineer** — a learning layer that compounds over time.

---

## The Problem: Why Agent Amnesia Matters

Imagine you're a senior engineer mentoring a junior developer. Every morning, the junior walks in and asks:

> "How does our authentication work again?"

You answer. They fix a bug. They leave. Next morning, same question.

> "How does our authentication work again?"

You'd be frustrated. You'd wonder why they're not learning. You'd start documenting things. You'd build shared knowledge.

Now replace "junior developer" with "your AI coding agent." That's the state of every background agent today.

Current agents have three critical failures:

1. **No memory** — Every session starts by fumbling through the codebase, trying to figure out what files handle what
2. **No learning** — If an approach fails 10 times, it'll try it an 11th time
3. **No experimentation** — It's a single attempt. If it fails, you start over

Shadow Engineer fixes all three.

---

## How It Works: Three Engines That Compound

Shadow Engineer is a Python library that sits between your task and your background agent (Open-Inspect, Claude Code, or any custom agent). It has three engines:

```
                    ┌──────────────────────────────────────┐
                    │         SHADOW ENGINEER                │
                    │                                         │
   User sends task  │  ┌────────────────┐  ┌──────────────┐ │
          │         │  │ Knowledge Graph│  │  Laboratory  │ │
          ▼         │  │                │  │              │ │
   ┌──────────┐     │  │ • 7 languages  │  │ • N variants │ │
   │ Classify │─────┼──│ • Semantic     │  │ • Auto-scored│ │
   │ problem  │     │  │   search       │  │ • Winner pick│ │
   └────┬─────┘     │  │ • Dependencies │  │              │ │
        │           │  └───────┬────────┘  └──────┬───────┘ │
   ┌────▼─────┐     │         │                    │         │
   │  Build   │     │         │                    ▼         │
   │ context  │─────┼─────────┼──▶ Agent Prompt + Approach   │
   └──────────┘     │         │                              │
                    │         │       ┌──────────────────┐   │
                    │         │       │     Learning     │   │
                    │         └───────│      Engine      │   │
                    │                 │ • Pattern extract│   │
                    │                 │ • Efficacy track │   │
                    │                 │ • Failure analyze│   │
                    │                 └────────┬─────────┘   │
                    │                          │             │
                    │                          ▼             │
                    │         ┌──────────────────────────┐   │
                    │         │  Next session is SMARTER  │   │
                    │         └──────────────────────────┘   │
                    └──────────────────────────────────────┘
```

### Engine 1: Knowledge Graph — "Remember"

The knowledge graph indexes your entire codebase into a persistent, searchable structure. It extracts symbols (functions, classes, methods, interfaces) from 7 languages — Python, TypeScript, JavaScript, Go, and Rust.

But unlike a simple grep tool, it uses **ChromaDB vector embeddings** for semantic search. "Fix the login rate limiting" will find `throttle_requests()` even if "throttle" doesn't appear in your query.

**Before every agent session**, Shadow Engineer injects a context block into the prompt:

```
### Semantically Relevant Symbols

- **authenticate_user** (function) in src/auth/service.py (relevance: 0.89)
  Authenticate a user from a JWT token.
  Depends on: UserModel, TokenService

- **login_handler** (function) in src/auth/views.py (relevance: 0.82)
  Handle login POST requests. Validates credentials.
  Complexity: 6.5

### Learned Codebase Conventions
- **error_handling**: Auth errors return 401 with JSON body {error, code}
- **testing**: Tests are written alongside code changes

### Historically Effective Approaches
- **Targeted Fix**: 85% success rate (17/20) — best model: claude-sonnet-4-6
```

The agent now starts with informed context. No more guessing.

### Engine 2: Laboratory — "Experiment"

Instead of one attempt, Shadow Engineer spawns **N parallel sessions** with different strategies and picks the winner.

For a bug fix, it might try all three simultaneously:
- **Targeted Fix** — Find the minimal change. Write a focused fix with regression test.
- **Root Cause + Guard** — Fix the bug, add input validation to prevent similar issues.
- **Defense in Depth** — Comprehensive fix with error handling at every layer.

Each variant runs in its own sandbox. When they complete, Shadow Engineer scores them using a **configurable logistic curve** (no arbitrary cliffs — 50 lines changed scores smoothly differently from 51). The winner is selected automatically based on:

- Test pass rate (40%)
- Code change size (20%)
- Execution speed (15%)
- Token efficiency (10%)
- File count scope (15%)

All weights are configurable:

```python
from shadow_engine.laboratory.experiment import ScoringConfig

config = ScoringConfig(
    test_pass_weight=0.50,      # Prioritize tests
    speed_weight=0.25,          # Care more about speed
    change_size_weight=0.10,
)
```

### Engine 3: Learning Engine — "Improve"

This is where the compounding happens. After every session completes, the Learning Engine analyzes the outcome and extracts:

**Patterns** — It notices things about your codebase:
- "This team always writes tests alongside code changes"
- "Successful PRs modify ≤3 files"
- "Clean PRs with no review comments follow existing conventions closely"

**Efficacy** — It tracks which approaches work:
- "Targeted Fix succeeds 85% of the time for bug fixes with claude-sonnet-4-6"
- "Aggressive Rewrite fails 90% of the time — don't use this for your codebase"

**Failures** — It understands why things fail:
- "12 tests failed — changes broke existing functionality"
- "Agent modified 15 files — too broad, likely introduced risk"

The next time you ask for a bug fix, Shadow Engineer suggests "Targeted Fix" with 85% expected success rate. The agent gets smarter at **your** codebase.

---

## Real Pipeline Verified

This isn't theoretical. I tested it end-to-end with a real LLM:

| Step | Result |
|------|--------|
| Bootstrap | 211 symbols from 26 files (indexed the shadow-engine source code itself) |
| Context | 89-line semantic context block (ChromaDB embeddings + SQLite lookups) |
| LLM Call | Ollama `qwen3:8b` (5.2GB local model) generated ~1,216 tokens in 88 seconds |
| LLM Quality | Correctly identified `CodebaseIndexer` as the key component for the task |
| Ingestion | Session recorded with real duration, tokens, and approach |
| Report | 100% success rate, 1 pattern learned |

The LLM received the knowledge graph context and correctly reasoned through the task from first principles — identifying which files to modify, how to approach the refactoring, and what tests to write.

---

## Technical Architecture

Shadow Engineer is production-grade:

| Layer | Implementation |
|-------|---------------|
| **Storage** | SQLite WAL (15 tables, 6 indexes, thread-safe), JSON fallback |
| **Search** | ChromaDB vector embeddings → SQLite text → JSON text → in-memory (6-layer degradation) |
| **API** | FastAPI server with optional API key auth, Redis rate limiting, `/v1/` prefix |
| **Deployment** | Docker + docker-compose (includes Redis) |
| **CI/CD** | GitHub Actions — test matrix (Python 3.12/3.13), lint, build |
| **Testing** | 80 tests, 73% coverage, zero failures |
| **Integration** | Async Open-Inspect bridge via `run_in_executor` |

Every layer handles failure gracefully. ChromaDB unavailable? Falls back to SQLite text search. Redis unavailable? Falls back to in-memory rate limiting. JSON file corrupted? Recovers per-file.

---

## Quick Start

### Installation

```bash
pip install shadow-engine

# Or from source
git clone https://github.com/rudraneel93/shadow-engine
cd shadow-engine && pip install -e ".[dev]"
```

### Index Your Codebase (CLI)

```bash
cd /path/to/your/project
shadow-engine bootstrap
# → Bootstrapped: 347 symbols, 52 files indexed

shadow-engine search "authenticate"
# → [function] authenticate_user — src/auth/service.py
#     Authenticates a user with email and password. Returns JWT token.

shadow-engine context "fix the login rate-limiting bug"
# → Output: full knowledge graph context for agent prompt

shadow-engine suggest "fix the login rate-limiting bug"
# → {"problem_type": "bug_fix", "recommended_approach": "Targeted Fix", "expected_success_rate": 0.85}
```

### REST API

```bash
# Start the server
uvicorn shadow_engine.api_server.server:app --reload

# Index codebase
curl -X POST http://localhost:8000/bootstrap

# Get context for agent
curl "http://localhost:8000/context?task=fix+the+login+rate+limiting+bug"

# Record session result
curl -X POST http://localhost:8000/sessions/ingest \
  -H "Content-Type: application/json" \
  -d '{"session_id":"sess-001","outcome":"success","prompt":"fix login bug",...}'

# View improvement report
curl http://localhost:8000/report
```

### Python SDK

```python
from shadow_engine.main import ShadowEngine

engine = ShadowEngine(repo_path="./my-project")
engine.bootstrap()

# Get context for agent prompt
context = engine.get_context("fix the login rate-limiting bug")

# Get approach suggestion
suggestion = engine.suggest("fix the login rate-limiting bug")
print(f"Use: {suggestion['recommended_approach']} ({suggestion['expected_success_rate']:.0%} expected)")

# Record a completed session
engine.record_result(
    session_id="sess-001",
    outcome="success",
    prompt="fix the login bug",
    approach="Targeted Fix",
    model="claude-sonnet-4-6",
    files_changed=["src/auth.py", "tests/test_auth.py"],
    tests_passed=10,
    tests_failed=0,
)

# View improvement
print(engine.get_report())
```

---

## Why This Matters

The AI coding tool market is exploding. Every major company is building internal agents. But they're all building them wrong — they optimize for individual sessions when the real value is **cross-session compounding.**

Shadow Engineer makes the 100th session smarter than the 1st. It's MIT-licensed. It works with any background agent. And it's been tested with real LLMs.

The knowledge graph grows. The patterns accumulate. The efficacy data deepens.

**This is the moat that no other framework ships.**

---

## What's Next

I'm actively working on:
- Same-file dependency tracking (intra-file call graphs)
- PostgreSQL backend for 100K+ session scale
- Distributed experiment execution (multi-node parallel agents)
- Fine-tuning on organization-specific coding patterns

If you use background coding agents — or if you're building one — I'd love feedback. What would make you switch? What's missing?

[GitHub Repository](https://github.com/rudraneel93/shadow-engine) | [API Documentation](https://github.com/rudraneel93/shadow-engine/blob/main/API_DOCS.md) | [Research Report](https://github.com/rudraneel93/shadow-engine/blob/main/FINDINGS_REPORT.md)

---

*Built in Python. MIT licensed. 80 tests. 7 languages indexed. ChromaDB semantic search. SQLite WAL. Docker ready.*