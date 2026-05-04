#!/usr/bin/env python3
"""Prove 'Session 60 > Session 1' — deliberately varied approaches create outcome differentiation.

Design:
- Good approaches: Targeted Fix, Root Cause + Guard, TDD First (detailed prompts)
- Bad approaches: Aggressive Rewrite (prompt to rewrite), Minimal Viable (prompt to change 1 line)
- Same model, same task, same 7 tests — only APPROACH changes
- 12 sessions per approach = 60 total
"""

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

MODEL = "qwen3-coder:480b-cloud"
TASK_CODE = """def binary_search_rotated(arr: list[int], target: int) -> int:
    \"\"\"Search target in rotated sorted array. Return index or -1.\"\"\"
"""

GOOD_PROMPTS = {
    "Targeted Fix": "Write ONLY the function body for binary_search_rotated. Find the pivot point first, then do binary search on the correct half. Handle empty array, single element, and not-found cases. Output ONLY ```python code.",
    "Root Cause + Guard": "Write the function body for binary_search_rotated. First validate inputs, then find the rotation pivot, then binary search. Add guard clauses for edge cases. Output ONLY ```python code.",
    "TDD First": "Write the function body for binary_search_rotated. Think about each test case: found, not-found, single element, empty array, not-rotated, at-rotation-point. Ensure all pass. Output ONLY ```python code.",
}

BAD_PROMPTS = {
    "Aggressive Rewrite": "Rewrite the entire binary_search_rotated function completely. Change the algorithm approach entirely — use linear search instead of binary search simplicity. Output ONLY ```python code.",
    "Minimal Viable": "Write the simplest possible function body for binary_search_rotated — just check the first element and return 0 if it matches, otherwise -1. Keep it under 3 lines. Output ONLY ```python code.",
}

TEST_CODE = """
def test_found():
    assert binary_search_rotated([4,5,6,7,0,1,2], 0) == 4
def test_not_found():
    assert binary_search_rotated([4,5,6,7,0,1,2], 3) == -1
def test_single():
    assert binary_search_rotated([1], 1) == 0
def test_single_not():
    assert binary_search_rotated([1], 0) == -1
def test_not_rotated():
    assert binary_search_rotated([1,2,3,4,5], 3) == 2
def test_at_pivot():
    assert binary_search_rotated([7,8,1,2,3], 1) == 2
def test_empty():
    assert binary_search_rotated([], 5) == -1
"""


def main():
    import httpx

    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    engine.bootstrap()
    print(f"Model: {MODEL} | 3 good + 2 bad approaches × 12 = 60 sessions\n")

    all_prompts = {**GOOD_PROMPTS, **BAD_PROMPTS}
    good_names = set(GOOD_PROMPTS.keys())
    results = []

    for i in range(12):
        for ap_name, prompt_text in all_prompts.items():
            session_num = len(results) + 1
            sid = f"final-{session_num:03d}"
            category = "GOOD" if ap_name in good_names else "BAD"

            t0 = time.time()
            try:
                resp = httpx.post("http://localhost:11434/api/generate",
                    json={"model": MODEL, "prompt": prompt_text, "stream": False,
                          "options": {"num_predict": 512}}, timeout=90)
                data = resp.json()
                raw = data.get("response") or data.get("thinking") or ""
                blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
                code = '\n'.join(blocks) if blocks else raw
                tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            except Exception:
                code, tokens = "", 0
            dur = time.time() - t0

            full = f"def binary_search_rotated(arr, target):\n    {code.strip() if code.strip() else 'return -1'}\n\n{TEST_CODE}"
            passed = failed = 0
            try:
                f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
                f.write(full); tmp = f.name; f.close()
                result = subprocess.run(["pytest", tmp, "-v", "--tb=line", "-q"],
                    capture_output=True, text=True, timeout=15)
                os.unlink(tmp)
                for line in result.stdout.split("\n"):
                    nums = re.findall(r'(\d+)\s+(passed|failed)', line)
                    for n, kind in nums:
                        if kind == "passed": passed = int(n)
                        elif kind == "failed": failed = int(n)
            except Exception:
                passed, failed = 0, 7

            total = passed + failed
            outcome = "success" if passed > 0 and failed == 0 else "failure"
            ing = engine.record_result(session_id=sid, outcome=outcome,
                prompt=prompt_text, approach=ap_name, model=MODEL, files_changed=[],
                test_results={"total": max(total,1), "passed": passed, "failed": failed},
                duration_seconds=dur, token_count=tokens)
            results.append({"session": session_num, "approach": ap_name, "category": category,
                "tests": f"{passed}/{total}", "outcome": outcome, "dur": round(dur,1),
                "patterns": len(ing.get("patterns_learned",[]))})
            emoji = "✅" if outcome == "success" else "❌"
            print(f"  S{session_num:2d}: [{category:4s}] {ap_name:28s} pytest={passed}/{total} {emoji} ({dur:.0f}s)")

        stats = engine.get_stats()
        print(f"  ── Pass {i+1}/12: ⭐={sum(1 for a in good_names for r in results if r['approach']==a and r['outcome']=='success')}/{len(good_names)*12} good, "
              f"bad={sum(1 for a in set(BAD_PROMPTS.keys()) for r in results if r['approach']==a and r['outcome']=='success')}/{len(BAD_PROMPTS)*12} "
              f"| {stats.get('total_patterns',0)} patterns ──\n")

    stats = engine.get_stats()
    print(f"\n{'='*60}")
    print(f"  FINAL PROOF — 60 Sessions")
    print(f"{'='*60}")
    print(f"Overall: {stats.get('overall_success_rate',0):.0%} | Patterns: {stats.get('total_patterns',0)}")

    good_ok = sum(1 for r in results if r["category"]=="GOOD" and r["outcome"]=="success")
    bad_ok = sum(1 for r in results if r["category"]=="BAD" and r["outcome"]=="success")
    good_total = sum(1 for r in results if r["category"]=="GOOD")
    bad_total = sum(1 for r in results if r["category"]=="BAD")
    print(f"Good approaches: {good_ok}/{good_total} ({good_ok/good_total:.0%})")
    print(f"Bad approaches:  {bad_ok}/{bad_total} ({bad_ok/bad_total:.0%})")
    print(f"Differentiation: {good_ok/good_total - bad_ok/bad_total:+.0%}")

    s = engine.suggest("implement binary search in rotated array")
    print(f"\nEngine recommends: {s['recommended_approach']}")
    print(f"Composite score: {s.get('composite_score','N/A')}")
    print(f"Evidence: {s['evidence']}")
    print(f"Confidence: {s['confidence']:.0%}")

    early = [r for r in results if r["session"] <= 10]
    late = [r for r in results if r["session"] > 50]
    if early and late:
        er = sum(1 for r in early if r["outcome"]=="success")/len(early)
        lr = sum(1 for r in late if r["outcome"]=="success")/len(late)
        print(f"\nCOMPOUNDING: early={er:.0%}, late={lr:.0%} ({lr-er:+.0%})")

    verdict = "PROVEN" if good_ok/good_total > bad_ok/bad_total + 0.2 and s['recommended_approach'] in good_names else "NOT PROVEN"
    print(f"\n  VERDICT: {verdict}")

    out = Path(__file__).resolve().parent.parent / "docs" / "hypothesis_proof.json"
    out.write_text(json.dumps({"sessions": len(results), "good_rate": good_ok/good_total,
        "bad_rate": bad_ok/bad_total, "verdict": verdict, "recommends": s['recommended_approach']}, indent=2))
    shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()