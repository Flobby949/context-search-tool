from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable, Literal

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
    vectors_bytes: int | None = None
    ids_bytes: int | None = None
    normalization: Literal["none", "l2"] | None = None


@dataclass(frozen=True)
class PreparedVectorGeneration:
    index_dir: Path
    descriptor: VectorGenerationDescriptor


@dataclass(frozen=True)
class PublishedVectorDescriptor:
    descriptor: VectorGenerationDescriptor
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class VerifiedVectorSnapshot:
    descriptor_snapshot: PublishedVectorDescriptor
    ids: tuple[str, ...]


class IncompatibleVectorDescriptorSchemaError(RuntimeError):
    code = "incompatible_vector_descriptor_schema"

    def __init__(self, stored_version: object) -> None:
        self.stored_version = stored_version
        super().__init__(f"incompatible vector descriptor schema {stored_version}")


class VectorDescriptorCorruptionError(ValueError):
    code = "vector_descriptor_corrupt"


_DESCRIPTOR_FILENAME = "vector_snapshot.json"
_GENERATION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
READABLE_VECTOR_DESCRIPTOR_VERSIONS = frozenset({1, 2})
WRITE_VECTOR_DESCRIPTOR_VERSION = 2
_MAX_DESCRIPTOR_BYTES = 64 * 1024
_FaultHook = Callable[[str], None]


class NumpyVectorStore:
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir
        self._ids: list[str] = []
        self._vectors = np.empty((0, 0), dtype=np.float32)
        self._load()

    @classmethod
    def fresh(
        cls,
        index_dir: Path,
        *,
        dimensions: int = 0,
    ) -> NumpyVectorStore:
        if dimensions < 0:
            raise ValueError("vector dimensions must be non-negative")
        store = cls.__new__(cls)
        store.index_dir = index_dir
        store._ids = []
        store._vectors = np.empty((0, dimensions), dtype=np.float32)
        return store

    @classmethod
    def load_published(
        cls,
        index_dir: Path,
        *,
        expected_embedding_identity: str | None = None,
    ) -> NumpyVectorStore:
        _descriptor, store = cls.load_published_snapshot(
            index_dir,
            expected_embedding_identity=expected_embedding_identity,
        )
        return store

    @classmethod
    def load_published_snapshot(
        cls,
        index_dir: Path,
        *,
        expected_embedding_identity: str | None = None,
    ) -> tuple[VectorGenerationDescriptor | None, NumpyVectorStore]:
        descriptor_path = index_dir / _DESCRIPTOR_FILENAME
        if not descriptor_path.exists():
            return None, cls(index_dir)
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
        return descriptor, store

    @classmethod
    def published_descriptor(
        cls,
        index_dir: Path,
    ) -> VectorGenerationDescriptor | None:
        descriptor_path = index_dir / _DESCRIPTOR_FILENAME
        if not descriptor_path.exists():
            return None
        descriptor = _read_descriptor(descriptor_path)
        _load_generation(index_dir, descriptor)
        return descriptor

    @classmethod
    def inspect_published_descriptor(
        cls,
        index_dir: Path,
    ) -> PublishedVectorDescriptor | None:
        descriptor_path = index_dir / _DESCRIPTOR_FILENAME
        if not os.path.lexists(descriptor_path):
            return None
        snapshot = _read_descriptor_snapshot(descriptor_path)
        _validate_generation_paths(index_dir, snapshot.descriptor)
        return snapshot

    @classmethod
    def verify_published_snapshot(
        cls,
        index_dir: Path,
        *,
        expected_ids: set[str] | None = None,
        expected_embedding_identity: str | None = None,
    ) -> VerifiedVectorSnapshot:
        snapshot = cls.inspect_published_descriptor(index_dir)
        if snapshot is None:
            raise VectorDescriptorCorruptionError("vector descriptor is missing")
        descriptor = snapshot.descriptor
        if (
            expected_embedding_identity is not None
            and descriptor.embedding_identity != expected_embedding_identity
        ):
            raise VectorDescriptorCorruptionError(
                "vector embedding identity mismatch"
            )
        ids, _vectors = _load_generation(index_dir, descriptor)
        if expected_ids is not None and set(ids) != expected_ids:
            raise VectorDescriptorCorruptionError("exact vector IDs mismatch")
        return VerifiedVectorSnapshot(snapshot, tuple(ids))

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

    def sort_by_id(self) -> None:
        if len(self._ids) < 2:
            return
        order = sorted(range(len(self._ids)), key=self._ids.__getitem__)
        self._ids = [self._ids[index] for index in order]
        self._vectors = self._vectors[order]

    def prepare_generation(
        self,
        *,
        generation: str,
        embedding_identity: str,
        fault_hook: _FaultHook | None = None,
    ) -> PreparedVectorGeneration:
        return self._prepare_generation(
            generation=generation,
            embedding_identity=embedding_identity,
            schema_version=1,
            normalization=None,
            fault_hook=fault_hook,
        )

    def prepare_generation_v2(
        self,
        *,
        generation: str,
        embedding_identity: str,
        normalization: Literal["none", "l2"],
        fault_hook: _FaultHook | None = None,
    ) -> PreparedVectorGeneration:
        if normalization not in {"none", "l2"}:
            raise ValueError("vector normalization must be none or l2")
        if normalization == "l2":
            _validate_l2_normalization(self._vectors)
        return self._prepare_generation(
            generation=generation,
            embedding_identity=embedding_identity,
            schema_version=WRITE_VECTOR_DESCRIPTOR_VERSION,
            normalization=normalization,
            fault_hook=fault_hook,
        )

    def _prepare_generation(
        self,
        *,
        generation: str,
        embedding_identity: str,
        schema_version: int,
        normalization: Literal["none", "l2"] | None,
        fault_hook: _FaultHook | None,
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
            vectors_sha256=(
                _sha256_file_safe(vectors_path)
                if schema_version == 2
                else _sha256_file(vectors_path)
            ),
            ids_sha256=(
                _sha256_file_safe(ids_path)
                if schema_version == 2
                else _sha256_file(ids_path)
            ),
            row_count=len(self._ids),
            dimensions=(
                int(self._vectors.shape[1]) if self._vectors.ndim == 2 else 0
            ),
            embedding_identity=embedding_identity,
            schema_version=schema_version,
            vectors_bytes=(
                vectors_path.stat().st_size if schema_version == 2 else None
            ),
            ids_bytes=ids_path.stat().st_size if schema_version == 2 else None,
            normalization=normalization,
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
    rendered: dict[str, object] = {
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
    if descriptor.schema_version == 2:
        rendered.update(
            {
                "vectors_bytes": descriptor.vectors_bytes,
                "ids_bytes": descriptor.ids_bytes,
                "normalization": descriptor.normalization,
            }
        )
    return rendered


def _read_descriptor(path: Path) -> VectorGenerationDescriptor:
    try:
        payload = path.read_text(encoding="utf-8").encode("utf-8")
    except (OSError, UnicodeError) as error:
        raise VectorDescriptorCorruptionError("invalid vector descriptor") from error
    return _decode_descriptor_payload(payload).descriptor


def _read_descriptor_snapshot(path: Path) -> PublishedVectorDescriptor:
    payload = _read_small_regular_file(path, "vector descriptor")
    return _decode_descriptor_payload(payload)


def _decode_descriptor_payload(payload: bytes) -> PublishedVectorDescriptor:
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if not isinstance(raw, dict):
            raise TypeError("descriptor root must be an object")
        raw_version = raw.get("schema_version")
        if type(raw_version) is not int or raw_version < 0:
            raise TypeError("descriptor schema must be an integer")
        if raw_version not in READABLE_VECTOR_DESCRIPTOR_VERSIONS:
            raise IncompatibleVectorDescriptorSchemaError(raw_version)
        descriptor = VectorGenerationDescriptor(
            schema_version=raw_version,
            generation=_descriptor_str(raw, "generation"),
            vectors_file=_descriptor_str(raw, "vectors_file"),
            ids_file=_descriptor_str(raw, "ids_file"),
            vectors_sha256=_descriptor_str(raw, "vectors_sha256"),
            ids_sha256=_descriptor_str(raw, "ids_sha256"),
            row_count=_descriptor_int(raw, "row_count"),
            dimensions=_descriptor_int(raw, "dimensions"),
            embedding_identity=_descriptor_str(raw, "embedding_identity"),
            vectors_bytes=(
                _descriptor_int(raw, "vectors_bytes") if raw_version == 2 else None
            ),
            ids_bytes=(
                _descriptor_int(raw, "ids_bytes") if raw_version == 2 else None
            ),
            normalization=(
                _descriptor_str(raw, "normalization")
                if raw_version == 2
                else None
            ),
        )
    except IncompatibleVectorDescriptorSchemaError:
        raise
    except VectorDescriptorCorruptionError:
        raise
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise VectorDescriptorCorruptionError("invalid vector descriptor") from error
    expected_keys = {
        "schema_version",
        "generation",
        "vectors_file",
        "ids_file",
        "vectors_sha256",
        "ids_sha256",
        "row_count",
        "dimensions",
        "embedding_identity",
    }
    if descriptor.schema_version == 2:
        expected_keys.update({"vectors_bytes", "ids_bytes", "normalization"})
    if (
        descriptor.schema_version == 1
        and not expected_keys <= set(raw)
    ) or (
        descriptor.schema_version == 2
        and set(raw) != expected_keys
    ):
        raise VectorDescriptorCorruptionError("invalid vector descriptor fields")
    if not _GENERATION_RE.fullmatch(descriptor.generation):
        raise VectorDescriptorCorruptionError("invalid vector descriptor generation")
    if descriptor.vectors_file != f"vectors.{descriptor.generation}.npy":
        raise VectorDescriptorCorruptionError("invalid vector descriptor path")
    if descriptor.ids_file != f"vector_ids.{descriptor.generation}.json":
        raise VectorDescriptorCorruptionError("invalid vector descriptor path")
    if (
        descriptor.row_count < 0
        or descriptor.dimensions < 0
        or not descriptor.embedding_identity
        or not _SHA256_RE.fullmatch(descriptor.vectors_sha256)
        or not _SHA256_RE.fullmatch(descriptor.ids_sha256)
    ):
        raise VectorDescriptorCorruptionError("invalid vector descriptor values")
    if descriptor.schema_version == 2 and (
        descriptor.vectors_bytes is None
        or descriptor.vectors_bytes < 0
        or descriptor.ids_bytes is None
        or descriptor.ids_bytes < 0
        or descriptor.normalization not in {"none", "l2"}
    ):
        raise VectorDescriptorCorruptionError("invalid vector descriptor v2")
    return PublishedVectorDescriptor(
        descriptor=descriptor,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


def _load_generation(
    index_dir: Path,
    descriptor: VectorGenerationDescriptor,
) -> tuple[list[str], np.ndarray]:
    vectors_path = index_dir / descriptor.vectors_file
    ids_path = index_dir / descriptor.ids_file
    hash_file = _sha256_file
    if descriptor.schema_version == 2:
        _validate_generation_paths(index_dir, descriptor)
        hash_file = _sha256_file_safe
    if (
        hash_file(vectors_path) != descriptor.vectors_sha256
        or hash_file(ids_path) != descriptor.ids_sha256
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
    if descriptor.normalization == "l2":
        _validate_l2_normalization(vectors)
    return ids, vectors


def _validate_generation_paths(
    index_dir: Path,
    descriptor: VectorGenerationDescriptor,
) -> None:
    vectors_size = _regular_file_size(
        index_dir / descriptor.vectors_file,
        "vector payload",
    )
    ids_size = _regular_file_size(
        index_dir / descriptor.ids_file,
        "vector IDs",
    )
    if descriptor.schema_version == 2 and (
        vectors_size != descriptor.vectors_bytes
        or ids_size != descriptor.ids_bytes
    ):
        raise VectorDescriptorCorruptionError("vector generation size mismatch")


def _descriptor_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise VectorDescriptorCorruptionError(f"invalid descriptor field: {key}")
    return value


def _descriptor_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if type(value) is not int:
        raise VectorDescriptorCorruptionError(f"invalid descriptor field: {key}")
    return value


def _read_small_regular_file(path: Path, label: str) -> bytes:
    size = _regular_file_size(path, label)
    if size > _MAX_DESCRIPTOR_BYTES:
        raise VectorDescriptorCorruptionError(f"{label} is too large")
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        payload = bytearray()
        while len(payload) <= _MAX_DESCRIPTOR_BYTES:
            block = os.read(
                descriptor,
                min(16 * 1024, _MAX_DESCRIPTOR_BYTES + 1 - len(payload)),
            )
            if not block:
                break
            payload.extend(block)
        after = os.fstat(descriptor)
        final = os.lstat(path)
    except OSError as error:
        raise VectorDescriptorCorruptionError(f"unreadable {label}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        len(payload) > _MAX_DESCRIPTOR_BYTES
        or len(payload) != size
        or identity
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or identity
        != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
    ):
        raise VectorDescriptorCorruptionError(f"{label} changed during read")
    return bytes(payload)


def _regular_file_size(path: Path, label: str) -> int:
    try:
        value = os.lstat(path)
    except OSError as error:
        raise VectorDescriptorCorruptionError(f"{label} is missing") from error
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise VectorDescriptorCorruptionError(
            f"{label} must be a regular non-symlink file"
        )
    if hasattr(os, "getuid") and value.st_uid != os.getuid():
        raise VectorDescriptorCorruptionError(f"{label} owner mismatch")
    if stat.S_IMODE(value.st_mode) & 0o022:
        raise VectorDescriptorCorruptionError(f"unsafe {label} permissions")
    return int(value.st_size)


def _validate_l2_normalization(vectors: np.ndarray) -> None:
    if vectors.ndim != 2:
        raise VectorDescriptorCorruptionError("invalid vector normalization shape")
    if not np.isfinite(vectors).all():
        raise VectorDescriptorCorruptionError("invalid vector normalization values")
    if vectors.shape[0] == 0:
        return
    norms = np.linalg.norm(vectors, axis=1)
    valid = np.logical_or(norms == 0.0, np.isclose(norms, 1.0, rtol=1e-5, atol=1e-6))
    if not bool(np.all(valid)):
        raise VectorDescriptorCorruptionError("vector normalization mismatch")


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


def _sha256_file_safe(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor: int | None = None
    try:
        _regular_file_size(path, "vector generation file")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", closefd=False) as file:
            for block in iter(lambda: file.read(64 * 1024), b""):
                digest.update(block)
        after = os.fstat(descriptor)
        final = os.lstat(path)
    except OSError as error:
        raise ValueError("vector generation file is missing") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
    ):
        raise VectorDescriptorCorruptionError(
            "vector generation file changed during hashing"
        )
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
