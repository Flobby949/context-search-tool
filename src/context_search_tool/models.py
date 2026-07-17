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
    qualified_name: str = ""
    signature: str = ""
    arity: int | None = None
    project_unit_key: str = ""
    producer: str = "legacy"
    start_column: int = 0
    end_column: int = 0
    recallable: bool = True


@dataclass(frozen=True)
class CodeRelation:
    relation_id: str
    source_signal_id: str
    target_name: str
    kind: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)
    target_kind: str = ""
    target_qualified_name: str = ""
    target_signature: str = ""
    target_arity: int | None = None
    target_project_unit_key: str = ""
    target_signal_id: str = ""
    resolution: str = "legacy"
    producer: str = "legacy"
    producer_confidence: float = 1.0
    resolution_confidence: float | None = None


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
class QueryPlan:
    original_query: str
    rewritten_queries: list[str] = field(default_factory=list)
    grep_keywords: list[str] = field(default_factory=list)
    symbol_hints: list[str] = field(default_factory=list)
    intent: str = "unknown"
    status: str = "disabled"
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    latency_ms: int | None = None
    error: str | None = None
    repo_profile_hash: str = ""
    repo_profile_truncated: bool = False
    discarded_hints: list[str] = field(default_factory=list)

    @staticmethod
    def disabled_default() -> QueryPlan:
        return QueryPlan(original_query="", status="disabled")


@dataclass(frozen=True)
class QueryVariant:
    variant_id: str
    text: str
    source: str


@dataclass(frozen=True)
class SemanticMatch:
    variant_id: str
    score: float


@dataclass(frozen=True)
class RepoProfile:
    languages: list[str] = field(default_factory=list)
    source_roots: list[str] = field(default_factory=list)
    important_files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    profile_hash: str = ""
    truncated: bool = False


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
    semantic_matches: list[SemanticMatch] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalSpan:
    start_line: int
    end_line: int
    score: float
    sources: tuple[str, ...]


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
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    spans: tuple[RetrievalSpan, ...] = ()
    _context_content: str | None = field(default=None, repr=False, compare=False)
    _context_role_hint: str | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class EvidenceAnchor:
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    anchor_kind: str
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    _context_content: str | None = field(default=None, repr=False, compare=False)


@dataclass
class RetrievalSummary:
    entry_points: list[str] = field(default_factory=list)
    implementation: list[str] = field(default_factory=list)
    related_types: list[str] = field(default_factory=list)
    possibly_legacy: list[str] = field(default_factory=list)
