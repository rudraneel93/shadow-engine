#!/usr/bin/env python3
"""Test that generated bugs actually cause Flask test failures."""
import json, re, subprocess
from pathlib import Path

bugs = json.load(open(Path(__file__).resolve().parent.parent / "docs" / "bug_database.json"))
flask_study = Path("/tmp/flask-study")

works = 0
total = 0
for bug in bugs:
    target = flask_study / bug["target_file"]
    if not target.exists():
        print(f'  {bug["id"]}: SKIP — file not found')
        total += 1
        continue

    original = target.read_text().split("\n")
    line_idx = bug["line"] - 1
    if line_idx >= len(original):
        print(f'  {bug["id"]}: SKIP — line out of range')
        total += 1
        continue

    # Apply mutation
    if bug["mutation"] == "delete_line":
        mutated = original[:line_idx] + original[line_idx + 1:]
    else:
        mutated = original[:line_idx] + [bug["mutated_code"]] + original[line_idx + 1:]

    backup = original.copy()
    target.write_text("\n".join(mutated))

    r = subprocess.run(
        ["/opt/miniconda3/bin/pytest", str(flask_study / "tests" / "test_basic.py"), "--tb=no", "-q"],
        capture_output=True, text=True, timeout=30, cwd=str(flask_study),
    )

    target.write_text("\n".join(backup))

    passed = failed = 0
    for line in r.stdout.split("\n"):
        nums = re.findall(r"(\d+)\s+(passed|failed)", line)
        for n, kind in nums:
            if kind == "passed": passed = int(n)
            elif kind == "failed": failed = int(n)

    ok = failed > 0
    works += ok
    total += 1
    print(f'  {bug["id"]}: {bug["mutation"]:20s} → {passed}p/{failed}f [{"WORKS" if ok else "NO EFFECT"}]')

print(f"\n{works}/{total} bugs cause test failures")