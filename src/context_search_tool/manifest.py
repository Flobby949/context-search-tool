from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from typing import Any, Callable

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.paths import (
    atomic_write_index_bytes,
    ensure_index_layout,
    index_dir_for,
)


SCHEMA_VERSION = 1
READABLE_MANIFEST_VERSIONS = frozenset({1, 2})
MAX_RAW_MANIFEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class Manifest:
    schema_version: int = SCHEMA_VERSION
    embedding_config_hash: str = ""
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 0
    total_files: int = 0
    total_chunks: int = 0


@dataclass(frozen=True)
class RawManifestSchema:
    status: Literal["missing", "valid", "invalid"]
    version: int | None
    error_code: str | None


def manifest_path(repo: Path) -> Path:
    return index_dir_for(repo) / "manifest.json"


def inspect_raw_manifest_schema(
    repo: Path,
    *,
    max_bytes: int = MAX_RAW_MANIFEST_BYTES,
) -> RawManifestSchema:
    if max_bytes < 1:
        raise ValueError("raw manifest byte limit must be positive")
    path = manifest_path(repo)
    if not os.path.lexists(path):
        return RawManifestSchema("missing", None, "missing_manifest")
    descriptor: int | None = None
    try:
        path_stat = os.lstat(path)
        if path.is_symlink() or not stat.S_ISREG(path_stat.st_mode):
            return RawManifestSchema("invalid", None, "unsafe_manifest")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            return RawManifestSchema("invalid", None, "manifest_too_large")
        content = bytearray()
        while len(content) <= max_bytes:
            block = os.read(descriptor, min(16 * 1024, max_bytes + 1 - len(content)))
            if not block:
                break
            content.extend(block)
        after = os.fstat(descriptor)
    except OSError:
        return RawManifestSchema("invalid", None, "unreadable_manifest")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(content) > max_bytes:
        return RawManifestSchema("invalid", None, "manifest_too_large")
    try:
        final_stat = os.lstat(path)
    except OSError:
        return RawManifestSchema("invalid", None, "manifest_changed")
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (
            final_stat.st_dev,
            final_stat.st_ino,
            final_stat.st_size,
            final_stat.st_mtime_ns,
        )
        or len(content) != after.st_size
    ):
        return RawManifestSchema("invalid", None, "manifest_changed")
    try:
        data = json.loads(
            bytes(content).decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return RawManifestSchema("invalid", None, "malformed_manifest")
    if not isinstance(data, dict):
        return RawManifestSchema("invalid", None, "invalid_manifest_schema")
    raw_version = data.get("schema_version")
    if type(raw_version) is not int or raw_version < 0:
        return RawManifestSchema("invalid", None, "invalid_manifest_schema")
    return RawManifestSchema("valid", raw_version, None)


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
