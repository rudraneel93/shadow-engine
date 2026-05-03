#!/usr/bin/env python3
"""Multi-model comparison test — runs 3 tasks against 3 local Ollama models.

Measures: file match rate, latency, tokens, response quality, cost.
Outputs a comparison matrix for the README.

Usage:
    python scripts/test_multimodel_e2e.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shadow_engine.main import ShadowEngine
from shadow_engine.llm import get_provider, LLMResponse

MODELS = ["qwen3:8b", "qwen3-coder:480b-cloud", "gpt-oss:120b-cloud"]

TASKS = [
    {
        "id": "bug_fix", "type": "bug_fix",
        "desc": "Fix the bug where ChromaDB search returns skeleton symbols without docstrings or dependencies",
        "expected_files": ["chroma_store/vector_store.py", "main.py"],
    },
    {
        "id": "feature", "type": "feature",
        "desc": "Add support for Go and Rust codebase indexing to the knowledge graph indexer",
        "expected_files": ["knowledge_graph/indexer.py"],
    },
    {
        "id": "refactor", "type": "refactor",
        "desc": "Refactor the learning engine to use LLM-based classification instead of keyword matching",
        "expected_files": ["learning/engine.py"],
    },
]

SYS_PROMPT = (
    "You are an expert software engineer with a knowledge graph of a codebase. "
    "Identify which files need modification and propose a concrete plan. "
    "Be specific — reference actual symbol names and file paths from the context."
)


def run_model(engine: ShadowEngine, model: str) -> dict:
    print(f"\n{'='*70}")
    print(f"  🧠 Testing model: {model}")
    print(f"{'='*70}")
    provider = get_provider("ollama", model=model)
    model_results: list[dict] = []

    for task in TASKS:
        print(f"\n  Task: {task['desc'][:70]}...")

        # Build context from knowledge graph
        context = engine.get_context(task["desc"])
        user_prompt = f"### Knowledge Graph\n{context[:3000]}\n\n### Task\n{task['desc']}\n\n### Instructions\nIdentify files to modify and propose a plan."

        t0 = time.time()
        resp: LLMResponse = provider.generate(prompt=user_prompt, system_prompt=SYS_PROMPT, max_tokens=1024)
        elapsed = time.time() - t0

        found = [ef for ef in task["expected_files"] if ef in resp.content]
        match_pct = len(found) / max(len(task["expected_files"]), 1) * 100

        print(f"     {'✅' if resp.success else '❌'} Files: {found} ({match_pct:.0f}%) | {resp.duration_seconds:.0f}s | ~{resp.total_tokens} tokens")

        model_results.append({
            "task": task["id"], "success": resp.success, "duration_s": resp.duration_seconds,
            "tokens": resp.total_tokens, "files_found": found, "match_pct": match_pct,
        })

    avg_match = sum(r["match_pct"] for r in model_results) / len(model_results)
    total_time = sum(r["duration_s"] for r in model_results)
    total_tokens = sum(r["tokens"] for r in model_results)
    success_count = sum(1 for r in model_results if r["success"])

    return {
        "model": model, "tasks": model_results, "avg_match_pct": avg_match,
        "total_time_s": total_time, "total_tokens": total_tokens,
        "success_rate": success_count / len(model_results) * 100,
    }


def print_matrix(all_results: list[dict]) -> None:
    print(f"\n\n{'='*80}")
    print(f"  📊 MULTI-MODEL COMPARISON MATRIX")
    print(f"{'='*80}\n")

    header = f"| Model | File Match | Success | Tokens | Total | Avg Latency | Cost |"
    sep = "|" + "|".join("-" * (len(h) - 2) for h in header.split("|")[1:-1]) + "|"

    print(header)
    print(sep)

    for r in all_results:
        model = r["model"].ljust(25)
        match = f"{r['avg_match_pct']:.0f}%".ljust(11)
        success = f"{r['success_rate']:.0f}%".ljust(8)
        tokens = f"~{r['total_tokens']:,}".ljust(7)
        total = f"{r['total_time_s']:.0f}s".ljust(6)
        avg = f"{r['total_time_s']/len(TASKS):.0f}s".ljust(13)
        cost = "$0.00".ljust(5)
        print(f"| {model}| {match}| {success}| {tokens}| {total}| {avg}| {cost}|")
    print(sep)

    # Grade each model
    print(f"\n{'='*80}")
    print(f"  📋 MODEL GRADES")
    print(f"{'='*80}")
    for r in all_results:
        m = r["avg_match_pct"]
        grade = "A" if m >= 80 else "B" if m >= 50 else "C" if m >= 30 else "D"
        print(f"  {r['model']:.<30s} {grade} ({r['avg_match_pct']:.0f}% file match, {r['total_time_s']:.0f}s total)")

    # Winner
    best = max(all_results, key=lambda r: r["avg_match_pct"])
    fastest = min(all_results, key=lambda r: r["total_time_s"])
    print(f"\n  🏆 Best accuracy:  {best['model']} ({best['avg_match_pct']:.0f}% match)")
    print(f"  ⚡ Fastest:        {fastest['model']} ({fastest['total_time_s']:.0f}s total)")
    print(f"{'='*80}\n")


def main():
    print("=" * 70)
    print("  SHADOW ENGINEER — Multi-Model E2E Comparison Test")
    print(f"  Models: {', '.join(MODELS)}")
    print(f"  Tasks: {len(TASKS)} (bug_fix, feature, refactor)")
    print("=" * 70)

    engine = ShadowEngine(storage_path="./.shadow-engine/multimodel-e2e", repo_path=".")
    print(f"\nStep 1: Bootstrapping...")
    t0 = time.time()
    result = engine.bootstrap()
    print(f"  ✅ {result['symbols_indexed']} symbols from {result['files_indexed']} files ({time.time()-t0:.1f}s)")

    all_results: list[dict] = []
    for model in MODELS:
        model_result = run_model(engine, model)
        all_results.append(model_result)

    engine.close()
    print_matrix(all_results)


if __name__ == "__main__":
    main()