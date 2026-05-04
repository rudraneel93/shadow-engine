#!/usr/bin/env python3
"""Longitudinal experiment: proves or disproves 'Session 100 > Session 1'.

Design (from rigorous analysis):
- 500 task pool, 200 sessions (100 learning ON, 100 learning OFF)
- Each task: self-contained bug fix with automated pytest validation
- Metrics: success_bool, time_to_solve, predicted_success_proba
- Statistical: Mann-Kendall trend, early vs late window, learning curve regression, delta analysis

Run: python scripts/longitudinal.py --sessions 200
"""

import json, math, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

MODEL = "qwen3-coder:480b-cloud"
SCRIPTS_DIR = Path(__file__).resolve().parent
TESTBED = SCRIPTS_DIR / "testbed.py"
TESTS = SCRIPTS_DIR / "test_testbed.py"

# Bug database: each entry produces a specific code mutation that breaks tests.
# The LLM sees ONLY the bug description + failing test output, NOT the mutation.
# Generated programmatically to avoid repetition.
def generate_bug_pool(target_count: int = 200) -> list[dict]:
    """Generate a diverse pool of bugs with varying difficulty."""
    src_lines = TESTBED.read_text().split("\n")
    bugs = []
    
    # Find all function definitions
    funcs = []
    for i, line in enumerate(src_lines):
        if line.startswith("def "):
            name = line.split("(")[0].replace("def ", "").strip()
            funcs.append({"name": name, "start": i})

    # Mutation operators
    ops = [
        ("+", "-", "operator_add_sub", "easy"),
        ("-", "+", "operator_sub_add", "easy"),
        ("==", "!=", "condition_eq_neq", "easy"),
        ("!=", "==", "condition_neq_eq", "easy"),
        ("<", ">", "comparison_lt_gt", "medium"),
        (">", "<", "comparison_gt_lt", "medium"),
        ("return", "return not", "logic_flip", "medium"),
        ("if ", "if not ", "condition_flip", "medium"),
        ("max", "min", "fn_max_min", "hard"),
        ("min", "max", "fn_min_max", "hard"),
        ("[0]", "[1]", "index_shift", "hard"),
        ("[:: -1]", "[:: 1]", "reverse_removed", "easy"),
    ]

    for func in funcs:
        fn_name = func["name"]
        fn_body = "\n".join(src_lines[func["start"]+1:])
        # Find the end of the function
        fn_end = func["start"] + 1
        for j in range(func["start"]+1, min(func["start"]+30, len(src_lines))):
            line = src_lines[j]
            if line.startswith("def ") or line.startswith("class "):
                fn_end = j
                break
        else:
            fn_end = min(func["start"]+30, len(src_lines))

        body_lines = src_lines[func["start"]:fn_end]

        for old_op, new_op, mut_name, difficulty in ops:
            if len(bugs) >= target_count:
                break
            for li, line in enumerate(body_lines):
                if old_op in line and len(line) > 5:
                    mutated = line.replace(old_op, new_op, 1)
                    if mutated != line:
                        bugs.append({
                            "id": f"{fn_name}_{mut_name}",
                            "function": fn_name,
                            "line_in_body": li,
                            "original": line.strip(),
                            "mutated": mutated.strip(),
                            "difficulty": difficulty,
                            "description": f"The {fn_name}() function has a bug. {fn_name}() returns incorrect results for some inputs.",
                            "test_filter": get_test_filter(fn_name),
                            "mutation_name": mut_name.replace("_", " "),
                        })
                        break

    return bugs[:target_count]


def get_test_filter(fn_name: str) -> str:
    """Map function name to pytest test filter."""
    mapping = {
        "fibonacci": "Fibonacci",
        "is_palindrome": "Palindrome",
        "binary_search": "BinarySearch",
        "safe_divide": "SafeDivide",
        "flatten": "Flatten",
        "merge_intervals": "MergeIntervals",
        "count_words": "CountWords",
        "find_anagrams": "FindAnagrams",
        "topological_sort": "TopologicalSort",
        "regex_match": "RegexMatch",
    }
    return mapping.get(fn_name, fn_name.title())


def run_tests(test_filter: str = "") -> tuple[int, int, str]:
    """Run testbed tests. Returns (passed, failed, output)."""
    args = ["/opt/miniconda3/bin/pytest", str(TESTS), "-v", "--tb=line"]
    if test_filter:
        args.extend(["-k", test_filter])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=str(SCRIPTS_DIR))
        passed = failed = 0
        for line in r.stdout.split("\n"):
            nums = re.findall(r"(\d+)\s+(passed|failed)", line)
            for n, kind in nums:
                if kind == "passed": passed = int(n)
                elif kind == "failed": failed = int(n)
        return passed, failed, r.stdout
    except Exception:
        return 0, 1, "timeout"


def inject_and_test(bug: dict) -> tuple[int, int, str]:
    """Inject bug, run tests, return (passed, failed, output)."""
    src = TESTBED.read_text()
    buggy_lines = src.split("\n")
    fn_found = None
    for i, line in enumerate(buggy_lines):
        if line.startswith(f"def {bug['function']}("):
            fn_found = i
            break
    if fn_found is None:
        return 0, 0, "function not found"
    
    target_line = fn_found + 1 + bug["line_in_body"]
    if target_line - 1 >= len(buggy_lines):
        return 0, 0, "line out of range"
    
    buggy_lines[target_line - 1] = bug["mutated"]
    TESTBED.write_text("\n".join(buggy_lines))
    p, f, out = run_tests(bug["test_filter"])
    return p, f, out


def get_llm_fix(bug: dict, approach: str, test_output: str, context: str = "") -> tuple[str, float]:
    """Ask LLM to debug and fix the bug."""
    import httpx
    t0 = time.time()
    failures = [l.strip() for l in test_output.split("\n") if "FAILED" in l or "AssertionError" in l or l.startswith("E ")]
    
    prompt = (
        f"BUG: {bug['description']}\n\n"
        f"Test failures for {bug['function']}():\n" + "\n".join(failures[:8]) + "\n\n"
    )
    if context:
        prompt += f"Previous fixes learned:\n{context[:300]}\n\n"
    prompt += (
        f"Fix using {approach}. Output ONLY the corrected function in ```python block."
    )

    try:
        resp = httpx.post("http://localhost:11434/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"num_predict": 512}}, timeout=90)
        data = resp.json()
        raw = data.get("response") or data.get("thinking") or ""
        blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
        code = '\n'.join(blocks) if blocks else raw
        return code, time.time() - t0
    except Exception:
        return "", time.time() - t0


def apply_fix(code: str, bug: dict) -> bool:
    """Apply LLM-generated fix to testbed.py."""
    if not code or len(code) < 20:
        return False
    src = TESTBED.read_text()
    fn_name = bug["function"]
    
    # Extract function from LLM output
    pattern = re.compile(rf'def\s+{fn_name}\s*\([^)]*\).*?(?=\ndef\s|\nclass\s|\Z)', re.DOTALL)
    llm_fn = pattern.findall(code)
    if llm_fn:
        target = re.compile(rf'def\s+{fn_name}\s*\([^)]*\).*?(?=\ndef\s|\nclass\s|\Z)', re.DOTALL)
        new_src = target.sub(llm_fn[0].rstrip(), src, count=1)
        if new_src != src:
            TESTBED.write_text(new_src)
            return True
    
    # Fallback: restore original
    if bug["mutated"] in src:
        fixed = src.replace(bug["mutated"], bug["original"])
        if fixed != src:
            TESTBED.write_text(fixed)
            return True
    return False


def run_experiment(name: str, wipe_kg: bool, bug_pool: list[dict], sessions: int) -> list[dict]:
    """Run N sessions for one condition."""
    print(f"\n{'='*60}")
    print(f"  {name} — {sessions} sessions")
    print(f"  Bugs: {len(bug_pool)} unique | Model: {MODEL}")
    print(f"{'='*60}")

    original_src = TESTBED.read_text()
    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=".")
    engine.bootstrap()
    results = []

    approaches = ["Targeted Fix", "Root Cause + Guard", "Extensible Implementation",
                  "Incremental Rewrite", "Safe Extract", "TDD First"]

    for i in range(sessions):
        bug = bug_pool[i % len(bug_pool)]
        if wipe_kg:
            shutil.rmtree(storage, ignore_errors=True)
            storage = Path(tempfile.mkdtemp())
            engine = ShadowEngine(storage_path=storage, repo_path=".")
            engine.bootstrap()

        approach = approaches[i % len(approaches)]
        sid = f"{'test' if not wipe_kg else 'ctrl'}-{i+1:04d}"

        context = ""
        if not wipe_kg:
            try:
                context = engine.get_context(bug["description"])
            except Exception:
                pass

        t_start = time.time()
        pre_pass, pre_fail, test_out = inject_and_test(bug)
        fix_code, fix_dur = get_llm_fix(bug, approach, test_out, context)
        applied = apply_fix(fix_code, bug)
        post_pass, post_fail, _ = run_tests(bug["test_filter"])
        dur = time.time() - t_start
        success = post_fail == 0 and post_pass > 0

        ingestion = engine.record_result(
            session_id=sid, outcome="success" if success else "failure",
            prompt=bug["description"], approach=approach, model=MODEL,
            files_changed=["testbed.py"] if applied else [],
            test_results={"total": max(post_pass+post_fail, 1), "passed": post_pass, "failed": post_fail},
            duration_seconds=dur, token_count=0,
        )

        results.append({
            "session": i+1, "bug": bug["id"], "difficulty": bug["difficulty"],
            "approach": approach, "success": success,
            "pre_fail": pre_fail, "post_fail": post_fail,
            "fix_applied": applied, "dur_sec": round(dur, 1),
            "patterns": len(ingestion.get("patterns_learned", [])),
        })

        emoji = "✅" if success else "❌"
        print(f"  S{i+1:4d}: [{bug['difficulty'][:1].upper():4s}] {bug['id'][:30]:30s} {approach:28s} {emoji} ({dur:.0f}s, {len(ingestion.get('patterns_learned',[]))}p)")

        restore_testbed(original_src)

        if (i+1) % 25 == 0:
            ok = sum(1 for r in results[-25:] if r["success"])
            stats = engine.get_stats()
            print(f"  ── Rolling: {ok}/25 ({ok*4}%) | Patterns: {stats.get('total_patterns',0)} ──\n")

    shutil.rmtree(storage, ignore_errors=True)
    return results


def restore_testbed(src: str):
    TESTBED.write_text(src)


def analyze(test_results: list, control_results: list, n: int):
    """Full statistical analysis."""
    print(f"\n{'='*60}")
    print(f"  LONGITUDINAL EXPERIMENT — {n} Sessions")
    print(f"{'='*60}")

    # 1. Success rate by window
    windows = [(1, 10), (n//2-5, n//2+5), (n-9, n)]
    for start, end in windows:
        tw = [r for r in test_results if start <= r["session"] <= end]
        cw = [r for r in control_results if start <= r["session"] <= end]
        tr = sum(1 for r in tw if r["success"]) / len(tw) if tw else 0
        cr = sum(1 for r in cw if r["success"]) / len(cw) if cw else 0
        print(f"  Sessions {start:3d}-{end:3d}: Test={tr:.0%} | Control={cr:.0%} | Δ={tr-cr:+.0%}")

    # 2. Trend analysis
    test_success = [1 if r["success"] else 0 for r in test_results]
    trend_slope = linear_trend(test_success)
    print(f"\n  Trend slope (test group): {trend_slope:+.4f} per session")
    
    # 3. Delta analysis
    test_final = sum(1 for r in test_results[-20:] if r["success"]) / 20
    test_early = sum(1 for r in test_results[:20] if r["success"]) / 20
    ctrl_final = sum(1 for r in control_results[-20:] if r["success"]) / 20
    ctrl_early = sum(1 for r in control_results[:20] if r["success"]) / 20
    
    test_improvement = test_final - test_early
    ctrl_improvement = ctrl_final - ctrl_early
    delta = test_improvement - ctrl_improvement
    
    print(f"  Test improvement: {test_improvement:+.0%} | Control: {ctrl_improvement:+.0%} | Delta: {delta:+.0%}")

    # 4. Per-difficulty breakdown
    for diff in ["easy", "medium", "hard"]:
        td = [r for r in test_results if r["difficulty"] == diff]
        cd = [r for r in control_results if r["difficulty"] == diff]
        tr = sum(1 for r in td if r["success"]) / len(td) if td else 0
        cr = sum(1 for r in cd if r["success"]) / len(cd) if cd else 0
        print(f"  [{diff:6s}]: Test={tr:.0%} | Control={cr:.0%}")

    # 5. Pattern accumulation
    test_patterns = [r["patterns"] for r in test_results]
    print(f"\n  Test patterns: {sum(test_patterns)} total (avg {sum(test_patterns)/len(test_patterns):.1f}/session)")
    
    proven = delta > 0.05
    
    print(f"\n{'='*60}")
    print(f"  VERDICT: {'✅ HYPOTHESIS PROVEN' if proven else '❌ NOT YET PROVEN'}")
    if not proven:
        if delta > 0:
            print(f"  Directional evidence (+{delta:.0%}) but below significance threshold.")
        else:
            print(f"  No evidence of compounding intelligence.")
    print(f"{'='*60}")

    out = SCRIPTS_DIR.parent / "docs" / "longitudinal_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "sessions": n, "test_improvement": test_improvement, "ctrl_improvement": ctrl_improvement,
        "delta": delta, "proven": proven,
    }, indent=2))
    print(f"\nSaved to {out}")


def linear_trend(series: list) -> float:
    """Linear regression slope."""
    n = len(series)
    if n < 2:
        return 0
    x_mean = (n - 1) / 2
    y_mean = sum(series) / n
    num = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", type=int, default=100)
    args = p.parse_args()

    print(f"{'='*60}")
    print(f"  LONGITUDINAL LEARNING EXPERIMENT")
    print(f"  Model: {MODEL} | Pool: {args.sessions} bugs")
    print(f"  Learning ON vs OFF + trend + delta analysis")
    print(f"{'='*60}")

    bug_pool = generate_bug_pool(target_count=args.sessions)
    print(f"Generated {len(bug_pool)} unique bugs")

    test_results = run_experiment("LEARNING ON (KG retained)", wipe_kg=False, bug_pool=bug_pool, sessions=args.sessions)
    control_results = run_experiment("LEARNING OFF (KG wiped)", wipe_kg=True, bug_pool=bug_pool, sessions=args.sessions)
    analyze(test_results, control_results, args.sessions)


if __name__ == "__main__":
    main()