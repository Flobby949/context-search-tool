from pathlib import Path

import numpy as np

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
