**Show HN: Shadow Engineer — Give AI coding agents memory across sessions**
https://github.com/rudraneel93/shadow-engine

---

Every AI coding agent (Copilot, Claude Code, Cursor, Aider) treats every session like it's never seen your codebase before. Session 100 knows nothing more than Session 1.

Shadow Engineer fixes this with three compounding engines:

**1. Knowledge Graph — "Remember"**
Persistent codebase indexing with ChromaDB semantic search across 5 languages (Python, TS/TSX, JS/JSX, Go, Rust). Semantic search finds relevant symbols even when keywords don't match.

**2. Laboratory — "Experiment"**
Spawns N parallel agent sessions with different strategies (Targeted Fix, Root Cause, Defense in Depth), scores them with logistic curve normalization, and picks the winner automatically.

**3. Learning Engine — "Improve"**
Analyzes every session outcome. Extracts patterns ("this team always writes tests alongside code"). Tracks efficacy ("Targeted Fix succeeds 100% for bugs — Aggressive Rewrite fails 100%"). Suggests approaches.

**v0.4.0 upgrade:** Also provides meta-reasoning priors (classification, strategy, historical efficacy) before knowledge graph context — so the LLM knows what type of problem this is and which approach historically works.

**Verified:** 155 tests (0 failures), multi-model E2E with real Ollama calls (qwen3:8b, qwen3-coder, gpt-oss). 83% file match accuracy across all 3 models — tested on Python and Rust codebases. `pip install shadow-engine` to try.

MIT licensed. Would love feedback from teams using background coding agents.