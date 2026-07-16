from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from context_search_tool.models import (
    DocumentChunk,
    RetrievalSpan,
    SemanticMatch,
)


@dataclass(frozen=True)
class _RankedChunk:
    chunk: DocumentChunk
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    rank_tier: int
    rerank_score: float
    evidence_class: str
    evidence_priority: int
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    pre_ceiling_rerank_score: float = 0.0
    was_ceiling_clamped: bool = False


@dataclass(frozen=True)
class _ExpandedResult:
    chunk_ids: list[str]
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    followup_keywords: list[str]
    rank_tier: int
    rerank_score: float
    evidence_class: str
    evidence_priority: int
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    pre_ceiling_rerank_score: float = 0.0
    was_ceiling_clamped: bool = False
    spans: tuple[RetrievalSpan, ...] = ()
    _context_content: str | None = field(default=None, repr=False, compare=False)
