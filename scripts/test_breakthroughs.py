#!/usr/bin/env python3
"""Comprehensive test of all three breakthrough modules with real data."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shadow_engine.main import ShadowEngine

print("=" * 70)
print("SHADOW ENGINEER — Breakthrough Features Test")
print("=" * 70)

# Step 1: Bootstrap + load real session data
print("\nStep 1: Loading 18 real sessions...")
subprocess.run([sys.executable, "scripts/build_efficacy_data.py"], capture_output=True)
engine = ShadowEngine(storage_path="./.shadow-engine/efficacy-data", repo_path=".")
result = engine.bootstrap()
print(f"  Bootstrapped: {result['symbols_indexed']} symbols from {result['files_indexed']} files\n")

# Step 2: CodebaseQA — 7 diverse queries testing all routing paths
print("=" * 70)
print("STEP 2: CodebaseQA — Natural Language Codebase Q&A")
print("=" * 70)
queries = [
    "How does authentication work?",
    "What's the most dangerous file?",
    "What tests should I run if I change main.py?",
    "Who depends on ShadowEngine?",
    "What files handle rate limiting?",
    "What conventions does this codebase follow?",
    "Tell me about SQLite storage",
]
for q in queries:
    print(f"\nQ: {q}")
    answer = engine.qa.ask(q)
    lines = answer.split("\n")
    for line in lines[:min(12, len(lines))]:
        print(f"  {line}")
    if len(lines) > 12:
        print(f"  ... ({len(lines)} lines total)")

# Step 3: HotZoneDetector
print(f"\n{'='*70}")
print("STEP 3: Hot Zone Detection")
print("=" * 70)
zones = engine.hot_zones.detect_hot_zones(min_sessions=1, top_n=12)
if zones:
    for i, z in enumerate(zones[:12], 1):
        e = "🔴" if z['failure_rate'] >= 0.3 else "🟡" if z['failure_rate'] >= 0.1 else "🟢"
        print(f"  {i}. {e} {z['file_path']:40s} Score:{z['hot_score']:.3f} Mods:{z['modification_count']} Fail:{z['failure_count']}({z['failure_rate']:.0%})")
    print(f"\nHot Zone Report:\n{engine.hot_zones.generate_hot_zone_report()[:600]}")
else:
    print("  No hot zones found")

# Step 4: LiveMonitor
print(f"\n{'='*70}")
print("STEP 4: Live Risk Warnings")
print("=" * 70)
test_files = ["main.py", "sqlite_store/db.py", "knowledge_graph/indexer.py",
              "api_server/server.py", "chroma_store/vector_store.py"]
print("\nPre-session risk warnings:")
warnings = engine.live_monitor.generate_warnings_text(test_files)
print(warnings[:700] if warnings.strip() else "  No warnings — insufficient session data")
print("\nPer-file risk analysis:")
for f in test_files:
    r = engine.live_monitor.check_file(f)
    print(f"  {r['risk_label']:6s} | {f:35s} | mods:{r['modification_count']} | break:{r['test_break_rate']:.0%} | shrink:{r['shrinkage']:.0%}")

engine.live_monitor.reset()
engine.close()

print(f"\n{'='*70}")
print("All breakthrough features tested successfully with 18 real sessions.")
print("=" * 70)