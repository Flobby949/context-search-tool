from __future__ import annotations

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
