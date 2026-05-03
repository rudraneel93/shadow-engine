#!/usr/bin/env python3
"""Comprehensive E2E test of all breakthrough modules with real session data.

Tests:
1. CodebaseQA — 7 diverse queries covering all routing paths
2. HotZoneDetector — weighted scoring with real session data
3. LiveMonitor — per-file risk warnings from historical data
4. Full integration test via get_context() — all context layers
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shadow_engine.main import ShadowEngine

BAR = "=" * 70

def main():
    print(BAR)
    print("  SHADOW ENGINEER — Comprehensive Breakthrough Test")
    print(BAR)

    # ── Step 1: Prepare real data ──────────────────────────────
    print("\nStep 1: Bootstrapping + loading 18 real sessions...")
    subprocess.run([sys.executable, "scripts/build_efficacy_data.py"],
                   capture_output=True, timeout=120)
    engine = ShadowEngine(storage_path="./.shadow-engine/efficacy-data", repo_path=".")
    r = engine.bootstrap()
    stats = engine.get_stats()
    print(f"  Symbols: {r['symbols_indexed']}  Files: {r['files_indexed']}")
    print(f"  Sessions: {stats['total_sessions']}  Successful: {stats['successful_sessions']} "
          f"({stats['overall_success_rate']:.0%})")

    # ── Step 2: CodebaseQA ─────────────────────────────────────
    print(f"\n{BAR}")
    print("  STEP 2: CodebaseQA — Natural Language Q&A")
    print(BAR)
    queries = [
        ("How does authentication work?", "how-question"),
        ("What's the most dangerous file?", "danger-question"),
        ("What tests should I run if I change main.py?", "test-question"),
        ("Who depends on ShadowEngine?", "dependency-question"),
        ("What files handle rate limiting?", "file-question"),
        ("What conventions does this codebase follow?", "pattern-question"),
        ("Tell me about SQLite storage", "general-question"),
    ]
    qa_results = {}
    for query, qtype in queries:
        print(f"\n🟢 [{qtype}] {query}")
        answer = engine.qa.ask(query)
        lines = answer.split("\n")
        for line in lines[:10]:
            print(f"    {line}")
        qa_results[qtype] = {
            "lines": len(lines),
            "has_data": len(lines) > 2 and bool(lines[3].strip()),
        }

    # ── Step 3: HotZoneDetector ─────────────────────────────────
    print(f"\n{BAR}")
    print("  STEP 3: Hot Zone Detection")
    print(BAR)

    zones = engine.hot_zones.detect_hot_zones(min_sessions=1, top_n=12)
    print(f"\n  {len(zones)} hot zones found:")
    for i, z in enumerate(zones[:10], 1):
        e = "🔴" if z["failure_rate"] >= 0.3 else "🟡" if z["failure_rate"] >= 0.1 else "🟢"
        print(f"    {i:2d}. {e} {z['file_path']:<40s} "
              f"Score:{z['hot_score']:.3f}  Mods:{z['modification_count']}  "
              f"Fail:{z['failure_count']}({z['failure_rate']:.0%})")

    hotzone_report = engine.hot_zones.generate_hot_zone_report()
    hotzone_lines = hotzone_report.split("\n")

    # ── Step 4: LiveMonitor ─────────────────────────────────────
    print(f"\n{BAR}")
    print("  STEP 4: LiveMonitor — Real-time Risk Warnings")
    print(BAR)

    test_files = [
        "main.py", "sqlite_store/db.py", "knowledge_graph/indexer.py",
        "api_server/server.py", "chroma_store/vector_store.py",
        "knowledge_graph/store.py",
    ]

    print(f"\n  Per-file risk analysis ({len(test_files)} files):")
    live_results = []
    for f in test_files:
        risk = engine.live_monitor.check_file(f)
        live_results.append(risk)
        print(f"    {risk['risk_label']:<7s} | {f:<40s} | "
              f"mods:{risk['modification_count']:2d} | "
              f"break:{risk['test_break_rate']:.0%} | "
              f"shrink:{risk['shrinkage']:.0%}")

    print(f"\n  Live warning text (pre-session):")
    warnings = engine.live_monitor.generate_warnings_text(test_files)
    for line in warnings.split("\n")[:12]:
        print(f"    {line}")

    engine.live_monitor.reset()

    # ── Step 5: get_context() integration ───────────────────────
    print(f"\n{BAR}")
    print("  STEP 5: Full get_context() Integration")
    print(BAR)

    context = engine.get_context("fix the login rate-limiting bug")
    context_lines = context.split("\n")
    sections_found = []

    for section in [
        "Problem Classification", "Historical Insight",
        "Proven Fix Patterns", "Proven Code-Level Fix Patterns",
        "Live Risk Warnings", "Test Risk by File",
        "Risk Assessment (Bayesian)", "Knowledge Graph Context",
    ]:
        if section in context:
            sections_found.append(section)

    print(f"\n  Context length: {len(context_lines)} lines")
    print(f"  Sections present ({len(sections_found)}/8):")
    for sec in sections_found:
        print(f"    ✅ {sec}")

    # ── Step 6: Full test suite ─────────────────────────────────
    print(f"\n{BAR}")
    print("  STEP 6: Full pytest suite")
    print(BAR)

    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True, text=True, timeout=360,
    )
    last_line = pytest_result.stdout.strip().split("\n")[-1] if pytest_result.stdout else "no output"
    print(f"  {last_line}")

    engine.close()

    # ── Step 7: Summary ─────────────────────────────────────────
    print(f"\n{BAR}")
    print("  📊 TEST RESULTS SUMMARY")
    print(BAR)

    # CodebaseQA
    qa_passing = sum(1 for v in qa_results.values() if v["has_data"])
    qa_total = len(qa_results)
    print(f"\n  CodebaseQA:   {qa_passing}/{qa_total} queries returned real data")

    # HotZoneDetector
    hz_passing = len(zones) >= 6
    print(f"  HotZones:     {'✅' if hz_passing else '❌'} {len(zones)} zones detected")

    # LiveMonitor
    live_passing = sum(1 for r in live_results if r["modification_count"] > 0)
    print(f"  LiveMonitor:  {'✅' if live_passing >= 2 else '⚠️'} {live_passing}/{len(live_results)} files have session data")

    # get_context
    ctx_passing = len(sections_found) >= 4
    print(f"  get_context:  {'✅' if ctx_passing else '⚠️'} {len(sections_found)}/8 context layers active")

    # Tests
    tests_passing = "passed" in last_line.lower()
    print(f"  Test suite:   {'✅' if tests_passing else '❌'} {last_line}")

    overall = sum([qa_passing >= 4, hz_passing, live_passing >= 2, ctx_passing, tests_passing])
    print(f"\n  Overall:      {overall}/5 checks passing")
    print(f"                {'✅ PRODUCTION-READY' if overall >= 4 else '⚠️ NEEDS ATTENTION'}")
    print(BAR)


if __name__ == "__main__":
    main()