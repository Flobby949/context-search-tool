from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_search_tool.models import RetrievalSpan


CONTEXT_PACK_SCHEMA_VERSION = 2
CONTEXT_GROUPS = (
    "entrypoints",
    "implementations",
    "related_types",
    "tests",
    "configs_docs",
    "supporting",
)


class ContextPackError(Exception):
    """A bounded public failure of the context pack v2 contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ContextPackOptions:
    max_items: int
    max_excerpts_per_item: int
    max_excerpt_bytes: int
    max_item_content_bytes: int
    max_total_content_bytes: int
    max_pack_bytes: int
    context_before_lines: int
    context_after_lines: int


@dataclass(frozen=True)
class ContextExcerpt:
    start_line: int
    end_line: int
    content: str
    content_bytes: int
    truncated: bool


@dataclass(frozen=True)
class ContextItem:
    id: str
    file_path: str
    group: str
    role: str
    classification_basis: str
    source_kind: str
    retrieval_rank: int | None
    relevance_score: float | None
    reasons: tuple[str, ...]
    matched_need_ids: tuple[str, ...]
    excerpts: tuple[ContextExcerpt, ...]


@dataclass(frozen=True)
class EvidenceNeed:
    id: str
    category: str
    subject_terms: tuple[str, ...]
    required: bool
    provenance: str
    matched_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class MissingEvidence:
    need_id: str
    category: str
    required: bool
    reason: str


@dataclass(frozen=True)
class NextQuery:
    need_id: str
    query: str
    purpose: str


@dataclass(frozen=True)
class Omission:
    file_path: str
    group: str
    reason: str
    matched_need_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReadinessConfidence:
    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContextBudget:
    max_items: int
    max_excerpts_per_item: int
    max_excerpt_bytes: int
    max_item_content_bytes: int
    max_total_content_bytes: int
    max_pack_bytes: int
    included_items: int
    included_excerpts: int
    content_bytes: int
    pack_bytes: int
    truncated_item_count: int
    omitted_item_count: int
    budget_exhausted: bool


@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    status: str
    items: tuple[ContextItem, ...]
    groups: dict[str, tuple[str, ...]]
    reading_order: tuple[str, ...]
    evidence_needs: tuple[EvidenceNeed, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    next_queries: tuple[NextQuery, ...]
    omissions: tuple[Omission, ...]
    confidence: ReadinessConfidence
    budget: ContextBudget


@dataclass(frozen=True)
class ContextCandidate:
    key: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    group: str
    role: str
    classification_basis: str
    source_kind: str
    retrieval_rank: int | None
    source_order: int
    relevance_score: float | None
    reasons: tuple[str, ...]
    score_parts: dict[str, float]
    spans: tuple[RetrievalSpan, ...]
    trusted_provenance_text: str
    protected_direct: bool


@dataclass(frozen=True)
class ExcerptWindow:
    start_line: int
    end_line: int
    required_need_ids: tuple[str, ...]
    recommended_need_ids: tuple[str, ...]
    score: float
    protected_direct: bool


__all__ = (
    "CONTEXT_GROUPS",
    "CONTEXT_PACK_SCHEMA_VERSION",
    "ContextBudget",
    "ContextCandidate",
    "ContextExcerpt",
    "ContextItem",
    "ContextPack",
    "ContextPackError",
    "ContextPackOptions",
    "EvidenceNeed",
    "ExcerptWindow",
    "MissingEvidence",
    "NextQuery",
    "Omission",
    "ReadinessConfidence",
)
