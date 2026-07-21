from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal
from typing import Any, Callable

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.paths import (
    atomic_write_index_bytes,
    ensure_index_layout,
    index_dir_for,
    prepare_index_directory,
)


SCHEMA_VERSION = 1
READABLE_MANIFEST_VERSIONS = frozenset({1, 2})
WRITE_MANIFEST_VERSION = 2
MAX_RAW_MANIFEST_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GENERATION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_WORK_METRIC_RE = re.compile(r"[a-z][a-z0-9_.]*\Z")
_OPERATION_MODES = frozenset({"index", "authoritative_index", "quick_refresh"})
_WORK_STRING_METRICS = {
    "vector.descriptor_action": frozenset({"reused", "published"}),
}
_MAX_WORK_METRICS = 128


class IncompatibleManifestSchemaError(RuntimeError):
    code = "incompatible_manifest_schema"

    def __init__(self, stored_version: object) -> None:
        self.stored_version = stored_version
        super().__init__(f"incompatible manifest schema {stored_version}")


class ManifestCorruptionError(ValueError):
    code = "manifest_corrupt"


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
class ManifestV2:
    embedding_config_hash: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    index_config_hash: str
    source_content_fingerprint: str
    source_observation_fingerprint: str
    observation_generation: int
    manifest_generation: str
    vector_descriptor_schema_version: int
    vector_generation: str
    vector_descriptor_sha256: str
    vector_bytes: int
    vector_ids_bytes: int
    indexed_at_epoch_s: int
    operational_schema_version: int
    operation_mode: str
    work_metrics: tuple[tuple[str, int | str], ...]
    total_files: int
    total_chunks: int
    schema_version: int = WRITE_MANIFEST_VERSION


@dataclass(frozen=True)
class PreparedManifestV2:
    manifest: ManifestV2
    payload: bytes
    sha256: str

    @property
    def byte_size(self) -> int:
        return len(self.payload)


@dataclass(frozen=True)
class LoadedManifestSnapshot:
    manifest: Manifest | ManifestV2
    payload: bytes
    sha256: str
    byte_size: int


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


def load_manifest(repo: Path) -> Manifest | ManifestV2:
    try:
        data = json.loads(
            manifest_path(repo).read_text(encoding="utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ManifestCorruptionError("malformed manifest") from error
    return _decode_manifest(data)


def load_manifest_snapshot(repo: Path) -> LoadedManifestSnapshot:
    payload = _read_manifest_payload(manifest_path(repo))
    try:
        data = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ManifestCorruptionError("malformed manifest") from error
    manifest = _decode_manifest(data)
    return LoadedManifestSnapshot(
        manifest=manifest,
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


def _decode_manifest(data: object) -> Manifest | ManifestV2:
    if not isinstance(data, dict):
        raise ManifestCorruptionError("invalid manifest schema")
    raw_version = data.get("schema_version")
    if type(raw_version) is not int or raw_version < 0:
        raise ManifestCorruptionError("invalid manifest schema version")
    if raw_version not in READABLE_MANIFEST_VERSIONS:
        raise IncompatibleManifestSchemaError(raw_version)
    if raw_version == 1:
        try:
            return _manifest_from_dict(data)
        except (TypeError, ValueError) as error:
            raise ManifestCorruptionError("invalid manifest v1") from error
    return _manifest_v2_from_dict(data)


def write_manifest(repo: Path, manifest: Manifest) -> None:
    _require_legacy_manifest(manifest)
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
    _require_legacy_manifest(manifest)
    payload = (
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write_index_bytes(
        manifest_path(repo),
        payload,
        fault_prefix="manifest",
        fault_hook=fault_hook,
    )


def _require_legacy_manifest(manifest: Manifest) -> None:
    if type(manifest) is not Manifest or manifest.schema_version != SCHEMA_VERSION:
        raise ValueError("public manifest writer only supports schema v1")


def prepare_manifest_v2(manifest: ManifestV2) -> PreparedManifestV2:
    normalized = replace(
        manifest,
        work_metrics=_normalize_work_metrics(manifest.work_metrics),
    )
    _validate_manifest_v2(normalized)
    payload = (
        json.dumps(
            _manifest_v2_dict(normalized),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return PreparedManifestV2(
        manifest=normalized,
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def publish_manifest_v2(
    repo: Path,
    prepared: PreparedManifestV2,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    checked = prepare_manifest_v2(prepared.manifest)
    if checked.payload != prepared.payload or checked.sha256 != prepared.sha256:
        raise ManifestCorruptionError("prepared manifest identity mismatch")
    prepare_index_directory(repo)
    atomic_write_index_bytes(
        manifest_path(repo),
        prepared.payload,
        fault_prefix="manifest_v2",
        fault_hook=fault_hook,
    )
    loaded = load_manifest_snapshot(repo)
    if loaded.manifest != prepared.manifest or loaded.sha256 != prepared.sha256:
        raise ManifestCorruptionError("published manifest identity mismatch")


def embedding_config_hash(config: EmbeddingConfig) -> str:
    payload = {
        "base_url": config.base_url,
        "dimensions": config.dimensions,
        "model": config.model,
        "provider": config.provider,
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def index_config_hash(config: ToolConfig) -> str:
    """Hash only settings that can change scanner eligibility or body limits."""
    payload = {
        "exclude": list(config.index.exclude),
        "include": list(config.index.include),
        "max_file_bytes": config.index.max_file_bytes,
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def assert_manifest_compatible(repo: Path, config: ToolConfig) -> None:
    path = manifest_path(repo)
    if not path.exists():
        return

    manifest = load_manifest(repo)
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


_MANIFEST_V2_KEYS = frozenset(
    {
        "schema_version",
        "embedding_config_hash",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "index_config_hash",
        "source_content_fingerprint",
        "source_observation_fingerprint",
        "observation_generation",
        "manifest_generation",
        "vector_descriptor_schema_version",
        "vector_generation",
        "vector_descriptor_sha256",
        "vector_bytes",
        "vector_ids_bytes",
        "indexed_at_epoch_s",
        "operational_schema_version",
        "operation_mode",
        "work_metrics",
        "total_files",
        "total_chunks",
    }
)


def _manifest_v2_from_dict(data: dict[str, Any]) -> ManifestV2:
    if frozenset(data) != _MANIFEST_V2_KEYS:
        raise ManifestCorruptionError("invalid manifest v2 fields")
    metrics = data.get("work_metrics")
    if not isinstance(metrics, dict):
        raise ManifestCorruptionError("invalid manifest work metrics")
    try:
        manifest = ManifestV2(
            schema_version=_required_int(data, "schema_version"),
            embedding_config_hash=_required_str(data, "embedding_config_hash"),
            embedding_provider=_required_str(data, "embedding_provider"),
            embedding_model=_required_str(data, "embedding_model"),
            embedding_dimensions=_required_int(data, "embedding_dimensions"),
            index_config_hash=_required_str(data, "index_config_hash"),
            source_content_fingerprint=_required_str(
                data, "source_content_fingerprint"
            ),
            source_observation_fingerprint=_required_str(
                data, "source_observation_fingerprint"
            ),
            observation_generation=_required_int(data, "observation_generation"),
            manifest_generation=_required_str(data, "manifest_generation"),
            vector_descriptor_schema_version=_required_int(
                data, "vector_descriptor_schema_version"
            ),
            vector_generation=_required_str(data, "vector_generation"),
            vector_descriptor_sha256=_required_str(
                data, "vector_descriptor_sha256"
            ),
            vector_bytes=_required_int(data, "vector_bytes"),
            vector_ids_bytes=_required_int(data, "vector_ids_bytes"),
            indexed_at_epoch_s=_required_int(data, "indexed_at_epoch_s"),
            operational_schema_version=_required_int(
                data, "operational_schema_version"
            ),
            operation_mode=_required_str(data, "operation_mode"),
            work_metrics=_normalize_work_metrics(tuple(metrics.items())),
            total_files=_required_int(data, "total_files"),
            total_chunks=_required_int(data, "total_chunks"),
        )
        _validate_manifest_v2(manifest)
    except ManifestCorruptionError:
        raise
    except (TypeError, ValueError) as error:
        raise ManifestCorruptionError("invalid manifest v2") from error
    return manifest


def _manifest_v2_dict(manifest: ManifestV2) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "embedding_config_hash": manifest.embedding_config_hash,
        "embedding_provider": manifest.embedding_provider,
        "embedding_model": manifest.embedding_model,
        "embedding_dimensions": manifest.embedding_dimensions,
        "index_config_hash": manifest.index_config_hash,
        "source_content_fingerprint": manifest.source_content_fingerprint,
        "source_observation_fingerprint": manifest.source_observation_fingerprint,
        "observation_generation": manifest.observation_generation,
        "manifest_generation": manifest.manifest_generation,
        "vector_descriptor_schema_version": (
            manifest.vector_descriptor_schema_version
        ),
        "vector_generation": manifest.vector_generation,
        "vector_descriptor_sha256": manifest.vector_descriptor_sha256,
        "vector_bytes": manifest.vector_bytes,
        "vector_ids_bytes": manifest.vector_ids_bytes,
        "indexed_at_epoch_s": manifest.indexed_at_epoch_s,
        "operational_schema_version": manifest.operational_schema_version,
        "operation_mode": manifest.operation_mode,
        "work_metrics": dict(manifest.work_metrics),
        "total_files": manifest.total_files,
        "total_chunks": manifest.total_chunks,
    }


def _validate_manifest_v2(manifest: ManifestV2) -> None:
    if manifest.schema_version != WRITE_MANIFEST_VERSION:
        if type(manifest.schema_version) is int and manifest.schema_version > 2:
            raise IncompatibleManifestSchemaError(manifest.schema_version)
        raise ManifestCorruptionError("invalid manifest v2 schema")
    for value in (
        manifest.embedding_config_hash,
        manifest.index_config_hash,
        manifest.source_content_fingerprint,
        manifest.source_observation_fingerprint,
        manifest.vector_descriptor_sha256,
    ):
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ManifestCorruptionError("invalid manifest digest")
    if not manifest.embedding_provider or not manifest.embedding_model:
        raise ManifestCorruptionError("invalid embedding identity")
    if not _GENERATION_RE.fullmatch(manifest.manifest_generation):
        raise ManifestCorruptionError("invalid manifest generation")
    if not _GENERATION_RE.fullmatch(manifest.vector_generation):
        raise ManifestCorruptionError("invalid vector generation")
    if manifest.vector_descriptor_schema_version != 2:
        raise ManifestCorruptionError("invalid vector descriptor schema")
    if manifest.operational_schema_version != 1:
        raise ManifestCorruptionError("invalid operational schema")
    if manifest.operation_mode not in _OPERATION_MODES:
        raise ManifestCorruptionError("invalid operation mode")
    if (
        type(manifest.embedding_dimensions) is not int
        or manifest.embedding_dimensions < 1
    ):
        raise ManifestCorruptionError("invalid embedding dimensions")
    for value in (
        manifest.observation_generation,
        manifest.vector_bytes,
        manifest.vector_ids_bytes,
        manifest.indexed_at_epoch_s,
        manifest.total_files,
        manifest.total_chunks,
    ):
        if type(value) is not int or value < 0:
            raise ManifestCorruptionError("invalid manifest count")
    _normalize_work_metrics(manifest.work_metrics)


def _normalize_work_metrics(
    metrics: tuple[tuple[str, int | str], ...],
) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(metrics, tuple) or len(metrics) > _MAX_WORK_METRICS:
        raise ManifestCorruptionError("invalid manifest work metrics")
    normalized: dict[str, int | str] = {}
    for item in metrics:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ManifestCorruptionError("invalid manifest work metrics")
        key, value = item
        if (
            not isinstance(key, str)
            or len(key) > 128
            or not _WORK_METRIC_RE.fullmatch(key)
            or key in normalized
        ):
            raise ManifestCorruptionError("invalid manifest work metrics")
        if type(value) is int:
            if value < 0:
                raise ManifestCorruptionError("invalid manifest work metrics")
        elif (
            not isinstance(value, str)
            or value not in _WORK_STRING_METRICS.get(key, frozenset())
        ):
            raise ManifestCorruptionError("invalid manifest work metrics")
        normalized[key] = value
    return tuple(sorted(normalized.items()))


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ManifestCorruptionError(f"invalid manifest field: {key}")
    return value


def _required_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if type(value) is not int:
        raise ManifestCorruptionError(f"invalid manifest field: {key}")
    return value


def _read_manifest_payload(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        path_stat = os.lstat(path)
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise ManifestCorruptionError("manifest must be a regular non-symlink")
        if path_stat.st_size > MAX_RAW_MANIFEST_BYTES:
            raise ManifestCorruptionError("manifest is too large")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ManifestCorruptionError("manifest must be a regular non-symlink")
        if hasattr(os, "getuid") and before.st_uid != os.getuid():
            raise ManifestCorruptionError("manifest owner mismatch")
        if stat.S_IMODE(before.st_mode) & 0o022:
            raise ManifestCorruptionError("unsafe manifest permissions")
        content = bytearray()
        while len(content) <= MAX_RAW_MANIFEST_BYTES:
            block = os.read(
                descriptor,
                min(
                    16 * 1024,
                    MAX_RAW_MANIFEST_BYTES + 1 - len(content),
                ),
            )
            if not block:
                break
            content.extend(block)
        payload = bytes(content)
        after = os.fstat(descriptor)
        final = os.lstat(path)
    except ManifestCorruptionError:
        raise
    except OSError as error:
        raise ManifestCorruptionError("unreadable manifest") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(payload) > MAX_RAW_MANIFEST_BYTES
        or len(payload) != after.st_size
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(after) != _stat_identity(final)
    ):
        raise ManifestCorruptionError("manifest changed during read")
    return payload


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
