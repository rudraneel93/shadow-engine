"""Shared pytest fixtures for shadow-engine tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def test_repo_path():
    """Path to a temporary test repository."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "test_repo"
        repo.mkdir()
        # Create a minimal Python project
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "__init__.py").write_text("")
        (repo / "src" / "math_utils.py").write_text(
            '"""Math utilities for testing."""\n\n'
            "def add(a: int, b: int) -> int:\n"
            '    """Add two integers."""\n'
            "    return a + b\n\n"
            "def multiply(a: int, b: int) -> int:\n"
            '    """Multiply two integers."""\n'
            "    return a * b\n"
        )
        (repo / "tests").mkdir(exist_ok=True)
        (repo / "tests" / "__init__.py").write_text("")
        (repo / "tests" / "test_math.py").write_text(
            "from src.math_utils import add, multiply\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n\n"
            "def test_multiply():\n"
            "    assert multiply(4, 5) == 20\n"
        )
        yield str(repo)


@pytest.fixture(scope="session")
def shadow_engine_root():
    """Path to the shadow-engine project root."""
    return str(Path(__file__).resolve().parent.parent)


@pytest.fixture(autouse=True)
def enable_experimental():
    """Enable experimental engines for all tests."""
    os.environ["SHADOW_EXPERIMENTAL"] = "1"
    yield