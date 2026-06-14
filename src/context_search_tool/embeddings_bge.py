# src/context_search_tool/embeddings_bge.py
from __future__ import annotations

import numpy as np
import requests

from context_search_tool.config import EmbeddingConfig

_MAX_TEXTS_PER_REQUEST = 8
_MAX_CHARS_PER_REQUEST = 6_000


class BGEEmbeddingProvider:
    """BGE-M3 embedding provider via local Ollama service.

    Requires:
    - Ollama running on localhost:11434
    - bge-m3 model installed: `ollama pull bge-m3`
    """

    def __init__(
        self,
        config: EmbeddingConfig,
        session: requests.Session | None = None,
    ) -> None:
        if config.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        self.config = config
        self._session = session or requests.Session()
        if session is None:
            self._session.trust_env = False
        self._session.headers.update({"Content-Type": "application/json"})

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for batch in _embedding_batches(texts):
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        response = self._session.post(
            "http://localhost:11434/api/embed",
            json={"model": self.config.model, "input": texts},
            timeout=30.0,
        )
        response.raise_for_status()

        payload = response.json()
        embeddings = payload.get("embeddings")
        if embeddings is None:
            raise ValueError("ollama response missing 'embeddings' field")
        if len(embeddings) != len(texts):
            raise ValueError(
                f"embedding response count {len(embeddings)} does not match "
                f"input count {len(texts)}"
            )

        vectors = []
        for index, embedding in enumerate(embeddings):
            vector = np.asarray(embedding, dtype=np.float32)

            # Normalize to unit vector
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm

            if vector.shape[0] != self.config.dimensions:
                raise ValueError(
                    f"model produced {vector.shape[0]} dimensions for response {index}, "
                    f"expected {self.config.dimensions}"
                )

            vectors.append(vector)

        return vectors

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "backend": "ollama",
        }


def _embedding_batches(texts: list[str]) -> list[list[str]]:
    batches = []
    current_batch: list[str] = []
    current_chars = 0
    for text in texts:
        text_chars = len(text)
        would_exceed_count = len(current_batch) >= _MAX_TEXTS_PER_REQUEST
        would_exceed_chars = (
            current_batch and current_chars + text_chars > _MAX_CHARS_PER_REQUEST
        )
        if would_exceed_count or would_exceed_chars:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(text)
        current_chars += text_chars
    if current_batch:
        batches.append(current_batch)
    return batches
