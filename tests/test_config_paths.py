from pathlib import Path

import pytest

from context_search_tool import config as config_module
from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    QueryPlannerConfig,
    ToolConfig,
    load_config,
    render_config,
    render_default_config,
)
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
    ensure_index_layout,
)


def test_render_default_config_contains_version_one_values() -> None:
    rendered = render_default_config()
    assert "max_file_bytes = 500000" in rendered
    assert "max_full_file_bytes = 200000" in rendered
    assert "semantic_top_k = 80" in rendered
    assert DEFAULT_CONFIG.embedding.provider == "hash"


def test_render_default_config_contains_query_planner_defaults() -> None:
    rendered = render_default_config()

    assert "[query_planner]" in rendered
    assert "enabled = false" in rendered
    assert 'provider = "ollama"' in rendered
    assert 'model = "qwen3.5:4b-mlx"' in rendered
    assert 'base_url = "http://localhost:11434"' in rendered
    assert "use_system_proxy = false" in rendered
    assert "timeout_seconds = 8.0" in rendered
    assert "max_rewritten_queries = 4" in rendered
    assert "max_keywords = 12" in rendered
    assert "max_symbol_hints = 8" in rendered
    assert DEFAULT_CONFIG.query_planner.enabled is False


def test_render_config_uses_passed_embedding_values() -> None:
    rendered = render_config(
        ToolConfig(
            embedding=EmbeddingConfig(
                provider="hash",
                model="hash-v2",
                dimensions=128,
            )
        )
    )

    assert 'provider = "hash"' in rendered
    assert 'model = "hash-v2"' in rendered
    assert "dimensions = 128" in rendered


def test_load_config_reads_query_planner_section(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)
    (repo / ".context-search" / "config.toml").write_text(
        """
[query_planner]
enabled = true
provider = "ollama"
model = "qwen3.5:4b-mlx"
base_url = "http://localhost:11434"
use_system_proxy = true
timeout_seconds = 2.5
max_rewritten_queries = 3
max_keywords = 9
max_symbol_hints = 5
""".lstrip(),
        encoding="utf-8",
    )

    config = load_config(repo)

    assert config.query_planner.enabled is True
    assert config.query_planner.provider == "ollama"
    assert config.query_planner.model == "qwen3.5:4b-mlx"
    assert config.query_planner.base_url == "http://localhost:11434"
    assert config.query_planner.use_system_proxy is True
    assert config.query_planner.timeout_seconds == 2.5
    assert config.query_planner.max_rewritten_queries == 3
    assert config.query_planner.max_keywords == 9
    assert config.query_planner.max_symbol_hints == 5


def test_render_default_config_places_exact_context_block_after_retrieval() -> None:
    rendered = render_default_config()

    assert """[retrieval]
semantic_top_k = 80
lexical_top_k = 80
final_top_k = 12
context_before_lines = 8
context_after_lines = 12

[context]
max_items = 12
max_excerpts_per_item = 2
max_excerpt_bytes = 4096
max_item_content_bytes = 8192
max_total_content_bytes = 49152
max_pack_bytes = 65536

[embedding]
""" in rendered


def test_context_config_render_load_round_trip_ignores_unknown_keys(
    tmp_path: Path,
) -> None:
    context_config_type = getattr(config_module, "ContextConfig")
    expected = context_config_type(
        max_items=7,
        max_excerpts_per_item=3,
        max_excerpt_bytes=1024,
        max_item_content_bytes=4096,
        max_total_content_bytes=16_384,
        max_pack_bytes=32_768,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)
    rendered = render_config(ToolConfig(context=expected))
    (repo / ".context-search" / "config.toml").write_text(
        rendered.replace(
            "max_pack_bytes = 32768",
            "max_pack_bytes = 32768\nfuture_context_option = 99",
        ),
        encoding="utf-8",
    )

    loaded = load_config(repo)

    assert loaded.context == expected


def test_render_config_uses_passed_query_planner_values() -> None:
    rendered = render_config(
        ToolConfig(
            query_planner=QueryPlannerConfig(
                enabled=True,
                provider="ollama",
                model="custom-model",
                base_url="http://127.0.0.1:11434",
                use_system_proxy=True,
                timeout_seconds=1.5,
                max_rewritten_queries=2,
                max_keywords=6,
                max_symbol_hints=4,
            )
        )
    )

    assert "enabled = true" in rendered
    assert 'model = "custom-model"' in rendered
    assert 'base_url = "http://127.0.0.1:11434"' in rendered
    assert "use_system_proxy = true" in rendered
    assert "timeout_seconds = 1.5" in rendered
    assert "max_rewritten_queries = 2" in rendered
    assert "max_keywords = 6" in rendered
    assert "max_symbol_hints = 4" in rendered


def test_load_config_creates_default_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)

    config = load_config(repo)

    assert config.index.max_file_bytes == 500000
    assert (repo / ".context-search" / "config.toml").exists()


def test_ensure_index_layout_creates_gitignore_entry_when_missing(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    ensure_index_layout(repo)

    assert (repo / ".gitignore").read_text(encoding="utf-8") == ".context-search/\n"


def test_ensure_index_layout_appends_gitignore_entry_to_existing_file(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("dist/", encoding="utf-8")

    ensure_index_layout(repo)

    assert (repo / ".gitignore").read_text(encoding="utf-8") == (
        "dist/\n.context-search/\n"
    )


def test_ensure_index_layout_does_not_duplicate_gitignore_entry(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text(".context-search/\n", encoding="utf-8")

    ensure_index_layout(repo)
    ensure_index_layout(repo)

    assert (repo / ".gitignore").read_text(encoding="utf-8") == ".context-search/\n"


def test_find_repo_root_prefers_existing_index_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    child = repo / "src" / "main"
    child.mkdir(parents=True)
    ensure_index_layout(repo)
    monkeypatch.chdir(child)

    assert find_repo_root(None) == repo


def test_find_repo_root_uses_explicit_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert find_repo_root(repo) == repo
    assert index_dir_for(repo) == repo / ".context-search"


def test_find_repo_root_errors_when_cwd_has_no_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RepositoryNotFoundError):
        find_repo_root(None)
