from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from context_search_tool import manifest as manifest_module
from context_search_tool.config import (
    EmbeddingConfig,
    IndexConfig,
    QueryPlannerConfig,
    RetrievalConfig,
    ToolConfig,
)


def _require(name: str) -> Any:
    assert hasattr(manifest_module, name), f"P6 manifest capability {name} is absent"
    return getattr(manifest_module, name)


def _literal_v2(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 2,
        "embedding_config_hash": "1" * 64,
        "embedding_provider": "hash",
        "embedding_model": "hash-v1",
        "embedding_dimensions": 2,
        "index_config_hash": "2" * 64,
        "source_content_fingerprint": "3" * 64,
        "source_observation_fingerprint": "4" * 64,
        "observation_generation": 7,
        "manifest_generation": "manifest-0007",
        "vector_descriptor_schema_version": 2,
        "vector_generation": "vectors-0007",
        "vector_descriptor_sha256": "5" * 64,
        "vector_bytes": 128,
        "vector_ids_bytes": 32,
        "indexed_at_epoch_s": 1234,
        "operational_schema_version": 1,
        "operation_mode": "authoritative_index",
        "work_metrics": {"source.bytes_hashed": 12, "vector.bytes_written": 128},
        "total_files": 1,
        "total_chunks": 2,
    }
    payload.update(overrides)
    return payload


def _write_literal(repo: Path, payload: object) -> bytes:
    index_dir = repo / ".context-search"
    index_dir.mkdir()
    rendered = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    (index_dir / "manifest.json").write_bytes(rendered)
    return rendered


def test_literal_manifest_v1_and_v2_dispatch_without_rewrite(tmp_path: Path) -> None:
    assert _require("READABLE_MANIFEST_VERSIONS") == frozenset({1, 2})
    assert _require("WRITE_MANIFEST_VERSION") == 2

    legacy_repo = tmp_path / "legacy"
    legacy_repo.mkdir()
    legacy_bytes = _write_literal(
        legacy_repo,
        {
            "schema_version": 1,
            "embedding_config_hash": "legacy",
            "embedding_provider": "hash",
            "embedding_model": "hash-v1",
            "embedding_dimensions": 2,
            "total_files": 3,
            "total_chunks": 4,
        },
    )
    legacy = manifest_module.load_manifest(legacy_repo)
    assert type(legacy) is manifest_module.Manifest
    assert legacy.schema_version == 1
    assert legacy.total_files == 3
    assert (legacy_repo / ".context-search" / "manifest.json").read_bytes() == legacy_bytes

    current_repo = tmp_path / "current"
    current_repo.mkdir()
    current_bytes = _write_literal(current_repo, _literal_v2())
    loaded = _require("load_manifest_snapshot")(current_repo)
    assert loaded.manifest.schema_version == 2
    assert loaded.manifest.work_metrics == (
        ("source.bytes_hashed", 12),
        ("vector.bytes_written", 128),
    )
    assert loaded.sha256 == hashlib.sha256(current_bytes).hexdigest()
    assert loaded.byte_size == len(current_bytes)
    assert (current_repo / ".context-search" / "manifest.json").read_bytes() == current_bytes


@pytest.mark.parametrize(
    ("payload", "error_name", "code"),
    [
        (
            {"schema_version": 3, "unknown_secret": "must-not-be-read"},
            "IncompatibleManifestSchemaError",
            "incompatible_manifest_schema",
        ),
        (
            _literal_v2(schema_version="2"),
            "ManifestCorruptionError",
            "manifest_corrupt",
        ),
        (
            _literal_v2(vector_descriptor_sha256="short"),
            "ManifestCorruptionError",
            "manifest_corrupt",
        ),
        (
            _literal_v2(work_metrics={"source.bytes_hashed": -1}),
            "ManifestCorruptionError",
            "manifest_corrupt",
        ),
    ],
)
def test_manifest_reader_fails_closed_for_future_and_corrupt_literals(
    tmp_path: Path,
    payload: dict[str, object],
    error_name: str,
    code: str,
) -> None:
    repo = tmp_path / error_name
    repo.mkdir()
    original = _write_literal(repo, payload)
    error_type = _require(error_name)

    with pytest.raises(error_type) as caught:
        manifest_module.load_manifest(repo)

    assert caught.value.code == code
    assert (repo / ".context-search" / "manifest.json").read_bytes() == original


def test_manifest_v2_preparation_is_canonical_and_public_writer_stays_v1(
    tmp_path: Path,
) -> None:
    ManifestV2 = _require("ManifestV2")
    prepare = _require("prepare_manifest_v2")
    publish = _require("publish_manifest_v2")
    manifest = ManifestV2(
        embedding_config_hash="1" * 64,
        embedding_provider="hash",
        embedding_model="hash-v1",
        embedding_dimensions=2,
        index_config_hash="2" * 64,
        source_content_fingerprint="3" * 64,
        source_observation_fingerprint="4" * 64,
        observation_generation=7,
        manifest_generation="manifest-0007",
        vector_descriptor_schema_version=2,
        vector_generation="vectors-0007",
        vector_descriptor_sha256="5" * 64,
        vector_bytes=128,
        vector_ids_bytes=32,
        indexed_at_epoch_s=1234,
        operational_schema_version=1,
        operation_mode="authoritative_index",
        work_metrics=(("vector.bytes_written", 128), ("source.bytes_hashed", 12)),
        total_files=1,
        total_chunks=2,
    )

    prepared = prepare(manifest)
    assert prepared.payload.endswith(b"\n")
    assert prepared.sha256 == hashlib.sha256(prepared.payload).hexdigest()
    assert b"api_key" not in prepared.payload
    decoded = json.loads(prepared.payload)
    assert list(decoded["work_metrics"]) == [
        "source.bytes_hashed",
        "vector.bytes_written",
    ]

    repo = tmp_path / "repo"
    repo.mkdir()
    publish(repo, prepared)
    assert (repo / ".context-search" / "manifest.json").read_bytes() == prepared.payload
    assert manifest_module.load_manifest(repo) == prepared.manifest

    legacy_repo = tmp_path / "public-v1"
    legacy_repo.mkdir()
    manifest_module.write_manifest(legacy_repo, manifest_module.Manifest())
    assert json.loads(
        (legacy_repo / ".context-search" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["schema_version"] == 1


def test_index_config_hash_is_scanner_specific_and_secret_safe() -> None:
    index_config_hash = _require("index_config_hash")
    baseline = ToolConfig(
        index=IndexConfig(include=["src/**"], exclude=["dist/**"], max_file_bytes=99),
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="private-model",
            dimensions=3,
            base_url="https://user:password@example.test/v1",
            api_key_env="PRIVATE_TOKEN",
        ),
    )
    query_only = ToolConfig(
        index=baseline.index,
        embedding=baseline.embedding,
        retrieval=RetrievalConfig(final_top_k=3),
        query_planner=QueryPlannerConfig(enabled=True),
    )
    changed_scanner = ToolConfig(
        index=IndexConfig(include=["src/**"], exclude=["vendor/**"], max_file_bytes=99),
        embedding=baseline.embedding,
    )

    digest = index_config_hash(baseline)

    assert len(digest) == 64
    assert digest == index_config_hash(query_only)
    assert digest != index_config_hash(changed_scanner)
    assert "password" not in digest
    assert "PRIVATE_TOKEN" not in digest
