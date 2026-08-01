from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for the task venv
    tomllib = None  # type: ignore[assignment]

from context_search_tool.paths import ensure_index_layout, index_dir_for


@dataclass(frozen=True)
class IndexConfig:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_file_bytes: int = 500_000
    max_full_file_bytes: int = 200_000


@dataclass(frozen=True)
class RetrievalConfig:
    semantic_top_k: int = 80
    lexical_top_k: int = 80
    final_top_k: int = 12
    context_before_lines: int = 8
    context_after_lines: int = 12
    consume_dependency_hints: bool = False


@dataclass(frozen=True)
class ContextConfig:
    max_items: int = 12
    max_excerpts_per_item: int = 2
    max_excerpt_bytes: int = 4096
    max_item_content_bytes: int = 8192
    max_total_content_bytes: int = 49152
    max_pack_bytes: int = 65536


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "hash"
    model: str = "hash-v1"
    dimensions: int = 384
    base_url: str | None = None
    api_key_env: str | None = None

    @property
    def api_key(self) -> str | None:
        # Keep secrets outside dataclass fields so asdict/report payloads omit them.
        return getattr(self, "_api_key", None)


@dataclass(frozen=True)
class QueryPlannerConfig:
    enabled: bool = False
    provider: str = "ollama"
    model: str = "qwen3.5:4b-mlx"
    base_url: str = "http://localhost:11434"
    use_system_proxy: bool = False
    send_repo_profile: bool = True
    timeout_seconds: float = 8.0
    max_rewritten_queries: int = 4
    max_keywords: int = 12
    max_symbol_hints: int = 8

    @property
    def api_key(self) -> str | None:
        # Keep secrets outside dataclass fields so asdict/report payloads omit them.
        return getattr(self, "_api_key", None)


@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query_planner: QueryPlannerConfig = field(default_factory=QueryPlannerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


DEFAULT_CONFIG = ToolConfig()
PROJECT_CONFIG_TEMPLATE = (
    "# Project-specific overrides. Missing values inherit the user config "
    "and built-in defaults.\n"
)


def render_default_config() -> str:
    return render_config(DEFAULT_CONFIG)


def render_config(config: ToolConfig) -> str:
    embedding_lines = [
        f"provider = {_toml_string(config.embedding.provider)}",
        f"model = {_toml_string(config.embedding.model)}",
        f"dimensions = {config.embedding.dimensions}",
    ]
    if config.embedding.base_url is not None:
        embedding_lines.append(
            f"base_url = {_toml_string(config.embedding.base_url)}"
        )
    if config.embedding.api_key is not None:
        embedding_lines.append(
            f"api_key = {_toml_string(config.embedding.api_key)}"
        )
    if config.embedding.api_key_env is not None:
        embedding_lines.append(
            f"api_key_env = {_toml_string(config.embedding.api_key_env)}"
        )

    query_planner_lines = [
        f"enabled = {_toml_bool(config.query_planner.enabled)}",
        f"provider = {_toml_string(config.query_planner.provider)}",
        f"model = {_toml_string(config.query_planner.model)}",
        f"base_url = {_toml_string(config.query_planner.base_url)}",
    ]
    if config.query_planner.api_key is not None:
        query_planner_lines.append(
            f"api_key = {_toml_string(config.query_planner.api_key)}"
        )
    query_planner_lines.extend(
        [
            f"use_system_proxy = {_toml_bool(config.query_planner.use_system_proxy)}",
            f"send_repo_profile = {_toml_bool(config.query_planner.send_repo_profile)}",
            f"timeout_seconds = {config.query_planner.timeout_seconds}",
            f"max_rewritten_queries = {config.query_planner.max_rewritten_queries}",
            f"max_keywords = {config.query_planner.max_keywords}",
            f"max_symbol_hints = {config.query_planner.max_symbol_hints}",
        ]
    )

    return "\n".join(
        [
            "[index]",
            f"include = {_toml_list(config.index.include)}",
            f"exclude = {_toml_list(config.index.exclude)}",
            f"max_file_bytes = {config.index.max_file_bytes}",
            f"max_full_file_bytes = {config.index.max_full_file_bytes}",
            "",
            "[retrieval]",
            f"semantic_top_k = {config.retrieval.semantic_top_k}",
            f"lexical_top_k = {config.retrieval.lexical_top_k}",
            f"final_top_k = {config.retrieval.final_top_k}",
            f"context_before_lines = {config.retrieval.context_before_lines}",
            f"context_after_lines = {config.retrieval.context_after_lines}",
            f"consume_dependency_hints = {_toml_bool(config.retrieval.consume_dependency_hints)}",
            "",
            "[context]",
            f"max_items = {config.context.max_items}",
            f"max_excerpts_per_item = {config.context.max_excerpts_per_item}",
            f"max_excerpt_bytes = {config.context.max_excerpt_bytes}",
            f"max_item_content_bytes = {config.context.max_item_content_bytes}",
            f"max_total_content_bytes = {config.context.max_total_content_bytes}",
            f"max_pack_bytes = {config.context.max_pack_bytes}",
            "",
            "[embedding]",
            *embedding_lines,
            "",
            "[query_planner]",
            *query_planner_lines,
            "",
        ]
    )


def load_config(repo: Path) -> ToolConfig:
    config_path = index_dir_for(repo) / "config.toml"
    if not config_path.exists():
        global_path = global_config_path()
        global_values = _load_toml(global_path) if global_path.exists() else {}
        config_path = ensure_index_layout(repo) / "config.toml"
        config_path.write_text(PROJECT_CONFIG_TEMPLATE, encoding="utf-8")
        return _build_tool_config(global_values, {})

    return read_config(repo)


def read_config(repo: Path) -> ToolConfig:
    """Read persisted configuration without creating or modifying repository files."""
    config_path = index_dir_for(repo) / "config.toml"
    global_path = global_config_path()
    global_values = _load_toml(global_path) if global_path.exists() else {}
    project_values = _load_toml(config_path)
    return _build_tool_config(global_values, project_values)


def global_config_path() -> Path:
    override = os.environ.get("CST_GLOBAL_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return root / "context-search" / "config.toml"


def _build_tool_config(
    global_values: dict[str, Any],
    project_values: dict[str, Any],
) -> ToolConfig:
    return ToolConfig(
        index=_build_section(
            IndexConfig,
            _merged_section(global_values, project_values, "index"),
        ),
        retrieval=_build_section(
            RetrievalConfig,
            _merged_section(global_values, project_values, "retrieval"),
        ),
        embedding=_build_embedding_section(
            _merged_section(global_values, project_values, "embedding")
        ),
        query_planner=_build_query_planner_section(
            _merged_section(global_values, project_values, "query_planner")
        ),
        context=_build_section(
            ContextConfig,
            _merged_section(global_values, project_values, "context"),
        ),
    )


def replace_query_planner_config(
    config: QueryPlannerConfig,
    **changes: Any,
) -> QueryPlannerConfig:
    api_key = changes.pop("api_key", config.api_key)
    return _attach_query_planner_api_key(replace(config, **changes), api_key)


def replace_embedding_config(
    config: EmbeddingConfig,
    **changes: Any,
) -> EmbeddingConfig:
    api_key = changes.pop("api_key", config.api_key)
    return _attach_embedding_api_key(replace(config, **changes), api_key)


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is not None:
        with path.open("rb") as config_file:
            return tomllib.load(config_file)
    return _parse_simple_toml(path.read_text(encoding="utf-8"))


def _merged_section(
    global_values: dict[str, Any],
    project_values: dict[str, Any],
    section_name: str,
) -> dict[str, Any]:
    inherited = global_values.get(section_name, {})
    overrides = project_values.get(section_name, {})
    if not isinstance(inherited, dict) or not isinstance(overrides, dict):
        raise ValueError("configuration sections must be TOML tables")
    return {**inherited, **overrides}


def _build_section(config_type: type[Any], values: dict[str, Any]) -> Any:
    if not isinstance(values, dict):
        raise ValueError("configuration sections must be TOML tables")
    allowed = set(config_type.__dataclass_fields__)
    return config_type(**{key: value for key, value in values.items() if key in allowed})


def _build_query_planner_section(values: dict[str, Any]) -> QueryPlannerConfig:
    if not isinstance(values, dict):
        raise ValueError("configuration sections must be TOML tables")
    public_values = dict(values)
    api_key = public_values.pop("api_key", None)
    config = _build_section(QueryPlannerConfig, public_values)
    return _attach_query_planner_api_key(config, api_key)


def _build_embedding_section(values: dict[str, Any]) -> EmbeddingConfig:
    if not isinstance(values, dict):
        raise ValueError("configuration sections must be TOML tables")
    public_values = dict(values)
    api_key = public_values.pop("api_key", None)
    config = _build_section(EmbeddingConfig, public_values)
    return _attach_embedding_api_key(config, api_key)


def _attach_query_planner_api_key(
    config: QueryPlannerConfig,
    api_key: object,
) -> QueryPlannerConfig:
    if api_key is not None and (type(api_key) is not str or not api_key):
        raise ValueError("query_planner.api_key must be a non-empty string")
    object.__setattr__(config, "_api_key", api_key)
    return config


def _attach_embedding_api_key(
    config: EmbeddingConfig,
    api_key: object,
) -> EmbeddingConfig:
    if api_key is not None and (type(api_key) is not str or not api_key):
        raise ValueError("embedding.api_key must be a non-empty string")
    object.__setattr__(config, "_api_key", api_key)
    return config


def _parse_simple_toml(content: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = data.setdefault(line[1:-1], {})
            continue
        if section is None or "=" not in line:
            continue
        key, raw_value = [part.strip() for part in line.split("=", 1)]
        section[key] = _parse_simple_toml_value(raw_value)

    return data


def _parse_simple_toml_value(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_simple_toml_value(item.strip()) for item in inner.split(",")]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _toml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return f"[{', '.join(_toml_string(value) for value in values)}]"


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"
