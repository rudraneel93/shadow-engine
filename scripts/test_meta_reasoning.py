#!/usr/bin/env python3
"""Demonstrates the meta-reasoning upgrade: before vs after."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shadow_engine.main import ShadowEngine

print("=" * 70)
print("  SHADOW ENGINEER — Meta-Reasoning Upgrade Demo")
print("=" * 70)
print()

engine = ShadowEngine(
    storage_path="./.shadow-engine/meta-reasoning-demo",
    repo_path="/Users/rudraneeldas/Desktop/hivemind",
)
result = engine.bootstrap()
print(f"Bootstrapped: {result['symbols_indexed']} symbols from {result['files_indexed']} files\n")

tasks = [
    "add peer scoring to the swarm reputation system",
    "fix the Discord bot message parsing",
    "optimize the peer discovery network loop",
]

for task in tasks:
    print("-" * 60)
    print(f"  Task: {task}")
    print("-" * 60)

    suggestion = engine.suggest(task)
    print(f"\n  📊 Classification:")
    print(f"     Type: {suggestion['problem_type']} (confidence: {suggestion['classification_confidence']:.2f})")
    print(f"     Approach: {suggestion['recommended_approach']}")
    if suggestion.get("expected_success_rate", 0) > 0:
        print(f"     Expected success: {suggestion['expected_success_rate']:.0%}")
    print(f"     Best model: {suggestion.get('best_model', 'unknown')}")
    print(f"     Evidence: {suggestion.get('evidence', 'No historical data yet')}")

    ctx = engine.get_context(task)
    print(f"\n  📄 Generated Prompt ({len(ctx.split(chr(10)))} lines)")
    for line in ctx.split("\n")[:25]:
        print(f"     {line}")
    if ctx.count("\n") > 25:
        print(f"     ... ({ctx.count(chr(10))} total lines)")
    print()

engine.close()
print("\n✅ Meta-reasoning upgrade demo complete.")
print("   Every context block now includes: classification, approach, historical evidence.")