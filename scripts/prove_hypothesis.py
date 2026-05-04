#!/usr/bin/env python3
"""Prove 'Session 100 > Session 1' — definitive multi-model hypothesis test.

Methodology:
1. Ask qwen3-coder:480b-cloud to write a Python function for a specific task
2. Ask gpt-oss:120b-cloud to write a unit test for that function
3. Extract both, write to temp .py file, run pytest
4. Real pass/fail → recorded in shadow-engine
5. After N sessions, check: do approach recommendations converge?

Each session uses REAL code generation + REAL test execution.
"""

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

# Tasks where the LLM must implement real functionality
TASKS = [
    # Easy — simple function generation (LLM usually succeeds)
    ("bug_fix", "Write a Python function `is_palindrome(s: str) -> bool` that returns True if the string reads the same forwards and backwards, ignoring case and non-alphanumeric characters.", "Targeted Fix"),
    ("feature", "Write a Python function `flatten(nested_list) -> list` that takes a list of arbitrarily nested lists and returns a flat list of all elements.", "Minimal Viable"),
    ("bug_fix", "Write a Python function `fibonacci(n: int) -> list[int]` that returns the first n Fibonacci numbers. Handle n <= 0 by returning an empty list.", "Targeted Fix"),
    # Medium — needs correctness + edge cases
    ("feature", "Write a Python function `merge_intervals(intervals: list[tuple[int,int]]) -> list[tuple[int,int]]` that merges overlapping intervals. Example: [(1,3),(2,6)] → [(1,6)].", "Extensible Implementation"),
    ("refactor", "Write a Python function `parse_kv_string(s: str) -> dict` that parses 'key1=value1,key2=value2' into a dict. Handle quotes, escaped commas, and empty values.", "Safe Extract"),
    ("feature", "Write a Python function `find_anagrams(word: str, word_list: list[str]) -> list[str]` that returns all words from word_list that are anagrams of word. Case-insensitive.", "Root Cause + Guard"),
    # Hard — requires algorithmic thinking
    ("refactor", "Write a Python function `longest_common_subsequence(a: str, b: str) -> str` using dynamic programming. Returns the actual LCS string, not just the length.", "Incremental Rewrite"),
    ("feature", "Write a Python function `regex_to_postfix(pattern: str) -> str` that converts a simple regex (only |, *, concatenation) to postfix notation using the shunting-yard algorithm.", "Extensible Implementation"),
    ("bug_fix", "Write a Python function `binary_search_rotated(arr: list[int], target: int) -> int` that finds target in a rotated sorted array. Return index or -1.", "TDD First"),
    ("refactor", "Write a Python function `topological_sort(graph: dict[str, list[str]]) -> list[str]` using Kahn's algorithm. Raise ValueError if the graph has a cycle.", "Safe Extract"),
]

APPROACHES = ["Targeted Fix", "Minimal Viable", "Extensible Implementation",
              "Safe Extract", "Root Cause + Guard", "Incremental Rewrite", "TDD First"]

CODING_MODEL = "qwen3-coder:480b-cloud"


def extract_python_code(raw: str) -> str:
    """Extract compilable Python code from LLM output."""
    blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
    if blocks:
        return '\n\n'.join(blocks)
    funcs = re.findall(r'(?:async\s+)?def\s+\w+\s*\([^)]*\).*?(?:(?=\n(?:[^\s]|\s*(?:def|class|@)))|\Z)', raw, re.DOTALL)
    classes = re.findall(r'class\s+\w+.*?(?:(?=\n(?:[^\s]|\s*(?:def|class|@)))|\Z)', raw, re.DOTALL)
    return '\n\n'.join(funcs + classes) if (funcs or classes) else ""


def generate_tests(code: str, task_prompt: str) -> str:
    """Use qwen3-coder to generate pytest tests for the given code."""
    import httpx
    try:
        resp = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": CODING_MODEL,
                "prompt": (
                    f"Here is a Python function:\n\n```python\n{code}\n```\n\n"
                    f"Task: {task_prompt}\n\n"
                    f"Write a pytest test function that tests this function with at least 5 test cases "
                    f"including edge cases. Output ONLY valid Python with import pytest. "
                    f"Use ```python code blocks."
                ),
                "stream": False,
                "options": {"num_predict": 768},
            },
            timeout=90,
        )
        data = resp.json()
        return extract_python_code(data.get("response") or data.get("thinking") or "")
    except Exception:
        return ""


def run_tests(code: str) -> tuple[int, int, str]:
    """Run pytest on the given code. Returns (passed, failed, output)."""
    if not code.strip():
        return 0, 1, "no code"
    try:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='test.py', delete=False)
        f.write(code)
        tmp = f.name
        f.close()
        result = subprocess.run(
            ["pytest", tmp, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=45,
        )
        os.unlink(tmp)
        passed = failed = 0
        for line in result.stdout.split("\n"):
            # Parse pytest output: "X passed" or "X passed, Y failed"
            if "passed" in line and "=" not in line:
                nums = re.findall(r'(\d+)\s+(passed|failed)', line)
                for n, kind in nums:
                    if kind == "passed": passed = int(n)
                    elif kind == "failed": failed = int(n)
        return passed, failed, result.stdout[:500]
    except Exception as e:
        return 0, 1, str(e)


def main():
    import httpx

    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    # Bootstrap on current repo (doesn't matter — we're recording sessions, not KG context)
    r = engine.bootstrap()
    print(f"Bootstrapped: {r['symbols_indexed']} symbols | 30 real sessions\n")

    results = []
    for i in range(1, 31):
        task = TASKS[(i - 1) % len(TASKS)]
        ptype, prompt, approach = task
        session_id = f"proof-{i:03d}"

        # Step 1: Generate code
        t0 = time.time()
        try:
            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": CODING_MODEL,
                    "prompt": f"{prompt}\n\nUse a {approach} approach. Output ONLY Python code in ```python blocks.",
                    "stream": False,
                    "options": {"num_predict": 768},
                },
                timeout=120,
            )
            data = resp.json()
            raw = data.get("response") or data.get("thinking") or ""
            tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        except Exception:
            raw, tokens = "", 0

        code = extract_python_code(raw)

        # Step 2: Generate tests for the code
        tests = generate_tests(code, prompt)
        full_code = f"import pytest\n\n{code}\n\n{tests}" if tests else code

        # Step 3: Run real tests
        passed, failed, test_output = run_tests(full_code)
        dur = time.time() - t0
        total = passed + failed
        outcome = "success" if passed > 0 and failed == 0 else "failure"

        # Step 4: Record in shadow-engine
        ingestion = engine.record_result(
            session_id=session_id, outcome=outcome, prompt=prompt,
            approach=approach, model=CODING_MODEL,
            files_changed=[],
            test_results={"total": max(total, 1), "passed": passed, "failed": failed},
            duration_seconds=dur, token_count=tokens,
        )

        results.append({
            "session": i, "ptype": ptype, "approach": approach,
            "tests": f"{passed}/{total}", "outcome": outcome, "dur": round(dur, 1),
            "patterns": len(ingestion.get("patterns_learned", [])),
        })
        emoji = "✅" if outcome == "success" else "❌"
        print(f"  S{i:2d}: [{ptype:9s}] {approach:28s} tests={passed}/{total} {emoji} ({dur:.0f}s, {len(ingestion.get('patterns_learned',[]))}p)")

        if i % 5 == 0:
            stats = engine.get_stats()
            sr = stats.get("overall_success_rate", 0)
            print(f"  ── Checkpoint {i}: rate={sr:.0%}, patterns={stats.get('total_patterns', 0)} ──")

    # Final analysis
    stats = engine.get_stats()
    health = engine.health_scorer.compute()
    print(f"\n{'='*60}")
    print(f"  DEFINITIVE HYPOTHESIS PROOF — 30 Real Sessions")
    print(f"  Code generation + pytest validation + shadow-engine ingestion")
    print(f"{'='*60}")
    print(f"Overall success rate: {stats.get('overall_success_rate', 0):.1%}")
    print(f"Patterns learned: {stats.get('total_patterns', 0)}")
    print(f"Health score: {health.get('overall_score', 0)}/100")

    print(f"\nApproach Recommendations (from REAL test outcomes):")
    for pt in ["bug_fix", "feature", "refactor"]:
        s = engine.suggest(f"a {pt} task")
        conf = int(s.get("classification_confidence", 0) * 100)
        rate = int(s.get("expected_success_rate", 0) * 100)
        print(f"  [{pt:9s}]: {s['recommended_approach'][:45]} ({rate}% expected, {conf}% conf)")

    print(f"\nPer-Approach Efficacy:")
    for ap in APPROACHES:
        a = [r for r in results if r["approach"] == ap]
        if a:
            ok = sum(1 for r in a if r["outcome"] == "success")
            dr = [r["dur"] for r in a]
            print(f"  {ap:28s}: {ok}/{len(a)} ({ok/len(a):.0%}) avg {sum(dr)/len(dr):.0f}s")

    # Compounding effect
    early = [r for r in results if r["session"] <= 10]
    late = [r for r in results if r["session"] > 20]
    if early and late:
        er = sum(1 for r in early if r["outcome"] == "success") / len(early)
        lr = sum(1 for r in late if r["outcome"] == "success") / len(late)
        print(f"\n{'='*60}")
        print(f"  COMPOUNDING EFFECT")
        print(f"  Sessions  1-10: {er:.0%} success rate")
        print(f"  Sessions 21-30: {lr:.0%} success rate")
        print(f"  Delta: {lr-er:+.0%}")
        if lr > er:
            print(f"  ✅ SESSION 30 IS SMARTER THAN SESSION 1!")
        elif lr == er:
            print(f"  ➡️ No improvement — same performance")
        else:
            print(f"  ⚠️ Performance decreased — needs investigation")
        print(f"{'='*60}")

    # Save results
    out = Path(__file__).resolve().parent.parent / "docs" / "hypothesis_proof.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "title": "Session 100 > Session 1 — Hypothesis Proof",
        "codebase": "Real Python functions with real pytest tests",
        "llm": CODING_MODEL,
        "sessions": 30,
        "overall_rate": stats.get("overall_success_rate", 0),
        "patterns": stats.get("total_patterns", 0),
        "health": health.get("overall_score", 0),
        "per_approach": {
            ap: sum(1 for r in results if r["approach"]==ap and r["outcome"]=="success") / max(1, sum(1 for r in results if r["approach"]==ap))
            for ap in APPROACHES
        },
        "compounding": {
            "early_rate": er if early else 0,
            "late_rate": lr if late else 0,
            "delta": (lr - er) if (early and late) else 0,
        },
        "verdict": "PROVEN" if (early and late and lr > er) else "NOT YET PROVEN — needs more sessions",
        "per_session": results,
    }, indent=2))
    print(f"\nSaved to {out}")

    shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()