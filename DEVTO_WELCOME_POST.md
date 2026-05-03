Hey! I'm Rudraneel, a developer from India who's been deep in the AI coding tools space. Most AI agents generate code. I built one that *remembers*.

For the past several months, I've been working on a background coding agent that solves the biggest problem no one talks about: **every AI coding agent has amnesia.** Ramp's Inspect, Open-Inspect, Copilot, Claude Code — they all treat every session like a blank slate. Session 100 knows nothing more than Session 1.

So I built **Shadow Engineer** — a learning layer that sits on top of any background coding agent and provides three things no other framework ships:

🧠 **Knowledge Graph** — Indexes your entire codebase (7 languages) into a persistent semantic graph. ChromaDB embeddings so "fix the login rate limiting" finds `throttle_requests()` even when "throttle" doesn't appear in your query.

🔬 **Laboratory** — Spawns N parallel agent sessions with different strategies (Targeted Fix, Root Cause + Guard, Defense in Depth) and picks the winner using configurable logistic scoring. Not one attempt — choose from proven solutions.

📈 **Learning Engine** — Analyzes every session outcome. Extracts patterns ("this team always writes tests alongside code changes"). Tracks efficacy ("Targeted Fix succeeds 85% of the time"). Suggests approaches. The 100th session has the benefit of 99 prior attempts.

**Tech stack:** Python 3.12+, SQLite WAL, ChromaDB, FastAPI, Redis rate limiting, Docker. 110 tests, MIT licensed. Tested end-to-end with a real Ollama LLM.

I recently open-sourced the full project:

🔗 github.com/rudraneel93/shadow-engine

If you're into AI agents, developer tools, Python, or just love the idea of software that *learns from its own mistakes*, I think you'll find something interesting there. Happy to connect with anyone building at the intersection of AI and developer experience.

— Rudraneel