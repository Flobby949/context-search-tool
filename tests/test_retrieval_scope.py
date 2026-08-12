import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from context_search_tool.cli import app
from context_search_tool.config import load_config
from context_search_tool.indexer import index_repository
from context_search_tool.mcp_tools import context_search_query_tool
from context_search_tool.retrieval import query_repository
from context_search_tool.retrieval_scope import RetrievalScope


def test_retrieval_scope_defaults_are_inactive_and_match_everything() -> None:
    scope = RetrievalScope()

    assert scope.is_active is False
    assert scope.matches(Path("docs/architecture.md"), "markdown") is True


def test_retrieval_scope_combines_include_exclude_language_and_code_filters() -> None:
    scope = RetrievalScope(
        include_paths=("src/",),
        exclude_paths=("src/generated/",),
        languages=("PYTHON", "typescript"),
        code_only=True,
    )

    assert scope.matches(Path("src/service.py"), "python") is True
    assert scope.matches(Path("src/view.ts"), "typescript") is True
    assert scope.matches(Path("src/generated/service.py"), "python") is False
    assert scope.matches(Path("tests/service.py"), "python") is False
    assert scope.matches(Path("src/service.go"), "go") is False
    assert scope.matches(Path("src/readme.md"), "markdown") is False


def test_retrieval_scope_preserves_leading_dot_in_repository_paths() -> None:
    scope = RetrievalScope(include_paths=(".github/",), languages=("yaml",))

    assert scope.matches(Path(".github/workflows/ci.yaml"), "yaml") is True
    assert scope.matches(Path("github/workflows/ci.yaml"), "yaml") is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("include_paths", ("/absolute/**",)),
        ("include_paths", ("../outside/**",)),
        ("exclude_paths", (r"src\\generated\\**",)),
        ("languages", ("python/3",)),
    ],
)
def test_retrieval_scope_rejects_unsafe_or_ambiguous_values(
    field: str,
    value: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match=field):
        RetrievalScope(**{field: value})


def test_code_only_keeps_tests_and_templates_but_rejects_non_code_artifacts() -> None:
    scope = RetrievalScope(code_only=True)

    assert scope.matches(Path("tests/test_service.py"), "python") is True
    assert scope.matches(Path("web/App.vue"), "vue") is True
    assert scope.matches(Path("schema/api.graphql"), "graphql") is True
    assert scope.matches(Path("docs/README.md"), "markdown") is False
    assert scope.matches(Path("config/app.yaml"), "yaml") is False
    assert scope.matches(Path("package-lock.json"), "lockfile") is False


def test_query_repository_applies_scope_as_a_hard_result_boundary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    files = {
        "src/service.py": "def shared_scope_sentinel():\n    return 'source'\n",
        "src/generated/service.py": (
            "def shared_scope_sentinel():\n    return 'generated'\n"
        ),
        "web/service.ts": "export function shared_scope_sentinel() { return 1 }\n",
        "docs/service.md": "# shared_scope_sentinel\n",
    }
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    index_repository(repo)

    bundle = query_repository(
        repo,
        "shared_scope_sentinel",
        load_config(repo),
        scope=RetrievalScope(
            include_paths=("src/",),
            exclude_paths=("src/generated/",),
            languages=("python",),
            code_only=True,
        ),
    )

    assert bundle.results
    assert {result.file_path.as_posix() for result in bundle.results} == {
        "src/service.py"
    }
    assert {
        anchor.file_path.as_posix() for anchor in bundle.evidence_anchors
    } <= {"src/service.py"}


def test_inactive_scope_preserves_default_query_behavior(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "def inactive_scope_sentinel():\n    return True\n",
        encoding="utf-8",
    )
    index_repository(repo)
    config = load_config(repo)

    baseline = query_repository(repo, "inactive_scope_sentinel", config)
    scoped = query_repository(
        repo,
        "inactive_scope_sentinel",
        config,
        scope=RetrievalScope(),
    )

    assert scoped == baseline


def test_scope_filters_graph_expansion_targets_outside_allowed_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    controller = repo / "src/ScopedController.java"
    service = repo / "internal/ScopedService.java"
    controller.parent.mkdir(parents=True)
    service.parent.mkdir(parents=True)
    controller.write_text(
        "class ScopedController { void handle() { new ScopedService().run(); } }\n",
        encoding="utf-8",
    )
    service.write_text(
        "class ScopedService { void run() {} }\n",
        encoding="utf-8",
    )
    index_repository(repo)

    bundle = query_repository(
        repo,
        "ScopedController handle",
        load_config(repo),
        scope=RetrievalScope(include_paths=("src/",)),
    )

    assert bundle.results
    assert {result.file_path.as_posix() for result in bundle.results} == {
        "src/ScopedController.java"
    }
    assert {
        anchor.file_path.as_posix() for anchor in bundle.evidence_anchors
    } <= {"src/ScopedController.java"}


def test_scope_also_bounds_the_repository_profile_sent_to_planner(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    for relative, content in {
        "src/public_service.py": "class PublicService:\n    pass\n",
        "excluded/SecretFramework.py": "class SecretFramework:\n    pass\n",
    }.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    index_repository(repo)

    class CapturingPlanner:
        profile = None

        def plan(self, query: str, repo_profile=None):
            self.profile = repo_profile
            from context_search_tool.models import QueryPlan

            return QueryPlan(original_query=query, status="ok")

    planner = CapturingPlanner()
    query_repository(
        repo,
        "where is the secret framework",
        load_config(repo),
        planner=planner,
        scope=RetrievalScope(include_paths=("src/",)),
    )

    assert planner.profile is not None
    serialized = repr(planner.profile).lower()
    assert "public_service" in serialized
    assert "secretframework" not in serialized
    assert "excluded" not in serialized


def test_cli_query_accepts_repeatable_scope_options(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for relative in ("src/first.py", "src/generated/second.py", "web/third.ts"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "def cli_scope_sentinel():\n    return True\n",
            encoding="utf-8",
        )
    index_repository(repo)

    result = CliRunner().invoke(
        app,
        [
            "query",
            str(repo),
            "cli_scope_sentinel",
            "--json",
            "--include-path",
            "src/",
            "--exclude-path",
            "src/generated/",
            "--language",
            "python",
            "--code-only",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {item["file_path"] for item in payload["results"]} == {
        "src/first.py"
    }


def test_mcp_query_scope_and_invalid_scope_are_stable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for relative in ("src/first.py", "docs/first.md"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mcp_scope_sentinel\n", encoding="utf-8")
    index_repository(repo)

    payload = context_search_query_tool(
        str(repo),
        "mcp_scope_sentinel",
        include_paths=["src/"],
        languages=["python"],
        code_only=True,
    )
    invalid = context_search_query_tool(
        str(repo),
        "mcp_scope_sentinel",
        include_paths=["../outside/**"],
    )

    assert payload["ok"] is True
    assert {item["file_path"] for item in payload["results"]} == {
        "src/first.py"
    }
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "query_failed"
    assert "include_paths" in invalid["error"]["message"]
