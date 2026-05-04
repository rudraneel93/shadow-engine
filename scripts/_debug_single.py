#!/usr/bin/env python3
"""Debug: test a single LLM code-gen + test-gen + pytest cycle."""
import httpx, re, py_compile, tempfile, os, subprocess

# Step 1: Generate code
resp = httpx.post('http://localhost:11434/api/generate',
    json={'model':'qwen3-coder:480b-cloud',
          'prompt':'Write a Python function is_palindrome(s: str) -> bool that returns True if the string reads the same forwards and backwards, ignoring case and non-alphanumeric characters. Use a Targeted Fix approach. Output ONLY Python code in ```python blocks.',
          'stream':False, 'options':{'num_predict':512}},
    timeout=90)
raw = resp.json().get('response','') or resp.json().get('thinking','')
blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
code = '\n\n'.join(blocks) if blocks else raw
print('=== GENERATED CODE ===')
print(code[:400])
print()

# Step 2: Get tests
resp2 = httpx.post('http://localhost:11434/api/generate',
    json={'model':'qwen3-coder:480b-cloud',
          'prompt': f'Here is a Python function:\n\n```python\n{code}\n```\n\nWrite a pytest test function that tests this function with at least 5 test cases including edge cases. Output ONLY valid Python with import pytest.',
          'stream':False, 'options':{'num_predict':768}},
    timeout=120)
raw2 = resp2.json().get('response','') or resp2.json().get('thinking','')
blocks2 = re.findall(r'```(?:python)?\s*\n(.*?)```', raw2, re.DOTALL)
test_code = '\n\n'.join(blocks2) if blocks2 else raw2

full = f"import pytest\n\n{code}\n\n{test_code}"
print('=== FULL TEST FILE ===')
print(full[:500])
print()

# Step 3: Run pytest
f = tempfile.NamedTemporaryFile(mode='w', suffix='test.py', delete=False)
f.write(full)
tmp = f.name
f.close()
result = subprocess.run(['pytest', tmp, '-v', '--tb=short', '--timeout=30'],
    capture_output=True, text=True, timeout=45)
print('=== PYTEST STDOUT ===')
print(result.stdout[-800:])
print('=== PYTEST STDERR ===')
print(result.stderr[-300:])
os.unlink(tmp)