from __future__ import annotations

import hashlib
import os
from typing import Protocol

import httpx
import numpy as np

from context_search_tool.config import EmbeddingConfig


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        ...

    def fingerprint(self) -> dict[str, object]:
        ...


class HashEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig) -> None:
        if config.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        self.config = config

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        return [self._embed_text(text) for text in texts]

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
        }

    def _embed_text(self, text: str) -> np.ndarray:
        vector = np.zeros(self.config.dimensions, dtype=np.float32)
        for token in text.split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.config.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        return _normalize_vector(vector)


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        config: EmbeddingConfig,
        client: httpx.Client | None = None,
    ) -> None:
        if not config.base_url:
            raise ValueError("base_url is required for openai-compatible embeddings")
        self.config = config
        self._client = client or httpx.Client()

    @classmethod
    def for_test(
        cls,
        config: EmbeddingConfig,
        response_vectors: list[list[float]],
    ) -> OpenAICompatibleEmbeddingProvider:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": index, "embedding": vector}
                        for index, vector in enumerate(response_vectors)
                    ]
                },
                request=request,
            )

        return cls(config, client=httpx.Client(transport=httpx.MockTransport(handler)))

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        response = self._client.post(
            f"{self.config.base_url.rstrip('/')}/embeddings",
            headers=self._headers(),
            json={"model": self.config.model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("embedding response data must be a list")
        if len(data) != len(texts):
            raise ValueError(
                f"embedding response count {len(data)} does not match "
                f"input count {len(texts)}"
            )

        vectors = []
        for index, item in enumerate(data):
            vector = np.asarray(item["embedding"], dtype=np.float32)
            if vector.ndim != 1 or vector.shape[0] != self.config.dimensions:
                raise ValueError(
                    f"embedding dimensions for response {index} do not match "
                    f"configured dimensions {self.config.dimensions}"
                )
            vectors.append(vector)
        return vectors

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "base_url": self.config.base_url,
        }

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key_env:
            return {}
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            return {}
        return {"Authorization": f"Bearer {api_key}"}


def provider_from_config(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "hash":
        return HashEmbeddingProvider(config)
    if config.provider == "openai-compatible":
        return OpenAICompatibleEmbeddingProvider(config)
    if config.provider == "bge":
        from context_search_tool.embeddings_bge import BGEEmbeddingProvider
        return BGEEmbeddingProvider(config)
    raise ValueError(f"unsupported embedding provider: {config.provider}")


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return vector.astype(np.float32, copy=False)
    return (vector / norm).astype(np.float32, copy=False)
