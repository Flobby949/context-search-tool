from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from p4_exploration_identity import IMPLEMENTATION_BASELINE, ROOT


PROTECTED_ROOTS = (
    ROOT / "src/context_search_tool/retrieval.py",
    ROOT / "src/context_search_tool/retrieval_core",
    ROOT / "src/context_search_tool/context_pack",
)

ALLOWED_PRODUCTION_CHANGES = {
    "src/context_search_tool/retrieval_trace/exploration.py",
    "src/context_search_tool/retrieval_trace/__init__.py",
    "src/context_search_tool/formatters.py",
    "src/context_search_tool/cli.py",
    "src/context_search_tool/mcp_tools.py",
    "src/context_search_tool/mcp_server.py",
    "src/context_search_tool/quality/cases.py",
    "src/context_search_tool/quality/runner.py",
    "src/context_search_tool/quality/metrics.py",
    "src/context_search_tool/quality/aggregate.py",
    "src/context_search_tool/quality/reports.py",
    "src/context_search_tool/quality/compare.py",
}


def _python_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(sorted(root.rglob("*.py")))


def _imports_exploration(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == "context_search_tool.exploration"
                or alias.name.startswith("context_search_tool.exploration.")
                for alias in node.names
            ):
                return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "context_search_tool.exploration" or module.startswith(
                "context_search_tool.exploration."
            ):
                return True
            if module == "context_search_tool" and any(
                alias.name == "exploration" for alias in node.names
            ):
                return True
    return False


def _changed_production_paths() -> set[str]:
    tracked = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            IMPLEMENTATION_BASELINE,
            "--",
            "src/context_search_tool",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        (
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src/context_search_tool",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {*tracked, *untracked}


def test_protected_modules_have_no_exploration_import_edge() -> None:
    protected_files = tuple(
        path for root in PROTECTED_ROOTS for path in _python_files(root)
    )
    assert protected_files
    assert [
        str(path.relative_to(ROOT))
        for path in protected_files
        if _imports_exploration(path)
    ] == []


def test_only_reviewed_production_change_roots_are_used() -> None:
    unexpected = []
    for path in sorted(_changed_production_paths()):
        if path.startswith("src/context_search_tool/exploration/"):
            continue
        if path not in ALLOWED_PRODUCTION_CHANGES:
            unexpected.append(path)
    assert unexpected == []
