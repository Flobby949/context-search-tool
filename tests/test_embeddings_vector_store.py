import json
import inspect
import io
import math
import sqlite3
import warnings
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from context_search_tool import vector_store as vector_store_module
from context_search_tool.config import DEFAULT_CONFIG, EmbeddingConfig
from context_search_tool.embeddings import (
    HashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from context_search_tool.indexer import index_repository, read_v5_vector_snapshot
from context_search_tool.sqlite_store import GraphReadSession, SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


def test_hash_embedding_provider_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(
        EmbeddingConfig(provider="hash", model="hash-v1", dimensions=16)
    )

    first = provider.embed_texts(["apply audit"])[0]
    second = provider.embed_texts(["apply audit"])[0]

    assert np.allclose(first, second)
    assert np.isclose(np.linalg.norm(first), 1.0)
    assert provider.fingerprint()["dimensions"] == 16


def test_openai_compatible_provider_uses_mock_transport() -> None:
    mock_session = Mock()
    mock_session.headers = {}
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]
    }
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    provider = OpenAICompatibleEmbeddingProvider(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
            api_key_env="CST_TEST_KEY",
        ),
        session=mock_session,
    )

    vector = provider.embed_texts(["hello"])[0]

    assert vector.tolist() == [1.0, 0.0, 0.0]
    mock_session.post.assert_called_once_with(
        "https://example.test/v1/embeddings",
        json={"model": "demo-embedding", "input": ["hello"]},
        timeout=30.0,
    )


def test_openai_compatible_provider_rejects_response_count_mismatch() -> None:
    mock_session = Mock()
    mock_session.headers = {}
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]
    }
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    provider = OpenAICompatibleEmbeddingProvider(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
        session=mock_session,
    )

    with pytest.raises(ValueError, match="embedding response count"):
        provider.embed_texts(["hello", "world"])


def test_openai_compatible_provider_rejects_dimension_mismatch() -> None:
    mock_session = Mock()
    mock_session.headers = {}
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [1.0, 0.0]}]
    }
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    provider = OpenAICompatibleEmbeddingProvider(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
        session=mock_session,
    )

    with pytest.raises(ValueError, match="embedding dimensions"):
        provider.embed_texts(["hello"])


def test_numpy_vector_store_persists_and_filters_deleted(tmp_path: Path) -> None:
    store = NumpyVectorStore(tmp_path)
    store.upsert_many(
        [
            ("chunk-a", np.array([1.0, 0.0], dtype=np.float32)),
            ("chunk-b", np.array([0.0, 1.0], dtype=np.float32)),
        ]
    )
    store.persist()

    reloaded = NumpyVectorStore(tmp_path)
    results = reloaded.search(
        np.array([1.0, 0.0], dtype=np.float32),
        top_k=2,
        deleted_ids={"chunk-a"},
    )

    assert [item.chunk_id for item in results] == ["chunk-b"]


def test_sort_by_id_reuses_an_already_sorted_matrix(tmp_path: Path) -> None:
    store = NumpyVectorStore.fresh(tmp_path, dimensions=2)
    store._ids = ["a", "b"]
    store._vectors = np.asarray(
        [[1.0, 0.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    original = store._vectors

    store.sort_by_id()

    assert store.ids == ("a", "b")
    assert store._vectors is original


def test_l2_validation_uses_bounded_row_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vectors = np.tile(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        (8_193, 1),
    )
    observed_rows: list[int] = []
    original_norm = np.linalg.norm

    def tracked_norm(values: np.ndarray, *args: object, **kwargs: object):
        observed_rows.append(values.shape[0])
        return original_norm(values, *args, **kwargs)

    monkeypatch.setattr(vector_store_module.np.linalg, "norm", tracked_norm)

    vector_store_module._validate_l2_normalization(vectors)

    assert len(observed_rows) == 3
    assert max(observed_rows) <= 4_096


def test_vector_store_bulk_batches_fill_one_normalized_matrix(tmp_path: Path) -> None:
    store = NumpyVectorStore.fresh(tmp_path, dimensions=2)
    batches = iter(
        [
            [
                ("chunk-c", np.asarray([3.0, 4.0], dtype=np.float32)),
                ("chunk-a", np.asarray([0.0, 0.0], dtype=np.float32)),
            ],
            [("chunk-b", np.asarray([np.nan, 2.0], dtype=np.float32))],
        ]
    )

    store.replace_all_batched(
        batches,
        ordered_ids=["chunk-a", "chunk-b", "chunk-c"],
        normalization="l2",
    )
    frozen = store.freeze_generation_v2(
        generation="bulk",
        embedding_identity="fixture",
        normalization="l2",
    )
    vectors = np.load(io.BytesIO(frozen.vectors_payload), allow_pickle=False)

    assert store.ids == ("chunk-a", "chunk-b", "chunk-c")
    assert np.all(np.isfinite(vectors))
    assert np.allclose(vectors[0], [0.0, 0.0])
    assert np.allclose(np.linalg.norm(vectors[1:], axis=1), [1.0, 1.0])


def test_vector_search_sanitizes_non_finite_values(tmp_path: Path) -> None:
    store = NumpyVectorStore(tmp_path)
    store.upsert_many(
        [
            ("finite", np.asarray([1.0, 0.0], dtype=np.float32)),
            ("zero", np.asarray([0.0, 0.0], dtype=np.float32)),
            ("nan", np.asarray([np.nan, 1.0], dtype=np.float32)),
            ("inf", np.asarray([np.inf, 1.0], dtype=np.float32)),
        ]
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        results = store.search(np.asarray([1.0, np.nan], dtype=np.float32), 4, set())

    assert captured == []
    assert [result.chunk_id for result in results] == ["finite", "inf", "nan", "zero"]
    assert all(math.isfinite(result.score) for result in results)


def test_vector_search_does_not_warn_for_finite_realistic_matrix(
    tmp_path: Path,
) -> None:
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(64, 384)).astype(np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    query = rng.normal(size=384).astype(np.float32)
    query = query / np.linalg.norm(query)
    store = NumpyVectorStore(tmp_path)
    store.upsert_many(
        [(f"chunk-{index:02d}", vector) for index, vector in enumerate(vectors)]
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        results = store.search(query, top_k=5, deleted_ids=set())

    assert captured == []
    assert len(results) == 5
    assert all(math.isfinite(result.score) for result in results)


def test_exact_top_k_avoids_full_score_sort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = np.random.default_rng(20260721)
    random_vectors = rng.normal(size=(257, 16)).astype(np.float32)
    random_query = rng.normal(size=16).astype(np.float32)
    cases = [
        ("empty", [], np.empty((0, 2), dtype=np.float32), [1.0, 0.0], 3, set()),
        ("one", ["only"], [[3.0, 4.0]], [3.0, 4.0], 5, set()),
        (
            "ties",
            ["z", "b", "a", "m", "c"],
            [[1.0, 0.0]] * 5,
            [1.0, 0.0],
            3,
            set(),
        ),
        (
            "deleted",
            ["a", "b", "c", "d"],
            [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.0, 1.0]],
            [1.0, 0.0],
            2,
            {"a", "c"},
        ),
        (
            "nonfinite",
            ["finite", "inf", "nan", "zero"],
            [[1.0, 0.0], [np.inf, 1.0], [np.nan, 1.0], [0.0, 0.0]],
            [1.0, np.nan],
            3,
            set(),
        ),
        (
            "random",
            [f"chunk-{index:04d}" for index in range(len(random_vectors))],
            random_vectors,
            random_query,
            7,
            {"chunk-0003", "chunk-0100"},
        ),
    ]
    result_type = vector_store_module.VectorSearchResult
    constructions = 0

    def counted_result(*args, **kwargs):
        nonlocal constructions
        constructions += 1
        return result_type(*args, **kwargs)

    monkeypatch.setattr(vector_store_module, "VectorSearchResult", counted_result)

    for name, ids, raw_vectors, raw_query, top_k, deleted in cases:
        vectors = np.asarray(raw_vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(0, len(raw_query))
        query = np.asarray(raw_query, dtype=np.float32)
        normalized_query = vector_store_module._normalize_vector(query)
        normalized_vectors = vector_store_module._normalize_matrix(vectors)
        scores = np.einsum(
            "ij,j->i",
            normalized_vectors,
            normalized_query,
            optimize=True,
        )
        scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
        expected = [
            result_type(chunk_id=chunk_id, score=float(score))
            for chunk_id, score in zip(ids, scores)
            if chunk_id not in deleted
        ]
        expected.sort(key=lambda item: (-item.score, item.chunk_id))
        expected = expected[:top_k]
        store = NumpyVectorStore.fresh(
            tmp_path / name,
            dimensions=len(raw_query),
        )
        store.upsert_many(list(zip(ids, vectors)))
        constructions = 0

        actual = store.search(query, top_k=top_k, deleted_ids=deleted)

        assert actual == expected
        assert constructions <= len(expected)


def test_ready_query_uses_bound_small_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "def ready_vector_query():\n    return 'ready'\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    expected_ids = store.active_embedding_ids()
    real_np_load = vector_store_module.np.load
    mmap_modes: list[str | None] = []

    def recorded_np_load(*args, **kwargs):
        mmap_modes.append(kwargs.get("mmap_mode"))
        return real_np_load(*args, **kwargs)

    def forbidden_payload_work(*_args, **_kwargs):
        raise AssertionError("ready query performed full payload verification")

    monkeypatch.setattr(vector_store_module.np, "load", recorded_np_load)
    monkeypatch.setattr(vector_store_module, "_sha256_file", forbidden_payload_work)
    monkeypatch.setattr(
        vector_store_module,
        "_sha256_file_safe",
        forbidden_payload_work,
    )
    monkeypatch.setattr(
        vector_store_module,
        "_validate_l2_normalization",
        forbidden_payload_work,
    )
    monkeypatch.setattr(
        GraphReadSession,
        "active_embedding_ids",
        forbidden_payload_work,
    )

    with store.graph_read_session() as session:
        assert session.capability.status == "ready"
        snapshot = read_v5_vector_snapshot(repo, DEFAULT_CONFIG, session)
        assert snapshot is not None
        assert snapshot.ids == tuple(sorted(expected_ids))
        mapping = getattr(snapshot._vectors, "_mmap", None)
        assert mapping is not None
        assert mapping.closed is False

    assert snapshot.ids == ()
    assert mapping.closed is True
    descriptor = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert descriptor is not None
    assert descriptor.descriptor.normalization == "l2"
    assert mmap_modes == ["r"]


def test_graph_read_session_runs_every_close_callback_before_reraising(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("def service(): pass\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    closed: list[str] = []

    def failing_close() -> None:
        closed.append("failing")
        raise RuntimeError("injected close failure")

    with pytest.raises(RuntimeError, match="injected close failure"):
        with store.graph_read_session() as session:
            register_close = getattr(session, "register_close_callback", None)
            assert callable(register_close), "graph session close ownership is absent"
            register_close(lambda: closed.append("first"))
            register_close(failing_close)
            register_close(lambda: closed.append("last"))

    assert closed == ["last", "failing", "first"]


def test_numpy_vector_store_rejects_mismatched_persisted_ids(tmp_path: Path) -> None:
    np.save(
        tmp_path / "vectors.npy",
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )
    (tmp_path / "vector_ids.json").write_text('["chunk-a"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="vector id count"):
        NumpyVectorStore(tmp_path)


def test_fresh_vector_replacement_ignores_corrupt_legacy_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "vectors.npy").write_bytes(b"not numpy")
    (tmp_path / "vector_ids.json").write_text("not json", encoding="utf-8")

    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many(
        [("fresh", np.asarray([1.0, 0.0], dtype=np.float32))]
    )

    assert store.ids == ("fresh",)


def test_empty_immutable_generation_retains_configured_dimensions(
    tmp_path: Path,
) -> None:
    store = NumpyVectorStore.fresh(tmp_path, dimensions=7)
    prepared = store.prepare_generation(
        generation="empty",
        embedding_identity="hash-v1:7",
    )
    store.publish_generation(prepared)

    descriptor = NumpyVectorStore.published_descriptor(tmp_path)

    assert descriptor is not None
    assert descriptor.row_count == 0
    assert descriptor.dimensions == 7
    assert NumpyVectorStore.load_published(tmp_path).ids == ()


def test_immutable_vector_generations_publish_only_one_validated_descriptor(
    tmp_path: Path,
) -> None:
    first = NumpyVectorStore.fresh(tmp_path)
    first.upsert_many(
        [("a", np.asarray([1.0, 0.0], dtype=np.float32))]
    )
    prepared_first = first.prepare_generation(
        generation="g1",
        embedding_identity="hash-v1:2",
    )
    first.publish_generation(prepared_first)

    loaded_first = NumpyVectorStore.load_published(
        tmp_path,
        expected_embedding_identity="hash-v1:2",
    )
    assert loaded_first.ids == ("a",)

    second = NumpyVectorStore.load_published(
        tmp_path,
        expected_embedding_identity="hash-v1:2",
    )
    second.remove_many(["a"])
    second.upsert_many(
        [("b", np.asarray([0.0, 1.0], dtype=np.float32))]
    )
    prepared_second = second.prepare_generation(
        generation="g2",
        embedding_identity="hash-v1:2",
    )

    assert NumpyVectorStore.load_published(tmp_path).ids == ("a",)
    second.publish_generation(prepared_second)
    assert NumpyVectorStore.load_published(tmp_path).ids == ("b",)
    assert (tmp_path / "vectors.g1.npy").is_file()
    assert (tmp_path / "vector_ids.g1.json").is_file()
    assert (tmp_path / "vectors.g2.npy").is_file()
    assert (tmp_path / "vector_ids.g2.json").is_file()


def test_published_snapshot_binds_one_descriptor_to_one_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = NumpyVectorStore.fresh(tmp_path)
    first.upsert_many(
        [("a", np.asarray([1.0, 0.0], dtype=np.float32))]
    )
    prepared_first = first.prepare_generation(
        generation="g1",
        embedding_identity="hash-v1:2",
    )
    first.publish_generation(prepared_first)

    second = NumpyVectorStore.fresh(tmp_path)
    second.upsert_many(
        [("b", np.asarray([0.0, 1.0], dtype=np.float32))]
    )
    prepared_second = second.prepare_generation(
        generation="g2",
        embedding_identity="hash-v1:2",
    )
    original_read_descriptor = vector_store_module._read_descriptor
    swapped = False

    def read_and_swap(path: Path):
        nonlocal swapped
        descriptor = original_read_descriptor(path)
        if not swapped:
            swapped = True
            second.publish_generation(prepared_second)
        return descriptor

    monkeypatch.setattr(vector_store_module, "_read_descriptor", read_and_swap)

    descriptor, loaded = NumpyVectorStore.load_published_snapshot(
        tmp_path,
        expected_embedding_identity="hash-v1:2",
    )

    assert descriptor is not None
    assert descriptor.generation == "g1"
    assert loaded.ids == ("a",)
    published = NumpyVectorStore.published_descriptor(tmp_path)
    assert published is not None
    assert published.generation == "g2"


def test_vector_descriptor_hash_and_embedding_identity_are_validated(
    tmp_path: Path,
) -> None:
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many(
        [("a", np.asarray([1.0, 0.0], dtype=np.float32))]
    )
    prepared = store.prepare_generation(
        generation="g1",
        embedding_identity="hash-v1:2",
    )
    store.publish_generation(prepared)

    with pytest.raises(ValueError, match="embedding identity"):
        NumpyVectorStore.load_published(
            tmp_path,
            expected_embedding_identity="other:2",
        )

    (tmp_path / "vector_ids.g1.json").write_text(
        '["tampered"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash"):
        NumpyVectorStore.load_published(tmp_path)


def test_vector_generation_fault_never_repoints_published_descriptor(
    tmp_path: Path,
) -> None:
    first = NumpyVectorStore.fresh(tmp_path)
    first.upsert_many(
        [("a", np.asarray([1.0, 0.0], dtype=np.float32))]
    )
    prepared = first.prepare_generation(
        generation="g1",
        embedding_identity="hash-v1:2",
    )
    first.publish_generation(prepared)

    second = NumpyVectorStore.fresh(tmp_path)
    second.upsert_many(
        [("b", np.asarray([0.0, 1.0], dtype=np.float32))]
    )

    def fail(stage: str) -> None:
        if stage == "ids_file_fsync":
            raise RuntimeError("vector fault")

    with pytest.raises(RuntimeError, match="vector fault"):
        second.prepare_generation(
            generation="g2",
            embedding_identity="hash-v1:2",
            fault_hook=fail,
        )

    assert NumpyVectorStore.load_published(tmp_path).ids == ("a",)


def test_descriptor_v2_quick_validation_uses_sizes_without_loading_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hasattr(NumpyVectorStore, "prepare_generation_v2"), (
        "P6 descriptor-v2 preparation is absent"
    )
    assert hasattr(NumpyVectorStore, "inspect_published_descriptor"), (
        "P6 quick descriptor inspection is absent"
    )
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many(
        [
            ("a", np.asarray([1.0, 0.0], dtype=np.float32)),
            ("b", np.asarray([0.0, 1.0], dtype=np.float32)),
        ]
    )
    prepared = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="l2",
    )
    store.publish_generation(prepared)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("quick descriptor inspection loaded vector payload")

    monkeypatch.setattr(vector_store_module, "_load_generation", forbidden)
    snapshot = NumpyVectorStore.inspect_published_descriptor(tmp_path)

    assert snapshot is not None
    assert snapshot.descriptor.schema_version == 2
    assert snapshot.descriptor.normalization == "l2"
    assert snapshot.descriptor.vectors_bytes == (
        tmp_path / "vectors.g2.npy"
    ).stat().st_size
    assert snapshot.descriptor.ids_bytes == (
        tmp_path / "vector_ids.g2.json"
    ).stat().st_size
    assert snapshot.byte_size == (tmp_path / "vector_snapshot.json").stat().st_size
    assert len(snapshot.sha256) == 64


def test_descriptor_v2_verified_load_checks_exact_ids_and_normalization(
    tmp_path: Path,
) -> None:
    assert hasattr(NumpyVectorStore, "verify_published_snapshot"), (
        "P6 verified vector inspection is absent"
    )
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many(
        [
            ("a", np.asarray([1.0, 0.0], dtype=np.float32)),
            ("b", np.asarray([0.0, 1.0], dtype=np.float32)),
        ]
    )
    prepared = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="l2",
    )
    store.publish_generation(prepared)

    verified = NumpyVectorStore.verify_published_snapshot(
        tmp_path,
        expected_ids={"a", "b"},
        expected_embedding_identity="hash-v1:2",
    )
    assert verified.ids == ("a", "b")
    with pytest.raises(ValueError, match="exact vector IDs"):
        NumpyVectorStore.verify_published_snapshot(
            tmp_path,
            expected_ids={"a", "missing"},
        )

    vectors_path = tmp_path / "vectors.g2.npy"
    np.save(vectors_path, np.asarray([[2.0, 0.0], [0.0, 2.0]], dtype=np.float32))
    descriptor_path = tmp_path / "vector_snapshot.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["vectors_sha256"] = vector_store_module._sha256_file(vectors_path)
    descriptor["vectors_bytes"] = vectors_path.stat().st_size
    descriptor_path.write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="normalization"):
        NumpyVectorStore.verify_published_snapshot(tmp_path, expected_ids={"a", "b"})


def test_descriptor_v2_verified_load_streams_vector_rows_without_materializing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row_count = 8_193
    store = NumpyVectorStore.fresh(tmp_path, dimensions=2)
    store._ids = [f"chunk-{index:05d}" for index in range(row_count)]
    store._vectors = np.tile(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        (row_count, 1),
    )
    prepared = store.prepare_generation_v2(
        generation="streamed",
        embedding_identity="hash-v1:2",
        normalization="l2",
    )
    store.publish_generation(prepared)

    def forbidden_materialization(*_args: object, **_kwargs: object):
        raise AssertionError("verified inspection materialized the vector matrix")

    observed_rows: list[int] = []
    original_validate = vector_store_module._validate_l2_normalization

    def tracked_validate(vectors: np.ndarray) -> None:
        observed_rows.append(vectors.shape[0])
        original_validate(vectors)

    monkeypatch.setattr(
        vector_store_module,
        "_read_generation_payload",
        forbidden_materialization,
    )
    monkeypatch.setattr(
        vector_store_module,
        "_validate_l2_normalization",
        tracked_validate,
    )

    verified = NumpyVectorStore.verify_published_snapshot(
        tmp_path,
        expected_ids=set(store._ids),
        expected_embedding_identity="hash-v1:2",
    )

    assert verified.ids == tuple(store._ids)
    assert len(observed_rows) == 3
    assert max(observed_rows) <= 4_096


def test_descriptor_v2_rejects_future_schema_size_damage_and_symlink(
    tmp_path: Path,
) -> None:
    assert hasattr(vector_store_module, "IncompatibleVectorDescriptorSchemaError"), (
        "P6 descriptor compatibility error is absent"
    )
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
    prepared = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(prepared)
    descriptor_path = tmp_path / "vector_snapshot.json"
    original = descriptor_path.read_text(encoding="utf-8")
    future = json.loads(original)
    future["schema_version"] = 3
    descriptor_path.write_text(json.dumps(future), encoding="utf-8")

    with pytest.raises(vector_store_module.IncompatibleVectorDescriptorSchemaError):
        NumpyVectorStore.inspect_published_descriptor(tmp_path)

    descriptor_path.write_text(original, encoding="utf-8")
    ids_path = tmp_path / "vector_ids.g2.json"
    ids_path.write_bytes(ids_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="size"):
        NumpyVectorStore.inspect_published_descriptor(tmp_path)

    ids_path.unlink()
    outside = tmp_path.parent / "outside-ids.json"
    outside.write_text('["a"]\n', encoding="utf-8")
    ids_path.symlink_to(outside)
    with pytest.raises(ValueError, match="non-symlink"):
        NumpyVectorStore.inspect_published_descriptor(tmp_path)


def test_provider_from_config_supports_bge() -> None:
    from context_search_tool.embeddings import provider_from_config
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider

    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )

    provider = provider_from_config(config)

    assert isinstance(provider, BGEEmbeddingProvider)
    assert provider.config.model == "bge-m3"


def test_vector_generation_cleanup_keeps_only_safe_referenced_pair(
    tmp_path: Path,
) -> None:
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
    first = store.prepare_generation_v2(
        generation="g1",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(first)
    second = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(second)
    outside = tmp_path.parent / "outside.npy"
    outside.write_bytes(b"outside")
    unsafe = tmp_path / "vectors.unsafe.npy"
    unsafe.symlink_to(outside)

    assert NumpyVectorStore.generation_pair_count(tmp_path) == 2
    removed = NumpyVectorStore.cleanup_unreferenced_generations(
        tmp_path,
        keep_generation="g2",
        journal_mode="DELETE",
    )

    assert removed == 1
    assert NumpyVectorStore.generation_pair_count(tmp_path) == 1
    assert not (tmp_path / "vectors.g1.npy").exists()
    assert not (tmp_path / "vector_ids.g1.json").exists()
    assert (tmp_path / "vectors.g2.npy").exists()
    assert (tmp_path / "vector_ids.g2.json").exists()
    assert unsafe.is_symlink()
    assert outside.read_bytes() == b"outside"


@pytest.mark.parametrize("journal_mode", ["WAL", "MEMORY", "OFF", "unknown"])
def test_vector_generation_cleanup_fails_closed_for_unsafe_journal_modes(
    tmp_path: Path,
    journal_mode: str,
) -> None:
    assert "journal_mode" in inspect.signature(
        NumpyVectorStore.cleanup_unreferenced_generations
    ).parameters, "P6 cleanup journal guard is absent"
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
    first = store.prepare_generation_v2(
        generation="g1",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(first)
    second = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(second)

    with pytest.raises(ValueError, match="rollback-journal"):
        NumpyVectorStore.cleanup_unreferenced_generations(
            tmp_path,
            keep_generation="g2",
            journal_mode=journal_mode,
        )

    assert NumpyVectorStore.generation_pair_count(tmp_path) == 2
    assert (tmp_path / "vectors.g1.npy").exists()
    assert (tmp_path / "vector_ids.g1.json").exists()


@pytest.mark.parametrize("journal_mode", ["DELETE", "truncate", "Persist"])
def test_vector_generation_cleanup_accepts_only_closed_rollback_journal_set(
    tmp_path: Path,
    journal_mode: str,
) -> None:
    assert "journal_mode" in inspect.signature(
        NumpyVectorStore.cleanup_unreferenced_generations
    ).parameters, "P6 cleanup journal guard is absent"
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
    first = store.prepare_generation_v2(
        generation="g1",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(first)
    second = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(second)

    removed = NumpyVectorStore.cleanup_unreferenced_generations(
        tmp_path,
        keep_generation="g2",
        journal_mode=journal_mode,
    )

    assert removed == 1
    assert NumpyVectorStore.generation_pair_count(tmp_path) == 1


@pytest.mark.parametrize(
    ("requested_mode", "cleanup_allowed"),
    [("DELETE", True), ("TRUNCATE", True), ("PERSIST", True), ("WAL", False)],
)
def test_vector_generation_cleanup_uses_live_sqlite_journal_mode(
    tmp_path: Path,
    requested_mode: str,
    cleanup_allowed: bool,
) -> None:
    database = tmp_path / "barrier.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE barrier (value INTEGER)")
        connection.commit()
        actual_mode = str(
            connection.execute(f"PRAGMA journal_mode={requested_mode}").fetchone()[0]
        ).upper()
        assert actual_mode == requested_mode
        live_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).upper()

        index_dir = tmp_path / "vectors"
        store = NumpyVectorStore.fresh(index_dir)
        store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
        first = store.prepare_generation_v2(
            generation="g1",
            embedding_identity="hash-v1:2",
            normalization="none",
        )
        store.publish_generation(first)
        second = store.prepare_generation_v2(
            generation="g2",
            embedding_identity="hash-v1:2",
            normalization="none",
        )
        store.publish_generation(second)
        before = {
            path.name: path.read_bytes()
            for path in index_dir.iterdir()
            if path.name != "vector_snapshot.json"
        }

        if cleanup_allowed:
            assert NumpyVectorStore.cleanup_unreferenced_generations(
                index_dir,
                keep_generation="g2",
                journal_mode=live_mode,
            ) == 1
            assert NumpyVectorStore.generation_pair_count(index_dir) == 1
        else:
            with pytest.raises(ValueError, match="rollback-journal"):
                NumpyVectorStore.cleanup_unreferenced_generations(
                    index_dir,
                    keep_generation="g2",
                    journal_mode=live_mode,
                )
            assert {
                path.name: path.read_bytes()
                for path in index_dir.iterdir()
                if path.name != "vector_snapshot.json"
            } == before


def test_vector_generation_cleanup_leaves_unsafe_mode_and_unknown_names(
    tmp_path: Path,
) -> None:
    assert "journal_mode" in inspect.signature(
        NumpyVectorStore.cleanup_unreferenced_generations
    ).parameters, "P6 cleanup journal guard is absent"
    store = NumpyVectorStore.fresh(tmp_path)
    store.upsert_many([("a", np.asarray([1.0, 0.0], dtype=np.float32))])
    first = store.prepare_generation_v2(
        generation="g1",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(first)
    second = store.prepare_generation_v2(
        generation="g2",
        embedding_identity="hash-v1:2",
        normalization="none",
    )
    store.publish_generation(second)
    unsafe_vector = tmp_path / "vectors.g1.npy"
    unsafe_ids = tmp_path / "vector_ids.g1.json"
    unsafe_vector.chmod(0o666)
    unsafe_ids.chmod(0o666)
    unknown = tmp_path / "vectors.g1.npy.backup"
    unknown.write_bytes(b"keep")

    removed = NumpyVectorStore.cleanup_unreferenced_generations(
        tmp_path,
        keep_generation="g2",
        journal_mode="DELETE",
    )

    assert removed == 0
    assert unsafe_vector.exists()
    assert unsafe_ids.exists()
    assert unknown.read_bytes() == b"keep"
