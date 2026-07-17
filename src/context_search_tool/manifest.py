from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.paths import (
    atomic_write_index_bytes,
    ensure_index_layout,
    index_dir_for,
)


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Manifest:
    schema_version: int = SCHEMA_VERSION
    embedding_config_hash: str = ""
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 0
    total_files: int = 0
    total_chunks: int = 0


def manifest_path(repo: Path) -> Path:
    return index_dir_for(repo) / "manifest.json"


def load_manifest(repo: Path) -> Manifest:
    data = json.loads(manifest_path(repo).read_text(encoding="utf-8"))
    return _manifest_from_dict(data)


def write_manifest(repo: Path, manifest: Manifest) -> None:
    path = ensure_index_layout(repo) / "manifest.json"
    path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_manifest_v5(
    repo: Path,
    manifest: Manifest,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    payload = (
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write_index_bytes(
        manifest_path(repo),
        payload,
        fault_prefix="manifest",
        fault_hook=fault_hook,
    )


def embedding_config_hash(config: EmbeddingConfig) -> str:
    payload = {
        "base_url": config.base_url,
        "dimensions": config.dimensions,
        "model": config.model,
        "provider": config.provider,
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def assert_manifest_compatible(repo: Path, config: ToolConfig) -> None:
    path = manifest_path(repo)
    if not path.exists():
        return

    manifest = load_manifest(repo)
    if manifest.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"incompatible manifest schema version: {manifest.schema_version}"
        )

    expected_hash = embedding_config_hash(config.embedding)
    if manifest.embedding_config_hash != expected_hash:
        raise ValueError("incompatible embedding configuration for existing index")


def _manifest_from_dict(data: dict[str, Any]) -> Manifest:
    return Manifest(
        schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        embedding_config_hash=str(data.get("embedding_config_hash", "")),
        embedding_provider=str(data.get("embedding_provider", "")),
        embedding_model=str(data.get("embedding_model", "")),
        embedding_dimensions=int(data.get("embedding_dimensions", 0)),
        total_files=int(data.get("total_files", 0)),
        total_chunks=int(data.get("total_chunks", 0)),
    )
