#!/usr/bin/env python3
"""Generate a database of injected bugs for definitive hypothesis testing.

Run: python scripts/generate_bugs.py
Output: docs/bug_database.json
"""

import ast, json, re
from pathlib import Path

FLASK_ROOT = Path("/tmp/flask-study")
FLASK_SRC = FLASK_ROOT / "src" / "flask"
BATCH_SIZE = 5

MUTATIONS = [
    ("condition_flip", lambda line: line.replace("if ", "if not ").replace("if not not ", "if ")),
    ("return_none", lambda line: re.sub(r"return\s+\S+", "return None", line) if "return " in line and "return None" not in line else line),
    ("operator_add_sub", lambda line: line.replace(" + ", " - ") if " + " in line else line),
    ("operator_mul_div", lambda line: line.replace(" * ", " / ") if " * " in line else line),
    ("constant_change", lambda line: re.sub(r'default\s*=\s*["\']\w+["\']', 'default = "BROKEN"', line)),
    ("delete_line", None),
]


def get_function_linenos(src_path: Path) -> list[dict]:
    tree = ast.parse(src_path.read_text())
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({"name": node.name, "lineno": node.lineno, "end_lineno": node.end_lineno or node.lineno})
    return funcs


def generate_bugs(src_file: Path, max_bugs: int = BATCH_SIZE) -> list[dict]:
    lines = src_file.read_text().split("\n")
    funcs = get_function_linenos(src_file)
    if not funcs:
        return []

    bugs = []
    used_lines = set()

    for func in funcs[:max(2, max_bugs // 2)]:
        for mname, mfn in MUTATIONS:
            if len(bugs) >= max_bugs:
                break
            start = func["lineno"]
            end = min(func["end_lineno"] + 1, len(lines))
            for line_idx in range(start, end):
                if line_idx in used_lines:
                    continue
                line = lines[line_idx - 1]

                if mname == "delete_line":
                    if line.strip() and not line.strip().startswith(("#", "def", "class", "@", '"""', "'''")):
                        original = line
                        mutated = "<deleted>"
                        used_lines.add(line_idx)
                        break
                else:
                    mutated_line = mfn(line)
                    if mutated_line != line and len(mutated_line) > 5:
                        original = line
                        mutated = mutated_line
                        used_lines.add(line_idx)
                        break
            else:
                continue

            bug = {
                "id": f"bug_{len(bugs)+1:03d}",
                "target_file": str(src_file.relative_to(FLASK_ROOT)),
                "function": func["name"],
                "line": line_idx,
                "mutation": mname,
                "original_code": original.strip(),
                "mutated_code": mutated.strip() if mname != "delete_line" else "<deleted>",
                "difficulty": "easy" if mname in ("condition_flip", "constant_change") else "medium",
                "description": f"{mname.replace('_', ' ')} in {func['name']}() at line {line_idx}",
            }
            bugs.append(bug)

    return bugs[:max_bugs]


def main():
    bugs = []
    src_files = list(FLASK_SRC.glob("*.py"))[:5]

    for src_file in src_files:
        file_bugs = generate_bugs(src_file, BATCH_SIZE)
        bugs.extend(file_bugs)
        if len(bugs) >= 30:
            break

    out = Path(__file__).resolve().parent.parent / "docs" / "bug_database.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(bugs, indent=2))
    print(f"Generated {len(bugs)} bugs → {out}")


if __name__ == "__main__":
    main()