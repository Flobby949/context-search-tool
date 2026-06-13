from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for the task venv
    tomllib = None  # type: ignore[assignment]

from context_search_tool.paths import ensure_index_layout


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


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "hash"
    model: str = "hash-v1"
    dimensions: int = 384
    base_url: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class ToolConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


DEFAULT_CONFIG = ToolConfig()


def render_default_config() -> str:
    return """[index]
include = []
exclude = []
max_file_bytes = 500000
max_full_file_bytes = 200000

[retrieval]
semantic_top_k = 80
lexical_top_k = 80
final_top_k = 12
context_before_lines = 8
context_after_lines = 12

[embedding]
provider = "hash"
model = "hash-v1"
dimensions = 384
"""


def load_config(repo: Path) -> ToolConfig:
    config_path = ensure_index_layout(repo) / "config.toml"
    if not config_path.exists():
        config_path.write_text(render_default_config(), encoding="utf-8")
        return DEFAULT_CONFIG

    data = _load_toml(config_path)
    return ToolConfig(
        index=_build_section(IndexConfig, data.get("index", {})),
        retrieval=_build_section(RetrievalConfig, data.get("retrieval", {})),
        embedding=_build_section(EmbeddingConfig, data.get("embedding", {})),
    )


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is not None:
        with path.open("rb") as config_file:
            return tomllib.load(config_file)
    return _parse_simple_toml(path.read_text(encoding="utf-8"))


def _build_section(config_type: type[Any], values: dict[str, Any]) -> Any:
    allowed = set(config_type.__dataclass_fields__)
    return config_type(**{key: value for key, value in values.items() if key in allowed})


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
    return int(value)
