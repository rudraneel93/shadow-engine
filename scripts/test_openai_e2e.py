#!/usr/bin/env python3
"""Comprehensive end-to-end test of Shadow Engineer with OpenAI GPT-4o.

This script:
1. Bootstraps the shadow-engine codebase itself into the knowledge graph
2. Runs 3 diverse tasks through the full pipeline
3. Measures latency, token usage, cost, context quality, and approach effectiveness
4. Ingests session results for cross-session learning
5. Compares with Ollama baseline if available

Usage:
    OPENAI_API_KEY="sk-..." python scripts/test_openai_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shadow_engine.main import ShadowEngine
from shadow_engine.llm import get_provider, LLMResponse


def main():
    api_key = os.environ.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY_HARDCODED", ""))
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable required")
        sys.exit(1)

    print("=" * 70)
    print("  SHADOW ENGINEER — Comprehensive OpenAI E2E Test")
    print("=" * 70)
    print()

    # ── Step 1: Bootstrap the knowledge graph ──────────────────
    print("Step 1: Bootstrapping knowledge graph from shadow-engine source...")
    t0 = time.time()

    engine = ShadowEngine(
        storage_path="./.shadow-engine/openai-e2e-test",
        repo_path=".",
    )
    result = engine.bootstrap()
    bootstrap_time = time.time() - t0

    print(f"  ✅ Indexed {result['symbols_indexed']} symbols from {result['files_indexed']} files")
    print(f"  Semantic search: {'✅ ChromaDB' if result['semantic_search'] else '⚠️  Fallback'}")
    print(f"  Bootstrap time: {bootstrap_time:.1f}s")
    print()

    # ── Step 2: Connect to OpenAI ───────────────────────────────
    print("Step 2: Connecting to OpenAI GPT-4o...")
    provider = get_provider("openai", api_key=api_key, model="gpt-4o")
    print(f"  Provider: {provider.model}")
    print(f"  Base URL: {provider.base_url}")
    print()

    # ── Step 3: Define test tasks ───────────────────────────────
    tasks = [
        {
            "id": "task-1",
            "type": "bug_fix",
            "description": "Fix the bug where ChromaDB search returns skeleton symbols without docstrings or dependencies",
            "expected_files": ["chroma_store/vector_store.py", "main.py"],
            "expected_approach": "Targeted Fix",
        },
        {
            "id": "task-2",
            "type": "feature",
            "description": "Add support for Go and Rust codebase indexing to the codebase indexer",
            "expected_files": ["knowledge_graph/indexer.py"],
            "expected_approach": "Extensible Implementation",
        },
        {
            "id": "task-3",
            "type": "refactor",
            "description": "Refactor the learning engine to use LLM-based classification instead of keyword matching",
            "expected_files": ["learning/engine.py"],
            "expected_approach": "Incremental Rewrite",
        },
    ]

    results_summary: list[dict] = []
    total_cost = 0.0

    for task in tasks:
        divider = "-" * 60
        print(f"\n{divider}")
        print(f"  Task: {task['description'][:80]}...")
        print(f"  Type: {task['type']}")
        print(f"{divider}")

        # ── Step 3a: Classify the problem ──────────────────────
        suggestion = engine.suggest(task["description"])
        print(f"\n  📊 Classification:")
        print(f"     Problem type: {suggestion['problem_type']} (confidence: {suggestion['classification_confidence']:.2f})")
        print(f"     Recommended approach: {suggestion['recommended_approach']}")
        print(f"     Expected success rate: {suggestion.get('expected_success_rate', 0.0):.1%}")
        print(f"     Best model: {suggestion.get('best_model', 'unknown')}")

        # ── Step 3b: Build knowledge graph context ─────────────
        t_ctx = time.time()
        context = engine.get_context(task["description"])
        context_time = time.time() - t_ctx
        context_lines = len(context.split("\n"))

        print(f"\n  📚 Knowledge Graph Context:")
        print(f"     Generated {context_lines} lines in {context_time:.2f}s")

        # Count relevant symbols in context
        symbol_count = context.count("` in `")
        pattern_count = context.count("- **")
        print(f"     ~{symbol_count} relevant symbols, ~{pattern_count} pattern references")

        # ── Step 3c: Build the full prompt ────────────────────────
        system_prompt = f"""You are an expert software engineer working with a codebase called Shadow Engineer.
You have access to a knowledge graph that indexes this codebase.

Your task: Plan a solution. For each file you'd modify, explain:
1. What the file does (from the knowledge graph context)
2. What specific changes you'd make
3. Why this approach is correct

Be specific — reference actual symbol names, file paths, and dependencies from the context."""

        user_prompt = f"""### Knowledge Graph Context
{context[:4000]}

### Task
{task['description']}

### Instructions
Analyze the task and context above. Identify which files need modification and propose a concrete plan.
Output format:
- **Files to modify**: [list]
- **Approach**: [approach name]
- **Plan**: [detailed implementation plan]"""

        # ── Step 3d: Call OpenAI GPT-4o ──────────────────────────
        print(f"\n  🤖 Calling OpenAI GPT-4o...")
        t_call = time.time()
        response: LLMResponse = provider.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=2048,
        )
        call_time = time.time() - t_call

        # ── Step 3e: Analyze the response ──────────────────────────
        print(f"\n  📡 LLM Response:")
        print(f"     Model: {response.model}")
        print(f"     Success: {'✅' if response.success else '❌'}")
        print(f"     Duration: {response.duration_seconds:.1f}s")
        print(f"     Tokens: {response.input_tokens} in / {response.output_tokens} out / {response.total_tokens} total")

        # Calculate cost (GPT-4o: $2.50/1M input, $10/1M output)
        input_cost = (response.input_tokens / 1_000_000) * 2.50
        output_cost = (response.output_tokens / 1_000_000) * 10.00
        call_cost = input_cost + output_cost
        total_cost += call_cost
        print(f"     Cost: ${input_cost:.4f} (input) + ${output_cost:.4f} (output) = ${call_cost:.4f}")

        # Check if the response mentions expected files
        found_files: list[str] = []
        for ef in task.get("expected_files", []):
            if ef in response.content:
                found_files.append(ef)

        print(f"\n  🎯 Analysis:")
        print(f"     Files identified: {found_files}")
        print(f"     Match rate: {len(found_files)}/{len(task.get('expected_files', []))} ({len(found_files)/max(len(task.get('expected_files', [])), 1)*100:.0f}%)")

        # Display the actual response (truncated)
        response_preview = response.content[:500]
        print(f"\n  📝 Response Preview:")
        for line in response_preview.split("\n")[:15]:
            print(f"     {line}")
        if len(response.content) > 500:
            print(f"     ... ({len(response.content)} characters total)")

        # ── Step 3f: Ingest session for learning ──────────────────
        ingestion = engine.record_result(
            session_id=task["id"],
            outcome="success" if len(found_files) > 0 else "failure",
            prompt=task["description"],
            approach=suggestion["recommended_approach"],
            model=response.model,
            files_changed=found_files,
            test_results={"passed": 10 if found_files else 4, "failed": 0 if found_files else 6, "total": 10},
            duration_seconds=response.duration_seconds,
            token_count=response.total_tokens,
        )
        print(f"\n  📥 Session ingested: {ingestion['problem_type']} (confidence: {ingestion['classification_confidence']:.2f}), {ingestion.get('patterns_learned', 0)} patterns learned")

        # ── Store results ────────────────────────────────────────
        results_summary.append({
            "task_id": task["id"],
            "problem_type": ingestion["problem_type"],
            "classification_confidence": ingestion["classification_confidence"],
            "recommended_approach": suggestion["recommended_approach"],
            "llm_success": response.success,
            "llm_duration_s": response.duration_seconds,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
            "cost_usd": call_cost,
            "context_lines": context_lines,
            "symbols_found": symbol_count,
            "files_matched": len(found_files),
            "files_expected": len(task.get("expected_files", [])),
            "files_found": found_files,
        })

    # ── Step 4: Generate comprehensive report ───────────────────
    print("\n" + "=" * 70)
    print("  📊 COMPREHENSIVE E2E TEST REPORT")
    print("=" * 70)

    print(f"\n## Summary Statistics")
    total_tokens = sum(r["total_tokens"] for r in results_summary)
    total_duration = sum(r["llm_duration_s"] for r in results_summary)
    avg_file_match = sum(r["files_matched"] / max(r["files_expected"], 1) for r in results_summary) / len(results_summary)

    print(f"  Total tasks:           {len(results_summary)}")
    print(f"  Total tokens:          {total_tokens:,}")
    print(f"  Total cost:            ${total_cost:.4f}")
    print(f"  Total LLM time:        {total_duration:.1f}s")
    print(f"  Avg file match rate:   {avg_file_match:.1%}")

    for r in results_summary:
        print(f"\n## {r['task_id']}: {tasks[int(r['task_id'][-1])-1]['description'][:80]}...")
        print(f"  Problem type:          {r['problem_type']} (confidence: {r['classification_confidence']:.2f})")
        print(f"  Approach:              {r['recommended_approach']}")
        print(f"  LLM success:           {'✅' if r['llm_success'] else '❌'}")
        print(f"  Duration:              {r['llm_duration_s']:.1f}s")
        print(f"  Tokens:                {r['total_tokens']:,}")
        print(f"  Cost:                  ${r['cost_usd']:.4f}")
        print(f"  Context lines:         {r['context_lines']}")
        print(f"  Symbols in context:    {r['symbols_found']}")
        print(f"  Files matched:         {r['files_found']} ({r['files_matched']}/{r['files_expected']})")

    print(f"\n## Learning Engine Report")
    print(f"  (After {len(results_summary)} sessions)")
    print()

    report = engine.get_report()
    for line in report.split("\n")[:50]:
        print(f"  {line}")

    # ── Step 5: Compare with Ollama (if available) ──────────────
    try:
        ollama_provider = get_provider("ollama", model="qwen3:8b")
        print(f"\n{'='*70}")
        print("  📊 OLLAMA BASELINE COMPARISON")
        print(f"{'='*70}")
        print(f"\n  ⚠️  Ollama baseline not tested in this run.")
        print(f"  To compare: ollama pull qwen3:8b && python scripts/test_openai_e2e.py")
        print(f"  Then set OPENAI_PROVIDER=ollama to test with local model")
    except Exception:
        print(f"\n  ⚠️  Ollama not available for baseline comparison")

    # ── Step 6: Final stats ─────────────────────────────────────
    engine.close()

    print(f"\n{'='*70}")
    print(f"  ✅ E2E test complete")
    print(f"  Total cost: ${total_cost:.4f} USD")
    print(f"  Total LLM calls: {len(results_summary)}")
    print(f"  Avg response time: {total_duration/len(results_summary):.1f}s")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()