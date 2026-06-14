# tests/test_embeddings_bge.py
import pytest
import numpy as np
import httpx

from context_search_tool.config import EmbeddingConfig
from context_search_tool.embeddings_bge import BGEEmbeddingProvider


def test_bge_provider_can_be_imported() -> None:
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider


def test_bge_provider_initializes_with_model_name() -> None:
    """Unit test - no network calls."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )

    provider = BGEEmbeddingProvider(config)

    assert provider.config.model == "bge-m3"
    assert provider.config.dimensions == 1024


def test_bge_provider_embeds_text_with_mock_response() -> None:
    """Unit test with mocked Ollama response."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=3
    )

    # Mock Ollama API
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://mock/api/embeddings"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={"embedding": [0.6, 0.0, 0.8]},  # Will be normalized to unit vector
        )

    mock_client = httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url="http://mock"
    )
    provider = BGEEmbeddingProvider(config, client=mock_client)

    vectors = provider.embed_texts(["hello"])

    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0, atol=1e-5)


def test_bge_provider_rejects_invalid_dimensions() -> None:
    """Unit test - dimension mismatch detection."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=512  # Wrong dimension
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"embedding": [0.5] * 1024},  # Returns 1024 dims
        )

    mock_client = httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url="http://mock"
    )
    provider = BGEEmbeddingProvider(config, client=mock_client)

    with pytest.raises(ValueError, match="model produced .* dimensions"):
        provider.embed_texts(["test"])


def test_bge_provider_handles_missing_embedding_field() -> None:
    """Unit test - malformed response handling."""
    config = EmbeddingConfig(provider="bge", model="bge-m3", dimensions=3)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})  # Missing 'embedding'

    mock_client = httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url="http://mock"
    )
    provider = BGEEmbeddingProvider(config, client=mock_client)

    with pytest.raises(ValueError, match="missing 'embedding' field"):
        provider.embed_texts(["test"])


@pytest.mark.slow
@pytest.mark.integration
def test_bge_provider_real_ollama_service() -> None:
    """Integration test - requires Ollama running with bge-m3 model.

    Skip by default: pytest -m "not slow"
    Run explicitly: pytest -m integration
    """
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )
    provider = BGEEmbeddingProvider(config)

    vectors = provider.embed_texts(["hello world", "测试查询"])

    assert len(vectors) == 2
    assert vectors[0].shape == (1024,)
    assert vectors[1].shape == (1024,)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0, atol=1e-5)
    assert np.isclose(np.linalg.norm(vectors[1]), 1.0, atol=1e-5)
