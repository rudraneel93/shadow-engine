# Contributing to Shadow Engineer

Thank you for your interest in contributing! Shadow Engineer is a solo-developed Alpha-stage project that welcomes community contributions, bug reports, and feature ideas.

## Development Setup

```bash
git clone https://github.com/rudraneel93/shadow-engine.git
cd shadow-engine
pip install -e ".[dev]"

# Bootstrap with the project's own codebase (dogfooding)
shadow-engine bootstrap
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src/shadow_engine --cov-report=term-missing

# Run specific test file
pytest tests/test_experimental_engines.py -v

# Lint checks
ruff check src/
```

## Code Style

- **Formatter:** Ruff (config in `pyproject.toml`)
- **Line length:** 100 characters
- **Type hints:** Required for all new functions/methods
- **Imports:** Use `from __future__ import annotations` at top of files
- **Docstrings:** Required for all public functions, classes, and modules

## Architecture Overview

Shadow Engineer has three core engines:

| Engine | Location | Purpose |
|--------|----------|---------|
| **Knowledge Graph** | `knowledge_graph/` | Indexes codebase into persistent SQLite + ChromaDB store |
| **Laboratory** | `laboratory/` | Spawns parallel agent experiments with configurable scoring and debate |
| **Learning Engine** | `learning/` | Analyzes sessions to extract patterns, track efficacy, and improve strategies |

Plus experimental engines in `learning/`:
- `causal_engine.py` — Structural causal models for counterfactual reasoning
- `pr_simulator.py` — Monte Carlo PR outcome simulation
- `temporal_anomaly.py` — Bayesian Online Changepoint Detection
- `intervention_engine.py` — Mid-session risk intervention
- `strategy_evolution.py` — Genetic algorithm strategy optimization
- `speculative_context.py` — LRU-cached context pre-computation
- `transfer_store.py` — Cross-codebase pattern transfer
- `context_budget.py` — Token-budget-aware context builder

## Adding a New Language

1. Add pre-compiled regex patterns to `_COMPILED_PATTERNS` in `knowledge_graph/indexer.py`
2. Add the file extension to `SUPPORTED_EXTENSIONS`
3. Add docstring extraction logic in `_extract_docstring()`
4. Add symbol end detection in `_find_symbol_end()`
5. For production-quality parsing, integrate a tree-sitter grammar (see `pyproject.toml` — tree-sitter is already a dependency)

## Adding a New LLM Provider

1. Subclass `LLMProvider` in `llm/providers.py`
2. Implement `generate(prompt, system_prompt, max_tokens, retries) -> LLMResponse`
3. Use `httpx` for HTTP API calls (not subprocess)
4. Handle errors with custom exceptions (`LLMRateLimitError`, `LLMAuthError`, `LLMConnectionError`, `LLMTimeoutError`)
5. Add to `get_provider()` factory function
6. Write tests in `tests/test_providers.py`

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes with tests
4. Run `ruff check src/` and `pytest tests/ -v`
5. Commit with a descriptive message
6. Push and open a Pull Request

## Issue Guidelines

- **Bug reports:** Include steps to reproduce, expected behavior, actual behavior, and environment details
- **Feature requests:** Describe the use case and why it's valuable
- **Questions:** Use GitHub Discussions or Issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

*Shadow Engineer is MIT-licensed. Build on it. Ship it. Make agents smarter.*