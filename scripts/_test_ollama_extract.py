#!/usr/bin/env python3
"""Test Ollama output extraction and py_compile validation."""
import re, py_compile, tempfile, os, httpx

resp = httpx.post('http://localhost:11434/api/generate',
    json={'model':'qwen3:8b','prompt':'Write a Python function called add(a,b) that returns a+b. Output ONLY code.','stream':False,'options':{'num_predict':100}},
    timeout=30)
data = resp.json()
raw = data.get('thinking','') or data.get('response','')
print('=== RAW (first 300) ===')
print(raw[:300])
print()

# Try extraction
code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
if code_blocks:
    code = '\n'.join(code_blocks)
    print('Found markdown blocks')
else:
    funcs = re.findall(
        r'(?:async\s+)?def\s+\w+\s*\([^)]*\).*?(?:(?=\n(?:[^\s]|\s*(?:def|class|@)))|\Z)',
        raw, re.DOTALL)
    code = '\n'.join(funcs)
    print(f'Extracted {len(funcs)} function(s)')

print('=== CODE ===')
print(code[:400])
print()

if code.strip():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        print('PASS: Valid Python!')
    except py_compile.PyCompileError as e:
        print(f'FAIL: {e}')
    os.unlink(tmp)