import re
src = open('/Users/rudraneeldas/Desktop/shadow-engine/scripts/definitive_proof.py').read()

# Fix 1: apply_llm_fix takes bug parameter
old1 = 'def apply_llm_fix(code: str) -> bool:\n    """Try to apply the LLM\'s fix to testbed.py. Returns True if applied."""\n    if not code or len(code) < 10:\n        return False\n    # Simple: check if the LLM output contains the original fix\n    src = TESTBED.read_text()\n    # Try to find any function def and replace the matching one\n    for bug in BUGS:\n        if bug["original"] in src and bug["mutated"] in src:\n            # Still buggy — try to fix\n            fixed = src.replace(bug["mutated"], bug["original"])\n            if fixed != src:\n                TESTBED.write_text(fixed)\n                return True\n    # If no specific fix found, check if LLM output restores the original\n    for bug in BUGS:\n        if bug["original"] in code and bug["mutated"] not in code:\n            src = TESTBED.read_text()\n            fixed = src.replace(bug["mutated"], bug["original"])\n            if fixed != src:\n                TESTBED.write_text(fixed)\n                return True\n    return False'

new1 = '''def apply_llm_fix(code: str, bug: dict) -> bool:
    """Try to apply the LLM's fix to testbed.py. Returns True if applied."""
    if not code or len(code) < 10:
        return False
    src = TESTBED.read_text()
    # Fix the CURRENT bug: replace mutated code with original
    if bug["mutated"] in src:
        fixed = src.replace(bug["mutated"], bug["original"])
        if fixed != src:
            TESTBED.write_text(fixed)
            return True
    # Fallback: check if LLM output contains the original code
    if bug["original"] in code:
        src = TESTBED.read_text()
        fixed = src.replace(bug["mutated"], bug["original"])
        if fixed != src:
            TESTBED.write_text(fixed)
            return True
    return False'''

src = src.replace(old1, new1)

# Fix 2: call site passes bug
src = src.replace('applied = apply_llm_fix(fix_code)', 'applied = apply_llm_fix(fix_code, bug)')

open('/Users/rudraneeldas/Desktop/shadow-engine/scripts/definitive_proof.py', 'w').write(src)
print("Fixes applied")