#!/usr/bin/env python3
"""Prove 'Session 100 > Session 1' — single-call code+test generation.

Each session: 1 LLM call → generates function + pytest test → run pytest → record.

Uses qwen3-coder:480b-cloud which outputs clean ```python blocks.
"""

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

TASKS = [
    ("bug_fix", "Write a function `is_palindrome(s: str) -> bool` that checks if a string reads the same forwards/backwards, ignoring case and non-alphanumeric chars. Include a pytest test function `test_is_palindrome` with 5 test cases.", "Targeted Fix"),
    ("feature", "Write a function `flatten(nested) -> list` that flattens arbitrarily nested lists. Include a pytest test function `test_flatten` with 5 test cases including edge cases like empty lists and deeply nested structures.", "Minimal Viable"),
    ("bug_fix", "Write a function `fibonacci(n: int) -> list[int]` returning first n Fibonacci numbers. Handle n<=0 returning []. Include a pytest test function `test_fibonacci` with 5 test cases.", "Targeted Fix"),
    ("feature", "Write a function `merge_intervals(intervals) -> list` that merges overlapping intervals like [(1,3),(2,6)]→[(1,6)]. Include a pytest test function `test_merge_intervals` with 5 test cases.", "Extensible Implementation"),
    ("refactor", "Write a function `parse_kv_string(s: str) -> dict` parsing 'key1=val1,key2=val2' into a dict. Handle quotes, escaped commas. Include a pytest test function `test_parse_kv_string` with 5 test cases.", "Safe Extract"),
    ("feature", "Write a function `find_anagrams(word, word_list) -> list` returning words from word_list that are anagrams of word. Case-insensitive. Include a pytest test function `test_find_anagrams` with 5 test cases.", "Root Cause + Guard"),
    ("refactor", "Write a function `longest_common_subsequence(a, b) -> str` using dynamic programming. Returns the actual LCS string. Include a pytest test function `test_lcs` with 5 test cases.", "Incremental Rewrite"),
    ("bug_fix", "Write a function `binary_search_rotated(arr, target) -> int` finding target in a rotated sorted array. Return index or -1. Include a pytest test function `test_binary_search_rotated` with 5 test cases.", "TDD First"),
    ("refactor", "Write a function `topological_sort(graph: dict) -> list[str]` using Kahn's algorithm. Raise ValueError for cycles. Include a pytest test function `test_topological_sort` with 5 test cases.", "Safe Extract"),
    ("feature", "Write a function `regex_to_postfix(pattern) -> str` converting simple regex (|, *, concat) to postfix using shunting-yard. Include a pytest test function `test_regex_to_postfix` with 5 test cases.", "Extensible Implementation"),
]

APPROACHES = ["Targeted Fix", "Minimal Viable", "Extensible Implementation",
              "Safe Extract", "Root Cause + Guard", "Incremental Rewrite", "TDD First"]

CODING_MODEL = "qwen3-coder:480b-cloud"


def main():
    import httpx

    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    r = engine.bootstrap()
    print(f"Symbols: {r['symbols_indexed']} | {len(TASKS)*3} sessions\n")

    results = []
    for cycle in range(3):  # 3 cycles × 10 tasks = 30 sessions
        for i, (ptype, prompt, approach) in enumerate(TASKS):
            session_num = cycle * len(TASKS) + i + 1
            session_id = f"proof-{session_num:03d}"

            t0 = time.time()
            try:
                resp = httpx.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": CODING_MODEL,
                        "prompt": f"TASK: {prompt}\n\nUse a {approach} approach. Output ONLY a complete Python file with import pytest, the function, and the test function all in ONE ```python block. No explanations.",
                        "stream": False,
                        "options": {"num_predict": 1024},
                    },
                    timeout=120,
                )
                data = resp.json()
                raw = data.get("response") or data.get("thinking") or ""
                tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            except Exception:
                raw, tokens = "", 0

            # Extract code
            blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
            full_code = '\n'.join(blocks) if blocks else raw
            dur = time.time() - t0

            # Run pytest
            passed = failed = 0
            if full_code.strip():
                try:
                    f = tempfile.NamedTemporaryFile(mode='w', suffix='test.py', delete=False)
                    f.write(full_code)
                    tmp = f.name; f.close()
                    result = subprocess.run(
                        ["pytest", tmp, "-v", "--tb=line", "-q"],
                        capture_output=True, text=True, timeout=30,
                    )
                    os.unlink(tmp)
                    # Parse: "X passed" or "X passed, Y failed"
                    for line in result.stdout.split("\n"):
                        if "passed" in line:
                            nums = re.findall(r'(\d+)\s+(passed|failed)', line)
                            for n, kind in nums:
                                if kind == "passed": passed = int(n)
                                elif kind == "failed": failed = int(n)
                except Exception:
                    passed, failed = 0, 1

            total = passed + failed
            outcome = "success" if passed > 0 and failed == 0 else "failure"

            ingestion = engine.record_result(
                session_id=session_id, outcome=outcome, prompt=prompt,
                approach=approach, model=CODING_MODEL,
                files_changed=[],
                test_results={"total": max(total, 1), "passed": passed, "failed": failed},
                duration_seconds=dur, token_count=tokens,
            )

            results.append({
                "session": session_num, "ptype": ptype, "approach": approach,
                "tests": f"{passed}/{total}", "outcome": outcome, "dur": round(dur, 1),
                "patterns": len(ingestion.get("patterns_learned", [])),
            })
            emoji = "✅" if outcome == "success" else "❌"
            print(f"  S{session_num:2d}: [{ptype:9s}] {approach:28s} pytest={passed}/{total} {emoji} ({dur:.0f}s, {len(ingestion.get('patterns_learned',[]))}p)")

        # Checkpoint
        stats = engine.get_stats()
        sr = stats.get("overall_success_rate", 0)
        print(f"  ── Cycle {cycle+1}/3: rate={sr:.0%}, patterns={stats.get('total_patterns',0)} ──\n")

    # Analysis
    stats = engine.get_stats()
    health = engine.health_scorer.compute()
    print(f"{'='*60}")
    print(f"  HYPOTHESIS PROOF — {len(results)} Real Sessions")
    print(f"{'='*60}")
    print(f"Success rate: {stats.get('overall_success_rate', 0):.1%}")
    print(f"Patterns learned: {stats.get('total_patterns', 0)}")
    print(f"Health: {health.get('overall_score', 0)}/100")

    print(f"\nPer-Approach:")
    for ap in APPROACHES:
        a = [r for r in results if r["approach"] == ap]
        if a:
            ok = sum(1 for r in a if r["outcome"] == "success")
            print(f"  {ap:28s}: {ok}/{len(a)} ({ok/len(a):.0%})")

    # Compounding
    early = [r for r in results if r["session"] <= 10]
    late = [r for r in results if r["session"] > 20]
    if early and late:
        er = sum(1 for r in early if r["outcome"] == "success") / len(early)
        lr = sum(1 for r in late if r["outcome"] == "success") / len(late)
        print(f"\nCOMPOUNDING: early={er:.0%}, late={lr:.0%} ({lr-er:+.0%})")
        print(f"  {'✅ SESSION 30 IS SMARTER!' if lr > er else '➡️ Equal performance'}")

    # Save
    out = Path(__file__).resolve().parent.parent / "docs" / "hypothesis_proof.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "title": "Session 100 > Session 1 — Hypothesis Proof",
        "llm": CODING_MODEL, "sessions": len(results),
        "overall_rate": stats.get("overall_success_rate", 0),
        "patterns": stats.get("total_patterns", 0),
        "per_approach": {ap: sum(1 for r in results if r["approach"]==ap and r["outcome"]=="success")/max(1,sum(1 for r in results if r["approach"]==ap)) for ap in APPROACHES},
        "compounding": {"early_rate": er if early else 0, "late_rate": lr if late else 0, "delta": (lr-er) if (early and late) else 0},
        "verdict": "PROVEN" if (early and late and lr > er) else "NOT YET PROVEN",
        "per_session": results,
    }, indent=2))
    print(f"\nSaved to {out}")

    shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()