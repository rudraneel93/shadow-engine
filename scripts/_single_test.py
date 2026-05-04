#!/usr/bin/env python3
"""Single clean run: code gen + test gen + pytest validation."""
import httpx, re, tempfile, os, subprocess

# Step 1: Generate code
resp = httpx.post('http://localhost:11434/api/generate',
    json={'model':'qwen3-coder:480b-cloud',
          'prompt':'Write a Python function is_palindrome(s) -> bool. Output ONLY Python code in ```python blocks.',
          'stream':False, 'options':{'num_predict':256}},
    timeout=90)
raw = resp.json().get('response','')
code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
code = '\n'.join(code_blocks) if code_blocks else raw
print('=== CODE ===')
print(code[:300])

# Step 2: Generate tests
resp2 = httpx.post('http://localhost:11434/api/generate',
    json={'model':'qwen3-coder:480b-cloud',
          'prompt': f'Here is a Python function:\n\n```python\n{code}\n```\n\nWrite a pytest test function test_is_palindrome with 3 test cases. Output ONLY valid Python starting with import pytest.',
          'stream':False, 'options':{'num_predict':512}},
    timeout=90)
raw2 = resp2.json().get('response','')
test_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw2, re.DOTALL)
test_code = '\n'.join(test_blocks) if test_blocks else raw2
print('\n=== TESTS ===')
print(test_code[:300])

# Step 3: Combine and run
full = f'import pytest\n\n{code}\n\n{test_code}'
print('\n=== FULL FILE ===')
print(full[:500])

f = tempfile.NamedTemporaryFile(mode='w', suffix='test.py', delete=False)
f.write(full); f.close()

result = subprocess.run(['pytest', f.name, '-v', '--tb=short'], capture_output=True, text=True, timeout=30)
print('\n=== PYTEST STDOUT (last 20 lines) ===')
for line in result.stdout.split('\n')[-20:]:
    print(line)
print('\n=== PYTEST STDERR ===')
print(result.stderr[:300])
os.unlink(f.name)