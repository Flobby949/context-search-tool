# src/context_search_tool/embeddings_bge.py
from __future__ import annotations

import numpy as np
import requests

from context_search_tool.config import EmbeddingConfig


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
        self._session.headers.update({"Content-Type": "application/json"})

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for text in texts:
            response = self._session.post(
                "http://localhost:11434/api/embeddings",
                json={"model": self.config.model, "prompt": text},
                timeout=30.0
            )
            response.raise_for_status()

            payload = response.json()
            embedding = payload.get("embedding")
            if embedding is None:
                raise ValueError("ollama response missing 'embedding' field")

            vector = np.asarray(embedding, dtype=np.float32)

            # Normalize to unit vector
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm

            if vector.shape[0] != self.config.dimensions:
                raise ValueError(
                    f"model produced {vector.shape[0]} dimensions, "
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
