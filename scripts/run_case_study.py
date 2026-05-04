#!/usr/bin/env python3
"""Real-data case study with actual code compilation validation.

Each LLM-generated Python code snippet is saved to a .py file and checked with
py_compile. Success = code is valid Python (no syntax errors).
Failure = code has syntax errors or LLM returned empty output.

This provides REAL pass/fail data for shadow-engine's learning loop.

Run: python scripts/run_case_study.py --sessions 50
"""

import json, os, py_compile, shutil, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine

TASKS = [
    ("bug_fix", "Write a Python function `fix_url_for` that patches Flask's url_for to handle subdomain when SERVER_NAME is missing. The function should check if SERVER_NAME is set before constructing subdomain URLs.", "Targeted Fix", "easy"),
    ("bug_fix", "Write a Python function `validate_json_body` that checks request.get_json() return value and raises a 400 BadRequest with descriptive message when Content-Type is missing.", "Root Cause + Guard", "easy"),
    ("bug_fix", "Write a Python function `redirect_with_fragment` that wraps Flask's redirect() and preserves any URL fragment passed to it.", "Targeted Fix", "medium"),
    ("feature", "Write a Python decorator class `AfterThisResponse` that hooks into Flask's response cycle. It should store a callback to be executed after the current response is sent.", "Extensible Implementation", "medium"),
    ("feature", "Write a Python context manager class `TestRequestContext` that sets up both the request context and app context for testing. Should work as a `with` statement.", "Minimal Viable", "medium"),
    ("feature", "Write a Python function `register_plugin` that adds a plugin system to Flask. Plugins should be callable objects that receive the Flask app instance and can modify routes, add middleware, etc.", "Extensible Implementation", "hard"),
    ("refactor", "Write a Python helper function `extract_route_params` that takes Flask's URL rule string and returns a list of parameter names. Should handle `<int:>`, `<string:>`, `<path:>` converters.", "Safe Extract", "medium"),
    ("refactor", "Write a Python base class `BaseRequestResponse` that extracts common functionality from Flask's Request and Response classes (e.g., header management, charset handling).", "Incremental Rewrite", "medium"),
    ("testing", "Write a Python test function `test_json_provider_default` using pytest that tests Flask's JSON provider default encoder by creating a custom object, registering it, and verifying JSON output.", "TDD First", "easy"),
    ("testing", "Write a Python test function `test_nested_blueprint_registration` using pytest that creates two nested blueprints, registers them, and verifies correct URL prefix generation.", "TDD First", "medium"),
]

APPROACHES = ["Targeted Fix", "Root Cause + Guard", "Extensible Implementation",
              "Minimal Viable", "Incremental Rewrite", "Safe Extract", "TDD First"]


def validate_python_code(code: str) -> tuple[bool, str]:
    """Check if Python code is syntactically valid. Returns (valid, error_msg)."""
    if not code or len(code) < 20:
        return False, "empty or too short response"
    # Extract code blocks from markdown/thinking output
    import re
    code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', code, re.DOTALL)
    if code_blocks:
        code = '\n'.join(code_blocks)
    # Save to temp file and compile
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            tmp = f.name
        py_compile.compile(tmp, doraise=True)
        os.unlink(tmp)
        return True, ""
    except py_compile.PyCompileError as e:
        os.unlink(tmp)
        return False, str(e)[:100]
    except Exception as e:
        return False, str(e)[:100]


def run_sessions(count: int = 50):
    # Bootstrap Flask
    flask_path = Path(tempfile.mkdtemp()) / "flask"
    if Path("/tmp/flask-study").exists():
        os.system(f"cp -r /tmp/flask-study {flask_path}")
    else:
        os.system(f"git clone --depth 1 https://github.com/pallets/flask.git {flask_path}")

    storage = Path(tempfile.mkdtemp())
    engine = ShadowEngine(storage_path=storage, repo_path=str(flask_path))
    r = engine.bootstrap()
    print(f"Codebase: Flask ({r['symbols_indexed']} symbols) | {count} sessions")
    print()

    results = []
    for i in range(1, count + 1):
        task = TASKS[(i - 1) % len(TASKS)]
        ptype, prompt, approach, difficulty = task
        session_id = f"cs-{i:03d}"

        # Real Ollama call
        import httpx
        t0 = time.time()
        try:
            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen3-coder:480b-cloud",
                    "prompt": f"Write a Python function for: {prompt}\n\nOutput ONLY valid Python code with no explanations. Include proper imports and type hints.",
                    "stream": False,
                    "options": {"num_predict": 512},
                },
                timeout=90,
            )
            data = resp.json()
            out = data.get("response") or data.get("thinking") or ""
            tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            dur = time.time() - t0
        except Exception:
            out, tokens, dur = "", 0, time.time() - t0

        # REAL validation: compile the generated Python code
        valid, error = validate_python_code(out)
        outcome = "success" if valid else "failure"
        passed_tests = 1 if valid else 0
        failed_tests = 0 if valid else 1

        ingestion = engine.record_result(
            session_id=session_id, outcome=outcome, prompt=prompt,
            approach=approach, model="qwen3:8b", files_changed=[],
            test_results={"total": 1, "passed": passed_tests, "failed": failed_tests},
            duration_seconds=dur, token_count=tokens,
        )

        results.append({
            "session": i, "ptype": ptype, "difficulty": difficulty,
            "approach": approach, "valid_code": valid,
            "dur": round(dur, 1), "tokens": tokens,
        })

        emoji = "✅" if valid else "❌"
        err = f" — {error[:60]}" if error else ""
        print(f"  S{i:3d}: [{difficulty:6s} {ptype:9s}] {approach:28s} {emoji} ({dur:.0f}s){err}")

        if i % 10 == 0:
            stats = engine.get_stats()
            print(f"  ── Checkpoint {i}: rate={stats.get('overall_success_rate',0):.0%}, "
                  f"patterns={stats.get('total_patterns',0)} ──")

    # Analysis
    stats = engine.get_stats()
    health = engine.health_scorer.compute()

    print(f"\n{'='*60}")
    print(f"  CASE STUDY RESULTS — {count} Real Sessions")
    print(f"{'='*60}")
    print(f"Sessions: {stats.get('total_sessions', 0)}")
    print(f"Code-compile pass rate: {stats.get('overall_success_rate', 0):.1%}")
    print(f"Patterns learned: {stats.get('total_patterns', 0)}")
    print(f"Health score: {health.get('overall_score', 0)}/100")

    print(f"\nPer-Difficulty:")
    for diff in ["easy", "medium", "hard"]:
        d = [r for r in results if r["difficulty"] == diff]
        if d:
            ok = sum(1 for r in d if r["valid_code"])
            print(f"  [{diff:6s}]: {ok}/{len(d)} ({ok/len(d):.0%})")

    print(f"\nPer-Approach:")
    for ap in APPROACHES:
        a = [r for r in results if r["approach"] == ap]
        if a:
            ok = sum(1 for r in a if r["valid_code"])
            print(f"  {ap:28s}: {ok}/{len(a)} ({ok/len(a):.0%})")

    print(f"\nApproach Recommendations:")
    for pt in ["bug_fix", "feature", "refactor", "testing"]:
        s = engine.suggest(f"a {pt} task")
        print(f"  [{pt:9s}]: {s['recommended_approach'][:55]}")

    # Compounding check
    early = [r for r in results if r["session"] <= count // 4]
    late = [r for r in results if r["session"] > 3 * count // 4]
    if early and late:
        er = sum(1 for r in early if r["valid_code"]) / len(early)
        lr = sum(1 for r in late if r["valid_code"]) / len(late)
        print(f"\n  Compounding: early={er:.0%}, late={lr:.0%} ({lr-er:+.0%})")
        print(f"  {'✅ Improving!' if lr > er else '⚠️ No compounding detected'}")

    # Save
    out_path = Path(__file__).resolve().parent.parent / "docs" / "case_study_results.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({
        "codebase": "Flask", "llm": "qwen3:8b", "sessions": count,
        "compile_pass_rate": stats.get("overall_success_rate", 0),
        "patterns": stats.get("total_patterns", 0),
        "health": health.get("overall_score", 0),
    }, indent=2))
    print(f"\nSaved to {out_path}")

    shutil.rmtree(storage, ignore_errors=True)
    shutil.rmtree(str(flask_path.parent), ignore_errors=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", type=int, default=50)
    args = p.parse_args()
    run_sessions(args.sessions)