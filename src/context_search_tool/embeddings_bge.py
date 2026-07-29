# src/context_search_tool/embeddings_bge.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

import numpy as np
import requests

from context_search_tool.config import EmbeddingConfig
from context_search_tool.manifest import embedding_config_hash


_DEFAULT_BASE_URL = "http://localhost:11434"
_INPUT_TRANSFORM_ID = "bge-input-v2"
_MAX_TEXTS_PER_REQUEST = 8
_MAX_TEXT_CODEPOINTS = 2_000
_HEAD_CODEPOINTS = 1_500
_TAIL_CODEPOINTS = 499
_PREFLIGHT_TIMEOUT_SECONDS = 5.0
_EMBED_TIMEOUT_SECONDS = 60.0
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_CONTEXT_LIMIT_PHRASES = (
    "input length exceeds the context length",
    "input length exceeds the context window",
)
_EGRESS_ORDER = {
    "not_attempted": 0,
    "possible": 1,
    "performed": 2,
}


class _BGEProviderError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _BGERuntimeAttestation:
    configured_model: str
    canonical_model: str
    model_digest: str
    ollama_version: str
    base_url: str
    dimensions: int
    input_transform_id: str
    embedding_identity: str

    def mapping(self) -> dict[str, object]:
        return {
            "configured_model": self.configured_model,
            "canonical_model": self.canonical_model,
            "model_digest": self.model_digest,
            "ollama_version": self.ollama_version,
            "base_url": self.base_url,
            "dimensions": self.dimensions,
            "input_transform_id": self.input_transform_id,
            "embedding_identity": self.embedding_identity,
        }


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
        self._base_url = (config.base_url or "").rstrip("/") or _DEFAULT_BASE_URL
        self._session = session if session is not None else requests.Session()
        if session is None:
            self._session.trust_env = False
        self._session.headers.update({"Content-Type": "application/json"})
        self._runtime_attestation: _BGERuntimeAttestation | None = None
        self.__network_egress_outcome = "not_attempted"

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        self.runtime_fingerprint()
        prepared = [_prepare_input(text) for text in texts]
        vectors: list[np.ndarray] = []
        for batch in _embedding_batches(prepared):
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        self._mark_network_egress("possible")
        try:
            response = self._session.post(
                f"{self._base_url}/api/embed",
                json={
                    "model": self.config.model,
                    "input": texts,
                    "truncate": False,
                },
                timeout=_EMBED_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            raise _BGEProviderError("bge_unavailable") from None
        self._mark_network_egress("performed")

        try:
            response.raise_for_status()
        except requests.RequestException:
            code = (
                "bge_context_limit"
                if _is_context_limit_response(response)
                else "bge_request_rejected"
            )
            raise _BGEProviderError(code) from None

        try:
            payload = response.json()
        except (TypeError, ValueError, requests.RequestException):
            raise _BGEProviderError("bge_response_invalid") from None
        if not isinstance(payload, dict):
            raise _BGEProviderError("bge_response_invalid")
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise _BGEProviderError("bge_response_invalid")
        if len(embeddings) != len(texts):
            raise _BGEProviderError("bge_response_invalid")

        vectors: list[np.ndarray] = []
        for embedding in embeddings:
            if not isinstance(embedding, (list, tuple)) or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                for value in embedding
            ):
                raise _BGEProviderError("bge_response_invalid")
            try:
                vector = np.asarray(embedding, dtype=np.float32)
            except (TypeError, ValueError, OverflowError):
                raise _BGEProviderError("bge_response_invalid") from None
            if vector.ndim != 1 or vector.shape[0] != self.config.dimensions:
                raise _BGEProviderError("bge_response_invalid")
            if not bool(np.isfinite(vector).all()):
                raise _BGEProviderError("bge_response_invalid")
            with np.errstate(over="ignore", invalid="ignore"):
                norm = float(np.linalg.norm(vector))
            if not np.isfinite(norm) or norm <= 0.0:
                raise _BGEProviderError("bge_response_invalid")
            vector = (vector / norm).astype(np.float32, copy=False)
            if not bool(np.isfinite(vector).all()):
                raise _BGEProviderError("bge_response_invalid")
            vectors.append(vector)
        return vectors

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "backend": "ollama",
        }

    def runtime_fingerprint(self) -> dict[str, object]:
        if self._runtime_attestation is None:
            self._runtime_attestation = self._fetch_runtime_attestation()
        return self._runtime_attestation.mapping()

    def assert_runtime_unchanged(self) -> dict[str, object]:
        if self._runtime_attestation is None:
            self._runtime_attestation = self._fetch_runtime_attestation()
        fresh = self._fetch_runtime_attestation()
        if fresh != self._runtime_attestation:
            raise _BGEProviderError("bge_runtime_mismatch")
        return fresh.mapping()

    @property
    def _network_egress_outcome(self) -> str:
        return self.__network_egress_outcome

    def _mark_network_egress(self, outcome: str) -> None:
        if _EGRESS_ORDER[outcome] > _EGRESS_ORDER[self.__network_egress_outcome]:
            self.__network_egress_outcome = outcome

    def _fetch_runtime_attestation(self) -> _BGERuntimeAttestation:
        version_payload = self._preflight_json("/api/version")
        version = version_payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise _BGEProviderError("bge_unavailable")

        tags_payload = self._preflight_json("/api/tags")
        models = tags_payload.get("models")
        if not isinstance(models, list):
            raise _BGEProviderError("bge_unavailable")
        canonical_model = (
            self.config.model
            if ":" in self.config.model
            else f"{self.config.model}:latest"
        )
        matches = [
            model
            for model in models
            if isinstance(model, dict) and model.get("name") == canonical_model
        ]
        if len(matches) != 1:
            raise _BGEProviderError("bge_model_unavailable")
        digest = matches[0].get("digest")
        if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
            raise _BGEProviderError("bge_model_unavailable")

        version_sha256 = hashlib.sha256(version.encode("utf-8")).hexdigest()
        identity = (
            f"bge-ollama-v1:{embedding_config_hash(self.config)}:"
            f"{digest}:{version_sha256}:{_INPUT_TRANSFORM_ID}"
        )
        return _BGERuntimeAttestation(
            configured_model=self.config.model,
            canonical_model=canonical_model,
            model_digest=digest,
            ollama_version=version,
            base_url=self._base_url,
            dimensions=self.config.dimensions,
            input_transform_id=_INPUT_TRANSFORM_ID,
            embedding_identity=identity,
        )

    def _preflight_json(self, endpoint: str) -> dict[str, object]:
        self._mark_network_egress("possible")
        try:
            response = self._session.get(
                f"{self._base_url}{endpoint}",
                timeout=_PREFLIGHT_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            raise _BGEProviderError("bge_unavailable") from None
        self._mark_network_egress("performed")
        try:
            response.raise_for_status()
            payload = response.json()
        except (TypeError, ValueError, requests.RequestException):
            raise _BGEProviderError("bge_unavailable") from None
        if not isinstance(payload, dict):
            raise _BGEProviderError("bge_unavailable")
        return payload


def _embedding_batches(texts: list[str]) -> list[list[str]]:
    return [
        texts[index : index + _MAX_TEXTS_PER_REQUEST]
        for index in range(0, len(texts), _MAX_TEXTS_PER_REQUEST)
    ]


def _prepare_input(text: str) -> str:
    if len(text) <= _MAX_TEXT_CODEPOINTS:
        return text
    return (
        text[:_HEAD_CODEPOINTS]
        + "\n"
        + text[-_TAIL_CODEPOINTS:]
    )


def _is_context_limit_response(response: requests.Response) -> bool:
    if response.status_code != 400:
        return False
    error_text = ""
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            error_text = payload["error"]
    except (TypeError, ValueError, requests.RequestException):
        pass
    if not error_text and isinstance(response.text, str):
        error_text = response.text
    normalized = " ".join(error_text.casefold().split())
    return any(phrase in normalized for phrase in _CONTEXT_LIMIT_PHRASES)
