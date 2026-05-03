"""Codebase indexer that parses source files into the knowledge graph using regex AST analysis."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

from .models import FileSummary, Symbol, SymbolKind


# Pre-compiled regex patterns grouped by file extension
_COMPILED_PATTERNS: dict[str, list[tuple[re.Pattern[str], SymbolKind]]] = {
    ".py": [
        (re.compile(r"^def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*(\S+))?\s*:"), SymbolKind.FUNCTION),
        (re.compile(r"^\s+def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*(\S+))?\s*:"), SymbolKind.METHOD),
        (re.compile(r"^class\s+(\w+)(?:\(([^)]*)\))?\s*:"), SymbolKind.CLASS),
    ],
    ".ts": [
        (re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*<?"), SymbolKind.FUNCTION),
        (re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"), SymbolKind.CLASS),
        (re.compile(r"(?:export\s+)?interface\s+(\w+)"), SymbolKind.INTERFACE),
        (re.compile(r"(?:export\s+)?enum\s+(\w+)"), SymbolKind.ENUM),
        (re.compile(r"(?:export\s+)?type\s+(\w+)\s*="), SymbolKind.TYPE_ALIAS),
    ],
    ".tsx": [
        (re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*<?"), SymbolKind.FUNCTION),
        (re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"), SymbolKind.CLASS),
        (re.compile(r"(?:export\s+)?interface\s+(\w+)"), SymbolKind.INTERFACE),
        (re.compile(r"(?:export\s+)?const\s+(\w+)\s*(?::\s*\w+)?\s*=\s*(?:\(|async)"), SymbolKind.FUNCTION),
    ],
    ".js": [
        (re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(?"), SymbolKind.FUNCTION),
        (re.compile(r"(?:export\s+)?class\s+(\w+)"), SymbolKind.CLASS),
        (re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:\(|async)"), SymbolKind.FUNCTION),
    ],
    ".jsx": [
        (re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(?"), SymbolKind.FUNCTION),
        (re.compile(r"(?:export\s+)?class\s+(\w+)"), SymbolKind.CLASS),
        (re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:\(|async)"), SymbolKind.FUNCTION),
    ],
    ".go": [
        (re.compile(r"^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)"), SymbolKind.FUNCTION),
        (re.compile(r"^type\s+(\w+)\s+struct\s*{"), SymbolKind.CLASS),
        (re.compile(r"^type\s+(\w+)\s+interface\s*{"), SymbolKind.INTERFACE),
    ],
    ".rs": [
        (re.compile(r"^(?:pub\s+)?fn\s+(\w+)\s*<?"), SymbolKind.FUNCTION),
        (re.compile(r"^(?:pub\s+)?struct\s+(\w+)"), SymbolKind.CLASS),
        (re.compile(r"^(?:pub\s+)?trait\s+(\w+)"), SymbolKind.INTERFACE),
        (re.compile(r"^(?:pub\s+)?enum\s+(\w+)"), SymbolKind.ENUM),
        (re.compile(r"^(?:pub\s+)?type\s+(\w+)\s*="), SymbolKind.TYPE_ALIAS),
    ],
}

_IMPORT_RE = re.compile(r"^\s*(?:from\s+(\S+)\s+import\s+(.+)|import\s+(\S+)(?:\s+as\s+(\S+))?)")

SUPPORTED_EXTENSIONS = frozenset(_COMPILED_PATTERNS.keys())

SKIP_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz", ".lock", ".map",
})

SKIP_DIRS = frozenset({
    "node_modules", "__pycache__", ".git", ".next", "dist", "build",
    "target", ".venv", "venv", ".tox", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "coverage", ".nyc_output", ".shadow-engine",
})


class CodebaseIndexer:
    """Parses a repository's source files and populates the knowledge graph."""

    def __init__(self, root_path: str | Path):
        self.root = Path(root_path).resolve()
        self._symbols: dict[str, Symbol] = {}
        self._files: dict[str, FileSummary] = {}

    @property
    def symbols(self) -> dict[str, Symbol]:
        return dict(self._symbols)

    @property
    def files(self) -> dict[str, FileSummary]:
        return dict(self._files)

    def index(self) -> tuple[dict[str, Symbol], dict[str, FileSummary]]:
        self._symbols.clear()
        self._files.clear()
        for file_path in self._walk_files():
            self._index_file(file_path)
        self._resolve_cross_file_dependencies()
        self._resolve_same_file_dependencies()
        return self.symbols, self.files

    def index_file(self, relative_path: str) -> FileSummary | None:
        full_path = self.root / relative_path
        if not full_path.exists():
            return None
        return self._index_file(full_path)

    def _walk_files(self) -> Generator[Path, None, None]:
        for entry in self.root.rglob("*"):
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                continue
            if any(p.name in SKIP_DIRS for p in entry.parents):
                continue
            if entry.suffix in SKIP_EXTENSIONS:
                continue
            if entry.suffix not in SUPPORTED_EXTENSIONS:
                continue
            try:
                if entry.stat().st_size > 1_000_000:
                    continue
            except OSError:
                continue
            yield entry

    def _index_file(self, file_path: Path) -> FileSummary:
        relative = str(file_path.relative_to(self.root))
        language = file_path.suffix

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        lines = content.split("\n")
        line_count = len(lines)

        file_summary = FileSummary(
            path=relative, language=language, line_count=line_count,
            last_indexed=datetime.now(timezone.utc),
        )

        patterns = _COMPILED_PATTERNS.get(language, [])
        if not patterns:
            self._files[relative] = file_summary
            return file_summary

        for line_num, line in enumerate(lines, start=1):
            for pattern, kind in patterns:
                m = pattern.match(line)
                if m:
                    name = m.group(1)
                    if not name:
                        continue
                    signature = line.strip()
                    docstring = self._extract_docstring(lines, line_num - 1, language)

                    symbol = Symbol(
                        id=Symbol.compute_id(relative, name),
                        name=name, kind=kind, file_path=relative,
                        line_start=line_num,
                        line_end=self._find_symbol_end(lines, line_num - 1, language),
                        signature=signature, docstring=docstring,
                    )
                    self._symbols[symbol.id] = symbol
                    file_summary.symbols.append(symbol.id)

                    im = _IMPORT_RE.match(line)
                    if im:
                        from_module = im.group(1)
                        import_targets = im.group(2)
                        import_module = im.group(3)
                        if from_module and import_targets:
                            targets = import_targets.strip()
                            if targets == "*":
                                file_summary.imports.append(f"*:{from_module}")
                            else:
                                for target in targets.split(","):
                                    target = target.strip()
                                    if " as " in target:
                                        target = target.split(" as ")[0].strip()
                                    file_summary.imports.append(target)
                        elif import_module:
                            file_summary.imports.append(import_module.strip())
                        elif from_module:
                            file_summary.imports.append(from_module.strip())
                    break

        self._files[relative] = file_summary
        return file_summary

    # ── Cross-File Dependencies ──────────────────────────────────

    def _resolve_cross_file_dependencies(self) -> None:
        """Resolve cross-file symbol dependencies via imports."""
        name_to_ids: dict[str, list[str]] = {}
        for sym_id, sym in self._symbols.items():
            name_to_ids.setdefault(sym.name, []).append(sym_id)

        module_to_symbols: dict[str, list[str]] = {}
        for sym_id, sym in self._symbols.items():
            module = sym.file_path.replace("/", ".").replace("\\", ".")
            for ext in SUPPORTED_EXTENSIONS:
                if module.endswith(ext):
                    module = module[:-len(ext)]
                    break
            module_to_symbols.setdefault(module, []).append(sym_id)

        for file_path, file_summary in self._files.items():
            file_symbol_ids = set(file_summary.symbols)
            file_module = file_path.replace("/", ".").replace("\\", ".")
            for ext in SUPPORTED_EXTENSIONS:
                if file_module.endswith(ext):
                    file_module = file_module[:-len(ext)]
                    break

            for imp in file_summary.imports:
                target_module = self._resolve_import_target(imp, file_module)
                if target_module and target_module in module_to_symbols:
                    for sym_id in file_symbol_ids:
                        if sym_id in self._symbols:
                            sym = self._symbols[sym_id]
                            for dep_id in module_to_symbols[target_module]:
                                if dep_id != sym_id and dep_id not in sym.dependencies:
                                    sym.dependencies.append(dep_id)
                elif imp and not imp.startswith(".") and not imp.startswith("*:") and imp in name_to_ids:
                    for sym_id in file_symbol_ids:
                        if sym_id in self._symbols:
                            sym = self._symbols[sym_id]
                            for dep_id in name_to_ids[imp]:
                                if dep_id != sym_id and dep_id not in sym.dependencies:
                                    sym.dependencies.append(dep_id)

    # ── Same-File Dependencies ───────────────────────────────────

    def _resolve_same_file_dependencies(self) -> None:
        """Resolve same-file symbol dependencies.

        For each file, scan the body of each symbol for references to
        other known symbols in the SAME file. When function A calls
        function B in the same file, add a dependency edge A → B.

        This was previously untracked — only cross-file imports were resolved.
        """
        name_to_sym: dict[str, str] = {}
        for sym_id, sym in self._symbols.items():
            name_to_sym[sym.name] = sym_id

        for file_path, file_summary in self._files.items():
            try:
                content = (self.root / file_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lines = content.split("\n")

            # For each symbol in this file, scan its body for references
            # to other symbols also in this file
            file_sym_ids = set(file_summary.symbols)
            for sym_id in file_sym_ids:
                if sym_id not in self._symbols:
                    continue
                sym = self._symbols[sym_id]
                start = sym.line_start - 1
                end = min(sym.line_end, len(lines))
                body = "\n".join(lines[start:end])

                # Check if any other same-file symbol name appears in this body
                for other_id in file_sym_ids:
                    if other_id == sym_id:
                        continue
                    other_sym = self._symbols[other_id]
                    # Use word-boundary check to avoid partial matches
                    if re.search(rf"\b{re.escape(other_sym.name)}\b", body):
                        if other_id not in sym.dependencies:
                            sym.dependencies.append(other_id)

    # ── Import Target Resolution ─────────────────────────────────

    def _resolve_import_target(self, imp_stmt: str, current_module: str) -> str | None:
        target = imp_stmt.strip()
        if target.startswith("*:"):
            module_name = target[2:]
            return self._resolve_import_target(module_name, current_module)
        if not target.startswith("."):
            return target
        dots = 0
        i = 0
        while i < len(target) and target[i] == ".":
            dots += 1
            i += 1
        relative_path = target[i:]
        parts = current_module.split(".")
        if len(parts) >= dots:
            base_parts = parts[:-dots] if dots > 0 else parts
        else:
            return None
        if relative_path:
            resolved = ".".join(base_parts + [relative_path]) if base_parts else relative_path
        else:
            resolved = ".".join(base_parts)
        return resolved or None

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_docstring(lines: list[str], start_idx: int, language: str) -> str:
        doc_lines: list[str] = []
        idx = start_idx + 1
        if idx >= len(lines):
            return ""
        line = lines[idx].strip()
        if language == ".py" and (line.startswith('"""') or line.startswith("'''")):
            quote = line[:3]
            doc_lines.append(line[len(quote):])
            idx += 1
            while idx < len(lines):
                line = lines[idx]
                if quote in line:
                    doc_lines.append(line[:line.index(quote)])
                    break
                doc_lines.append(line)
                idx += 1
        elif language in (".ts", ".tsx", ".js", ".jsx"):
            while idx < len(lines):
                line = lines[idx].strip()
                if line.startswith("/**"):
                    doc_lines.append(line[3:].rstrip("*/").strip())
                elif line.startswith("*") and not line.startswith("*/"):
                    doc_lines.append(line[1:].strip())
                elif line.startswith("///"):
                    doc_lines.append(line[3:].strip())
                elif line.startswith("*/"):
                    break
                else:
                    break
                idx += 1
        elif language == ".go":
            while idx < len(lines):
                line = lines[idx].strip()
                if line.startswith("//"):
                    doc_lines.append(line[2:].strip())
                else:
                    break
                idx += 1
        elif language == ".rs":
            while idx < len(lines):
                line = lines[idx].strip()
                if line.startswith("///"):
                    doc_lines.append(line[3:].strip())
                elif line.startswith("//!"):
                    doc_lines.append(line[3:].strip())
                else:
                    break
                idx += 1
        return "\n".join(doc_lines).strip()

    @staticmethod
    def _find_symbol_end(lines: list[str], start_idx: int, language: str) -> int:
        if start_idx >= len(lines):
            return start_idx + 1
        start_line = lines[start_idx] if start_idx < len(lines) else ""
        base_indent = len(start_line) - len(start_line.lstrip())
        brace_langs = {".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
        if language in brace_langs:
            brace_count = 0
            found_open = False
            for i in range(start_idx, min(start_idx + 500, len(lines))):
                line = lines[i]
                if "{" in line:
                    brace_count += line.count("{")
                    found_open = True
                if "}" in line:
                    brace_count -= line.count("}")
                if found_open and brace_count == 0:
                    return i + 1
            return start_idx + 1
        idx = start_idx + 1
        while idx < len(lines):
            line = lines[idx]
            if line.strip() == "":
                idx += 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            idx += 1
        return idx


def compute_file_hash(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()