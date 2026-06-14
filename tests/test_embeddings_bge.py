# tests/test_embeddings_bge.py
import pytest
import numpy as np
import requests
from unittest.mock import Mock, patch

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


def test_bge_provider_default_session_bypasses_environment_proxies() -> None:
    config = EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024)

    provider = BGEEmbeddingProvider(config)

    assert provider._session.trust_env is False


def test_bge_provider_embeds_text_with_mock_response() -> None:
    """Unit test with mocked Ollama response."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=3
    )

    # Mock requests.Session
    mock_session = Mock(spec=requests.Session)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.6, 0.0, 0.8]]}
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    mock_session.headers = {}

    provider = BGEEmbeddingProvider(config, session=mock_session)
    vectors = provider.embed_texts(["hello"])

    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0, atol=1e-5)
    mock_session.post.assert_called_once_with(
        "http://localhost:11434/api/embed",
        json={"model": "bge-m3", "input": ["hello"]},
        timeout=30.0,
    )


def test_bge_provider_splits_large_embedding_requests() -> None:
    config = EmbeddingConfig(provider="bge", model="bge-m3", dimensions=3)
    mock_session = Mock(spec=requests.Session)
    mock_session.headers = {}

    first_response = Mock()
    first_response.json.return_value = {"embeddings": [[1.0, 0.0, 0.0]]}
    first_response.raise_for_status = Mock()
    second_response = Mock()
    second_response.json.return_value = {
        "embeddings": [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    }
    second_response.raise_for_status = Mock()
    mock_session.post.side_effect = [first_response, second_response]

    provider = BGEEmbeddingProvider(config, session=mock_session)
    vectors = provider.embed_texts(["a" * 4000, "b" * 3000, "small"])

    assert [vector.tolist() for vector in vectors] == [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    assert mock_session.post.call_count == 2


def test_bge_provider_rejects_invalid_dimensions() -> None:
    """Unit test - dimension mismatch detection."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=512  # Wrong dimension
    )

    mock_session = Mock(spec=requests.Session)
    mock_response = Mock()
    mock_response.json.return_value = {"embeddings": [[0.5] * 1024]}
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    mock_session.headers = {}

    provider = BGEEmbeddingProvider(config, session=mock_session)

    with pytest.raises(ValueError, match="model produced .* dimensions"):
        provider.embed_texts(["test"])


def test_bge_provider_handles_missing_embedding_field() -> None:
    """Unit test - malformed response handling."""
    config = EmbeddingConfig(provider="bge", model="bge-m3", dimensions=3)

    mock_session = Mock(spec=requests.Session)
    mock_response = Mock()
    mock_response.json.return_value = {}  # Missing 'embeddings'
    mock_response.raise_for_status = Mock()
    mock_session.post.return_value = mock_response
    mock_session.headers = {}

    provider = BGEEmbeddingProvider(config, session=mock_session)

    with pytest.raises(ValueError, match="missing 'embeddings' field"):
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
