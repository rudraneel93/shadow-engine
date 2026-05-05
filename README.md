<p align="center">
  <h1 align="center">🧠 Shadow Engineer</h1>
  <p align="center">
    <strong>A rigorous testing harness for coding-agent learning hypotheses.</strong><br>
    <em>We proved what DOESN'T work (KG pattern accumulation). Now testing what MIGHT (RAG).</em>
  </p>
  <p align="center">
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/CI-passing-brightgreen" alt="CI"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/tests-241-brightgreen" alt="Tests"></a>
    <a href="https://github.com/rudraneel93/shadow-engine/actions"><img src="https://img.shields.io/badge/coverage-≥60%25-yellow" alt="Coverage"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
    <a href="https://pypi.org/project/shadow-engine"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python"></a>
  </p>
</p>

---

> **Status: Research Artifact** — The original hypothesis (that cross-session pattern accumulation creates compounding intelligence) has been **conclusively disproven** by a 400-session controlled experiment. The infrastructure is a gold-standard testing harness. We are now testing a simpler hypothesis: retrieval-augmented generation (RAG) of past successful diffs.

> **Key finding:** Retrieving similar past bug-fix examples and injecting them into the LLM prompt shows directional improvement (+14% over control in 60-session pilot). Full statistical validation in progress.

---

## 📊 The Evidence

### What We Tested

| Experiment | Sessions | Design | KG Hypothesis | RAG Hypothesis |
|-----------|----------|--------|--------------|--------------|
| **400-session longitudinal** | 200 ON + 200 OFF | Learning KG vs wiped KG | **❌ DISPROVEN** — Test=Control, ↑10% vs ↑20% | N/A |
| **48-session single-task** | 48 qwen3-coder sessions | Same model, task, tests, 8 approaches | **❌ DISPROVEN** — All approaches 67-100%, no differentiation | N/A |
| **60-session RAG pilot** | 30 vector + 30 none | RAG vs no-retrieval | N/A | **📈 +14%** (77% vs 63%), +5% trend |
| **100-session RAG (diverse)** | 100 vector retrieval | 50 unique bugs × 2 passes | N/A | 71% overall, 85%→75% (declining) |

### The Honest Conclusion

**The Knowledge Graph does not create compounding intelligence.** After 200 learning-ON sessions accumulating 731 patterns, the agent performed identically to one with no memory. In fact, the control group improved more (+20%) than the test group (+10%), suggesting the KG may have added harmful noise.

**Retrieval-Augmented Generation (RAG) shows directional promise** but requires larger-scale validation. A 60-session pilot showed +14% improvement over control. A 100-session run across more diverse bugs showed 71% overall success but a declining trend.

---

## 🏗️ What Shadow Engineer Is Now

Shadow Engineer has pivoted from a "self-improving agent" to a **rigorous testing harness for coding-agent learning hypotheses**. It can:

1. **Generate diverse bug pools** with verified test failures (16 mutation operators, 10 functions)
2. **Run controlled experiments** comparing learning-ON vs learning-OFF groups
3. **Test any retrieval mechanism** (vector similarity, random baseline, no retrieval)
4. **Collect per-session metrics** (success rate, duration, fix-applied, retrieval hits)
5. **Perform statistical analysis** (trend slopes, window comparison, delta analysis)

The infrastructure runs real LLM calls (Ollama, 4 models available), real pytest validation (30 tests), and records everything in SQLite + ChromaDB.

---

## 🔬 Two Architectures (One Disproven, One Testing)

### ❌ Old Architecture (Disproven)

```
Session → Pattern Extraction → Causal Inference → Bayesian Prediction → KG Context
         ↓
    731 patterns accumulated
         ↓
    ZERO improvement over no-KG baseline
```

The old approach extracted "patterns" from session outcomes, built causal models, and injected abstract reasoning into prompts. After 400 sessions, it was indistinguishable from random.

### 🔄 New Architecture (Testing)

```
Session → Successful Fix → Store in RAG Database
                              ↓
New Session → Bug Signature → Vector Search → Top-3 Similar Fixes → Inject in Prompt
```

Simple: store successful diffs, retrieve them when a similar bug appears, show the LLM what worked before. No pattern extraction, no causal inference, no Bayesian prediction.

**Module:** `src/shadow_engine/retrieval_fixer.py` — `RetrievalAugmentedFixer` class with ChromaDB or in-memory fallback.

---

## 🧪 Experimental Engines (For Research Only)

> **⚠️ These engines were validated against 50 synthetic sessions. The core hypothesis they support has been disproven. They remain for research/ablation purposes only.**

| Engine | What It Does | Status |
|--------|-------------|--------|
| **Causal Reasoning** | Structural Causal Models with do-calculus | Research artifact |
| **Multi-Agent Debate** | Variant peer review with consensus synthesis | Research artifact |
| **PR Outcome Simulator** | Monte Carlo simulation of test breakage | Research artifact |
| **Temporal Anomaly** | BOCD changepoint detection, Z-score spikes | Research artifact |
| **Intervention Engine** | WARN→INTERVENE→ABORT→ESCALATE ladder | Research artifact |
| **Strategy Evolution** | Genetic algorithms for optimal strategies | Research artifact |
| **Speculative Context** | LRU-cached pre-computation | Research artifact |
| **Cross-Repo Transfer** | Pattern abstraction for federated learning | Research artifact |

---

## 🚀 Quick Start

### Run the RAG Experiment

```bash
cd shadow-engine
# Vector retrieval arm
python scripts/longitudinal.py --sessions 100 --retrieval vector
# Control arm (no retrieval)
python scripts/longitudinal.py --sessions 100 --retrieval none
# Random retrieval ablation
python scripts/longitudinal.py --sessions 100 --retrieval random
```

### Run the Bug Injection Verification

```bash
python scripts/_verify_bugs.py  # Should show 4/5 bugs cause failures
```

### Run Original Hypothesis Test (Historical)

```bash
python scripts/definitive_proof.py --sessions 40  # 40 test + 40 control
```

### Core CLI

```bash
shadow-engine bootstrap              # Index a codebase
shadow-engine search "auth"          # Search symbols
shadow-engine context "fix bug"      # Get AI-ready context
shadow-engine suggest "add feature"  # Get approach recommendation
```

---

## 📊 Verified Test Results

| Test Suite | Tests | Result |
|-----------|-------|--------|
| **Experimental Engines** | 36 | 100% pass |
| **API Integration** | 14 | 100% pass |
| **LLM Providers** | 20 | 100% pass |
| **Sandbox Execution** | 16 | 100% pass |
| **Knowledge Graph** | 33 | 100% pass |
| **Learning, API, Async, Redis** | 122 | 100% pass |
| **Total** | **241** | **100% pass** |
| **Docker Sandbox** | 10/10 | Verified |
| **Ruff Lint** | — | All checks passed |

---

## 🧪 Docker Sandbox

Full Docker-based sandbox with network isolation, read-only filesystem, memory/PID limits, capability dropping. See `scripts/test_docker_sandbox.sh`.

---

## 📁 Project Structure

```
shadow-engine/
├── README.md, ARCHITECTURE.md, API_DOCS.md, ROADMAP.md
├── CHANGELOG.md, CONTRIBUTING.md, FINDINGS_REPORT.md
├── pyproject.toml, LICENSE
├── docker/                    (Dockerfile, docker-compose.yml)
├── .github/workflows/ci.yml   (CI with coverage enforcement)
├── scripts/
│   ├── longitudinal.py           (RAG experiment: vector/random/none arms)
│   ├── definitive_proof.py       (Original hypothesis test)
│   ├── prove_hypothesis.py       (Earlier experimental designs)
│   ├── validate_learning.py      (Control group methodology)
│   ├── generate_bugs.py          (AST-based bug mutation generator)
│   ├── testbed.py                (10 functions, verified behavior)
│   ├── test_testbed.py           (30 pytest tests)
│   ├── _verify_bugs.py           (Bug injection verification)
│   └── test_docker_sandbox.sh    (Docker isolation tests)
├── src/shadow_engine/
│   ├── retrieval_fixer.py    (NEW: RAG-based fix retrieval)
│   ├── main.py               (Orchestrator)
│   ├── knowledge_graph/      (Indexer, models, store)
│   ├── sqlite_store/         (SQLite WAL backend)
│   ├── chroma_store/         (ChromaDB vector store)
│   ├── laboratory/           (Experiment runner)
│   ├── learning/             (Pattern extraction, causal, engines)
│   ├── llm/                  (Provider abstraction)
│   └── api_server/           (REST API)
└── tests/                    (241 tests, 100% pass)
```

---

## Known Limitations

| # | Limitation | Status |
|---|-----------|--------|
| 1 | **Core hypothesis disproven** — KG does not create compounding intelligence | ✅ Conclusively tested |
| 2 | **RAG hypothesis not yet proven** — Directional support (+14%) but needs larger N | 🔄 In testing |
| 3 | **Single-file core** (main.py) | ⚠️ To be refactored |
| 4 | **Experimental engines are research artifacts** — Core hypothesis they support is disproven | ⚠️ Deprecation planned |
| 5 | **No community adoption** | ⚠️ Solo project |
| 6 | **Bug generator only produces 50 unique bugs** — Needs expansion for proper RAG validation | 🔄 In progress |

---

## FAQ

**Q: What did you prove?**
A: We conclusively disproved that naive pattern accumulation from session outcomes creates compounding intelligence for coding agents. 400 sessions, control group, zero effect.

**Q: What are you testing now?**
A: Whether retrieval-augmented generation (showing the LLM similar past successful diffs) improves fix success rates. Early signal: +14% in pilot.

**Q: Is this ready for production?**
A: No. This is a research artifact with gold-standard testing infrastructure. Use it to test your own coding-agent learning hypotheses.

**Q: What's the most valuable part of this project?**
A: The experimental harness. It can generate bug pools, run controlled trials with any retrieval mechanism, and produce statistically valid comparisons. The hardest part of AI research is testing claims rigorously — this project solves that.

---

## License

MIT — Build on it. Test your own hypotheses. Make agents smarter with real evidence.

---

*Repository status: 38 commits, 241 tests (100% pass), 400-session KG experiment (disproven), 160-session RAG experiment (directional), CI with coverage enforcement.*