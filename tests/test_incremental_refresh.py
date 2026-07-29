from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from context_search_tool import indexer as indexer_module
from context_search_tool import sqlite_store as sqlite_store_module
from context_search_tool.config import DEFAULT_CONFIG, EmbeddingConfig
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    OPERATIONAL_SCHEMA_VERSION_KEY,
    read_graph_capability,
)
from context_search_tool.graph_plugins import MaterializedGraph, ParsedGraphFacts
from context_search_tool.index_lock import exclusive_index_lock
from context_search_tool.indexer import build_v5_index_snapshot, index_repository
from context_search_tool.manifest import (
    Manifest,
    ManifestV2,
    load_manifest,
    prepare_manifest_v2,
    publish_manifest_v2,
    write_manifest,
)
from context_search_tool.scanner import (
    ObservedFileRead,
    observe_workspace,
    read_observed_file,
    scan_workspace_v5,
)
from context_search_tool.sqlite_store import FILE_WRITE_IN_PROGRESS_KEY, SQLiteStore
from context_search_tool.vector_store import (
    NumpyVectorStore,
    PreparedVectorGeneration,
)


class _RecordingPlugin:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def supports(self, context: Any) -> bool:
        return context.language == "java"

    def parse(self, context: Any, content: bytes) -> ParsedGraphFacts:
        self.events.append(f"parse:{context.file_path.as_posix()}")
        return ParsedGraphFacts(facts=None)

    def materialize(
        self,
        context: Any,
        parsed: ParsedGraphFacts,
        chunks: tuple[Any, ...],
        module_signal: Any,
    ) -> MaterializedGraph:
        self.events.append(f"materialize:{context.file_path.as_posix()}")
        return MaterializedGraph()


class _RecordingRemoteProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failure: Exception | None = None

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": "openai-compatible",
            "model": "fixture-embedding",
            "dimensions": 3,
        }

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        self.calls.append(tuple(texts))
        if self.failure is not None:
            raise self.failure
        return [np.asarray([1.0, 0.0, 0.0], dtype=np.float32) for _ in texts]


_BGE_CONFIG_HASH = "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929"
_BGE_DIGEST = "1111111111111111111111111111111111111111111111111111111111111111"
_BGE_DRIFT_DIGEST = (
    "2222222222222222222222222222222222222222222222222222222222222222"
)
_BGE_VERSION = "0.30.10"
_BGE_VERSION_SHA256 = (
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503"
)
_BGE_V1_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "1111111111111111111111111111111111111111111111111111111111111111:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
_BGE_V2_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "1111111111111111111111111111111111111111111111111111111111111111:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v2"
)
_BGE_IDENTITY = _BGE_V2_IDENTITY
_BGE_DIGEST_DRIFT_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "2222222222222222222222222222222222222222222222222222222222222222:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v2"
)
_WAL_WITNESS = "WAL_LOGICAL_WITNESS_P13"
_WAL_WITNESS_KEY = "p13_wal_logical_witness"


def _bge_config():
    return replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="bge",
            model="bge-m3",
            dimensions=3,
            base_url="http://localhost:11434",
        ),
    )


class _FakeBGEFailure(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _AttestedBGEProvider:
    def __init__(
        self,
        config: Any,
        *,
        identity: str | None = None,
        digest: str = _BGE_DIGEST,
        transform_id: str = "bge-input-v2",
        failure: str | None = None,
    ) -> None:
        self.config = config
        self.identity = identity or _BGE_IDENTITY
        self.digest = digest
        self.transform_id = transform_id
        self.failure = failure
        self.events: list[str] = []
        self.embedded_texts: list[str] = []
        self.successful_embed_responses = 0
        self._egress = "not_attempted"

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.embedding.provider,
            "model": self.config.embedding.model,
            "dimensions": self.config.embedding.dimensions,
            "backend": "ollama",
        }

    def runtime_fingerprint(self) -> dict[str, object]:
        self.events.append("preflight")
        self._egress = "possible"
        if self.failure == "preflight_possible":
            raise _FakeBGEFailure("bge_unavailable")
        self._egress = "performed"
        if self.failure == "preflight_performed":
            raise _FakeBGEFailure("bge_unavailable")
        return self._runtime_mapping()

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        self.events.append("embed")
        self.embedded_texts.extend(texts)
        self._egress = "possible"
        if self.failure == "first_batch":
            raise _FakeBGEFailure("bge_unavailable")
        if self.failure == "middle_batch":
            assert len(texts) >= 2
            self.successful_embed_responses = 1
            self._egress = "performed"
            raise _FakeBGEFailure("bge_unavailable")
        if self.failure == "response_invalid":
            self._egress = "performed"
            raise _FakeBGEFailure("bge_response_invalid")
        self._egress = "performed"
        self.successful_embed_responses += 1
        vectors: list[np.ndarray] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = np.asarray(
                [float(digest[index]) + 1.0 for index in range(3)],
                dtype=np.float32,
            )
            vectors.append(vector / np.linalg.norm(vector))
        return vectors

    def assert_runtime_unchanged(self) -> dict[str, object]:
        self.events.append("postflight")
        self._egress = "performed"
        if self.failure == "postflight":
            raise _FakeBGEFailure("bge_runtime_mismatch")
        return self._runtime_mapping()

    def _runtime_mapping(self) -> dict[str, object]:
        return {
            "configured_model": self.config.embedding.model,
            "canonical_model": "bge-m3:latest",
            "model_digest": self.digest,
            "ollama_version": _BGE_VERSION,
            "base_url": self.config.embedding.base_url,
            "dimensions": self.config.embedding.dimensions,
            "input_transform_id": self.transform_id,
            "embedding_identity": self.identity,
        }

    @property
    def _network_egress_outcome(self) -> str:
        return self._egress


def _build_bge(
    repo: Path,
    provider: _AttestedBGEProvider,
    *,
    fault_hook=None,
):
    return build_v5_index_snapshot(
        repo,
        provider.config,
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
        fault_hook=fault_hook,
    )


class _InjectedFault(RuntimeError):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"injected fault at {stage}")


class _RestoreBoundaryFailure(OSError):
    pass


class _SQLiteConnectBoundaryFailure(RuntimeError):
    pass


class _VectorStoreBoundaryFailure(RuntimeError):
    pass


class _TrackingSQLiteConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        backup_failure: RuntimeError | None = None,
    ) -> None:
        self._connection = connection
        self._backup_failure = backup_failure
        self.close_calls = 0

    def backup(self, destination: Any) -> None:
        if self._backup_failure is not None:
            raise self._backup_failure
        target = (
            destination._connection
            if isinstance(destination, _TrackingSQLiteConnection)
            else destination
        )
        self._connection.backup(target)

    def close(self) -> None:
        self.close_calls += 1
        self._connection.close()

    def force_close(self) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _CloseTrackingVectorStore:
    def __init__(
        self,
        store: NumpyVectorStore,
        *,
        ids: tuple[str, ...] | None = None,
        search_failure: RuntimeError | None = None,
    ) -> None:
        self._store = store
        self._ids = ids
        self._search_failure = search_failure
        self.close_calls = 0
        vectors: object | None = store._vectors
        seen: set[int] = set()
        while vectors is not None and id(vectors) not in seen:
            seen.add(id(vectors))
            if isinstance(vectors, np.memmap):
                self.mapping = vectors._mmap
                break
            vectors = getattr(vectors, "base", None)
        else:
            raise AssertionError("loaded rollback vector store is not mmap-backed")
        assert self.mapping is not None
        assert self.mapping.closed is False

    @property
    def ids(self) -> tuple[str, ...]:
        return self._ids if self._ids is not None else self._store.ids

    def search(self, *args: Any, **kwargs: Any):
        if self._search_failure is not None:
            raise self._search_failure
        return self._store.search(*args, **kwargs)

    def close(self) -> None:
        self.close_calls += 1
        self._store.close()

    def force_close(self) -> None:
        if not self.mapping.closed:
            self._store.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


def _traceback_contains(traceback: Any, expected: Any) -> bool:
    current = traceback
    while current is not None:
        if current is expected:
            return True
        current = current.tb_next
    return False


@dataclass(frozen=True)
class _BGEReadyTuple:
    manifest_payload: bytes
    manifest_sha256: str
    manifest_mode: int
    manifest_source_content_fingerprint: str
    manifest_source_observation_fingerprint: str
    descriptor_payload: bytes
    descriptor_sha256: str
    descriptor_mode: int
    descriptor_generation: str
    descriptor_identity: str
    operation_mode: str
    graph_status: str
    binding: Any
    ids: tuple[str, ...]
    pinned_query: tuple[tuple[str, float], ...]
    journal_mode: str
    wal_logical_witness: str | None
    generation_artifacts: tuple[str, ...]


_GENERATION_ARTIFACT_PATTERNS = (
    re.compile(r"vectors\.([A-Za-z0-9][A-Za-z0-9_-]*)\.npy"),
    re.compile(r"vector_ids\.([A-Za-z0-9][A-Za-z0-9_-]*)\.json"),
)


def _generation_artifacts(index_dir: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name
            for path in index_dir.iterdir()
            if path.is_file()
            and any(
                pattern.fullmatch(path.name)
                for pattern in _GENERATION_ARTIFACT_PATTERNS
            )
        )
    )


def _vector_prefixed_artifacts(index_dir: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name
            for path in index_dir.iterdir()
            if path.is_file()
            and (
                path.name.lstrip(".").startswith("vectors.")
                or path.name.lstrip(".").startswith("vector_ids.")
            )
        )
    )


def _force_attested_ready_fixture(
    repo: Path,
    *,
    identity: str = _BGE_IDENTITY,
) -> None:
    index_dir = repo / ".context-search"
    descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert descriptor is not None
    publisher = NumpyVectorStore.fresh(
        index_dir,
        dimensions=descriptor.descriptor.dimensions,
    )
    publisher.publish_generation(
        PreparedVectorGeneration(
            index_dir,
            replace(
                descriptor.descriptor,
                embedding_identity=identity,
            ),
        )
    )
    rebound = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert rebound is not None
    assert rebound.descriptor.embedding_identity == identity

    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    prepared_manifest = prepare_manifest_v2(
        replace(
            manifest,
            vector_descriptor_sha256=rebound.sha256,
        )
    )
    publish_manifest_v2(repo, prepared_manifest)

    store = SQLiteStore(index_dir / "index.sqlite")
    operational = store.read_operational_snapshot()
    assert operational is not None
    topology = store.get_metadata("project_unit_topology_fingerprint")
    assert topology is not None
    store.commit_operational_ready_v1(
        binding=replace(
            operational.binding,
            manifest_sha256=prepared_manifest.sha256,
            vector_descriptor_sha256=rebound.sha256,
        ),
        topology_fingerprint=topology,
        expected_embedding_ids=set(operational.active_embedding_ids),
        expected_source_count=operational.source_count,
        expected_chunk_count=operational.chunk_count,
        external_validator=lambda: None,
        graph_snapshot_unchanged=True,
    )


def _bge_ready_state(
    repo: Path,
    *,
    expected_identity: str = _BGE_IDENTITY,
) -> _BGEReadyTuple:
    index_dir = repo / ".context-search"
    manifest_path = index_dir / "manifest.json"
    descriptor_path = index_dir / "vector_snapshot.json"
    manifest_payload = manifest_path.read_bytes()
    descriptor_payload = descriptor_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    descriptor_sha256 = hashlib.sha256(descriptor_payload).hexdigest()
    manifest = load_manifest(repo)
    descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert isinstance(manifest, ManifestV2)
    assert descriptor is not None
    assert manifest.embedding_config_hash == _BGE_CONFIG_HASH
    assert descriptor.sha256 == descriptor_sha256
    identity_parts = descriptor.descriptor.embedding_identity.split(":")
    assert len(identity_parts) == 5
    assert identity_parts[0] == "bge-ollama-v1"
    assert identity_parts[1] == _BGE_CONFIG_HASH
    assert identity_parts[3] == _BGE_VERSION_SHA256
    assert identity_parts[4] == expected_identity.rsplit(":", 1)[-1]
    assert descriptor.descriptor.embedding_identity == expected_identity
    operational = SQLiteStore(
        index_dir / "index.sqlite"
    ).read_operational_snapshot()
    assert operational is not None
    assert operational.graph_status == "ready"
    assert operational.binding.manifest_sha256 == manifest_sha256
    assert operational.binding.vector_descriptor_sha256 == descriptor_sha256
    assert operational.binding.vector_generation == descriptor.descriptor.generation
    assert (
        operational.binding.source_content_fingerprint
        == manifest.source_content_fingerprint
    )
    assert (
        operational.binding.source_observation_fingerprint
        == manifest.source_observation_fingerprint
    )
    assert operational.binding.operation_mode == manifest.operation_mode
    assert descriptor.descriptor.vectors_bytes is not None
    assert descriptor.descriptor.ids_bytes is not None
    vectors = NumpyVectorStore.load_bound_ready_snapshot(
        index_dir,
        expected_descriptor_sha256=descriptor_sha256,
        expected_generation=descriptor.descriptor.generation,
        expected_vectors_bytes=descriptor.descriptor.vectors_bytes,
        expected_ids_bytes=descriptor.descriptor.ids_bytes,
        expected_row_count=descriptor.descriptor.row_count,
        expected_dimensions=descriptor.descriptor.dimensions,
        expected_embedding_identity=descriptor.descriptor.embedding_identity,
    )
    assert vectors.ids == tuple(sorted(operational.active_embedding_ids))
    query = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    pinned = tuple(
        (item.chunk_id, round(item.score, 7))
        for item in vectors.search(query, 20, set())
    )
    assert pinned
    with sqlite3.connect(index_dir / "index.sqlite") as connection:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    return _BGEReadyTuple(
        manifest_payload=manifest_payload,
        manifest_sha256=manifest_sha256,
        manifest_mode=manifest_path.stat().st_mode & 0o777,
        manifest_source_content_fingerprint=manifest.source_content_fingerprint,
        manifest_source_observation_fingerprint=(
            manifest.source_observation_fingerprint
        ),
        descriptor_payload=descriptor_payload,
        descriptor_sha256=descriptor_sha256,
        descriptor_mode=descriptor_path.stat().st_mode & 0o777,
        descriptor_generation=descriptor.descriptor.generation,
        descriptor_identity=descriptor.descriptor.embedding_identity,
        operation_mode=manifest.operation_mode,
        graph_status=operational.graph_status,
        binding=operational.binding,
        ids=vectors.ids,
        pinned_query=pinned,
        journal_mode=journal_mode,
        wal_logical_witness=SQLiteStore(
            index_dir / "index.sqlite"
        ).get_metadata(_WAL_WITNESS_KEY),
        generation_artifacts=_generation_artifacts(index_dir),
    )


def _assert_wal_logical_witness(repo: Path) -> None:
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(_WAL_WITNESS_KEY) == _WAL_WITNESS


def _prepare_wal_ready_tuple(
    repo: Path,
    config: Any,
) -> tuple[sqlite3.Connection, _BGEReadyTuple]:
    alpha = repo / "Alpha.java"
    beta = repo / "Beta.java"
    alpha.write_text("class Alpha { int initialAlpha; }\n", encoding="utf-8")
    beta.write_text("class Beta { int initialBeta; }\n", encoding="utf-8")
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    database = repo / ".context-search" / "index.sqlite"
    keeper = sqlite3.connect(database, isolation_level=None)
    assert keeper.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    keeper.execute("PRAGMA wal_autocheckpoint=0")
    keeper.execute("BEGIN")
    keeper.execute(
        "SELECT value FROM index_metadata WHERE key = ?",
        (GRAPH_RESOLUTION_STATE_KEY,),
    ).fetchone()
    writer = sqlite3.connect(database, isolation_level=None)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            """
            INSERT INTO index_metadata (key, value, updated_at)
            VALUES (?, ?, 0)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (_WAL_WITNESS_KEY, _WAL_WITNESS),
        )
        writer.execute("COMMIT")
    finally:
        writer.close()
    wal_path = database.with_name("index.sqlite-wal")
    assert wal_path.exists()
    assert _WAL_WITNESS.encode("utf-8") in wal_path.read_bytes()
    assert _WAL_WITNESS.encode("utf-8") not in database.read_bytes()
    ready = _bge_ready_state(repo)
    assert ready.journal_mode == "wal"
    assert ready.wal_logical_witness == _WAL_WITNESS
    _assert_wal_logical_witness(repo)
    return keeper, ready


def _remote_config():
    return replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="fixture-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
    )


def _build(
    repo: Path,
    *,
    events: list[str] | None = None,
    **kwargs: Any,
):
    recorded = events if events is not None else []
    return build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[_RecordingPlugin(recorded)],
        scanner=scan_workspace_v5,
        **kwargs,
    )


def _snapshot_bytes(repo: Path) -> tuple[bytes, bytes, bytes]:
    index_dir = repo / ".context-search"
    return (
        (index_dir / "manifest.json").read_bytes(),
        (index_dir / "vector_snapshot.json").read_bytes(),
        (index_dir / "index.sqlite").read_bytes(),
    )


def _refresh(
    repo: Path,
    config: Any = DEFAULT_CONFIG,
    *,
    events: list[str] | None = None,
    **kwargs: Any,
):
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh), "P6 internal quick-refresh entry is absent"
    recorded = events if events is not None else []
    return refresh(
        repo,
        config,
        graph_plugins=[_RecordingPlugin(recorded)],
        **kwargs,
    )


def test_repository_path_index_built_once_per_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_type = getattr(indexer_module, "RepositoryPathIndex", None)
    assert index_type is not None, "shared repository path index is absent"

    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("Alpha.java", "Beta.java", "Gamma.java"):
        (repo / name).write_text(f"class {name[:-5]} {{}}\n", encoding="utf-8")

    built_indexes: list[Any] = []
    real_index_type = index_type

    def tracked_index(*args: Any, **kwargs: Any) -> Any:
        index = real_index_type(*args, **kwargs)
        built_indexes.append(index)
        return index

    monkeypatch.setattr(indexer_module, "RepositoryPathIndex", tracked_index)
    contexts: list[Any] = []

    class RecordingPathPlugin(_RecordingPlugin):
        def parse(self, context: Any, content: bytes) -> ParsedGraphFacts:
            contexts.append(context)
            return super().parse(context, content)

    plugin = RecordingPathPlugin([])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )

    assert len(built_indexes) == 1
    assert len(contexts) == 3
    assert all(
        context.repository_path_index is built_indexes[0] for context in contexts
    )

    contexts.clear()
    (repo / "Alpha.java").write_text("class Alpha { int changed; }\n", encoding="utf-8")
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh)
    result = refresh(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
    )

    assert result.ok is True
    assert len(built_indexes) == 2
    assert contexts
    assert all(
        context.repository_path_index is built_indexes[1] for context in contexts
    )
    assert result.summary.work.path_index.builds == 1
    assert result.summary.work.path_index.paths_canonicalized == 3


def test_authoritative_prepares_and_closes_inventory_before_stale(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    events: list[str] = []
    inventory_calls = 0

    def inventory_reader(repo_path: Path, config: Any):
        nonlocal inventory_calls
        inventory_calls += 1
        events.append("opening_inventory" if inventory_calls == 1 else "closing_inventory")
        return observe_workspace(repo_path, config)

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        events.append(f"hash:{observation.path.as_posix()}")
        return read_observed_file(repo_path, observation, **kwargs)

    def observe_stage(stage: str) -> None:
        events.append(stage)
        if stage == "stale_committed":
            assert events.index("opening_inventory") < events.index("hash:App.java")
            assert events.index("hash:App.java") < events.index("parse:App.java")
            assert events.index("parse:App.java") < events.index("closing_inventory")
            assert events.index("closing_inventory_complete") < events.index(
                "stale_committed"
            )

    _build(
        repo,
        events=events,
        inventory_observer=inventory_reader,
        observed_reader=source_reader,
        fault_hook=observe_stage,
    )

    assert inventory_calls == 2
    assert isinstance(load_manifest(repo), ManifestV2)


def test_closing_inventory_drift_preserves_prior_ready_snapshot(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    calls = 0

    def drifting_inventory(repo_path: Path, config: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("class App { int newValue; }\n", encoding="utf-8")
        return observe_workspace(repo_path, config)

    error_type = getattr(indexer_module, "WorkspaceChangedError", ValueError)
    with pytest.raises(error_type):
        _build(repo, inventory_observer=drifting_inventory)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert _snapshot_bytes(repo) == before


def test_quick_refresh_remote_payload_contains_only_changed_and_added_chunks(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    stable = repo / "Stable.java"
    changed = repo / "Changed.java"
    stable.write_text("class Stable { int stableOnlyToken; }\n", encoding="utf-8")
    changed.write_text("class Changed { int oldOnlyToken; }\n", encoding="utf-8")
    config = _remote_config()
    provider = _RecordingRemoteProvider()
    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )
    provider.calls.clear()
    changed.write_text("class Changed { int changedOnlyToken; }\n", encoding="utf-8")
    (repo / "Added.java").write_text(
        "class Added { int addedOnlyToken; }\n",
        encoding="utf-8",
    )

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is True
    assert result.network_egress_performed is True
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == result.summary.chunks.embedded == 2
    payload = "\n".join(provider.calls[0])
    assert "changedOnlyToken" in payload
    assert "addedOnlyToken" in payload
    assert "stableOnlyToken" not in payload
    assert "oldOnlyToken" not in payload


def test_quick_refresh_remote_transport_failure_is_possible_and_non_mutating(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _remote_config()
    provider = _RecordingRemoteProvider()
    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )
    provider.calls.clear()
    provider.failure = RuntimeError("SECRET provider transport detail")
    source.write_text("class App { int after; }\n", encoding="utf-8")
    before = _snapshot_bytes(repo)

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is False
    assert result.code == "refresh_failed"
    assert result.network_egress_outcome == "possible"
    assert "SECRET" not in result.message
    assert len(provider.calls) == 1
    assert _snapshot_bytes(repo) == before


def test_quick_refresh_post_response_fault_is_performed_and_non_mutating(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _remote_config()
    provider = _RecordingRemoteProvider()
    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )
    provider.calls.clear()
    source.write_text("class App { int after; }\n", encoding="utf-8")
    before = _snapshot_bytes(repo)

    def fail_after_response(stage: str) -> None:
        if stage == "embedding_complete":
            raise RuntimeError("SECRET post-response detail")

    result = _refresh(
        repo,
        config,
        embedding_provider=provider,
        fault_hook=fail_after_response,
    )

    assert result.ok is False
    assert result.code == "refresh_failed"
    assert result.network_egress_outcome == "performed"
    assert "SECRET" not in result.message
    assert len(provider.calls) == 1
    assert _snapshot_bytes(repo) == before


def test_authoritative_noop_hashes_every_source_without_parse_or_embedding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    _build(repo)
    source_metadata = (repo / "App.java").stat()
    os.utime(
        repo / "App.java",
        ns=(source_metadata.st_atime_ns, source_metadata.st_mtime_ns + 1_000_000),
    )
    reads: list[Path] = []
    events: list[str] = []

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        reads.append(observation.path)
        return read_observed_file(repo_path, observation, **kwargs)

    class _ForbiddenProvider:
        def fingerprint(self) -> dict[str, object]:
            raise AssertionError("no-op constructed or validated an embedding provider")

        def embed_texts(self, texts: list[str]):
            raise AssertionError("no-op sent unchanged source for embedding")

    def forbidden_graph_work(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("no-op repeated unchanged graph work")

    graph_integrity_calls = 0
    original_graph_integrity = sqlite_store_module._graph_integrity

    def tracked_graph_integrity(*args: Any, **kwargs: Any):
        nonlocal graph_integrity_calls
        graph_integrity_calls += 1
        return original_graph_integrity(*args, **kwargs)

    vector_verify_calls = 0
    original_vector_verify = NumpyVectorStore.verify_published_snapshot.__func__

    def tracked_vector_verify(cls: type[Any], *args: Any, **kwargs: Any):
        nonlocal vector_verify_calls
        vector_verify_calls += 1
        return original_vector_verify(cls, *args, **kwargs)

    monkeypatch.setattr(
        indexer_module,
        "resolve_graph_relations",
        forbidden_graph_work,
    )
    monkeypatch.setattr(
        indexer_module,
        "regenerate_test_associations",
        forbidden_graph_work,
    )
    monkeypatch.setattr(
        SQLiteStore,
        "active_embedding_ids",
        forbidden_graph_work,
    )
    monkeypatch.setattr(
        sqlite_store_module,
        "_graph_integrity",
        tracked_graph_integrity,
    )
    monkeypatch.setattr(
        NumpyVectorStore,
        "verify_published_snapshot",
        classmethod(tracked_vector_verify),
    )

    summary = _build(
        repo,
        events=events,
        observed_reader=source_reader,
        embedding_provider=_ForbiddenProvider(),
    )

    assert reads == [Path("App.java"), Path("notes.md")]
    assert events == []
    assert summary.files_indexed == 0
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    work = dict(manifest.work_metrics)
    assert work["source.files_hashed"] == 2
    assert work["source.bytes_hashed"] == len(b"class App {}\nnotes\n")
    assert work["files.parsed"] == 0
    assert work["chunks.embedded"] == 0
    assert work["vector.descriptor_action"] == "reused"
    assert graph_integrity_calls == 0
    assert vector_verify_calls == 1


def test_authoritative_noop_recovers_graph_changed_after_ready(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    _build(repo)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "DELETE FROM code_signals WHERE kind = 'module' AND deleted_at IS NULL"
        )
    assert store.graph_integrity().ok is False

    summary = _build(repo)

    assert summary.files_indexed == 1
    assert store.graph_integrity().ok is True
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_authoritative_embedding_batches_are_bounded_before_the_closing_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for index in range(5):
        (repo / f"Service{index}.java").write_text(
            f"class Service{index} {{ int value{index}; }}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        indexer_module,
        "_AUTHORITATIVE_EMBEDDING_BATCH_SIZE",
        2,
        raising=False,
    )
    monkeypatch.setattr(
        indexer_module,
        "_AUTHORITATIVE_EMBEDDING_BATCH_BYTES",
        100,
        raising=False,
    )
    stages: list[str] = []

    class _CeilingProvider(_RecordingRemoteProvider):
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            assert len(texts) <= 2, "authoritative embedding batch exceeded ceiling"
            assert len(texts) == 1 or sum(
                len(text.encode("utf-8")) for text in texts
            ) <= 100, "authoritative embedding text batch exceeded ceiling"
            return super().embed_texts(texts)

    provider = _CeilingProvider()
    summary = build_v5_index_snapshot(
        repo,
        _remote_config(),
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
        fault_hook=stages.append,
    )

    assert sum(len(call) for call in provider.calls) == 5
    assert all(len(call) <= 2 for call in provider.calls)
    assert summary.files_indexed == 5
    assert stages.index("embedding_complete") < stages.index(
        "closing_inventory_complete"
    )
    assert stages.index("closing_inventory_complete") < stages.index(
        "stale_committed"
    )


def test_authoritative_persistence_uses_bounded_file_batches_after_closing_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for index in range(5):
        (repo / f"Service{index}.java").write_text(
            f"class Service{index} {{ int value{index}; }}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        indexer_module,
        "_AUTHORITATIVE_PERSISTENCE_BATCH_SIZE",
        2,
        raising=False,
    )
    original = SQLiteStore.write_v5_file_batch
    batches: list[tuple[Path, ...]] = []

    def counted_batch(self: SQLiteStore, writes: list[Any], **kwargs: Any) -> None:
        batches.append(tuple(write[0].path for write in writes))
        original(self, writes, **kwargs)

    monkeypatch.setattr(SQLiteStore, "write_v5_file_batch", counted_batch)
    stages: list[str] = []
    summary = _build(repo, events=[], fault_hook=stages.append)

    assert summary.files_indexed == 5
    assert batches == [
        (Path("Service0.java"), Path("Service1.java")),
        (Path("Service2.java"), Path("Service3.java")),
        (Path("Service4.java"),),
    ]
    assert stages.index("closing_inventory_complete") < stages.index(
        "file_write_started"
    )


def test_authoritative_persistence_batch_fault_rolls_back_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for index in range(3):
        (repo / f"Service{index}.java").write_text(
            f"class Service{index} {{ int value{index}; }}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        indexer_module,
        "_AUTHORITATIVE_PERSISTENCE_BATCH_SIZE",
        2,
        raising=False,
    )
    completed = 0

    def fail_second_file(stage: str) -> None:
        nonlocal completed
        if stage == "source_hash_persisted":
            completed += 1
            if completed == 2:
                raise RuntimeError("batch persistence fault")

    with pytest.raises(RuntimeError, match="batch persistence fault"):
        _build(repo, events=[], fault_hook=fail_second_file)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.source_files_snapshot() == ()
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"
    assert store.get_metadata(FILE_WRITE_IN_PROGRESS_KEY)

    recovered = _build(repo, events=[])
    assert recovered.files_indexed == 3
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert store.get_metadata(FILE_WRITE_IN_PROGRESS_KEY) == ""


def test_fresh_v5_persistence_skips_only_provably_empty_relation_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App {}\n", encoding="utf-8")
    statements: list[str] = []
    original_open = sqlite_store_module._open_connection

    def traced_open(*args: Any, **kwargs: Any):
        connection = original_open(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite_store_module, "_open_connection", traced_open)
    _build(repo, events=[])
    relation_cleanup = "UPDATE code_relations SET deleted_at"

    def is_source_file_cleanup(statement: str) -> bool:
        normalized = " ".join(statement.split())
        return (
            relation_cleanup in normalized
            and "WHERE source_file_path =" in normalized
        )

    assert not any(
        is_source_file_cleanup(statement) for statement in statements
    )

    statements.clear()
    source.write_text("class App { int changed; }\n", encoding="utf-8")
    _build(repo, events=[])
    assert any(
        is_source_file_cleanup(statement) for statement in statements
    )


def test_authoritative_discards_observed_content_before_rebuild_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    reads: list[Path] = []
    original = indexer_module.read_scanned_file_bytes

    def counted_reader(repo_path: Path, scanned_file: Any, **kwargs: Any) -> bytes:
        reads.append(scanned_file.path)
        return original(repo_path, scanned_file, **kwargs)

    monkeypatch.setattr(indexer_module, "read_scanned_file_bytes", counted_reader)

    _build(repo)
    assert reads == [Path("App.java"), Path("notes.md")]

    reads.clear()
    _build(repo)
    assert reads == []


def test_authoritative_hash_detects_same_size_same_mtime_content_edit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int aa; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = source.stat()
    source.write_text("class App { int bb; }\n", encoding="utf-8")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    stored = SQLiteStore(repo / ".context-search" / "index.sqlite").source_file_for_path(
        Path("App.java")
    )
    assert stored is not None
    assert stored.sha256 != ""
    assert stored.sha256 == __import__("hashlib").sha256(source.read_bytes()).hexdigest()


def test_manifest_v1_upgrade_reuses_the_immutable_vector_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    descriptor_path = index_dir / "vector_snapshot.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    for key in ("vectors_bytes", "ids_bytes", "normalization"):
        descriptor.pop(key, None)
    descriptor["schema_version"] = 1
    descriptor_path.write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    vector_path = index_dir / descriptor["vectors_file"]
    ids_path = index_dir / descriptor["ids_file"]
    vector_before = vector_path.read_bytes()
    ids_before = ids_path.read_bytes()
    generation = descriptor["generation"]
    manifest = load_manifest(repo)
    legacy_manifest = {
        "schema_version": 1,
        "embedding_config_hash": manifest.embedding_config_hash,
        "embedding_provider": manifest.embedding_provider,
        "embedding_model": manifest.embedding_model,
        "embedding_dimensions": manifest.embedding_dimensions,
        "total_files": manifest.total_files,
        "total_chunks": manifest.total_chunks,
    }
    (index_dir / "manifest.json").write_text(
        json.dumps(legacy_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with sqlite3.connect(index_dir / "index.sqlite") as connection:
        connection.execute("DELETE FROM index_metadata WHERE key LIKE 'operational_%'")

    class _ForbiddenProvider:
        def fingerprint(self) -> dict[str, object]:
            raise AssertionError("v1 upgrade validated an unused provider")

        def embed_texts(self, texts: list[str]):
            raise AssertionError("v1 upgrade re-embedded unchanged source")

    summary = _build(repo, embedding_provider=_ForbiddenProvider())

    upgraded_descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert upgraded_descriptor is not None
    assert upgraded_descriptor.descriptor.schema_version == 2
    assert upgraded_descriptor.descriptor.generation == generation
    assert vector_path.read_bytes() == vector_before
    assert ids_path.read_bytes() == ids_before
    assert summary.files_indexed == 0
    assert isinstance(load_manifest(repo), ManifestV2)
    assert SQLiteStore(index_dir / "index.sqlite").read_operational_snapshot() is not None


def test_config_edit_after_closing_fence_is_not_overwritten(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    edited = b"[index]\nexclude = [\"App.java\"]\n"

    def edit_after_fence(stage: str) -> None:
        if stage == "closing_inventory_complete":
            (repo / ".context-search" / "config.toml").write_bytes(edited)

    _build(repo, fault_hook=edit_after_fence)

    assert (repo / ".context-search" / "config.toml").read_bytes() == edited


def test_quick_refresh_missing_legacy_and_busy_are_non_mutating(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    missing_result = _refresh(missing)
    assert missing_result.ok is False
    assert missing_result.code == "missing_index"
    assert missing_result.network_egress_outcome == "not_attempted"
    assert not (missing / ".context-search").exists()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    current = load_manifest(repo)
    assert isinstance(current, ManifestV2)
    write_manifest(
        repo,
        Manifest(
            embedding_config_hash=current.embedding_config_hash,
            embedding_provider=current.embedding_provider,
            embedding_model=current.embedding_model,
            embedding_dimensions=current.embedding_dimensions,
            total_files=current.total_files,
            total_chunks=current.total_chunks,
        ),
    )
    before_legacy = _snapshot_bytes(repo)
    legacy_result = _refresh(repo)
    assert legacy_result.ok is False
    assert legacy_result.code == "authoritative_index_required"
    assert _snapshot_bytes(repo) == before_legacy

    index_repository(repo, DEFAULT_CONFIG)
    before_busy = _snapshot_bytes(repo)
    with exclusive_index_lock(repo / ".context-search"):
        busy_result = _refresh(
            repo,
            inventory_observer=lambda *_args: pytest.fail(
                "busy refresh performed an inventory"
            ),
        )
    assert busy_result.ok is False
    assert busy_result.code == "index_busy"
    assert busy_result.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before_busy


def test_quick_refresh_noop_has_exact_zero_work_and_never_rewrites_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    before_manifest = load_manifest(repo)
    assert isinstance(before_manifest, ManifestV2)
    inventory_calls = 0

    def inventory_reader(repo_path: Path, config: Any):
        nonlocal inventory_calls
        inventory_calls += 1
        return observe_workspace(repo_path, config)

    def forbidden(*_args: Any, **_kwargs: Any):
        raise AssertionError("zero-work refresh crossed a mutation/body seam")

    monkeypatch.setattr(sqlite_store_module, "_maintenance_counts", forbidden)

    for name in (
        "mark_graph_stale",
        "replace_chunks",
        "replace_signals",
        "replace_relations",
        "replace_operational_observations",
        "upsert_source_file",
        "mark_file_deleted",
        "commit_operational_ready_v1",
    ):
        monkeypatch.setattr(SQLiteStore, name, forbidden)
    for name in (
        "freeze_generation_v2",
        "materialize_frozen_generation",
        "publish_generation",
    ):
        monkeypatch.setattr(NumpyVectorStore, name, forbidden)

    result = _refresh(
        repo,
        inventory_observer=inventory_reader,
        observed_reader=forbidden,
        embedding_provider=forbidden,
    )

    assert result.ok is True
    assert result.freshness == "metadata_fresh"
    assert result.network_egress_performed is False
    assert inventory_calls == 2
    assert _snapshot_bytes(repo) == before
    summary = result.summary.to_dict()
    assert summary["operation"] == "quick_refresh"
    assert summary["outcome"] == "ready"
    assert summary["verification"] == "metadata"
    assert summary["observation_generation"] == before_manifest.manifest_generation
    assert summary["files"] == {
        "direct_dirty": 0,
        "content_changed": 0,
        "metadata_only": 0,
        "dependent_rebuild": 0,
        "dependent_rebuilds": [],
        "deleted": 0,
        "coverage_skips": 0,
        "parsed": 0,
    }
    assert summary["chunks"] == {"embedded": 0}
    assert summary["work"]["inventory"] == {
        "passes": 2,
        "entries": 2,
        "errors": 0,
        "retryable_skip_attempts": 0,
    }
    assert summary["work"]["source"] == {
        "bytes_read": 0,
        "bytes_hashed": 0,
    }
    assert summary["work"]["path_index"] == {
        "builds": 0,
        "paths_canonicalized": 0,
    }
    assert summary["work"]["graph"] == {
        "relations_scanned": 0,
        "relations_resolved": 0,
        "association_inputs": 0,
        "association_writes": 0,
    }
    assert summary["work"]["vector"] == {
        "bytes_read": 0,
        "bytes_copied": 0,
        "bytes_written": 0,
        "bytes_hashed": 0,
        "payload_passes": 0,
        "prior_payload_passes": 0,
        "prepared_payload_passes": 0,
        "generations_before": 1,
        "generations_after": 1,
        "descriptor_action": "reused",
    }
    maintenance = summary["work"]["maintenance"]
    assert maintenance["tombstones_before"] == 0
    assert maintenance["tombstones_purged"] == 0
    assert maintenance["tombstones_after"] == 0
    assert maintenance["sqlite_pages_before"] > 0
    assert maintenance["sqlite_pages_after"] == maintenance["sqlite_pages_before"]
    assert maintenance["sqlite_freelist_after"] == maintenance["sqlite_freelist_before"]


def test_quick_refresh_hashes_only_dirty_metadata_and_reuses_equal_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = source.stat()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    reads: list[Path] = []
    events: list[str] = []

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        reads.append(observation.path)
        return read_observed_file(repo_path, observation, **kwargs)

    result = _refresh(
        repo,
        events=events,
        observed_reader=source_reader,
    )

    assert result.ok is True
    assert reads == [Path("App.java")]
    assert events == []
    summary = result.summary.to_dict()
    assert summary["files"]["direct_dirty"] == 1
    assert summary["files"]["content_changed"] == 0
    assert summary["files"]["metadata_only"] == 1
    assert summary["files"]["parsed"] == 0
    assert summary["chunks"]["embedded"] == 0
    assert summary["work"]["source"] == {
        "bytes_read": len(b"class App {}\n"),
        "bytes_hashed": len(b"class App {}\n"),
    }
    assert summary["work"]["vector"]["descriptor_action"] == "reused"
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    assert manifest.operation_mode == "quick_refresh"


def test_quick_refresh_closing_drift_and_incomplete_inventory_preserve_ready(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    source.write_text("class App { int changed; }\n", encoding="utf-8")
    before = _snapshot_bytes(repo)
    calls = 0

    def drifting_inventory(repo_path: Path, config: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("class App { int drifted; }\n", encoding="utf-8")
        return observe_workspace(repo_path, config)

    drifted = _refresh(repo, inventory_observer=drifting_inventory)
    assert drifted.ok is False
    assert drifted.code == "workspace_changed"
    assert drifted.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before

    complete = observe_workspace(repo, DEFAULT_CONFIG)
    incomplete = replace(
        complete,
        complete=False,
        unscannable_subtrees=("blocked",),
    )
    before_incomplete = _snapshot_bytes(repo)
    failed = _refresh(repo, inventory_observer=lambda *_args: incomplete)
    assert failed.ok is False
    assert failed.code == "inventory_incomplete"
    assert failed.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before_incomplete


def test_quick_refresh_configuration_legality_matrix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    before_manifest = load_manifest(repo)
    assert isinstance(before_manifest, ManifestV2)

    retrieval_only = replace(
        DEFAULT_CONFIG,
        retrieval=replace(
            DEFAULT_CONFIG.retrieval,
            final_top_k=DEFAULT_CONFIG.retrieval.final_top_k + 1,
        ),
    )
    no_index_work = _refresh(repo, retrieval_only)
    assert no_index_work.ok is True
    assert no_index_work.summary.observation_generation == (
        before_manifest.manifest_generation
    )
    assert _snapshot_bytes(repo) == before

    incompatible = replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="hash",
            model="hash-v1",
            dimensions=DEFAULT_CONFIG.embedding.dimensions + 1,
        ),
    )
    rejected = _refresh(repo, incompatible)
    assert rejected.ok is False
    assert rejected.code == "authoritative_index_required"
    assert rejected.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before

    scanner_changed = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, exclude=["App.java"]),
    )
    refreshed = _refresh(repo, scanner_changed)
    assert refreshed.ok is True
    assert refreshed.summary.files.deleted == 1
    assert refreshed.summary.work.vector.descriptor_action == "published"
    assert SQLiteStore(repo / ".context-search" / "index.sqlite").stats()[
        "source_files"
    ] == 0


def test_quick_refresh_future_schemas_and_stable_corruption_are_exact(
    tmp_path: Path,
) -> None:
    def indexed_repo(name: str) -> Path:
        repo = tmp_path / name
        repo.mkdir()
        (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
        index_repository(repo, DEFAULT_CONFIG)
        return repo

    future_manifest = indexed_repo("future-manifest")
    manifest_path = future_manifest / ".context-search" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    before = _snapshot_bytes(future_manifest)
    result = _refresh(future_manifest)
    assert result.ok is False and result.code == "incompatible_manifest_schema"
    assert _snapshot_bytes(future_manifest) == before

    future_operational = indexed_repo("future-operational")
    store = SQLiteStore(future_operational / ".context-search" / "index.sqlite")
    store.set_metadata(OPERATIONAL_SCHEMA_VERSION_KEY, "99")
    before = _snapshot_bytes(future_operational)
    result = _refresh(future_operational)
    assert result.ok is False and result.code == "incompatible_operational_schema"
    assert _snapshot_bytes(future_operational) == before

    future_graph = indexed_repo("future-graph")
    SQLiteStore(future_graph / ".context-search" / "index.sqlite").set_metadata(
        "signal_schema_version", "99"
    )
    before = _snapshot_bytes(future_graph)
    result = _refresh(future_graph)
    assert result.ok is False and result.code == "incompatible_signal_schema"
    assert _snapshot_bytes(future_graph) == before

    corrupt = indexed_repo("corrupt")
    descriptor_path = corrupt / ".context-search" / "vector_snapshot.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["row_count"] += 1
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    before = _snapshot_bytes(corrupt)
    result = _refresh(corrupt)
    assert result.ok is False
    assert result.code == "authoritative_index_required"
    assert result.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(corrupt) == before


def test_quick_refresh_retries_confirmed_orphans_before_preparing_a_third_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool import index_health

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int generationOne; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    original_cleanup = NumpyVectorStore.cleanup_unreferenced_generations

    def cleanup_failure(cls, *_args: Any, **_kwargs: Any) -> int:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(
        NumpyVectorStore,
        "cleanup_unreferenced_generations",
        classmethod(cleanup_failure),
    )
    source.write_text("class App { int generationTwo; }\n", encoding="utf-8")
    first = _refresh(repo)

    assert first.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2
    report = index_health.inspect_repository_health(repo, mode="quick")
    assert report.diagnostics is not None
    assert any(item.code == "orphan_generation" for item in report.diagnostics)

    source.write_text("class App { int generationThree; }\n", encoding="utf-8")
    retry_failed = _refresh(repo)

    assert retry_failed.ok is False
    assert retry_failed.code == "refresh_failed"
    assert retry_failed.network_egress_outcome == "not_attempted"
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    monkeypatch.setattr(
        NumpyVectorStore,
        "cleanup_unreferenced_generations",
        original_cleanup,
    )

    def fail_after_prepare(stage: str) -> None:
        if stage == "vectors_prepared":
            raise RuntimeError("post-prepare fault")

    prepared_failure = _refresh(repo, fault_hook=fail_after_prepare)
    assert prepared_failure.ok is False
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    recovered = _refresh(repo)
    assert recovered.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1
    assert index_health.inspect_repository_health(repo, mode="quick").health == (
        "healthy_metadata"
    )


def test_authoritative_v1_migration_cleans_safe_historical_generations(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    current = load_manifest(repo)
    assert isinstance(current, ManifestV2)
    index_dir = repo / ".context-search"
    _descriptor, vector_store = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=current.embedding_config_hash,
    )
    vector_store.prepare_generation_v2(
        generation="historical-p5",
        embedding_identity=current.embedding_config_hash,
        normalization="none",
    )
    write_manifest(
        repo,
        Manifest(
            embedding_config_hash=current.embedding_config_hash,
            embedding_provider=current.embedding_provider,
            embedding_model=current.embedding_model,
            embedding_dimensions=current.embedding_dimensions,
            total_files=current.total_files,
            total_chunks=current.total_chunks,
        ),
    )
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    assert isinstance(load_manifest(repo), ManifestV2)
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1
    NumpyVectorStore.verify_published_snapshot(
        index_dir,
        expected_ids=SQLiteStore(index_dir / "index.sqlite").active_embedding_ids(),
    )


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_authoritative_descriptor_inspection_failure_blocks_third_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    _descriptor, vector_store = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=manifest.embedding_config_hash,
    )
    vector_store.prepare_generation_v2(
        generation="orphan-before-authoritative-retry",
        embedding_identity=manifest.embedding_config_hash,
        normalization="none",
    )
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    def unreadable_descriptor(cls, *_args: Any, **_kwargs: Any):
        raise error_type("sensitive descriptor detail")

    def forbidden_prepare(*_args: Any, **_kwargs: Any):
        raise AssertionError("authoritative preparation started before cleanup")

    monkeypatch.setattr(
        NumpyVectorStore,
        "inspect_published_descriptor",
        classmethod(unreadable_descriptor),
    )
    monkeypatch.setattr(
        indexer_module,
        "_prepare_authoritative_index",
        forbidden_prepare,
    )

    with pytest.raises(
        ValueError,
        match="vector generation cleanup requires a readable descriptor",
    ) as caught:
        index_repository(repo, DEFAULT_CONFIG)

    assert "sensitive descriptor detail" not in str(caught.value)
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2


def test_authoritative_cleanup_skips_descriptor_inspection_with_one_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    calls = 0

    def transient_failure(cls, *_args: Any, **_kwargs: Any):
        nonlocal calls
        calls += 1
        raise OSError("transient descriptor failure")

    monkeypatch.setattr(
        NumpyVectorStore,
        "inspect_published_descriptor",
        classmethod(transient_failure),
    )

    indexer_module._retry_existing_vector_generation_cleanup(
        repo,
        SQLiteStore(index_dir / "index.sqlite"),
    )

    assert calls == 0
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1


def test_authoritative_writer_ignores_an_unsafe_incomplete_generation_decoy(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    outside = tmp_path / "outside.npy"
    outside.write_bytes(b"outside")
    decoy = index_dir / "vectors.decoy.npy"
    decoy.symlink_to(outside)

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    assert decoy.is_symlink()
    assert outside.read_bytes() == b"outside"
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1


def test_quick_refresh_orphan_retry_fails_closed_under_persistent_wal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int generationOne; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    db_path = index_dir / "index.sqlite"

    def cleanup_failure(cls, *_args: Any, **_kwargs: Any) -> int:
        raise OSError("injected cleanup failure")

    source.write_text("class App { int generationTwo; }\n", encoding="utf-8")
    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(
            NumpyVectorStore,
            "cleanup_unreferenced_generations",
            classmethod(cleanup_failure),
        )
        first = _refresh(repo)
    assert first.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    with sqlite3.connect(db_path) as connection:
        actual_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert str(actual_mode).upper() == "WAL"
    store = SQLiteStore(db_path)
    assert store.journal_mode() == "WAL"
    source.write_text("class App { int generationThree; }\n", encoding="utf-8")
    reader_called = False

    def forbidden_reader(*_args: Any, **_kwargs: Any):
        nonlocal reader_called
        reader_called = True
        raise AssertionError("WAL cleanup failure reached source preparation")

    blocked = _refresh(repo, observed_reader=forbidden_reader)

    assert blocked.ok is False
    assert blocked.code == "refresh_failed"
    assert reader_called is False
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    with sqlite3.connect(db_path) as connection:
        assert str(
            connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        ).upper() == "DELETE"
    assert store.journal_mode() == "DELETE"

    recovered = _refresh(repo)

    assert recovered.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1


def test_quick_refresh_maintenance_purges_each_table_and_orphan_symbols(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    row_count = 5_001

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO code_signals (
                signal_id, chunk_id, file_path, kind, name, qualified_name,
                signature, arity, project_unit_key, producer, start_line,
                end_line, start_column, end_column, language, recallable,
                tokens, metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"deleted-signal-{index}",
                    f"deleted-chunk-{index}",
                    "deleted.java",
                    "method",
                    "deleted",
                    "Deleted.deleted",
                    "deleted()",
                    0,
                    ".",
                    "fixture",
                    1,
                    1,
                    0,
                    1,
                    "java",
                    0,
                    "[]",
                    "{}",
                    1,
                )
                for index in range(row_count)
            ),
        )
        connection.executemany(
            """
            INSERT INTO code_relations (
                relation_id, source_signal_id, source_chunk_id,
                source_file_path, target_name, kind, confidence, target_kind,
                target_qualified_name, target_signature, target_arity,
                target_project_unit_key, target_signal_id, resolution,
                producer, producer_confidence, resolution_confidence,
                metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"deleted-relation-{index}",
                    f"deleted-signal-{index}",
                    f"deleted-chunk-{index}",
                    "deleted.java",
                    "Deleted.target",
                    "tests",
                    1.0,
                    "method",
                    "Deleted.target",
                    "target()",
                    0,
                    ".",
                    "",
                    "unresolved",
                    "test_association",
                    1.0,
                    None,
                    "{}",
                    1,
                )
                for index in range(row_count)
            ),
        )
        connection.executemany(
            """
            INSERT INTO symbols (
                name, kind, start_line, end_line, language, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (f"orphan-{index}", "field", 1, 1, "java", "{}")
                for index in range(row_count)
            ),
        )
        connection.commit()

    source.write_text("class App { int after; }\n", encoding="utf-8")
    result = _refresh(repo)

    assert result.ok is True
    assert result.summary.work.maintenance.tombstones_purged > 0
    with sqlite3.connect(db_path) as connection:
        deleted_signals = connection.execute(
            "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
        deleted_relations = connection.execute(
            "SELECT COUNT(*) FROM code_relations WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
        orphan_symbols = connection.execute(
            """
            SELECT COUNT(*)
            FROM symbols
            LEFT JOIN chunk_symbols USING (symbol_id)
            WHERE chunk_symbols.symbol_id IS NULL
            """
        ).fetchone()[0]
    assert deleted_signals <= 5_000
    assert deleted_relations <= 5_000
    assert orphan_symbols <= 5_000
    assert NumpyVectorStore.verify_published_snapshot(
        repo / ".context-search",
        expected_ids=SQLiteStore(db_path).active_embedding_ids(),
    )


def test_quick_refresh_reports_orphan_symbol_maintenance_work(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    store = SQLiteStore(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO symbols (
                name, kind, start_line, end_line, language, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (f"orphan-only-{index}", "field", 1, 1, "java", "{}")
                for index in range(5_001)
            ),
        )
        connection.commit()

    assert store.tombstone_count() == 5_001
    source.write_text("class App { int after; }\n", encoding="utf-8")
    result = _refresh(repo)

    assert result.ok is True
    assert result.summary.work.maintenance.tombstones_purged == 5_000
    assert store.maintenance_counts()["orphan_symbols"] <= 5_000


def test_relation_maintenance_uses_one_shared_physical_table_batch(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO code_relations (
                relation_id, source_signal_id, source_chunk_id,
                source_file_path, target_name, kind, confidence, target_kind,
                target_qualified_name, target_signature, target_arity,
                target_project_unit_key, target_signal_id, resolution,
                producer, producer_confidence, resolution_confidence,
                metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"bounded-association-{index}",
                    f"missing-signal-{index}",
                    f"missing-chunk-{index}",
                    "deleted-test.java",
                    "Deleted.target",
                    "tests",
                    1.0,
                    "method",
                    "Deleted.target",
                    "target()",
                    0,
                    ".",
                    "",
                    "unresolved",
                    "test_association",
                    1.0,
                    None,
                    "{}",
                    1,
                )
                for index in range(10_001)
            ),
        )
        connection.commit()

    source.write_text("class App { int after; }\n", encoding="utf-8")
    result = _refresh(repo)

    assert result.ok is True
    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute(
            """
            SELECT COUNT(*)
            FROM code_relations
            WHERE producer = 'test_association' AND deleted_at IS NOT NULL
            """
        ).fetchone()[0]
    assert remaining == 5_001
    assert result.summary.work.maintenance.tombstones_purged == 5_000


def test_maintenance_leaves_below_threshold_chunk_tombstones_when_signals_trigger(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int first; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    store = SQLiteStore(db_path)

    source.write_text("class App { int second; }\n", encoding="utf-8")
    assert _refresh(repo).ok is True
    preserved_chunk_ids = store.deleted_chunk_ids()
    assert preserved_chunk_ids
    with sqlite3.connect(db_path) as connection:
        placeholders = ", ".join("?" for _ in preserved_chunk_ids)
        assert connection.execute(
            f"SELECT COUNT(*) FROM chunks_fts WHERE chunk_id IN ({placeholders})",
            tuple(sorted(preserved_chunk_ids)),
        ).fetchone()[0] == 0
        connection.executemany(
            """
            INSERT INTO code_signals (
                signal_id, chunk_id, file_path, kind, name, qualified_name,
                signature, arity, project_unit_key, producer, start_line,
                end_line, start_column, end_column, language, recallable,
                tokens, metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"maintenance-signal-{index}",
                    f"missing-chunk-{index}",
                    "deleted.java",
                    "method",
                    "deleted",
                    "Deleted.deleted",
                    "deleted()",
                    0,
                    ".",
                    "fixture",
                    1,
                    1,
                    0,
                    1,
                    "java",
                    0,
                    "[]",
                    "{}",
                    1,
                )
                for index in range(5_001)
            ),
        )
        connection.commit()

    source.write_text("class App { int third; }\n", encoding="utf-8")
    result = _refresh(repo)

    assert result.ok is True
    assert preserved_chunk_ids <= store.deleted_chunk_ids()
    assert store.maintenance_counts()["deleted_signals"] <= 5_000
    with sqlite3.connect(db_path) as connection:
        placeholders = ", ".join("?" for _ in preserved_chunk_ids)
        assert connection.execute(
            f"SELECT COUNT(*) FROM chunks_fts WHERE chunk_id IN ({placeholders})",
            tuple(sorted(preserved_chunk_ids)),
        ).fetchone()[0] == 0


def test_maintenance_purge_rolls_back_with_the_final_ready_transaction(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    store = SQLiteStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO symbols (
                name, kind, start_line, end_line, language, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (f"rollback-orphan-{index}", "field", 1, 1, "java", "{}")
                for index in range(5_001)
            ),
        )
        connection.commit()

    source.write_text("class App { int after; }\n", encoding="utf-8")
    committed_before_purge: dict[str, int] = {}

    def fail_before_ready_commit(stage: str) -> None:
        if stage == "before_ready_commit":
            committed_before_purge.update(store.maintenance_counts())
            raise RuntimeError("injected maintenance rollback")

    failed = _refresh(repo, fault_hook=fail_before_ready_commit)

    assert failed.ok is False
    assert failed.code == "refresh_failed"
    assert committed_before_purge["orphan_symbols"] > 5_000
    assert store.maintenance_counts() == committed_before_purge

    retry = _refresh(repo)
    assert retry.ok is False
    assert retry.code == "authoritative_index_required"
    index_repository(repo, DEFAULT_CONFIG)
    source.write_text("class App { int final; }\n", encoding="utf-8")
    recovered = _refresh(repo)

    assert recovered.ok is True
    assert recovered.summary.work.maintenance.tombstones_purged == 5_000
    assert store.maintenance_counts()["orphan_symbols"] <= 5_000


def test_quick_refresh_100_step_scaled_churn_preserves_exact_ready_state(
    tmp_path: Path,
) -> None:
    from context_search_tool import index_health
    from context_search_tool.retrieval import query_repository

    schedule = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "p6_performance"
            / "workload_manifest.json"
        ).read_text(encoding="utf-8")
    )["edit_schedule"]
    assert schedule["steps"] == 100
    assert schedule["cycle_length"] == 10
    assert schedule["sample_every_steps"] == 10

    repo = tmp_path / "repo"
    repo.mkdir()
    base_paths = [repo / f"Type{index}.java" for index in range(6)]
    for index, path in enumerate(base_paths):
        path.write_text(
            f'class Type{index} {{ String stableToken() {{ return "stableToken"; }} }}\n',
            encoding="utf-8",
        )
    index_repository(repo, DEFAULT_CONFIG)
    original_second = base_paths[1].read_bytes()

    sampled_generations: list[int] = []
    for cycle in range(10):
        added = repo / f"Added{cycle}.java"
        actions = (
            "modify",
            "delete",
            "restore",
            "add",
            "delete_added",
            "equal_content_touch",
            "same_metadata_content_edit",
            "stable_skip",
            "retryable_skip",
            "injected_failure",
        )
        for offset, operation in enumerate(actions):
            if operation == "modify":
                base_paths[0].write_text(
                    f'class Type0 {{ int cycle{cycle}; String stableToken() {{ return "stableToken"; }} }}\n',
                    encoding="utf-8",
                )
                result = _refresh(repo)
            elif operation == "delete":
                base_paths[1].unlink()
                result = _refresh(repo)
            elif operation == "restore":
                base_paths[1].write_bytes(original_second)
                result = _refresh(repo)
            elif operation == "add":
                added.write_text(
                    f"class Added{cycle} {{}}\n",
                    encoding="utf-8",
                )
                result = _refresh(repo)
            elif operation == "delete_added":
                added.unlink()
                result = _refresh(repo)
            elif operation == "equal_content_touch":
                before = base_paths[2].stat()
                os.utime(
                    base_paths[2],
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000),
                )
                result = _refresh(repo)
            elif operation == "same_metadata_content_edit":
                before = base_paths[3].stat()
                payload = base_paths[3].read_text(encoding="utf-8")
                base_paths[3].write_text(
                    payload.replace("Type3", "TyPe3"),
                    encoding="utf-8",
                )
                os.utime(
                    base_paths[3],
                    ns=(before.st_atime_ns, before.st_mtime_ns),
                )
                result = _refresh(repo)
            elif operation in {"stable_skip", "retryable_skip"}:
                target = base_paths[4 if operation == "stable_skip" else 5]
                target.write_text(
                    f"class {target.stem} {{ int skipped{cycle}; }}\n",
                    encoding="utf-8",
                )

                def skipped_reader(
                    repo_path: Path,
                    observation: Any,
                    **kwargs: Any,
                ) -> ObservedFileRead:
                    if observation.path == target.relative_to(repo):
                        return ObservedFileRead(
                            status="skipped",
                            path=observation.path,
                            content=None,
                            sha256=None,
                            size=observation.size,
                            reason=(
                                "too_large"
                                if operation == "stable_skip"
                                else "unreadable"
                            ),
                            retryable=operation == "retryable_skip",
                            metadata=observation.metadata,
                        )
                    return read_observed_file(repo_path, observation, **kwargs)

                result = _refresh(repo, observed_reader=skipped_reader)
            else:
                complete = observe_workspace(repo, DEFAULT_CONFIG)
                incomplete = replace(
                    complete,
                    complete=False,
                    unscannable_subtrees=("injected",),
                )
                result = _refresh(
                    repo,
                    inventory_observer=lambda *_args: incomplete,
                )

            step = cycle * 10 + offset + 1
            if operation == "injected_failure":
                assert result.ok is False
                assert result.code == "inventory_incomplete"
            else:
                assert result.ok is True
            if step % schedule["sample_every_steps"] == 0:
                report = index_health.inspect_repository_health(repo, mode="quick")
                assert report.queryable is True
                bundle = query_repository(repo, "stableToken", DEFAULT_CONFIG)
                assert bundle.results
                store = SQLiteStore(repo / ".context-search" / "index.sqlite")
                NumpyVectorStore.verify_published_snapshot(
                    repo / ".context-search",
                    expected_ids=store.active_embedding_ids(),
                )
                sampled_generations.append(
                    NumpyVectorStore.generation_pair_count(repo / ".context-search")
                )

    assert len(sampled_generations) == 10
    assert max(sampled_generations) == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.tombstone_count() <= 5_000


def test_pre_p8_ready_index_activates_python_producer_exactly_once(
    tmp_path: Path,
) -> None:
    from context_search_tool.graph_lifecycle import (
        GRAPH_PRODUCER_VERSION_KEY,
        read_graph_capability,
    )
    from context_search_tool.python_graph import PythonGraphProducer

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "api.py").write_text(
        "from app.service import build\n\n\ndef handler():\n    return build()\n",
        encoding="utf-8",
    )
    (repo / "app" / "service.py").write_text(
        "def build():\n    return 1\n", encoding="utf-8"
    )

    def _index():
        return build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[PythonGraphProducer()],
            scanner=scan_workspace_v5,
        )

    _index()
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")

    def _python_rows() -> tuple[int, int]:
        with sqlite3.connect(store.db_path) as connection:
            signals = connection.execute(
                "SELECT COUNT(*) FROM code_signals"
                " WHERE producer = 'python_ast' AND deleted_at IS NULL"
            ).fetchone()[0]
            relations = connection.execute(
                "SELECT COUNT(*) FROM code_relations"
                " WHERE producer = 'python_ast' AND resolution != 'obsolete'"
            ).fetchone()[0]
        return signals, relations

    signals, relations = _python_rows()
    assert signals >= 2 and relations >= 1
    assert store.get_metadata(GRAPH_PRODUCER_VERSION_KEY) == "1"

    # Simulate a pre-P8 ready-v5 index: strip the producer version.
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "DELETE FROM index_metadata WHERE key = ?",
            (GRAPH_PRODUCER_VERSION_KEY,),
        )
    capability = read_graph_capability(store)
    assert capability.status == "stale"
    assert capability.stale_reason == "producer_contract_changed"

    # One authoritative run re-parses and restores ready + version 1.
    summary = _index()
    assert summary.files_indexed >= 1
    assert store.get_metadata(GRAPH_PRODUCER_VERSION_KEY) == "1"
    assert read_graph_capability(store).status == "ready"
    signals_after, relations_after = _python_rows()
    assert (signals_after, relations_after) == (signals, relations)

    # The next authoritative run is a no-op for parsing.
    noop = _index()
    assert noop.files_indexed == 0
    assert read_graph_capability(store).status == "ready"

    # A source change reparses; deletion removes its facts.
    (repo / "app" / "service.py").write_text(
        "def build():\n    return 2\n\n\ndef extra():\n    return 3\n",
        encoding="utf-8",
    )
    changed = _index()
    assert changed.files_indexed == 1
    changed_signals, _ = _python_rows()
    assert changed_signals == signals + 1

    (repo / "app" / "service.py").unlink()
    _index()
    with sqlite3.connect(store.db_path) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM code_signals"
            " WHERE producer = 'python_ast' AND deleted_at IS NULL"
            " AND file_path = 'app/service.py'"
        ).fetchone()[0]
    assert remaining == 0
    assert read_graph_capability(store).status == "ready"


def test_bge_quiet_refresh_attests_without_embedding_and_reports_egress(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { int quietIdentity; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    provider = _AttestedBGEProvider(config)

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is True
    assert result.network_egress_performed is True
    assert provider.events == ["preflight"]
    assert provider.embedded_texts == []
    assert _bge_ready_state(repo) == before


def test_bge_v1_transform_requires_authoritative_reindex_before_v2_embedding(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { int legacyTransform; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo, identity=_BGE_V1_IDENTITY)
    before = _bge_ready_state(repo, expected_identity=_BGE_V1_IDENTITY)

    class _QuickMigrationForbiddenProvider(_AttestedBGEProvider):
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            self.events.append("embed")
            self.embedded_texts.extend(texts)
            raise AssertionError(
                "quick refresh migrated bge-input-v1 vectors instead of "
                "requiring authoritative indexing"
            )

    quick_provider = _QuickMigrationForbiddenProvider(
        config,
        identity=_BGE_V2_IDENTITY,
        transform_id="bge-input-v2",
    )

    rejected = _refresh(
        repo,
        config,
        embedding_provider=quick_provider,
    )

    assert rejected.ok is False
    assert (
        _bge_ready_state(repo, expected_identity=_BGE_V1_IDENTITY)
        == before
    )
    assert quick_provider.events == ["preflight"]
    assert quick_provider.embedded_texts == []
    assert rejected.code == "authoritative_index_required"
    assert rejected.network_egress_outcome == "performed"

    authoritative_provider = _AttestedBGEProvider(
        config,
        identity=_BGE_V2_IDENTITY,
        transform_id="bge-input-v2",
    )
    _build_bge(repo, authoritative_provider)

    index_dir = repo / ".context-search"
    after = NumpyVectorStore.inspect_published_descriptor(index_dir)
    manifest = load_manifest(repo)
    operational = SQLiteStore(
        index_dir / "index.sqlite"
    ).read_operational_snapshot()
    assert after is not None
    assert isinstance(manifest, ManifestV2)
    assert operational is not None
    loaded = NumpyVectorStore.load_bound_ready_snapshot(
        index_dir,
        expected_descriptor_sha256=after.sha256,
        expected_generation=after.descriptor.generation,
        expected_vectors_bytes=after.descriptor.vectors_bytes,
        expected_ids_bytes=after.descriptor.ids_bytes,
        expected_row_count=after.descriptor.row_count,
        expected_dimensions=after.descriptor.dimensions,
        expected_embedding_identity=_BGE_V2_IDENTITY,
    )
    assert authoritative_provider.events == ["preflight", "embed", "postflight"]
    assert authoritative_provider.embedded_texts
    assert after.descriptor.generation != before.descriptor_generation
    assert after.descriptor.embedding_identity == _BGE_V2_IDENTITY
    assert manifest.embedding_config_hash == _BGE_CONFIG_HASH
    assert manifest.vector_descriptor_sha256 == after.sha256
    assert operational.graph_status == "ready"
    assert operational.binding.vector_generation == after.descriptor.generation
    assert operational.binding.vector_descriptor_sha256 == after.sha256
    assert loaded.embedding_identity == _BGE_V2_IDENTITY
    assert loaded.ids == tuple(sorted(operational.active_embedding_ids))


def test_bge_quick_refresh_zero_row_digest_drift_publishes_new_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    index_dir = repo / ".context-search"
    before = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert before is not None
    assert before.descriptor.row_count == 0
    assert before.descriptor.dimensions == 3
    assert before.descriptor.embedding_identity == _BGE_IDENTITY
    provider = _AttestedBGEProvider(
        config,
        identity=_BGE_DIGEST_DRIFT_IDENTITY,
        digest=_BGE_DRIFT_DIGEST,
    )

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is True
    assert result.network_egress_performed is True
    assert provider.events == ["preflight"]
    assert provider.embedded_texts == []
    assert result.summary.chunks.embedded == 0
    assert result.summary.work.vector.descriptor_action == "published"
    after = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert after is not None
    assert after.descriptor.generation != before.descriptor.generation
    assert after.descriptor.row_count == 0
    assert after.descriptor.dimensions == 3
    assert after.descriptor.embedding_identity == _BGE_DIGEST_DRIFT_IDENTITY
    assert (index_dir / after.descriptor.vectors_file).is_file()
    assert (index_dir / after.descriptor.ids_file).is_file()

    manifest = load_manifest(repo)
    operational = SQLiteStore(
        index_dir / "index.sqlite"
    ).read_operational_snapshot()
    assert isinstance(manifest, ManifestV2)
    assert operational is not None
    assert manifest.embedding_config_hash == _BGE_CONFIG_HASH
    assert manifest.vector_descriptor_sha256 == after.sha256
    assert operational.graph_status == "ready"
    assert operational.binding.vector_descriptor_sha256 == after.sha256
    assert (
        operational.binding.vector_generation
        == after.descriptor.generation
    )
    loaded_descriptor, loaded = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=_BGE_DIGEST_DRIFT_IDENTITY,
    )
    assert loaded_descriptor == after.descriptor
    assert loaded.ids == ()
    assert loaded.embedding_identity == _BGE_DIGEST_DRIFT_IDENTITY


def test_bge_changed_refresh_uses_one_provider_for_pre_embed_postflight(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    provider = _AttestedBGEProvider(config)

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is True
    assert result.network_egress_performed is True
    assert provider.events == ["preflight", "embed", "postflight"]
    descriptor = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert descriptor is not None
    assert descriptor.descriptor.embedding_identity == _BGE_IDENTITY
    assert result.summary.chunks.embedded == len(provider.embedded_texts) == 1


@pytest.mark.parametrize("source_changed", [False, True])
def test_bge_runtime_drift_refreshes_every_vector_without_mixing_identities(
    tmp_path: Path,
    source_changed: bool,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int original; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert before is not None
    if source_changed:
        source.write_text("class App { int changed; }\n", encoding="utf-8")
    provider = _AttestedBGEProvider(
        config,
        identity=_BGE_DIGEST_DRIFT_IDENTITY,
        digest=_BGE_DRIFT_DIGEST,
    )

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is True
    assert provider.events == ["preflight", "embed", "postflight"]
    after = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    operational = SQLiteStore(
        repo / ".context-search" / "index.sqlite"
    ).read_operational_snapshot()
    assert after is not None
    assert operational is not None
    assert after.descriptor.generation != before.descriptor.generation
    assert after.descriptor.embedding_identity == _BGE_DIGEST_DRIFT_IDENTITY
    assert after.descriptor.row_count == len(operational.active_embedding_ids)
    assert len(provider.embedded_texts) == after.descriptor.row_count


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_egress", "change_source"),
    [
        ("preflight_possible", "bge_unavailable", "possible", False),
        ("preflight_performed", "bge_unavailable", "performed", False),
        ("postflight", "bge_runtime_mismatch", "performed", True),
    ],
)
def test_bge_refresh_failure_reports_provider_egress_and_preserves_ready(
    tmp_path: Path,
    failure: str,
    expected_code: str,
    expected_egress: str,
    change_source: bool,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    if change_source:
        source.write_text("class App { int after; }\n", encoding="utf-8")
    provider = _AttestedBGEProvider(config, failure=failure)

    result = _refresh(repo, config, embedding_provider=provider)

    assert result.ok is False
    assert result.code == expected_code
    assert result.network_egress_outcome == expected_egress
    expected_events = (
        ["preflight", "embed", "postflight"]
        if failure == "postflight"
        else ["preflight"]
    )
    assert provider.events == expected_events
    assert _bge_ready_state(repo) == before


def test_bge_vectors_rename_rollback_preserves_non_generation_decoys(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    index_dir = repo / ".context-search"
    legal_before = _generation_artifacts(index_dir)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    provider = _AttestedBGEProvider(config)
    fault_events: list[str] = []
    legal_delta_at_fault: tuple[str, ...] = ()
    decoy_state: dict[Path, tuple[bytes, int, int]] = {}

    def fail_with_decoys(stage: str) -> None:
        nonlocal legal_delta_at_fault
        fault_events.append(stage)
        if stage != "vectors_rename":
            return
        legal_delta_at_fault = tuple(
            sorted(set(_generation_artifacts(index_dir)) - set(legal_before))
        )
        for name, payload, mode in (
            ("vectors.user-notes.txt", b"preserve vector notes\n", 0o640),
            ("vector_ids.user-notes.txt", b"preserve id notes\n", 0o600),
            (".vectors.user_notes.npy", b"preserve dot vector\n", 0o640),
            (".vector_ids.user_notes.json", b"preserve dot ids\n", 0o600),
        ):
            path = index_dir / name
            path.write_bytes(payload)
            path.chmod(mode)
            metadata = path.stat()
            decoy_state[path] = (
                path.read_bytes(),
                metadata.st_mode & 0o777,
                metadata.st_ino,
            )
        raise _InjectedFault(stage)

    result = _refresh(
        repo,
        config,
        embedding_provider=provider,
        fault_hook=fail_with_decoys,
    )

    assert result.ok is False
    assert result.code == "refresh_failed"
    assert result.network_egress_outcome == "performed"
    assert provider.events == ["preflight", "embed", "postflight"]
    assert fault_events.count("vectors_rename") == 1
    assert len(legal_delta_at_fault) == 1
    assert _GENERATION_ARTIFACT_PATTERNS[0].fullmatch(
        legal_delta_at_fault[0]
    )
    assert _generation_artifacts(index_dir) == legal_before
    assert _bge_ready_state(repo) == before
    assert tuple(path.name for path in decoy_state) == (
        "vectors.user-notes.txt",
        "vector_ids.user-notes.txt",
        ".vectors.user_notes.npy",
        ".vector_ids.user_notes.json",
    )
    for path, expected in decoy_state.items():
        assert path.exists(), f"rollback deleted non-generation decoy {path.name}"
        metadata = path.stat()
        assert (
            path.read_bytes(),
            metadata.st_mode & 0o777,
            metadata.st_ino,
        ) == expected


@pytest.mark.parametrize(
    "artifact_name",
    ["manifest.json", "vector_snapshot.json"],
)
def test_bge_rollback_snapshot_read_swap_never_accepts_external_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    index_dir = repo / ".context-search"
    artifact = index_dir / artifact_name
    original_payload = artifact.read_bytes()
    external_sentinel = tmp_path / f"{artifact_name}.external-sentinel"
    sentinel_payload = bytes([original_payload[0] ^ 0xFF]) + original_payload[1:]
    external_sentinel.write_bytes(sentinel_payload)
    parked = index_dir / f".{artifact_name}.p13-parked"
    provider = _AttestedBGEProvider(config)
    real_postflight = provider.assert_runtime_unchanged
    real_path_open = Path.open
    real_os_open = indexer_module.os.open
    armed = False
    swap_injected = False

    def arm_after_postflight() -> dict[str, object]:
        nonlocal armed
        result = real_postflight()
        armed = True
        return result

    def should_swap(path: Any) -> bool:
        try:
            return (
                armed
                and not swap_injected
                and Path(os.fsdecode(path)).name == artifact_name
            )
        except TypeError:
            return False

    def open_with_adversarial_swap(open_target: Any):
        nonlocal swap_injected
        os.replace(artifact, parked)
        os.symlink(external_sentinel, artifact)
        swap_injected = True
        try:
            return open_target()
        finally:
            artifact.unlink()
            os.replace(parked, artifact)

    def swap_before_path_open(path: Path, *args: Any, **kwargs: Any):
        if not should_swap(path):
            return real_path_open(path, *args, **kwargs)
        return open_with_adversarial_swap(
            lambda: real_path_open(path, *args, **kwargs)
        )

    def swap_before_os_open(
        path: Any,
        flags: int,
        *args: Any,
        **kwargs: Any,
    ):
        if not should_swap(path):
            return real_os_open(path, flags, *args, **kwargs)
        return open_with_adversarial_swap(
            lambda: real_os_open(path, flags, *args, **kwargs)
        )

    monkeypatch.setattr(
        provider,
        "assert_runtime_unchanged",
        arm_after_postflight,
    )
    monkeypatch.setattr(Path, "open", swap_before_path_open)
    monkeypatch.setattr(indexer_module.os, "open", swap_before_os_open)
    caught: OSError | RuntimeError | ValueError | None = None
    try:
        _build_bge(repo, provider)
    except (OSError, RuntimeError, ValueError) as error:
        caught = error
    finally:
        armed = False
        if artifact.is_symlink():
            artifact.unlink()
        if parked.exists():
            os.replace(parked, artifact)

    assert swap_injected is True
    assert caught is not None
    assert _bge_ready_state(repo) == before
    assert str(external_sentinel) not in str(caught)
    assert (index_dir / "manifest.json").read_bytes() != sentinel_payload
    assert (index_dir / "vector_snapshot.json").read_bytes() != sentinel_payload


def test_bge_generation_inventory_symlink_swap_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    index_dir = repo / ".context-search"
    descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert descriptor is not None
    artifact = index_dir / descriptor.descriptor.vectors_file
    external_sentinel = tmp_path / "generation.external-sentinel"
    external_sentinel.write_bytes(b"outside generation inventory\n")
    parked = index_dir / f".{artifact.name}.p13-parked"
    provider = _AttestedBGEProvider(config)
    real_postflight = provider.assert_runtime_unchanged
    real_stat = indexer_module.os.stat
    armed = False
    swap_active = False
    swap_injected = False

    def arm_after_postflight() -> dict[str, object]:
        nonlocal armed
        result = real_postflight()
        armed = True
        return result

    def swap_between_stats(
        path: Any,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ):
        nonlocal swap_active, swap_injected
        candidate = os.fsdecode(path)
        if (
            not armed
            or candidate != artifact.name
            or dir_fd is None
            or follow_symlinks is not False
            or (swap_injected and not swap_active)
        ):
            return real_stat(
                path,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )
        if not swap_active:
            original = real_stat(
                path,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )
            os.replace(artifact, parked)
            os.symlink(external_sentinel, artifact)
            swap_active = True
            swap_injected = True
            return original
        artifact.unlink()
        os.replace(parked, artifact)
        swap_active = False
        return real_stat(
            path,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(
        provider,
        "assert_runtime_unchanged",
        arm_after_postflight,
    )
    monkeypatch.setattr(indexer_module.os, "stat", swap_between_stats)
    caught: OSError | RuntimeError | ValueError | None = None
    try:
        _build_bge(repo, provider)
    except (OSError, RuntimeError, ValueError) as error:
        caught = error
    finally:
        if parked.exists():
            if artifact.exists() or artifact.is_symlink():
                artifact.unlink()
            os.replace(parked, artifact)
            swap_active = False

    assert swap_injected is True
    assert caught is not None
    assert _bge_ready_state(repo) == before
    assert str(external_sentinel) not in str(caught)


def test_bge_capture_destination_connect_failure_closes_source_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    real_connect = sqlite3.connect
    sentinel = _SQLiteConnectBoundaryFailure(
        "injected capture destination connect failure"
    )
    injected_tracebacks: list[Any] = []
    tracked: list[_TrackingSQLiteConnection] = []
    connect_calls = 0

    def connect(*args: Any, **kwargs: Any):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 1:
            connection = _TrackingSQLiteConnection(real_connect(*args, **kwargs))
            tracked.append(connection)
            return connection
        if connect_calls == 2:
            try:
                raise sentinel
            except _SQLiteConnectBoundaryFailure as error:
                injected_tracebacks.append(error.__traceback__)
                raise
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(
        indexer_module,
        "sqlite3",
        SimpleNamespace(connect=connect),
    )
    caught: RuntimeError | None = None
    try:
        _build_bge(repo, _AttestedBGEProvider(config))
    except RuntimeError as error:
        caught = error
    observed_close_calls = [connection.close_calls for connection in tracked]
    for connection in tracked:
        connection.force_close()

    assert caught is sentinel
    assert connect_calls == 2
    assert len(injected_tracebacks) == 1
    assert _traceback_contains(caught.__traceback__, injected_tracebacks[0])
    assert observed_close_calls == [1]
    assert _bge_ready_state(repo) == before


def test_bge_restore_destination_connect_failure_closes_source_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    real_connect = sqlite3.connect
    sentinel = _SQLiteConnectBoundaryFailure(
        "injected restore destination connect failure"
    )
    tracked: list[_TrackingSQLiteConnection] = []
    restore_armed = False
    restore_connect_calls = 0

    def connect(*args: Any, **kwargs: Any):
        nonlocal restore_connect_calls
        if not restore_armed:
            return real_connect(*args, **kwargs)
        restore_connect_calls += 1
        if restore_connect_calls == 1:
            connection = _TrackingSQLiteConnection(real_connect(*args, **kwargs))
            tracked.append(connection)
            return connection
        if restore_connect_calls == 2:
            raise sentinel
        return real_connect(*args, **kwargs)

    def fail_after_capture(stage: str) -> None:
        nonlocal restore_armed
        if stage == "vectors_rename":
            restore_armed = True
            raise _InjectedFault(stage)

    monkeypatch.setattr(
        indexer_module,
        "sqlite3",
        SimpleNamespace(connect=connect),
    )
    caught: RuntimeError | AttributeError | None = None
    try:
        _build_bge(
            repo,
            _AttestedBGEProvider(config),
            fault_hook=fail_after_capture,
        )
    except (RuntimeError, AttributeError) as error:
        caught = error
    observed_close_calls = [connection.close_calls for connection in tracked]
    for connection in tracked:
        connection.force_close()

    assert caught is not None
    assert not isinstance(caught, AttributeError)
    assert str(repo) not in str(caught)
    assert "class App" not in str(caught)
    assert restore_connect_calls == 2
    assert observed_close_calls == [1]


@pytest.mark.parametrize(
    "scenario",
    [
        "capture_success",
        "verify_success",
        "ids_mismatch",
        "search_exception",
        "backup_exception",
    ],
)
def test_bge_rollback_mmap_store_is_closed_once_on_every_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    real_loader = NumpyVectorStore.load_bound_ready_snapshot
    tracked: list[_CloseTrackingVectorStore] = []
    boundary_failure = _VectorStoreBoundaryFailure(
        f"injected {scenario} failure"
    )

    def load_tracking_store(
        _class: type[NumpyVectorStore],
        *args: Any,
        **kwargs: Any,
    ) -> _CloseTrackingVectorStore:
        store = real_loader(*args, **kwargs)
        tracker = _CloseTrackingVectorStore(
            store,
            ids=("mismatched-ready-id",)
            if scenario == "ids_mismatch" and not tracked
            else None,
            search_failure=boundary_failure
            if scenario == "search_exception" and not tracked
            else None,
        )
        tracked.append(tracker)
        return tracker

    monkeypatch.setattr(
        NumpyVectorStore,
        "load_bound_ready_snapshot",
        classmethod(load_tracking_store),
    )
    sqlite_connections: list[_TrackingSQLiteConnection] = []
    if scenario == "backup_exception":
        real_connect = sqlite3.connect
        connect_calls = 0

        def connect(*args: Any, **kwargs: Any):
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                connection = _TrackingSQLiteConnection(
                    real_connect(*args, **kwargs),
                    backup_failure=boundary_failure,
                )
                sqlite_connections.append(connection)
                return connection
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(
            indexer_module,
            "sqlite3",
            SimpleNamespace(connect=connect),
        )

    def fail_before_ready(stage: str) -> None:
        if scenario == "verify_success" and stage == "before_ready_commit":
            raise _InjectedFault(stage)

    caught: RuntimeError | None = None
    try:
        _build_bge(
            repo,
            _AttestedBGEProvider(config),
            fault_hook=fail_before_ready if scenario == "verify_success" else None,
        )
    except RuntimeError as error:
        caught = error
    observed_close_calls = [store.close_calls for store in tracked]
    observed_mapping_closed = [store.mapping.closed for store in tracked]
    for store in tracked:
        store.force_close()
    for connection in sqlite_connections:
        connection.force_close()

    if scenario in {"capture_success", "ids_mismatch"}:
        assert caught is None
    elif scenario == "verify_success":
        assert type(caught) is _InjectedFault
        assert caught.stage == "before_ready_commit"
    else:
        assert caught is boundary_failure
    expected_store_count = 2 if scenario == "verify_success" else 1
    assert len(tracked) == expected_store_count
    assert observed_close_calls == [1] * expected_store_count
    assert observed_mapping_closed == [True] * expected_store_count


@pytest.mark.parametrize(
    ("provider_failure", "fault_stage", "expected_code"),
    [
        ("preflight_possible", None, "bge_unavailable"),
        ("first_batch", None, "bge_unavailable"),
        ("middle_batch", None, "bge_unavailable"),
        ("response_invalid", None, "bge_response_invalid"),
        ("postflight", None, "bge_runtime_mismatch"),
        (None, "freeze_generation_v2", "freeze_generation_v2"),
        (None, "vectors_rename", "vectors_rename"),
        (None, "descriptor_rename", "descriptor_rename"),
        (None, "manifest_v2_rename", "manifest_v2_rename"),
        (None, "before_ready_commit", "before_ready_commit"),
    ],
)
def test_bge_reindex_failure_matrix_restores_the_old_ready_tuple(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_failure: str | None,
    fault_stage: str | None,
    expected_code: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _bge_config()
    keeper, before = _prepare_wal_ready_tuple(repo, config)
    alpha = repo / "Alpha.java"
    beta = repo / "Beta.java"
    alpha.write_text("class Alpha { int afterAlpha; }\n", encoding="utf-8")
    beta.write_text("class Beta { int afterBeta; }\n", encoding="utf-8")
    provider = _AttestedBGEProvider(config, failure=provider_failure)
    fault_events: list[str] = []

    if fault_stage == "freeze_generation_v2":

        def fail_freeze(*_args: Any, **_kwargs: Any):
            fault_events.append("freeze_generation_v2")
            raise _InjectedFault("freeze_generation_v2")

        monkeypatch.setattr(
            NumpyVectorStore,
            "freeze_generation_v2",
            fail_freeze,
        )
        hook = None
    else:

        def fail_stage(stage: str) -> None:
            fault_events.append(stage)
            if stage == fault_stage:
                raise _InjectedFault(stage)

        hook = fail_stage if fault_stage is not None else None

    expected_type = _FakeBGEFailure if provider_failure is not None else _InjectedFault
    try:
        with pytest.raises(expected_type) as caught:
            _build_bge(repo, provider, fault_hook=hook)

        assert type(caught.value) is expected_type
        if provider_failure is not None:
            assert caught.value.code == expected_code
            expected_events = {
                "preflight_possible": ["preflight"],
                "first_batch": ["preflight", "embed"],
                "middle_batch": ["preflight", "embed"],
                "response_invalid": ["preflight", "embed"],
                "postflight": ["preflight", "embed", "postflight"],
            }
            assert provider.events == expected_events[provider_failure]
        else:
            assert caught.value.stage == expected_code
            assert fault_events.count(expected_code) == 1

        assert _vector_prefixed_artifacts(
            repo / ".context-search"
        ) == before.generation_artifacts
        after = _bge_ready_state(repo)
        assert after == before
        _assert_wal_logical_witness(repo)
        if provider_failure == "middle_batch":
            assert provider.successful_embed_responses == 1
    finally:
        keeper.close()


def test_bge_commit_state_probe_database_error_restores_original_fault_and_tuple(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _bge_config()
    keeper, before = _prepare_wal_ready_tuple(repo, config)
    (repo / "Alpha.java").write_text(
        "class Alpha { int afterProbeFailure; }\n",
        encoding="utf-8",
    )
    (repo / "Beta.java").write_text(
        "class Beta { int afterProbeFailure; }\n",
        encoding="utf-8",
    )
    real_read_operational_snapshot = SQLiteStore.read_operational_snapshot
    original_fault = _InjectedFault("before_ready_commit")
    probe_failure = sqlite3.DatabaseError(
        "injected commit-state probe failure"
    )
    probe_armed = False
    probe_injections = 0

    def fail_commit_state_probe(store: SQLiteStore):
        nonlocal probe_armed, probe_injections
        if probe_armed:
            probe_armed = False
            probe_injections += 1
            raise probe_failure
        return real_read_operational_snapshot(store)

    def fail_before_ready_commit(stage: str) -> None:
        nonlocal probe_armed
        if stage == "before_ready_commit":
            probe_armed = True
            raise original_fault

    monkeypatch.setattr(
        SQLiteStore,
        "read_operational_snapshot",
        fail_commit_state_probe,
    )
    caught: sqlite3.DatabaseError | _InjectedFault | None = None
    try:
        try:
            _build_bge(
                repo,
                _AttestedBGEProvider(config),
                fault_hook=fail_before_ready_commit,
            )
        except (sqlite3.DatabaseError, _InjectedFault) as error:
            caught = error

        assert probe_injections == 1
        assert caught is original_fault
        assert type(caught) is _InjectedFault
        assert caught.stage == "before_ready_commit"
        assert _vector_prefixed_artifacts(
            repo / ".context-search"
        ) == before.generation_artifacts
        after = _bge_ready_state(repo)
        assert after == before
        _assert_wal_logical_witness(repo)
    finally:
        keeper.close()


def test_bge_after_ready_fault_keeps_the_new_committed_tuple(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    _force_attested_ready_fixture(repo)
    before = _bge_ready_state(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    fault_events: list[str] = []

    def fail_after_ready(stage: str) -> None:
        fault_events.append(stage)
        if stage == "after_ready_commit":
            raise _InjectedFault(stage)

    with pytest.raises(_InjectedFault) as caught:
        _build_bge(
            repo,
            _AttestedBGEProvider(config),
            fault_hook=fail_after_ready,
        )

    assert type(caught.value) is _InjectedFault
    assert caught.value.stage == "after_ready_commit"
    assert fault_events.count("after_ready_commit") == 1
    after = _bge_ready_state(repo)
    assert after.graph_status == "ready"
    assert after.manifest_sha256 != before.manifest_sha256
    assert after.descriptor_sha256 != before.descriptor_sha256
    assert after.descriptor_generation != before.descriptor_generation
    assert (
        after.manifest_source_content_fingerprint
        != before.manifest_source_content_fingerprint
    )
    assert (
        after.manifest_source_observation_fingerprint
        != before.manifest_source_observation_fingerprint
    )
    assert after.binding.manifest_sha256 == after.manifest_sha256
    assert after.binding.vector_descriptor_sha256 == after.descriptor_sha256
    assert after.binding.vector_generation == after.descriptor_generation
    assert (
        after.binding.source_content_fingerprint
        == after.manifest_source_content_fingerprint
    )
    assert (
        after.binding.source_observation_fingerprint
        == after.manifest_source_observation_fingerprint
    )
    assert (
        f"vectors.{after.descriptor_generation}.npy"
        in after.generation_artifacts
    )
    assert (
        f"vector_ids.{after.descriptor_generation}.json"
        in after.generation_artifacts
    )


def test_bge_restore_failure_fails_closed_instead_of_claiming_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool import index_health
    from context_search_tool.config import render_config
    from context_search_tool.retrieval import query_repository
    from context_search_tool.retrieval_core import candidates

    repo = tmp_path / "repo"
    repo.mkdir()
    config = _bge_config()
    keeper, before = _prepare_wal_ready_tuple(repo, config)
    (repo / ".context-search" / "config.toml").write_text(
        render_config(config),
        encoding="utf-8",
    )
    (repo / "Alpha.java").write_text(
        "class Alpha { int restoreFailure; }\n",
        encoding="utf-8",
    )
    (repo / "Beta.java").write_text(
        "class Beta { int restoreFailure; }\n",
        encoding="utf-8",
    )
    index_dir = repo / ".context-search"
    real_replace = os.replace
    restore_armed = False
    restore_attempted: list[str] = []
    fault_events: list[str] = []

    def fail_restore_replace(source_path, destination_path) -> None:
        destination = Path(destination_path)
        if restore_armed and destination.name in {
            "manifest.json",
            "vector_snapshot.json",
        }:
            restore_attempted.append(destination.name)
            raise _RestoreBoundaryFailure("injected restore rename failure")
        real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", fail_restore_replace)

    def make_restore_impossible(stage: str) -> None:
        nonlocal restore_armed
        fault_events.append(stage)
        if stage == "before_ready_commit":
            restore_armed = True
            raise _InjectedFault(stage)

    try:
        with pytest.raises((RuntimeError, OSError, ValueError)) as caught:
            _build_bge(
                repo,
                _AttestedBGEProvider(config),
                fault_hook=make_restore_impossible,
            )

        assert not isinstance(caught.value, (AssertionError, AttributeError))
        assert fault_events.count("before_ready_commit") == 1
        assert restore_attempted
        error_text = str(caught.value)
        assert str(repo) not in error_text
        assert "restoreFailure" not in error_text
        assert _WAL_WITNESS not in error_text

        operational = SQLiteStore(
            index_dir / "index.sqlite"
        ).read_operational_snapshot()
        assert operational is not None
        assert operational.graph_status != "ready"
        descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
        if descriptor is not None:
            published_as_ready = (
                operational.graph_status == "ready"
                and operational.binding.vector_descriptor_sha256
                == descriptor.sha256
                and operational.binding.vector_generation
                == descriptor.descriptor.generation
            )
            assert published_as_ready is False
            if descriptor.descriptor.generation != before.descriptor_generation:
                assert operational.graph_status != "ready"

        try:
            report = index_health.inspect_repository_health(repo, mode="quick")
        except (RuntimeError, OSError, ValueError) as status_error:
            assert not isinstance(
                status_error,
                (AssertionError, AttributeError),
            )
            status_error_text = str(status_error)
            assert str(repo) not in status_error_text
            assert "restoreFailure" not in status_error_text
            assert _WAL_WITNESS not in status_error_text
        else:
            assert report.queryable is False

        query_provider = _AttestedBGEProvider(config)
        monkeypatch.setattr(
            candidates,
            "provider_from_config",
            lambda _config: query_provider,
        )
        with pytest.raises((RuntimeError, OSError, ValueError)) as query_error:
            query_repository(repo, "WAL logical witness P13", config)
        assert not isinstance(
            query_error.value,
            (AssertionError, AttributeError),
        )
        query_error_text = str(query_error.value)
        assert str(repo) not in query_error_text
        assert "restoreFailure" not in query_error_text
        assert _WAL_WITNESS not in query_error_text
    finally:
        keeper.close()


@pytest.mark.parametrize("provider_name", ["hash", "openai-compatible"])
def test_before_ready_rollback_remains_bge_only(
    tmp_path: Path,
    provider_name: str,
) -> None:
    repo = tmp_path / provider_name
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    if provider_name == "hash":
        config = DEFAULT_CONFIG
        provider = None
    else:
        config = _remote_config()
        provider = _RecordingRemoteProvider()
    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[_RecordingPlugin([])],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )
    before = _snapshot_bytes(repo)
    source.write_text("class App { int after; }\n", encoding="utf-8")
    fault_events: list[str] = []

    def fail_before_ready(stage: str) -> None:
        fault_events.append(stage)
        if stage == "before_ready_commit":
            raise _InjectedFault(stage)

    with pytest.raises(_InjectedFault) as caught:
        build_v5_index_snapshot(
            repo,
            config,
            graph_plugins=[_RecordingPlugin([])],
            scanner=scan_workspace_v5,
            embedding_provider=provider,
            fault_hook=fail_before_ready,
        )

    assert type(caught.value) is _InjectedFault
    assert caught.value.stage == "before_ready_commit"
    assert fault_events.count("before_ready_commit") == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert _snapshot_bytes(repo) != before
