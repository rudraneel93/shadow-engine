"""Verify that injected bugs cause test failures."""
import subprocess, shutil
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent
testbed = scripts_dir / "testbed.py"
test_file = scripts_dir / "test_testbed.py"
backup = scripts_dir / "testbed_backup.py"

# Backup original
shutil.copy(testbed, backup)

bugs_tested = 0
bugs_causing_failure = 0

# Bug 1: fibonacci: + → - 
src = testbed.read_text()
buggy = src.replace("result[-1] + result[-2]", "result[-1] - result[-2]")
testbed.write_text(buggy)
r = subprocess.run(["/opt/miniconda3/bin/pytest", str(test_file), "--tb=no", "-q", "-k", "Fibonacci"],
    capture_output=True, text=True, timeout=15, cwd=str(scripts_dir))
failed = "failed" in r.stdout.split("\n")[-2] if r.stdout else False
bugs_tested += 1
bugs_causing_failure += failed
print(f"Bug 1 (fibonacci +→−): {'WORKS ✅' if failed else 'NO EFFECT ❌'}")

# Bug 2: binary_search: <= → <
testbed.write_text(src.replace("while left <= right:", "while left < right:"))
r = subprocess.run(["/opt/miniconda3/bin/pytest", str(test_file), "--tb=no", "-q", "-k", "BinarySearch"],
    capture_output=True, text=True, timeout=15, cwd=str(scripts_dir))
failed = "failed" in r.stdout.split("\n")[-2] if r.stdout else False
bugs_tested += 1
bugs_causing_failure += failed
print(f"Bug 2 (binary_search <=→<): {'WORKS ✅' if failed else 'NO EFFECT ❌'}")

# Bug 3: palindrome: return reversed → return original
testbed.write_text(src.replace("return cleaned == cleaned[::-1]", "return cleaned == cleaned"))
r = subprocess.run(["/opt/miniconda3/bin/pytest", str(test_file), "--tb=no", "-q", "-k", "Palindrome"],
    capture_output=True, text=True, timeout=15, cwd=str(scripts_dir))
failed = "failed" in r.stdout.split("\n")[-2] if r.stdout else False
bugs_tested += 1
bugs_causing_failure += failed
print(f"Bug 3 (palindrome reversed→original): {'WORKS ✅' if failed else 'NO EFFECT ❌'}")

# Bug 4: safe_divide: b=0 check removed
testbed.write_text(src.replace("if b == 0:\n        return 0.0", "if b == 0:\n        return 999.0"))
r = subprocess.run(["/opt/miniconda3/bin/pytest", str(test_file), "--tb=no", "-q", "-k", "SafeDivide"],
    capture_output=True, text=True, timeout=15, cwd=str(scripts_dir))
failed = "failed" in r.stdout.split("\n")[-2] if r.stdout else False
bugs_tested += 1
bugs_causing_failure += failed
print(f"Bug 4 (safe_divide 0→999): {'WORKS ✅' if failed else 'NO EFFECT ❌'}")

# Bug 5: merge_intervals: max→min
testbed.write_text(src.replace("max(last_end, end)", "min(last_end, end)"))
r = subprocess.run(["/opt/miniconda3/bin/pytest", str(test_file), "--tb=no", "-q", "-k", "MergeIntervals"],
    capture_output=True, text=True, timeout=15, cwd=str(scripts_dir))
failed = "failed" in r.stdout.split("\n")[-2] if r.stdout else False
bugs_tested += 1
bugs_causing_failure += failed
print(f"Bug 5 (merge max→min): {'WORKS ✅' if failed else 'NO EFFECT ❌'}")

# Restore
shutil.copy(backup, testbed)
backup.unlink()

print(f"\n{bugs_causing_failure}/{bugs_tested} bugs cause test failures")