from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from p4_exploration_identity import IMPLEMENTATION_BASELINE, ROOT


PROTECTED_ROOTS = (
    ROOT / "src/context_search_tool/retrieval.py",
    ROOT / "src/context_search_tool/retrieval_core",
    ROOT / "src/context_search_tool/context_pack",
)

CONSUMER_MODULES = (
    ROOT / "src/context_search_tool/formatters.py",
    ROOT / "src/context_search_tool/cli.py",
    ROOT / "src/context_search_tool/mcp_tools.py",
    ROOT / "src/context_search_tool/mcp_server.py",
    ROOT / "src/context_search_tool/quality/runner.py",
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


def test_consumer_modules_have_no_module_scope_exploration_imports() -> None:
    offenders: list[str] = []
    allowed_functions = {
        "cli.py": {"explore"},
        "mcp_tools.py": {"context_search_explore_tool"},
        "quality/runner.py": set(),
    }
    for path in CONSUMER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = str(path.relative_to(ROOT))

        class ImportScopeVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.functions: list[str] = []
                self.type_checking_depth = 0

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self.functions.append(node.name)
                self.generic_visit(node)
                self.functions.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_If(self, node: ast.If) -> None:
                is_type_checking = isinstance(node.test, ast.Name) and (
                    node.test.id == "TYPE_CHECKING"
                )
                self.type_checking_depth += int(is_type_checking)
                for child in node.body:
                    self.visit(child)
                self.type_checking_depth -= int(is_type_checking)
                for child in node.orelse:
                    self.visit(child)

            def visit_Import(self, node: ast.Import) -> None:
                self._check(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                self._check(node)

            def _check(self, node: ast.Import | ast.ImportFrom) -> None:
                if not _node_imports_exploration(node):
                    return
                if self.type_checking_depth:
                    return
                function = self.functions[-1] if self.functions else None
                suffix = (
                    "quality/runner.py"
                    if relative.endswith("quality/runner.py")
                    else path.name
                )
                if function not in allowed_functions.get(suffix, set()):
                    offenders.append(f"{relative}:{getattr(node, 'lineno', 0)}")

        ImportScopeVisitor().visit(tree)
    assert offenders == []


def test_ordinary_surfaces_do_not_load_exploration_runner_in_fresh_process() -> None:
    script = r'''
import json
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app
from context_search_tool.config import load_config
from context_search_tool.indexer import index_repository
from context_search_tool.mcp_tools import (
    context_search_context_tool,
    context_search_query_tool,
    context_search_trace_tool,
)
from context_search_tool.retrieval import query_repository, trace_repository
import context_search_tool.formatters
import context_search_tool.mcp_server
import context_search_tool.quality.runner

runner_module = "context_search_tool.exploration.runner"
assert runner_module not in sys.modules
with tempfile.TemporaryDirectory() as raw:
    repo = Path(raw) / "repo"
    repo.mkdir()
    (repo / "AppController.py").write_text(
        "class AppController:\n    pass\n",
        encoding="utf-8",
    )
    config = load_config(repo)
    index_repository(repo, config)
    assert query_repository(repo, "AppController", config).results
    assert trace_repository(repo, "AppController", config).trace.schema_version == 1
    assert context_search_query_tool(str(repo), "AppController")["ok"] is True
    assert context_search_trace_tool(str(repo), "AppController")["ok"] is True
    assert context_search_context_tool(str(repo), "AppController")["ok"] is True
    cli = CliRunner()
    for command in ("query", "trace", "context"):
        result = cli.invoke(app, [command, str(repo), "AppController", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["ok"] is True if command != "query" else True
    assert runner_module not in sys.modules
print("isolated")
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        (sys.executable, "-c", script),
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "isolated"


def _node_imports_exploration(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.Import):
        return any(
            alias.name == "context_search_tool.exploration"
            or alias.name.startswith("context_search_tool.exploration.")
            for alias in node.names
        )
    module = node.module or ""
    return (
        module == "context_search_tool.exploration"
        or module.startswith("context_search_tool.exploration.")
        or module == "context_search_tool"
        and any(alias.name == "exploration" for alias in node.names)
    )
