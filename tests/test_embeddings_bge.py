import pytest


def test_bge_provider_can_be_imported() -> None:
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider

    assert BGEEmbeddingProvider is not None
