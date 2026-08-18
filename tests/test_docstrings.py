"""Enforce project-wide NumPy-style documentation coverage."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_FILES = [
    *sorted(Path("zulip_hermes").glob("*.py")),
    Path("main.py"),
    Path("zulip_mcp.py"),
    Path("zulip_hermes_bot.py"),
    Path("zulip_query.py"),
]


def test_every_module_function_method_and_class_has_a_docstring() -> None:
    """Require docstrings on all source definitions."""
    missing: list[str] = []

    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not ast.get_docstring(tree):
            missing.append(f"{path}: module")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(node):
                missing.append(f"{path}:{node.lineno}: {node.name}")

    assert not missing, "Missing docstrings:\n" + "\n".join(missing)


def test_multiline_docstrings_use_numpy_section_underlines() -> None:
    """Require standard NumPy section underlines where sections are used."""
    section_names = {"Parameters", "Returns", "Raises", "Attributes", "Notes"}
    invalid: list[str] = []

    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        documentable = [
            tree,
            *(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ),
        ]
        for node in documentable:
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            lines = docstring.splitlines()
            for index, line in enumerate(lines):
                if line.strip() in section_names:
                    if index + 1 >= len(lines) or set(lines[index + 1].strip()) != {"-"}:
                        name = getattr(node, "name", "module")
                        invalid.append(f"{path}: {name}: {line.strip()}")

    assert not invalid, "Invalid NumPy docstring sections:\n" + "\n".join(invalid)
