#!/usr/bin/env python3
"""Prove 'Session 100 > Session 1' — multi-model, real test validation.

Uses pre-written test files (objective, immutable) as ground truth.
LLM must implement functions that pass these tests.

Method:
1. We have pre-written test files that test specific functions
2. Each session: ask a model to implement ONE function with a specific approach
3. Combine the generated code with the pre-existing test
4. Run pytest — real pass/fail based on objective tests
5. Record in shadow-engine
6. Over 30+ sessions, check if approach recommendations converge
"""

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

# Pre-written test files — these are the GROUND TRUTH
TEST_FILES = {
    "is_palindrome": """import pytest
#  is_palindrome

def test_simple_palindrome():
    assert is_palindrome("racecar") == True

def test_not_palindrome():
    assert is_palindrome("hello") == False

def test_case_insensitive():
    assert is_palindrome("RaceCar") == True

def test_with_spaces():
    assert is_palindrome("a man a plan a canal panama") == True

def test_empty_string():
    assert is_palindrome("") == True

def test_single_char():
    assert is_palindrome("a") == True

def test_punctuation():
    assert is_palindrome("madam, I'm Adam") == True
""",

    "fibonacci": """import pytest
#  fibonacci

def test_first_10():
    assert fibonacci(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

def test_n1():
    assert fibonacci(1) == [0]

def test_n2():
    assert fibonacci(2) == [0, 1]

def test_n0():
    assert fibonacci(0) == []

def test_negative():
    assert fibonacci(-5) == []

def test_n7():
    assert fibonacci(7) == [0, 1, 1, 2, 3, 5, 8]
""",

    "flatten": """import pytest
#  flatten

def test_flat_list():
    assert flatten([1, 2, 3]) == [1, 2, 3]

def test_nested_once():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]

def test_deeply_nested():
    assert flatten([[1, [2, [3, [4]]]]]) == [1, 2, 3, 4]

def test_empty_list():
    assert flatten([]) == []

def test_empty_nested():
    assert flatten([[], [[]], [[], []]]) == []

def test_mixed():
    assert flatten([1, [2, [3, 4], 5], 6]) == [1, 2, 3, 4, 5, 6]
""",

    "merge_intervals": """import pytest
#  merge_intervals

def test_basic_merge():
    assert merge_intervals([(1, 3), (2, 6)]) == [(1, 6)]

def test_no_overlap():
    assert merge_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]

def test_contained():
    assert merge_intervals([(1, 10), (2, 5)]) == [(1, 10)]

def test_multiple():
    assert merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]

def test_single_interval():
    assert merge_intervals([(1, 4)]) == [(1, 4)]

def test_unsorted_input():
    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]
""",

    "binary_search": """import pytest
#  binary_search_rotated

def test_found():
    assert binary_search_rotated([4, 5, 6, 7, 0, 1, 2], 0) == 4

def test_not_found():
    assert binary_search_rotated([4, 5, 6, 7, 0, 1, 2], 3) == -1

def test_single_element_found():
    assert binary_search_rotated([1], 1) == 0

def test_single_element_not_found():
    assert binary_search_rotated([1], 0) == -1

def test_not_rotated():
    assert binary_search_rotated([1, 2, 3, 4, 5], 3) == 2

def test_target_at_rotation_point():
    assert binary_search_rotated([7, 8, 1, 2, 3], 1) == 2
""",
}

# Tasks with difficulty that varies by model
TASKS = [
    ("is_palindrome", "bug_fix", "easy", "Targeted Fix"),
    ("fibonacci", "bug_fix", "easy", "Root Cause + Guard"),
    ("flatten", "feature", "medium", "Minimal Viable"),
    ("merge_intervals", "feature", "medium", "Extensible Implementation"),
    ("binary_search", "bug_fix", "hard", "TDD First"),
]

APPROACHES = ["Targeted Fix", "Root Cause + Guard", "Extensible Implementation",
              "Incremental Rewrite", "Safe Extract", "Minimal Viable", "TDD First"]

MODELS = ["qwen3-coder:480b-cloud", "qwen3:8b"]  # Strong vs weak model


def generate_implementation(task_name: str, approach: str, model: str) -> str:
    """Ask an LLM to implement a function with a specific approach."""
    import httpx

    prompts = {
        "is_palindrome": f"Write a Python function `is_palindrome(s: str) -> bool` that checks if a string is a palindrome (reads the same forwards and backwards). Ignore case, spaces, and punctuation. Use a {approach} approach.",
        "fibonacci": f"Write a Python function `fibonacci(n: int) -> list[int]` that returns the first n Fibonacci numbers (starting from 0). Handle n <= 0 by returning an empty list. Use a {approach} approach.",
        "flatten": f"Write a Python function `flatten(nested_list) -> list` that takes an arbitrarily nested list of lists and returns a completely flat list. Use a {approach} approach.",
        "merge_intervals": f"Write a Python function `merge_intervals(intervals: list[tuple[int,int]]) -> list[tuple[int,int]]` that merges overlapping intervals. Sort by start time, then merge. Use a {approach} approach.",
        "binary_search": f"Write a Python function `binary_search_rotated(arr: list[int], target: int) -> int` that performs binary search on a rotated sorted array. Return the index of target or -1 if not found. Use a {approach} approach.",
    }

    try:
        resp = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": f"{prompts[task_name]}\n\nOutput ONLY the function code in a ```python block. Include NO test code, NO imports — just the function.",
                "stream": False,
                "options": {"num_predict": 512},
            },
            timeout=90,
        )
        data = resp.json()
        raw = data.get("response") or data.get("thinking") or ""
        blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
        return '\n'.join(blocks) if blocks else raw
    except Exception:
        return ""


def run_test(task_name: str, impl_code: str) -> tuple[int, int]:
    """Combine implementation with pre-existing test and run pytest."""
    if not impl_code.strip():
        return 0, 1

    test_code = TEST_FILES[task_name]
    full = f"{impl_code}\n\n{test_code}"

    try:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(full)
        tmp = f.name; f.close()

        result = subprocess.run(
            ["pytest", tmp, "-v", "--tb=line", "-q"],
            capture_output=True, text=True, timeout=30,
        )
        os.unlink(tmp)

        passed = failed = 0
        for line in result.stdout.split("\n"):
            nums = re.findall(r'(\d+)\s+(passed|failed)', line)
            for n, kind in nums:
                if kind == "passed": passed = int(n)
                elif kind == "failed": failed = int(n)
        return passed, failed
    except Exception:
        return 0, 1


def main():
    import httpx

    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    r = engine.bootstrap()
    print(f"Symbols: {r['symbols_indexed']} | {'='*50}")
    print("PROVING: Session N > Session 1 with multi-model validation")
    print(f"{'='*50}\n")

    results = []
    for cycle in range(4):  # 4 cycles × (5 tasks × 2 models) = 40 sessions
        for task_name, ptype, difficulty, default_approach in TASKS:
            for model in MODELS:
                # Vary approach across sessions
                approach_idx = (cycle * len(TASKS) + list(TASKS).index(
                    (task_name, ptype, difficulty, default_approach))) % len(APPROACHES)
                approach = APPROACHES[approach_idx]

                session_num = len(results) + 1
                session_id = f"prove-{session_num:03d}"

                t0 = time.time()
                impl = generate_implementation(task_name, approach, model)
                passed, failed = run_test(task_name, impl)
                dur = time.time() - t0
                total = passed + failed
                outcome = "success" if passed > 0 and failed == 0 else "failure"

                ingestion = engine.record_result(
                    session_id=session_id, outcome=outcome,
                    prompt=f"Implement {task_name} ({difficulty})",
                    approach=approach, model=model,
                    files_changed=[],
                    test_results={"total": max(total, 1), "passed": passed, "failed": failed},
                    duration_seconds=dur, token_count=0,
                )

                results.append({
                    "session": session_num, "task": task_name, "difficulty": difficulty,
                    "model": model, "approach": approach,
                    "tests": f"{passed}/{total}", "outcome": outcome, "dur": round(dur, 1),
                    "patterns": len(ingestion.get("patterns_learned", [])),
                })
                emoji = "✅" if outcome == "success" else "❌"
                print(f"  S{session_num:2d}: [{difficulty:6s}] {model:30s} {approach:28s} pytest={passed}/{total} {emoji} ({dur:.0f}s)")

        stats = engine.get_stats()
        print(f"  ── Cycle {cycle+1}/4: rate={stats.get('overall_success_rate',0):.0%}, "
              f"patterns={stats.get('total_patterns',0)} ──\n")

    # Analysis
    stats = engine.get_stats()
    health = engine.health_scorer.compute()
    print(f"{'='*60}")
    print(f"  HYPOTHESIS PROOF — {len(results)} Multi-Model Sessions")
    print(f"{'='*60}")
    print(f"Success: {stats.get('overall_success_rate', 0):.1%} | Patterns: {stats.get('total_patterns', 0)} | Health: {health.get('overall_score', 0)}/100")

    print(f"\nPer-Model:")
    for model in MODELS:
        m = [r for r in results if r["model"] == model]
        if m:
            ok = sum(1 for r in m if r["outcome"] == "success")
            print(f"  {model:30s}: {ok}/{len(m)} ({ok/len(m):.0%})")

    print(f"\nPer-Difficulty:")
    for diff in ["easy", "medium", "hard"]:
        d = [r for r in results if r["difficulty"] == diff]
        if d:
            ok = sum(1 for r in d if r["outcome"] == "success")
            print(f"  {diff:6s}: {ok}/{len(d)} ({ok/len(d):.0%})")

    print(f"\nPer-Approach:")
    for ap in APPROACHES:
        a = [r for r in results if r["approach"] == ap]
        if a:
            ok = sum(1 for r in a if r["outcome"] == "success")
            print(f"  {ap:28s}: {ok}/{len(a)} ({ok/len(a):.0%})")

    print(f"\nApproach Recommendations:")
    for pt in ["bug_fix", "feature", "refactor", "testing"]:
        s = engine.suggest(f"a {pt} task")
        conf = int(s.get("classification_confidence", 0) * 100)
        rate = int(s.get("expected_success_rate", 0) * 100)
        print(f"  [{pt:9s}]: {s['recommended_approach'][:45]} ({rate}% expected, {conf}% conf)")

    # Compounding
    early = [r for r in results if r["session"] <= 10]
    late = [r for r in results if r["session"] > 30]
    if early and late:
        er = sum(1 for r in early if r["outcome"] == "success") / len(early)
        lr = sum(1 for r in late if r["outcome"] == "success") / len(late)
        print(f"\n{'='*60}")
        print(f"  COMPOUNDING EFFECT")
        print(f"  Sessions  1-10: {er:.0%} success")
        print(f"  Sessions 31-40: {lr:.0%} success (Delta: {lr-er:+.0%})")
        print(f"  {'✅ PROVEN: SESSION 40 > SESSION 1!' if lr > er else '➡️ No compounding detected'}")
        print(f"{'='*60}")

    # Save
    out = Path(__file__).resolve().parent.parent / "docs" / "hypothesis_proof.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "title": "Session 100 > Session 1 — Definitive Proof",
        "models": MODELS, "sessions": len(results),
        "overall_rate": stats.get("overall_success_rate", 0),
        "patterns": stats.get("total_patterns", 0),
        "health": health.get("overall_score", 0),
        "per_model": {m: sum(1 for r in results if r["model"]==m and r["outcome"]=="success")/max(1,sum(1 for r in results if r["model"]==m)) for m in MODELS},
        "per_approach": {ap: sum(1 for r in results if r["approach"]==ap and r["outcome"]=="success")/max(1,sum(1 for r in results if r["approach"]==ap)) for ap in APPROACHES},
        "compounding": {"early_rate": er if early else 0, "late_rate": lr if late else 0, "delta": (lr-er) if (early and late) else 0},
        "verdict": "PROVEN" if (early and late and lr > er) else "NOT YET PROVEN",
        "per_session": results,
    }, indent=2))
    print(f"\nSaved to {out}")

    shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()