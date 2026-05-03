#!/usr/bin/env python3
"""Test Shadow Engineer on the Hivemind project (Rust codebase)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shadow_engine.main import ShadowEngine

print("Shadow Engineer - Testing on Hivemind (Rust project)")
print("=" * 60)

engine = ShadowEngine(
    storage_path="/Users/rudraneeldas/Desktop/shadow-engine/.shadow-engine/hivemind-test",
    repo_path="/Users/rudraneeldas/Desktop/hivemind",
)

t0 = time.time()
result = engine.bootstrap()
elapsed = time.time() - t0
print(f"Bootstrapped: {result['symbols_indexed']} symbols from {result['files_indexed']} files in {elapsed:.1f}s")
print(f"Semantic search: {'ChromaDB' if result['semantic_search'] else 'fallback'}")
print()

print("Semantic search: 'peer connection'")
for r in engine.search("peer connection")[:3]:
    print(f"  [{r['kind']}] {r['name']} - {r['file_path']}")
print()

print("Semantic search: 'swarm'")
for r in engine.search("swarm")[:3]:
    print(f"  [{r['kind']}] {r['name']} - {r['file_path']}")
print()

print("Semantic search: 'kad'")
for r in engine.search("kad")[:3]:
    print(f"  [{r['kind']}] {r['name']} - {r['file_path']}")
print()

print("Classify: 'optimize the peer discovery loop'")
s = engine.suggest("optimize the peer discovery loop")
print(f"  Type: {s['problem_type']} (confidence: {s['classification_confidence']:.2f})")
print(f"  Approach: {s['recommended_approach']}")
print()

print("Classify: 'add support for relay connections'")
s2 = engine.suggest("add support for relay connections")
print(f"  Type: {s2['problem_type']} (confidence: {s2['classification_confidence']:.2f})")
print(f"  Approach: {s2['recommended_approach']}")
print()

print("Context for LLM: 'add support for relay connections'")
ctx = engine.get_context("add support for relay connections")
print(f"  {len(ctx.split(chr(10)))} lines")
print(f"  Preview: {ctx[:300]}...")
print()

engine.close()
print("Done - Hivemind test complete.")