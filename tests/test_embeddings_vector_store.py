import math
import warnings
from pathlib import Path
from unittest.mock import Mock

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


def test_numpy_vector_store_rejects_mismatched_persisted_ids(tmp_path: Path) -> None:
    np.save(
        tmp_path / "vectors.npy",
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )
    (tmp_path / "vector_ids.json").write_text('["chunk-a"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="vector id count"):
        NumpyVectorStore(tmp_path)


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
