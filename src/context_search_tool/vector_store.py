from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    score: float


@dataclass(frozen=True)
class VectorGenerationDescriptor:
    generation: str
    vectors_file: str
    ids_file: str
    vectors_sha256: str
    ids_sha256: str
    row_count: int
    dimensions: int
    embedding_identity: str
    schema_version: int = 1


@dataclass(frozen=True)
class PreparedVectorGeneration:
    index_dir: Path
    descriptor: VectorGenerationDescriptor


_DESCRIPTOR_FILENAME = "vector_snapshot.json"
_GENERATION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_FaultHook = Callable[[str], None]


class NumpyVectorStore:
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir
        self._ids: list[str] = []
        self._vectors = np.empty((0, 0), dtype=np.float32)
        self._load()

    @classmethod
    def fresh(cls, index_dir: Path) -> NumpyVectorStore:
        store = cls.__new__(cls)
        store.index_dir = index_dir
        store._ids = []
        store._vectors = np.empty((0, 0), dtype=np.float32)
        return store

    @classmethod
    def load_published(
        cls,
        index_dir: Path,
        *,
        expected_embedding_identity: str | None = None,
    ) -> NumpyVectorStore:
        descriptor_path = index_dir / _DESCRIPTOR_FILENAME
        if not descriptor_path.exists():
            return cls(index_dir)
        descriptor = _read_descriptor(descriptor_path)
        if (
            expected_embedding_identity is not None
            and descriptor.embedding_identity != expected_embedding_identity
        ):
            raise ValueError("vector embedding identity mismatch")
        ids, vectors = _load_generation(index_dir, descriptor)
        store = cls.fresh(index_dir)
        store._ids = ids
        store._vectors = vectors
        return store

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

    def remove_many(self, chunk_ids: list[str]) -> None:
        removed = set(chunk_ids)
        if not removed or not self._ids:
            return
        keep_indexes = [
            index for index, chunk_id in enumerate(self._ids) if chunk_id not in removed
        ]
        self._ids = [self._ids[index] for index in keep_indexes]
        if keep_indexes:
            self._vectors = self._vectors[keep_indexes]
        else:
            self._vectors = self._vectors[:0]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._ids)

    def prepare_generation(
        self,
        *,
        generation: str,
        embedding_identity: str,
        fault_hook: _FaultHook | None = None,
    ) -> PreparedVectorGeneration:
        if not _GENERATION_RE.fullmatch(generation):
            raise ValueError("invalid vector generation")
        if not embedding_identity:
            raise ValueError("embedding identity must not be empty")
        if len(self._ids) != self._vectors.shape[0]:
            raise ValueError("vector id count does not match vector row count")
        if len(set(self._ids)) != len(self._ids):
            raise ValueError("vector IDs must be unique")

        self.index_dir.mkdir(parents=True, exist_ok=True)
        vectors_name = f"vectors.{generation}.npy"
        ids_name = f"vector_ids.{generation}.json"
        vectors_path = self.index_dir / vectors_name
        ids_path = self.index_dir / ids_name
        if vectors_path.exists() or ids_path.exists():
            raise ValueError("vector generation already exists")

        def write_vectors(file) -> None:
            np.save(file, self._vectors, allow_pickle=False)

        ids_payload = (
            json.dumps(self._ids, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        _atomic_file_write(
            vectors_path,
            write_vectors,
            prefix="vectors",
            fault_hook=fault_hook,
            replace=False,
        )
        _atomic_file_write(
            ids_path,
            lambda file: file.write(ids_payload),
            prefix="ids",
            fault_hook=fault_hook,
            replace=False,
        )
        descriptor = VectorGenerationDescriptor(
            generation=generation,
            vectors_file=vectors_name,
            ids_file=ids_name,
            vectors_sha256=_sha256_file(vectors_path),
            ids_sha256=_sha256_file(ids_path),
            row_count=len(self._ids),
            dimensions=(
                int(self._vectors.shape[1]) if self._vectors.ndim == 2 else 0
            ),
            embedding_identity=embedding_identity,
        )
        _load_generation(self.index_dir, descriptor)
        return PreparedVectorGeneration(self.index_dir, descriptor)

    def publish_generation(
        self,
        prepared: PreparedVectorGeneration,
        *,
        fault_hook: _FaultHook | None = None,
    ) -> None:
        if prepared.index_dir.resolve() != self.index_dir.resolve():
            raise ValueError("prepared vector generation belongs to another index")
        _load_generation(self.index_dir, prepared.descriptor)
        payload = (
            json.dumps(
                _descriptor_dict(prepared.descriptor),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        _atomic_file_write(
            self.index_dir / _DESCRIPTOR_FILENAME,
            lambda file: file.write(payload),
            prefix="descriptor",
            fault_hook=fault_hook,
            replace=True,
        )
        published = _read_descriptor(self.index_dir / _DESCRIPTOR_FILENAME)
        if published != prepared.descriptor:
            raise ValueError("published vector descriptor mismatch")

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


def _descriptor_dict(
    descriptor: VectorGenerationDescriptor,
) -> dict[str, object]:
    return {
        "schema_version": descriptor.schema_version,
        "generation": descriptor.generation,
        "vectors_file": descriptor.vectors_file,
        "ids_file": descriptor.ids_file,
        "vectors_sha256": descriptor.vectors_sha256,
        "ids_sha256": descriptor.ids_sha256,
        "row_count": descriptor.row_count,
        "dimensions": descriptor.dimensions,
        "embedding_identity": descriptor.embedding_identity,
    }


def _read_descriptor(path: Path) -> VectorGenerationDescriptor:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        descriptor = VectorGenerationDescriptor(
            schema_version=int(raw["schema_version"]),
            generation=str(raw["generation"]),
            vectors_file=str(raw["vectors_file"]),
            ids_file=str(raw["ids_file"]),
            vectors_sha256=str(raw["vectors_sha256"]),
            ids_sha256=str(raw["ids_sha256"]),
            row_count=int(raw["row_count"]),
            dimensions=int(raw["dimensions"]),
            embedding_identity=str(raw["embedding_identity"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid vector descriptor") from error
    if descriptor.schema_version != 1:
        raise ValueError("invalid vector descriptor schema")
    if not _GENERATION_RE.fullmatch(descriptor.generation):
        raise ValueError("invalid vector descriptor generation")
    if descriptor.vectors_file != f"vectors.{descriptor.generation}.npy":
        raise ValueError("invalid vector descriptor path")
    if descriptor.ids_file != f"vector_ids.{descriptor.generation}.json":
        raise ValueError("invalid vector descriptor path")
    if descriptor.row_count < 0 or descriptor.dimensions < 0:
        raise ValueError("invalid vector descriptor dimensions")
    return descriptor


def _load_generation(
    index_dir: Path,
    descriptor: VectorGenerationDescriptor,
) -> tuple[list[str], np.ndarray]:
    vectors_path = index_dir / descriptor.vectors_file
    ids_path = index_dir / descriptor.ids_file
    if (
        _sha256_file(vectors_path) != descriptor.vectors_sha256
        or _sha256_file(ids_path) != descriptor.ids_sha256
    ):
        raise ValueError("vector generation hash mismatch")
    try:
        vectors = np.load(vectors_path, allow_pickle=False).astype(
            np.float32,
            copy=False,
        )
        ids = json.loads(ids_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid vector generation") from error
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    if vectors.ndim != 2 or not isinstance(ids, list) or not all(
        isinstance(item, str) for item in ids
    ):
        raise ValueError("invalid vector generation shape")
    if len(ids) != descriptor.row_count or vectors.shape[0] != descriptor.row_count:
        raise ValueError("vector generation row count mismatch")
    if vectors.shape[1] != descriptor.dimensions:
        raise ValueError("vector generation dimensions mismatch")
    if len(set(ids)) != len(ids):
        raise ValueError("vector generation IDs must be unique")
    return ids, vectors


def _atomic_file_write(
    path: Path,
    writer: Callable[[object], object],
    *,
    prefix: str,
    fault_hook: _FaultHook | None,
    replace: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace and path.exists():
        raise ValueError("immutable vector generation already exists")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            writer(file)
            _fault(fault_hook, f"{prefix}_temp_write")
            file.flush()
            os.fsync(file.fileno())
            _fault(fault_hook, f"{prefix}_file_fsync")
        if replace:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as error:
                raise ValueError(
                    "immutable vector generation already exists"
                ) from error
            temporary_path.unlink()
        _fault(fault_hook, f"{prefix}_rename")
        _fsync_directory(path.parent)
        _fault(fault_hook, f"{prefix}_directory_fsync")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _fault(fault_hook: _FaultHook | None, stage: str) -> None:
    if fault_hook is not None:
        fault_hook(stage)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for block in iter(lambda: file.read(64 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ValueError("vector generation file is missing") from error
    return digest.hexdigest()


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
