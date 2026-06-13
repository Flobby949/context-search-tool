from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceFile:
    path: Path
    language: str
    sha256: str
    size: int
    mtime_ns: int
    is_generated: bool = False
    is_test: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SymbolRef:
    name: str
    kind: str
    start_line: int
    end_line: int
    language: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodeSignal:
    signal_id: str
    chunk_id: str
    file_path: Path
    kind: str
    name: str
    start_line: int
    end_line: int
    language: str
    tokens: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodeRelation:
    relation_id: str
    source_signal_id: str
    target_name: str
    kind: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


def generate_signal_id(file_path: Path, kind: str, start_line: int, name: str) -> str:
    path_hash = _short_hash(file_path.as_posix())
    name_hash = _short_hash(name)
    return f"{path_hash}:{kind}:{start_line}:{name_hash}"


def generate_relation_id(source_signal_id: str, target_name: str, kind: str) -> str:
    source_hash = _short_hash(source_signal_id)
    target_hash = _short_hash(target_name)
    return f"{source_hash}:{kind}:{target_hash}"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    file_path: Path
    start_line: int
    end_line: int
    content: str
    chunk_type: str
    symbols: list[SymbolRef] = field(default_factory=list)
    lexical_tokens: list[str] = field(default_factory=list)
    embedding_id: str | None = None
    deleted_at: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    score: float
    source: str
    score_parts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    followup_keywords: list[str]


@dataclass
class RetrievalSummary:
    entry_points: list[str] = field(default_factory=list)
    implementation: list[str] = field(default_factory=list)
    related_types: list[str] = field(default_factory=list)
    possibly_legacy: list[str] = field(default_factory=list)
