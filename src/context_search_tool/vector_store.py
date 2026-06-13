from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    score: float


class NumpyVectorStore:
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir
        self._ids: list[str] = []
        self._vectors = np.empty((0, 0), dtype=np.float32)
        self._load()

    def upsert_many(self, items: list[tuple[str, np.ndarray]]) -> None:
        if not items:
            return

        vectors_by_id = {
            chunk_id: vector for chunk_id, vector in zip(self._ids, self._vectors)
        }
        dimensions = self._vectors.shape[1] if self._vectors.size else None

        for chunk_id, vector in items:
            incoming = np.asarray(vector, dtype=np.float32).reshape(-1)
            if dimensions is None:
                dimensions = incoming.shape[0]
            if incoming.shape[0] != dimensions:
                raise ValueError("all vectors must have the same dimensions")
            if chunk_id not in vectors_by_id:
                self._ids.append(chunk_id)
            vectors_by_id[chunk_id] = incoming

        self._vectors = np.vstack([vectors_by_id[chunk_id] for chunk_id in self._ids])

    def persist(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        np.save(self._vectors_path, self._vectors)
        self._ids_path.write_text(
            json.dumps(self._ids, indent=2) + "\n",
            encoding="utf-8",
        )

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        deleted_ids: set[str],
    ) -> list[VectorSearchResult]:
        if top_k <= 0 or not self._ids:
            return []

        query = _normalize_vector(np.asarray(query_vector, dtype=np.float32).reshape(-1))
        vectors = _normalize_matrix(self._vectors)
        scores = np.einsum("ij,j->i", vectors, query, optimize=True)
        scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
        results = [
            VectorSearchResult(chunk_id=chunk_id, score=float(score))
            for chunk_id, score in zip(self._ids, scores)
            if chunk_id not in deleted_ids
        ]
        results.sort(key=lambda item: (-item.score, item.chunk_id))
        return results[:top_k]

    def _load(self) -> None:
        if not self._vectors_path.exists() or not self._ids_path.exists():
            return

        vectors = np.load(self._vectors_path).astype(np.float32, copy=False)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        ids = json.loads(self._ids_path.read_text(encoding="utf-8"))
        if len(ids) != vectors.shape[0]:
            raise ValueError(
                f"vector id count {len(ids)} does not match "
                f"vector row count {vectors.shape[0]}"
            )
        self._vectors = vectors
        self._ids = ids

    @property
    def _vectors_path(self) -> Path:
        return self.index_dir / "vectors.npy"

    @property
    def _ids_path(self) -> Path:
        return self.index_dir / "vector_ids.json"


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0).astype(
        np.float32,
        copy=False,
    )
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return vector.astype(np.float32, copy=False)
    return (vector / norm).astype(np.float32, copy=False)


def _normalize_matrix(vectors: np.ndarray) -> np.ndarray:
    vectors = np.nan_to_num(vectors, nan=0.0, posinf=0.0, neginf=0.0).astype(
        np.float32,
        copy=False,
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(
        vectors,
        norms,
        out=np.zeros_like(vectors, dtype=np.float32),
        where=norms != 0,
    )
