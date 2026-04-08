"""
Property 18: Legacy module zero-reference invariant.

Validates: Requirements 13.6

For any removed Legacy_Files module, the codebase SHALL contain zero import
statements referencing the removed module path.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# Patterns that must NOT appear in any Python source file.
LEGACY_IMPORT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"from\s+backend\.services\.chunker\b"),
    re.compile(r"from\s+backend\.services\.rag_service\b"),
    re.compile(r"from\s+backend\.services\.embedding_service\b"),
    re.compile(r"from\s+backend\.agents\._base_agent\b"),
]

# Root of the backend package (two levels up from this test file).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Directories to skip during scanning.
_SKIP_DIRS = {"__pycache__", ".git", ".hypothesis", "node_modules", ".kiro"}


def _python_files() -> list[Path]:
    """Collect all .py files under the backend/ tree."""
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(_BACKEND_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                result.append(Path(dirpath) / fname)
    return result


@pytest.mark.parametrize(
    "pattern",
    LEGACY_IMPORT_PATTERNS,
    ids=[p.pattern for p in LEGACY_IMPORT_PATTERNS],
)
def test_property_18_zero_references_to_legacy_modules(pattern: re.Pattern[str]) -> None:
    """No Python file under backend/ may import a removed legacy module."""
    violations: list[str] = []
    for py_file in _python_files():
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = py_file.relative_to(_BACKEND_ROOT)
                violations.append(f"  {rel}:{lineno}: {line.strip()}")

    assert not violations, (
        f"Found {len(violations)} import(s) matching /{pattern.pattern}/:\n"
        + "\n".join(violations)
    )
