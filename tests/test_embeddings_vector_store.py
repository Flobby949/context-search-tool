import math
import warnings
from pathlib import Path

import numpy as np
import pytest

from context_search_tool.config import EmbeddingConfig
from context_search_tool.embeddings import (
    HashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
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
    provider = OpenAICompatibleEmbeddingProvider.for_test(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
            api_key_env="CST_TEST_KEY",
        ),
        response_vectors=[[1.0, 0.0, 0.0]],
    )

    vector = provider.embed_texts(["hello"])[0]

    assert vector.tolist() == [1.0, 0.0, 0.0]


def test_openai_compatible_provider_rejects_response_count_mismatch() -> None:
    provider = OpenAICompatibleEmbeddingProvider.for_test(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
        response_vectors=[[1.0, 0.0, 0.0]],
    )

    with pytest.raises(ValueError, match="embedding response count"):
        provider.embed_texts(["hello", "world"])


def test_openai_compatible_provider_rejects_dimension_mismatch() -> None:
    provider = OpenAICompatibleEmbeddingProvider.for_test(
        config=EmbeddingConfig(
            provider="openai-compatible",
            model="demo-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
        response_vectors=[[1.0, 0.0]],
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


def test_numpy_vector_store_rejects_mismatched_persisted_ids(tmp_path: Path) -> None:
    np.save(
        tmp_path / "vectors.npy",
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )
    (tmp_path / "vector_ids.json").write_text('["chunk-a"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="vector id count"):
        NumpyVectorStore(tmp_path)
