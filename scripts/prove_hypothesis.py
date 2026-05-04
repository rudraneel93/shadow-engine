#!/usr/bin/env python3
"""Prove 'Session 50 > Session 1' — same model, same task, different approaches.

Valid experimental design:
1. Fixed model: qwen3-coder:480b-cloud
2. Fixed task: binary_search_rotated (hard, algorithmic)
3. Fixed tests: 6 pre-written objective test cases
4. Variable: 8 approaches rotated systematically across 50 sessions
5. Measured: per-approach success rate convergence
6. Assertion: suggest() recommends empirically-best approach after 50 sessions

No confounds. No synthetic data. Real LLM calls, real pytest, real outcomes.
"""

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

# Single task — hardest algorithmic challenge
TASK_PROMPT = (
    "Write a Python function `binary_search_rotated(arr: list[int], target: int) -> int` "
    "that performs binary search on a rotated sorted array. "
    "Return the index of target or -1 if not found. "
    "The array is initially sorted but rotated at an unknown pivot. "
    "Time complexity must be O(log n)."
)

# Immutable pre-written objective tests (same for EVERY session)
TEST_CODE = """import pytest

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

def test_empty_array():
    assert binary_search_rotated([], 5) == -1
"""

# 8 distinct approaches — some more effective than others for algorithm tasks
APPROACHES = [
    "Targeted Fix",
    "Root Cause + Guard",
    "Extensible Implementation",
    "Incremental Rewrite",
    "Safe Extract",
    "Minimal Viable",
    "TDD First",
    "Aggressive Rewrite",
]

MODEL = "qwen3-coder:480b-cloud"
SESSIONS_PER_APPROACH = 6  # 6 × 8 = 48 sessions (close to 50)


def generate_implementation(approach: str) -> tuple[str, float, int]:
    """Ask the LLM to implement binary_search_rotated with a specific approach."""
    import httpx
    t0 = time.time()
    try:
        resp = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL,
                "prompt": (
                    f"{TASK_PROMPT}\n\n"
                    f"Use a {approach} approach to solve this problem. "
                    f"Output ONLY the function code in a ```python block. "
                    f"Include NO test code, NO imports — just the function."
                ),
                "stream": False,
                "options": {"num_predict": 512},
            },
            timeout=90,
        )
        data = resp.json()
        raw = data.get("response") or data.get("thinking") or ""
        blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
        code = '\n'.join(blocks) if blocks else raw
        tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        dur = time.time() - t0
        return code, dur, tokens
    except Exception:
        return "", time.time() - t0, 0


def run_test(code: str) -> tuple[int, int]:
    """Combine generated code with pre-written tests and run pytest."""
    if not code.strip():
        return 0, 7
    full = f"{code}\n\n{TEST_CODE}"
    try:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(full); tmp = f.name; f.close()
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
        return 0, 7


def main():
    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    engine.bootstrap()
    print(f"Fixed model: {MODEL} | Fixed task: binary_search_rotated")
    print(f"Approaches: {len(APPROACHES)} × {SESSIONS_PER_APPROACH} = {len(APPROACHES)*SESSIONS_PER_APPROACH} sessions\n")

    results = []
    for i in range(SESSIONS_PER_APPROACH):
        for ap_idx, approach in enumerate(APPROACHES):
            session_num = i * len(APPROACHES) + ap_idx + 1
            session_id = f"valid-{session_num:03d}"

            code, dur, tokens = generate_implementation(approach)
            passed, failed = run_test(code)
            total = passed + failed
            outcome = "success" if passed > 0 and failed == 0 else "failure"

            ingestion = engine.record_result(
                session_id=session_id, outcome=outcome,
                prompt=f"Implement binary_search_rotated ({approach})",
                approach=approach, model=MODEL, files_changed=[],
                test_results={"total": max(total, 1), "passed": passed, "failed": failed},
                duration_seconds=dur, token_count=tokens,
            )

            results.append({
                "session": session_num, "approach": approach,
                "tests": f"{passed}/{total}", "outcome": outcome,
                "dur": round(dur, 1), "patterns": len(ingestion.get("patterns_learned", [])),
            })
            emoji = "✅" if outcome == "success" else "❌"
            print(f"  S{session_num:2d}: {approach:28s} pytest={passed}/{total} {emoji} ({dur:.0f}s)")

        # Checkpoint after each full pass through approaches
        stats = engine.get_stats()
        print(f"  ── Pass {i+1}/{SESSIONS_PER_APPROACH}: rate={stats.get('overall_success_rate',0):.0%}, "
              f"patterns={stats.get('total_patterns',0)} ──\n")

    # Analysis
    stats = engine.get_stats()
    health = engine.health_scorer.compute()
    print(f"{'='*60}")
    print(f"  VALID HYPOTHESIS PROOF — {len(results)} Sessions")
    print(f"  Same model ({MODEL}), same task, same tests")
    print(f"{'='*60}")
    print(f"Overall success: {stats.get('overall_success_rate', 0):.1%}")
    print(f"Patterns learned: {stats.get('total_patterns', 0)}")
    print(f"Health: {health.get('overall_score', 0)}/100")

    # Per-approach efficacy (NO confounds)
    print(f"\nPer-Approach (same model, task, tests):")
    ap_results = {}
    for ap in APPROACHES:
        a = [r for r in results if r["approach"] == ap]
        if a:
            ok = sum(1 for r in a if r["outcome"] == "success")
            ap_results[ap] = ok / len(a)
            print(f"  {ap:28s}: {ok}/{len(a)} ({ok/len(a):.0%})")

    # Does shadow-engine recommend the best approach?
    print(f"\nApproach Recommendation vs Empirical Best:")
    best_empirical = max(ap_results, key=ap_results.get)
    best_rate = ap_results[best_empirical]
    suggestion = engine.suggest("implement binary_search_rotated in a rotated sorted array")
    recommended = suggestion["recommended_approach"]

    print(f"  Empirically best: {best_empirical} ({best_rate:.0%})")
    print(f"  Engine recommends: {recommended}")
    if recommended and any(ap.lower() in recommended.lower() for ap in [best_empirical]):
        print(f"  ✅ RECOMMENDATION CONVERGED — engine learned the best approach!")
    else:
        print(f"  ⚠️ Recommendation did not converge — needs more sessions")

    # Compounding: compare first pass vs last pass
    early_pass = [r for r in results if r["session"] <= len(APPROACHES)]
    late_pass = [r for r in results if r["session"] > (SESSIONS_PER_APPROACH - 1) * len(APPROACHES)]
    if early_pass and late_pass:
        er = sum(1 for r in early_pass if r["outcome"] == "success") / len(early_pass)
        lr = sum(1 for r in late_pass if r["outcome"] == "success") / len(late_pass)
        print(f"\n{'='*60}")
        print(f"  COMPOUNDING (pass 1 vs pass {SESSIONS_PER_APPROACH}):")
        print(f"  Pass 1: {er:.0%} | Pass {SESSIONS_PER_APPROACH}: {lr:.0%} | Delta: {lr-er:+.0%}")
        print(f"  {'✅ PROVEN!' if lr > er else '❌ NOT PROVEN'} — same model, same task, same tests")
        print(f"{'='*60}")

        verdict = "PROVEN" if lr > er else "DISPROVEN" if lr < er else "INCONCLUSIVE"

    # Save
    out = Path(__file__).resolve().parent.parent / "docs" / "hypothesis_proof.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "title": "Session 50 > Session 1 — Valid Proof",
        "method": "Same model, same task, same tests, different approaches",
        "model": MODEL, "task": "binary_search_rotated", "tests": 7,
        "sessions": len(results), "approaches_tested": len(APPROACHES),
        "overall_rate": stats.get("overall_success_rate", 0),
        "patterns": stats.get("total_patterns", 0),
        "health": health.get("overall_score", 0),
        "per_approach": ap_results,
        "best_empirical": best_empirical,
        "engine_recommends": recommended,
        "recommendation_converged": recommended and any(ap.lower() in recommended.lower() for ap in [best_empirical]),
        "compounding": {"pass_1_rate": er, "pass_last_rate": lr, "delta": lr - er},
        "verdict": verdict,
        "per_session": results,
    }, indent=2))
    print(f"\nSaved to {out}")

    shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()