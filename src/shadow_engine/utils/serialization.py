"""Centralized JSON serialization helpers for shadow-engine.

Eliminates duplicated _datetime_encoder / _datetime_decoder across the codebase.
Handles datetime, Path, Enum, and other common non-serializable types.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def json_dumps(obj: Any, indent: int | None = None) -> str:
    """Serialize any object to JSON with datetime/Path/Enum support."""
    return json.dumps(obj, default=_default_encoder, indent=indent)


def json_loads(s: str) -> Any:
    """Parse JSON string."""
    return json.loads(s)


def safe_json_load(path: str | Path, default: Any = None) -> Any:
    """Read and parse a JSON file, returning `default` on any error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def safe_json_dump(path: str | Path, obj: Any, indent: int = 2) -> bool:
    """Write object to a JSON file atomically (tmp → rename). Returns success."""
    try:
        file_path = Path(path)
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp_path.write_text(json_dumps(obj, indent=indent), encoding="utf-8")
        tmp_path.replace(file_path)
        return True
    except Exception:
        return False


def _default_encoder(obj: Any) -> Any:
    """JSON encoder for non-serializable types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def parse_iso_datetime(s: str | None) -> datetime | None:
    """Parse an ISO-format datetime string, returning None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def utc_now() -> datetime:
    """Current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)