#!/usr/bin/env python3
"""Longitudinal experiment with Retrieval-Augmented Fixing (RAG).

Tests the NEW hypothesis:
  "Providing the LLM with similar past successful bug-fix pairs
   improves its success rate on new bugs."

Arms: --retrieval vector (similarity) / random (baseline) / none (control)

Run: python scripts/longitudinal.py --sessions 50 --retrieval vector
"""

import json, os, random, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine
from shadow_engine.retrieval_fixer import RetrievalAugmentedFixer, format_retrieval_context

MODEL = "qwen3-coder:480b-cloud"
SCRIPTS_DIR = Path(__file__).resolve().parent
TESTBED = SCRIPTS_DIR / "testbed.py"
TESTS = SCRIPTS_DIR / "test_testbed.py"


def generate_hard_bug_pool(target_count: int = 50) -> list[dict]:
    """Generate bugs targeting hard functions (low baseline success)."""
    src_lines = TESTBED.read_text().split("\n")
    hard_funcs = ["topological_sort", "regex_match", "merge_intervals", "binary_search"]
    funcs = []
    for i, line in enumerate(src_lines):
        if line.startswith("def "):
            name = line.split("(")[0].replace("def ", "").strip()
            if name in hard_funcs:
                funcs.append({"name": name, "start": i})

    hard_ops = [
        ("max", "min", "fn_max_min", "hard"),
        ("min", "max", "fn_min_max", "hard"),
        ("pop(0)", "pop(-1)", "queue_invert", "hard"),
        ("return result", "return result[:1]", "truncate_result", "hard"),
        ("left <= right", "left < right", "binary_break", "hard"),
        ("if b == 0:", "if False:", "zero_div_break", "hard"),
        (".get(", "[", "dict_break", "hard"),
        ("sorted(word.lower())", "word.lower()", "anagram_break", "hard"),
    ]

    bugs = []
    for func in funcs:
        fn_end = func["start"] + 1
        for j in range(func["start"]+1, min(func["start"]+50, len(src_lines))):
            if src_lines[j].startswith("def "):
                fn_end = j; break
        else:
            fn_end = min(func["start"]+50, len(src_lines))

        body_lines = src_lines[func["start"]:fn_end]
        for old_op, new_op, mut_name, difficulty in hard_ops:
            if len(bugs) >= target_count: break
            for li, line in enumerate(body_lines):
                if old_op in line and len(line) > 5:
                    mutated = line.replace(old_op, new_op, 1)
                    if mutated != line and len(mutated) > 5:
                        bugs.append({
                            "id": f"{func['name']}_{mut_name}",
                            "function": func["name"],
                            "line_in_body": li,
                            "original": line.strip(),
                            "mutated": mutated.strip(),
                            "difficulty": difficulty,
                            "description": f"The {func['name']}() function has a subtle bug. Fix it.",
                            "test_filter": _get_filter(func["name"]),
                            "mutation_name": mut_name.replace("_", " "),
                        })
                        break
    return bugs[:target_count]


def _get_filter(fn_name: str) -> str:
    m = {"fibonacci":"Fibonacci","is_palindrome":"Palindrome","binary_search":"BinarySearch",
         "safe_divide":"SafeDivide","flatten":"Flatten","merge_intervals":"MergeIntervals",
         "count_words":"CountWords","find_anagrams":"FindAnagrams",
         "topological_sort":"TopologicalSort","regex_match":"RegexMatch"}
    return m.get(fn_name, fn_name.title())


def run_tests(test_filter: str = "") -> tuple[int, int, str]:
    args = ["/opt/miniconda3/bin/pytest", str(TESTS), "-v", "--tb=line"]
    if test_filter: args.extend(["-k", test_filter])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=str(SCRIPTS_DIR))
        p, f = 0, 0
        for line in r.stdout.split("\n"):
            nums = re.findall(r"(\d+)\s+(passed|failed)", line)
            for n, kind in nums:
                if kind == "passed": p = int(n)
                elif kind == "failed": f = int(n)
        return p, f, r.stdout
    except Exception:
        return 0, 1, "timeout"


def inject_and_test(bug: dict) -> tuple[int, int, str]:
    src = TESTBED.read_text()
    lines = src.split("\n")
    fn_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {bug['function']}("):
            fn_idx = i; break
    if fn_idx is None: return 0, 0, "fn not found"
    target = fn_idx + 1 + bug["line_in_body"]
    if target - 1 >= len(lines): return 0, 0, "OOB"
    lines[target - 1] = bug["mutated"]
    TESTBED.write_text("\n".join(lines))
    return run_tests(bug["test_filter"])


def get_llm_fix(bug: dict, approach: str, test_output: str, rag_context: str = "") -> tuple[str, float]:
    import httpx
    t0 = time.time()
    failures = [l.strip() for l in test_output.split("\n") if "FAILED" in l or "AssertionError" in l or l.startswith("E ")]
    prompt = f"BUG: {bug['description']}\n\nTest failures:\n" + "\n".join(failures[:8]) + "\n\n"
    if rag_context: prompt += rag_context + "\n\n"
    prompt += f"Fix using {approach}. Output ONLY the corrected function in ```python block."
    try:
        resp = httpx.post("http://localhost:11434/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"num_predict": 512}}, timeout=90)
        data = resp.json()
        raw = data.get("response") or data.get("thinking") or ""
        blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
        return '\n'.join(blocks) if blocks else raw, time.time() - t0
    except Exception:
        return "", time.time() - t0


def apply_fix(code: str, bug: dict) -> bool:
    if not code or len(code) < 20: return False
    src = TESTBED.read_text()
    fn = bug["function"]
    pat = re.compile(rf'def\s+{fn}\s*\([^)]*\).*?(?=\ndef\s|\nclass\s|\Z)', re.DOTALL)
    matches = pat.findall(code)
    if matches:
        tgt = re.compile(rf'def\s+{fn}\s*\([^)]*\).*?(?=\ndef\s|\nclass\s|\Z)', re.DOTALL)
        ns = tgt.sub(matches[0].rstrip(), src, count=1)
        if ns != src: TESTBED.write_text(ns); return True
    if bug["mutated"] in src:
        ns = src.replace(bug["mutated"], bug["original"])
        if ns != src: TESTBED.write_text(ns); return True
    return False


def run_rag_experiment(arm_name: str, retrieval_mode: str, bug_pool: list[dict], sessions: int) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"  {arm_name} — {sessions} sessions | Retrieval: {retrieval_mode.upper()}")
    print(f"{'='*60}")
    orig = TESTBED.read_text()
    fixer = RetrievalAugmentedFixer()
    results = []
    approaches = ["Targeted Fix","Root Cause + Guard","Extensible Implementation",
                  "Incremental Rewrite","Safe Extract","TDD First"]
    all_diffs = []

    for i in range(sessions):
        bug = bug_pool[i % len(bug_pool)]
        approach = approaches[i % len(approaches)]
        sid = f"rag-{i+1:04d}"

        rag_ctx = ""
        if retrieval_mode == "vector":
            sim = fixer.get_similar_fixes(bug["description"])
            rag_ctx = format_retrieval_context(sim)
        elif retrieval_mode == "random" and all_diffs:
            rd = random.choice(all_diffs)
            rag_ctx = f"Past fix:\n```diff\n{rd['diff'][:500]}\n```\n"

        t0 = time.time()
        pre_pass, pre_fail, test_out = inject_and_test(bug)
        fix_code, _ = get_llm_fix(bug, approach, test_out, rag_ctx)
        applied = apply_fix(fix_code, bug)
        post_pass, post_fail, _ = run_tests(bug["test_filter"])
        dur = time.time() - t0
        success = post_fail == 0 and post_pass > 0

        if success:
            d = f"Replace '{bug['mutated'][:80]}' with '{bug['original'][:80]}' in {bug['function']}()"
            fixer.add_successful_fix(sid, bug["description"], d, bug["function"])
            if retrieval_mode == "random":
                all_diffs.append({"diff": d, "function": bug["function"]})

        results.append({
            "session": i+1, "bug": bug["id"], "difficulty": bug["difficulty"],
            "approach": approach, "success": success,
            "pre_fail": pre_fail, "post_fail": post_fail,
            "fix_applied": applied, "dur_sec": round(dur, 1),
            "db_size": fixer.count(),
        })
        emoji = "✅" if success else "❌"
        print(f"  S{i+1:4d}: [{bug['difficulty'][:1].upper():4s}] {bug['id'][:30]:30s} {approach:28s} {emoji} ({dur:.0f}s, db={fixer.count()})")

        TESTBED.write_text(orig)

        if (i+1) % 25 == 0:
            ok = sum(1 for r in results[-25:] if r["success"])
            print(f"  ── Rolling: {ok}/25 ({ok*4}%) | DB: {fixer.count()} fixes ──\n")

    return results


def analyze(all_results: dict):
    print(f"\n{'='*60}")
    print(f"  RAG HYPOTHESIS TEST RESULTS")
    print(f"{'='*60}")
    for arm, results in all_results.items():
        if not results: continue
        n = len(results)
        rate = sum(1 for r in results if r["success"]) / n
        early = sum(1 for r in results[:min(20,n)] if r["success"]) / min(20,n)
        late = sum(1 for r in results[-min(20,n):] if r["success"]) / min(20,n)
        print(f"\n  [{arm}]")
        print(f"    Overall: {rate:.0%} | Early: {early:.0%} → Late: {late:.0%} ({late-early:+.0%})")
        for diff in ["easy","medium","hard"]:
            d = [r for r in results if r["difficulty"]==diff]
            if d: print(f"    [{diff:6s}]: {sum(1 for r in d if r['success'])/len(d):.0%}")

    arms = list(all_results.keys())
    if len(arms) >= 2:
        r1 = [1 if r["success"] else 0 for r in all_results[arms[0]]]
        r2 = [1 if r["success"] else 0 for r in all_results[arms[1]]]
        p1, p2 = sum(r1)/len(r1) if r1 else 0, sum(r2)/len(r2) if r2 else 0
        proven = p1 > p2 + 0.05
        print(f"\n  {arms[0]} vs {arms[1]}: {p1:.0%} vs {p2:.0%} ({p1-p2:+.0%})")
        print(f"  VERDICT: {'✅ RETRIEVAL HELPS' if proven else '❌ NO EVIDENCE'}")

    out = SCRIPTS_DIR.parent / "docs" / "rag_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({k: sum(1 for r in v if r["success"])/len(v) if v else 0 for k,v in all_results.items()}, indent=2))
    print(f"\nSaved to {out}")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", type=int, default=50)
    p.add_argument("--retrieval", choices=["vector","random","none"], default="vector")
    args = p.parse_args()

    print(f"{'='*60}")
    print(f"  RETRIEVAL-AUGMENTED FIXING EXPERIMENT")
    print(f"  New hypothesis: similar past diffs → better fixes")
    print(f"  Model: {MODEL} | {args.sessions} sessions | Retrieval: {args.retrieval.upper()}")
    print(f"{'='*60}")

    bug_pool = generate_hard_bug_pool(target_count=max(30, args.sessions//2))
    print(f"Generated {len(bug_pool)} hard bugs (targets: topological_sort, regex_match, merge_intervals, binary_search)")

    results = run_rag_experiment(f"RAG={args.retrieval.upper()}", args.retrieval, bug_pool, args.sessions)
    analyze({"retrieval": results})


if __name__ == "__main__":
    main()