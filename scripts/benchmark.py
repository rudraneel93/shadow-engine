#!/usr/bin/env python3
"""Performance benchmark for shadow-engine core operations.

Measures: bootstrap time, search latency, context generation time.
Run: cd shadow-engine && python scripts/benchmark.py
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from shadow_engine.main import ShadowEngine


def benchmark(name: str, func, iterations: int = 1) -> float:
    """Run a benchmark and return average time in ms."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    avg = sum(times) / len(times)
    print(f"  {name}: {avg:.1f}ms (avg over {iterations} run(s))")
    return avg


def main():
    import sys
    ci_mode = "--ci" in sys.argv
    print("Shadow Engineer — Performance Benchmarks")
    print("=" * 50)

    engine = ShadowEngine(repo_path=".")

    # Bootstrap
    benchmark("Bootstrap (incremental)", lambda: engine.bootstrap())

    # Search
    benchmark("Search (keyword)", lambda: engine.search("ShadowEngine"))
    benchmark("Search (semantic)", lambda: engine.search("rate limiting"))

    # Context
    benchmark("Context generation", lambda: engine.get_context("fix the login bug"))

    # Impact
    benchmark("Impact analysis", lambda: engine.impact("ShadowEngine"))

    # Suggest
    benchmark("Approach suggestion", lambda: engine.suggest("fix a bug"))

    print("=" * 50)
    print("Done.")


if __name__ == "__main__":
    main()