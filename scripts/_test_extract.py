import py_compile, tempfile, os, re

# Simulate qwen3:8b raw output format
raw_output = """Okay, I need to write a Python function called add that takes two integers.
Let me think about this.

def add(a: int, b: int) -> int:
    return a + b

That should work. The function is simple."""

# Extract code blocks first
code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw_output, re.DOTALL)
if code_blocks:
    code = '\n'.join(code_blocks)
else:
    # Extract def/class blocks from thinking text
    funcs = re.findall(
        r'(?:async\s+)?def\s+\w+\s*\([^)]*\).*?(?:(?=\n(?:[^\s]|\s*(?:def|class|@)))|\Z)',
        raw_output, re.DOTALL)
    classes = re.findall(
        r'class\s+\w+.*?(?:(?=\n(?:[^\s]|\s*(?:def|class|@)))|\Z)',
        raw_output, re.DOTALL)
    code = '\n'.join(funcs + classes)

print('Extracted code:')
print(repr(code[:500]))
print()

# Try compiling
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write(code)
    tmp = f.name
try:
    py_compile.compile(tmp, doraise=True)
    print('✅ PASS: Code is valid Python')
except py_compile.PyCompileError as e:
    print(f'❌ FAIL: {e}')
os.unlink(tmp)