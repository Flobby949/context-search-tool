"""Pure evidence-need derivation and candidate-scoped matching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
import unicodedata
from typing import TYPE_CHECKING, Iterable, Mapping

from context_search_tool.context_pack.models import (
    CONTEXT_GROUPS,
    ContextCandidate,
    ContextExcerpt,
    ContextItem,
    EvidenceNeed,
    MissingEvidence,
    NextQuery,
    ReadinessConfidence,
)
from context_search_tool.identifier_intent import infer_identifier_intent
from context_search_tool.query_intent import infer_query_intent
from context_search_tool.tokenizer import tokenize_query

if TYPE_CHECKING:
    from context_search_tool.retrieval import QueryBundle


_EXPLICIT_ROLE_TERMS = {
    "entrypoints": (
        "controller",
        "route",
        "router",
        "endpoint",
        "entrypoint",
        "form",
        "page",
        "view",
        "详情页",
        "页面",
    ),
    "implementations": (
        "implementation",
        "service",
        "handler",
        "repository",
        "storage",
        "实现",
        "服务",
    ),
    "related_types": (
        "dto",
        "model",
        "entity",
        "type",
        "record",
        "enum",
        "模型",
        "类型",
    ),
    "tests": ("test", "tests", "integration test", "测试", "集成测试"),
    "configs_docs": (
        "config",
        "configuration",
        "properties",
        "profile",
        "documentation",
        "配置",
        "文档",
    ),
}

_STRUCTURAL_RECOMMENDATIONS = {
    "entrypoints": ("implementations", "tests"),
    "implementations": ("entrypoints", "tests"),
    "related_types": (),
    "tests": (),
    "configs_docs": (),
}

_IDENTIFIER_SUFFIX_CATEGORIES = (
    (
        "entrypoints",
        (
            ("controller",),
            ("router",),
            ("route",),
            ("endpoint",),
            ("entrypoint",),
            ("command",),
            ("form",),
            ("page",),
            ("view",),
        ),
    ),
    (
        "implementations",
        (
            ("implementation",),
            ("service", "impl"),
            ("repository",),
            ("handler",),
            ("storage",),
            ("service",),
            ("impl",),
        ),
    ),
    (
        "related_types",
        (
            ("dto",),
            ("vo",),
            ("request",),
            ("response",),
            ("entity",),
            ("model",),
            ("record",),
            ("enum",),
            ("type",),
        ),
    ),
    (
        "tests",
        (
            ("integration", "tests"),
            ("integration", "test"),
            ("tests",),
            ("test",),
        ),
    ),
    (
        "configs_docs",
        (("configuration",), ("properties",), ("config",)),
    ),
)

_SUBJECT_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "database",
        "does",
        "find",
        "flow",
        "for",
        "how",
        "integration",
        "is",
        "load",
        "loading",
        "of",
        "or",
        "registration",
        "the",
        "validation",
        "with",
    }
)
_CONJUNCTION_RE = re.compile(r"\s+(?:and|or)\s+|[,;/&]+", re.IGNORECASE)
_CLAUSE_SEPARATOR_RE = re.compile(
    r"\s+(?:and|or)\s+|[,;/&]+|[\r\n]+",
    re.IGNORECASE,
)
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CAMEL_PART_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+"
)
_CHINESE_PAGE_RE = re.compile(r"[\u3400-\u9fff]+?(?:详情页|页面)")
_DATABASE_RE = re.compile(r"(?<![A-Za-z0-9])(?:mysql|postgresql)(?![A-Za-z0-9])", re.I)
_MAX_SUBJECT_CODE_POINTS = 64
_MAX_NEXT_QUERIES = 3
_MAX_NEXT_QUERY_CODE_POINTS = 160
_MAX_CONFIDENCE_REASONS = 4

_EVIDENCE_LABELS = {
    "entrypoints": "entrypoint",
    "implementations": "implementation",
    "related_types": "model type",
    "tests": "test",
    "configs_docs": "configuration",
}
_NEXT_QUERY_SUFFIXES = {
    "entrypoints": "controller route entrypoint",
    "implementations": "service implementation",
    "related_types": "model type",
    "tests": "test",
    "configs_docs": "configuration documentation",
}
_RECOMMENDED_CONFIDENCE_REASONS = {
    "entrypoints": "recommended entrypoints are missing",
    "implementations": "recommended implementations are missing",
    "related_types": "recommended model types are missing",
    "tests": "recommended tests are missing",
    "configs_docs": "recommended configuration evidence is missing",
}
_CONFIDENCE_REASON_EMPTY = "no usable retrieval evidence"
_CONFIDENCE_REASON_PARTIAL = "required evidence is missing"
_CONFIDENCE_REASON_NO_ITEM = "no evidence item fits the context budget"
_CONFIDENCE_REASON_READY = "all required evidence is selected"
_CONFIDENCE_REASON_TRUNCATED = "selected required evidence is truncated"
_CONFIDENCE_REASON_PLANNER = (
    "planner-supported evidence is material to readiness"
)
_CONFIDENCE_REASON_NO_PROTECTED = (
    "protected original-direct evidence is absent"
)
_CONFIDENCE_REASON_PROTECTED = (
    "protected original-direct evidence is present"
)
_CONFIDENCE_REASONS = frozenset(
    {
        _CONFIDENCE_REASON_EMPTY,
        _CONFIDENCE_REASON_PARTIAL,
        _CONFIDENCE_REASON_NO_ITEM,
        _CONFIDENCE_REASON_READY,
        _CONFIDENCE_REASON_TRUNCATED,
        _CONFIDENCE_REASON_PLANNER,
        _CONFIDENCE_REASON_NO_PROTECTED,
        _CONFIDENCE_REASON_PROTECTED,
        *_RECOMMENDED_CONFIDENCE_REASONS.values(),
    }
)


@dataclass(frozen=True)
class _NeedSpec:
    category: str
    subject_terms: tuple[str, ...]
    required: bool
    provenance: str


@dataclass(frozen=True)
class _IdentifierSubject:
    value: str
    start: int
    end: int
    category: str | None


@dataclass(frozen=True)
class _Clause:
    start: int
    end: int
    coordinated_with_previous: bool
    roles: tuple[tuple[str, int], ...]
    identifiers: tuple[_IdentifierSubject, ...]
    subjects: tuple[tuple[int, str], ...]
    database_subjects: bool
    chinese_page_subject: bool


@dataclass(frozen=True)
class _OrderedNeedSpec:
    spec: _NeedSpec
    category_position: int
    subject_position: int
    order: int


def derive_evidence_needs(
    bundle: QueryBundle,
    *,
    candidates: tuple[ContextCandidate, ...] | Iterable[ContextCandidate],
) -> tuple[EvidenceNeed, ...]:
    """Derive ordered needs only from bounded in-memory query evidence."""
    query = bundle.query if isinstance(bundle.query, str) else ""
    # Run both shared intent parsers exactly once against original-query data.
    infer_query_intent(query, query.split())
    identifier_intent = infer_identifier_intent(query, tokenize_query(query))
    normalized_candidates = tuple(candidates)
    explicit_specs = _derive_explicit_specs(
        query,
        identifier_intent.identifiers,
    )

    planner_specs = _derive_planner_specs(
        bundle,
        normalized_candidates,
        existing=explicit_specs,
    )
    structural_specs = _derive_structural_specs(
        explicit_specs,
        existing=(*explicit_specs, *planner_specs),
    )
    return _materialize_needs((*explicit_specs, *planner_specs, *structural_specs))


def candidate_matches_need(
    candidate: ContextCandidate,
    need: EvidenceNeed,
    content: str | None = None,
) -> bool:
    """Return whether one same-category candidate carries every scoped subject."""
    if candidate.group != need.category:
        return False
    if not need.subject_terms:
        return True

    searchable_content = candidate.content if content is None else content
    fields = (
        candidate.file_path,
        candidate.trusted_provenance_text,
        searchable_content,
    )
    return all(
        _subject_matches_fields(subject, fields)
        for subject in need.subject_terms
    )


def retained_item_matches_need(
    item: ContextItem,
    need: EvidenceNeed,
) -> bool:
    """Match one link against public fields and one retained excerpt at a time."""
    if item.group != need.category or not item.excerpts:
        return False
    return any(
        _retained_excerpt_matches_need(item, excerpt, need)
        for excerpt in item.excerpts
    )


def _retained_excerpt_matches_need(
    item: ContextItem,
    excerpt: ContextExcerpt,
    need: EvidenceNeed,
) -> bool:
    if item.group != need.category:
        return False
    if not need.subject_terms:
        return True
    provenance_text = "\n".join((item.file_path, *item.reasons))
    return all(
        _subject_matches_fields(
            subject,
            (item.file_path, provenance_text, excerpt.content),
        )
        for subject in need.subject_terms
    )


def derive_missing_evidence(
    evidence_needs: tuple[EvidenceNeed, ...] | Iterable[EvidenceNeed],
) -> tuple[MissingEvidence, ...]:
    """Describe each final unmatched need with one bounded fixed template."""
    return tuple(
        MissingEvidence(
            need_id=need.id,
            category=need.category,
            required=need.required,
            reason=missing_evidence_reason(need),
        )
        for need in evidence_needs
        if not need.matched_item_ids
    )


def missing_evidence_reason(need: EvidenceNeed) -> str:
    """Return the canonical public reason for one missing evidence need."""
    requiredness = "required" if need.required else "recommended"
    subject = _normalize_whitespace(" ".join(need.subject_terms))
    label = _EVIDENCE_LABELS[need.category]
    subject_prefix = f"{subject} " if subject else ""
    return (
        f"{requiredness} {subject_prefix}{label} evidence is missing "
        "from the bounded context"
    )


def derive_readiness_confidence(
    status: str,
    evidence_needs: tuple[EvidenceNeed, ...],
    items: tuple[ContextItem, ...],
    candidates_by_path: Mapping[str, ContextCandidate],
) -> ReadinessConfidence:
    """Derive the closed confidence table from final retained evidence."""
    if status == "empty":
        return ReadinessConfidence(
            level="none",
            reasons=(_CONFIDENCE_REASON_EMPTY,),
        )
    if status == "partial":
        reason = (
            _CONFIDENCE_REASON_PARTIAL
            if any(need.required and not need.matched_item_ids for need in evidence_needs)
            else _CONFIDENCE_REASON_NO_ITEM
        )
        return ReadinessConfidence(level="low", reasons=(reason,))

    protected_present = any(
        candidates_by_path[item.file_path].protected_direct
        for item in items
    )
    return derive_ready_confidence(
        evidence_needs,
        items,
        protected_present=protected_present,
    )


def derive_ready_confidence(
    evidence_needs: tuple[EvidenceNeed, ...],
    items: tuple[ContextItem, ...],
    *,
    protected_present: bool,
) -> ReadinessConfidence:
    """Derive the bounded, self-describing confidence for a ready pack."""
    need_by_id = {need.id: need for need in evidence_needs}
    missing_recommended = next(
        (
            need
            for need in evidence_needs
            if not need.required and not need.matched_item_ids
        ),
        None,
    )
    required_truncated = any(
        excerpt.truncated
        and any(
            need_by_id[need_id].required
            and _retained_excerpt_matches_need(
                item,
                excerpt,
                need_by_id[need_id],
            )
            for need_id in item.matched_need_ids
        )
        for item in items
        for excerpt in item.excerpts
    )
    planner_material = any(
        need_by_id[need_id].provenance == "planner_supported"
        for item in items
        for need_id in item.matched_need_ids
    )

    medium_reasons: list[str] = []
    if missing_recommended is not None:
        medium_reasons.append(
            _RECOMMENDED_CONFIDENCE_REASONS[missing_recommended.category]
        )
    if required_truncated:
        medium_reasons.append(_CONFIDENCE_REASON_TRUNCATED)
    if planner_material:
        medium_reasons.append(_CONFIDENCE_REASON_PLANNER)

    protected_reason = (
        _CONFIDENCE_REASON_PROTECTED
        if protected_present
        else _CONFIDENCE_REASON_NO_PROTECTED
    )
    reasons = (
        _CONFIDENCE_REASON_READY,
        *medium_reasons[: _MAX_CONFIDENCE_REASONS - 2],
        protected_reason,
    )
    level = "high" if protected_present and not medium_reasons else "medium"
    return ReadinessConfidence(level=level, reasons=reasons)


def protected_confidence_claim(reasons: Iterable[str]) -> bool | None:
    """Return the single protected-evidence claim, or None if not singular."""
    normalized = tuple(reasons)
    protected_present = _CONFIDENCE_REASON_PROTECTED in normalized
    protected_absent = _CONFIDENCE_REASON_NO_PROTECTED in normalized
    if protected_present == protected_absent:
        return None
    return protected_present


def derive_next_queries(
    bundle: QueryBundle,
    evidence_needs: tuple[EvidenceNeed, ...],
    items: tuple[ContextItem, ...],
    candidates_by_path: Mapping[str, ContextCandidate],
) -> tuple[NextQuery, ...]:
    """Build at most three grounded deterministic suggestions for missing needs."""
    ordered_missing = tuple(
        need
        for required in (True, False)
        for need in evidence_needs
        if need.required is required and not need.matched_item_ids
    )
    selected_candidates = tuple(
        candidates_by_path[item.file_path] for item in items
    )
    original_query = _normalize_whitespace(
        bundle.query if isinstance(bundle.query, str) else ""
    )
    suggestions: list[NextQuery] = []
    seen: set[str] = set()
    for need in ordered_missing:
        grounded = tuple(
            candidate
            for candidate in selected_candidates
            if candidate_matches_need(candidate, need)
        )
        seeds: list[str] = []
        if need.provenance != "planner_supported" and need.subject_terms:
            seeds.append(_normalize_whitespace(" ".join(need.subject_terms)))
        seeds.extend(
            PurePosixPath(candidate.file_path).stem
            for candidate in grounded
            if candidate.protected_direct
        )
        if (
            need.provenance == "planner_supported"
            and grounded
            and need.subject_terms
        ):
            seeds.append(_normalize_whitespace(" ".join(need.subject_terms)))
        seeds.append(original_query)

        query = next_query_text(need.category, seeds)
        if not query or query.casefold() in seen:
            continue
        seen.add(query.casefold())
        suggestions.append(
            NextQuery(
                need_id=need.id,
                query=query,
                purpose=next_query_purpose(need.category, need.required),
            )
        )
        if len(suggestions) == _MAX_NEXT_QUERIES:
            break
    return tuple(suggestions)


def next_query_purpose(category: str, required: bool) -> str:
    """Return the closed purpose string for one category and requiredness."""
    requiredness = "required" if required else "recommended"
    return (
        f"find missing {requiredness} {_EVIDENCE_LABELS[category]} evidence"
    )


def next_query_suffix(category: str) -> str:
    """Return the closed category suffix for a follow-up query."""
    return _NEXT_QUERY_SUFFIXES[category]


def confidence_reason_is_closed(reason: str) -> bool:
    """Return whether a confidence reason belongs to the fixed public set."""
    return reason in _CONFIDENCE_REASONS


def next_query_text(category: str, seeds: Iterable[str]) -> str:
    """Choose the first safe seed and append the complete bounded suffix."""
    suffix = _NEXT_QUERY_SUFFIXES[category]
    for raw_seed in seeds:
        seed = _normalize_whitespace(raw_seed)
        if not seed or "/oups" in seed.casefold():
            continue
        available = _MAX_NEXT_QUERY_CODE_POINTS - len(suffix) - 1
        if available <= 0:
            return suffix[:_MAX_NEXT_QUERY_CODE_POINTS]
        seed = seed[:available].rstrip()
        if seed:
            return f"{seed} {suffix}"
    return ""


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalized_subject_match_span(
    content: str,
    subject: str,
) -> tuple[int, int] | None:
    """Return the first candidate-semantic match in NFC-casefolded offsets."""
    matches = _normalized_subject_match_spans(content, subject, first_only=True)
    return matches[0] if matches else None


def normalized_subject_match_spans(
    content: str,
    subject: str,
) -> tuple[tuple[int, int], ...]:
    """Return all candidate-semantic matches in NFC-casefolded offsets."""
    return _normalized_subject_match_spans(content, subject, first_only=False)


def _normalized_subject_match_spans(
    content: str,
    subject: str,
    *,
    first_only: bool,
) -> tuple[tuple[int, int], ...]:
    normalized_subject = _normalize_subject(subject)
    if not normalized_subject:
        return ()
    normalized_content = unicodedata.normalize("NFC", content)

    if _contains_cjk(normalized_subject) or not normalized_subject.isascii():
        folded_content = normalized_content.casefold()
        needle = normalized_subject.casefold()
        matches: list[tuple[int, int]] = []
        offset = 0
        while offset < len(folded_content):
            start = folded_content.find(needle, offset)
            if start < 0:
                break
            matches.append((start, start + len(needle)))
            if first_only:
                break
            offset = start + 1
        return tuple(matches)

    raw_subject_spans, camel_subject_spans = _ascii_and_camel_token_spans(
        normalized_subject
    )
    raw_content_spans, camel_content_spans = _ascii_and_camel_token_spans(
        normalized_content
    )
    raw_subject = tuple(token for token, _, _ in raw_subject_spans)
    camel_subject = tuple(token for token, _, _ in camel_subject_spans)
    matches = sorted(
        {
            *_token_sequence_spans(
                raw_content_spans,
                raw_subject,
                first_only=first_only,
            ),
            *_token_sequence_spans(
                camel_content_spans,
                camel_subject,
                first_only=first_only,
            ),
        }
    )
    if not matches:
        plural_variant = _simple_ascii_plural_variant(
            normalized_subject,
            raw_subject,
        )
        if plural_variant:
            matches = sorted(
                {
                    *_token_sequence_spans(
                        raw_content_spans,
                        plural_variant,
                        first_only=first_only,
                    ),
                    *_token_sequence_spans(
                        camel_content_spans,
                        plural_variant,
                        first_only=first_only,
                    ),
                }
            )
    if not matches:
        return ()
    offsets = _casefold_offsets(normalized_content)
    converted = tuple((offsets[start], offsets[end]) for start, end in matches)
    return converted[:1] if first_only else converted


def _simple_ascii_plural_variant(
    normalized_subject: str,
    raw_subject: tuple[str, ...],
) -> tuple[str, ...]:
    if not normalized_subject.isalpha() or len(raw_subject) != 1:
        return ()
    token = raw_subject[0]
    if token.endswith(("ss", "us", "is")):
        return ()
    if token.endswith("s"):
        stem = token[:-1]
        return (stem,) if len(stem) >= 4 else ()
    return (f"{token}s",) if len(token) >= 4 else ()


def _derive_explicit_specs(
    query: str,
    inferred_identifiers: tuple[str, ...],
) -> list[_NeedSpec]:
    identifiers = _ordered_identifiers(query, inferred_identifiers)
    clauses = _query_clauses(query, identifiers)
    ordered: list[_OrderedNeedSpec] = []
    positions: dict[tuple[str, tuple[str, ...]], int] = {}
    resolved_clause_subjects: dict[int, tuple[tuple[int, str], ...]] = {}

    def add(
        spec: _NeedSpec,
        *,
        category_position: int,
        subject_position: int,
    ) -> None:
        key = (spec.category, spec.subject_terms)
        existing_position = positions.get(key)
        if existing_position is not None:
            existing = ordered[existing_position]
            merged_spec = (
                existing.spec
                if existing.spec.provenance == "explicit_identifier"
                or spec.provenance != "explicit_identifier"
                else spec
            )
            ordered[existing_position] = _OrderedNeedSpec(
                merged_spec,
                min(existing.category_position, category_position),
                min(existing.subject_position, subject_position),
                existing.order,
            )
            return
        positions[key] = len(ordered)
        ordered.append(
            _OrderedNeedSpec(
                spec,
                category_position,
                subject_position,
                len(ordered),
            )
        )

    for identifier in identifiers:
        if identifier.category is None:
            continue
        add(
            _NeedSpec(
                identifier.category,
                (_normalize_subject(identifier.value),),
                True,
                "explicit_identifier",
            ),
            category_position=identifier.start,
            subject_position=identifier.start,
        )

    for clause_index, clause in enumerate(clauses):
        for category, role_position in clause.roles:
            subjects = _subjects_for_clause_role(
                clauses,
                clause_index,
                category,
                role_position,
                resolved_clause_subjects,
            )
            resolved_clause_subjects[clause_index] = _dedupe_subjects(
                (
                    *resolved_clause_subjects.get(clause_index, ()),
                    *subjects,
                )
            )
            if not subjects:
                add(
                    _NeedSpec(category, (), True, "explicit_query"),
                    category_position=role_position,
                    subject_position=role_position,
                )
                continue
            for subject_position, subject in subjects:
                identifier = next(
                    (
                        item
                        for item in identifiers
                        if item.start == subject_position
                        and _normalize_subject(item.value) == subject
                    ),
                    None,
                )
                provenance = (
                    "explicit_identifier"
                    if identifier is not None and identifier.category == category
                    else "explicit_query"
                )
                add(
                    _NeedSpec(category, (subject,), True, provenance),
                    category_position=role_position,
                    subject_position=subject_position,
                )

    category_positions: dict[str, int] = {}
    for item in ordered:
        category_positions[item.spec.category] = min(
            category_positions.get(item.spec.category, len(query)),
            item.category_position,
        )
    category_order = {
        category: index
        for index, category in enumerate(
            sorted(
                category_positions,
                key=lambda category: (
                    category_positions[category],
                    CONTEXT_GROUPS.index(category),
                ),
            )
        )
    }
    ordered.sort(
        key=lambda item: (
            category_order[item.spec.category],
            item.subject_position,
            item.order,
        )
    )
    return [item.spec for item in ordered]


def _explicit_category_positions(query: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    for category in CONTEXT_GROUPS:
        if category == "supporting":
            continue
        position = _first_category_term_position(query, category)
        if position < len(query):
            positions[category] = position
    return positions


def _ordered_identifiers(
    query: str,
    identifiers: tuple[str, ...],
) -> tuple[_IdentifierSubject, ...]:
    values: list[_IdentifierSubject] = []
    seen: set[tuple[int, str]] = set()
    for identifier in identifiers:
        for match in re.finditer(re.escape(identifier), query):
            key = (match.start(), identifier)
            if key in seen:
                continue
            seen.add(key)
            values.append(
                _IdentifierSubject(
                    value=identifier,
                    start=match.start(),
                    end=match.end(),
                    category=_identifier_category(identifier),
                )
            )
    values.sort(key=lambda value: (value.start, value.end, value.value))
    return tuple(values)


def _query_clauses(
    query: str,
    identifiers: tuple[_IdentifierSubject, ...],
) -> tuple[_Clause, ...]:
    clauses: list[_Clause] = []
    for start, end, coordinated_with_previous in _clause_spans(query):
        text = query[start:end]
        roles = tuple(
            sorted(
                (
                    (category, start + position)
                    for category, position in _explicit_category_positions(text).items()
                ),
                key=lambda item: (item[1], CONTEXT_GROUPS.index(item[0])),
            )
        )
        clause_identifiers = tuple(
            identifier
            for identifier in identifiers
            if start <= identifier.start < end
        )
        database_subjects = tuple(
            (start + match.start(), _normalize_subject(match.group(0)))
            for match in _DATABASE_RE.finditer(text)
        )
        chinese_match = _CHINESE_PAGE_RE.search(text)
        chinese_subjects = (
            (
                (
                    start + chinese_match.start(),
                    _normalize_subject(chinese_match.group(0)),
                ),
            )
            if chinese_match
            else ()
        )
        if database_subjects:
            subjects = database_subjects
        elif chinese_subjects:
            subjects = chinese_subjects
        elif clause_identifiers:
            subjects = tuple(
                (identifier.start, _normalize_subject(identifier.value))
                for identifier in clause_identifiers
            )
        else:
            subjects = tuple(
                (start + position, subject)
                for position, subject in _extract_generic_subjects(text)
            )
        clauses.append(
            _Clause(
                start=start,
                end=end,
                coordinated_with_previous=coordinated_with_previous,
                roles=roles,
                identifiers=clause_identifiers,
                subjects=_dedupe_subjects(subjects),
                database_subjects=bool(database_subjects),
                chinese_page_subject=bool(chinese_subjects),
            )
        )
    return tuple(clauses)


def _clause_spans(query: str) -> tuple[tuple[int, int, bool], ...]:
    spans: list[tuple[int, int, bool]] = []
    start = 0
    coordinated_with_previous = False
    for separator in _CLAUSE_SEPARATOR_RE.finditer(query):
        _append_trimmed_span(
            query,
            spans,
            start,
            separator.start(),
            coordinated_with_previous,
        )
        start = separator.end()
        coordinated_with_previous = _separator_coordinates(separator.group(0))
    _append_trimmed_span(
        query,
        spans,
        start,
        len(query),
        coordinated_with_previous,
    )
    return tuple(spans)


def _append_trimmed_span(
    query: str,
    spans: list[tuple[int, int, bool]],
    start: int,
    end: int,
    coordinated_with_previous: bool,
) -> None:
    while start < end and query[start].isspace():
        start += 1
    while end > start and query[end - 1].isspace():
        end -= 1
    if start < end:
        spans.append((start, end, coordinated_with_previous))


def _separator_coordinates(separator: str) -> bool:
    if re.search(r"\b(?:and|or)\b", separator, re.IGNORECASE):
        return True
    return not any(char in separator for char in ";\r\n")


def _subjects_for_clause_role(
    clauses: tuple[_Clause, ...],
    clause_index: int,
    category: str,
    role_position: int,
    resolved_clause_subjects: dict[int, tuple[tuple[int, str], ...]],
) -> tuple[tuple[int, str], ...]:
    clause = clauses[clause_index]
    direct = _direct_role_subjects(clause, category, role_position)

    preceding: list[tuple[int, str]] = []
    index = clause_index - 1
    connected = clause.coordinated_with_previous
    while index >= 0 and connected and not clauses[index].roles:
        exact_identifier_boundary = _is_exact_identifier_boundary(clauses[index])
        if direct and exact_identifier_boundary:
            break
        preceding[0:0] = clauses[index].subjects
        if exact_identifier_boundary:
            break
        connected = clauses[index].coordinated_with_previous
        index -= 1

    following: list[tuple[int, str]] = []
    index = clause_index + 1
    while (
        index < len(clauses)
        and clauses[index].coordinated_with_previous
        and not clauses[index].roles
    ):
        exact_identifier_boundary = _is_exact_identifier_boundary(clauses[index])
        if direct and exact_identifier_boundary:
            break
        following.extend(clauses[index].subjects)
        if exact_identifier_boundary:
            break
        index += 1

    combined = _dedupe_subjects((*preceding, *direct, *following))
    if combined:
        return combined

    index = clause_index - 1
    while index >= 0 and clauses[index + 1].coordinated_with_previous:
        if resolved_clause_subjects.get(index):
            return resolved_clause_subjects[index]
        if clauses[index].subjects:
            return clauses[index].subjects
        index -= 1
    return _connected_trailing_subjects(clauses, clause_index)


def _is_exact_identifier_boundary(clause: _Clause) -> bool:
    return any(
        identifier.category is not None
        for identifier in clause.identifiers
    )


def _connected_trailing_subjects(
    clauses: tuple[_Clause, ...],
    clause_index: int,
) -> tuple[tuple[int, str], ...]:
    index = clause_index + 1
    while index < len(clauses) and clauses[index].coordinated_with_previous:
        clause = clauses[index]
        if not clause.roles:
            index += 1
            continue
        if not clause.subjects:
            index += 1
            continue
        first_role_position = min(position for _, position in clause.roles)
        trailing = tuple(
            subject
            for subject in clause.subjects
            if subject[0] > first_role_position
        )
        if not trailing:
            return ()

        following: list[tuple[int, str]] = []
        following_index = index + 1
        while (
            following_index < len(clauses)
            and clauses[following_index].coordinated_with_previous
            and not clauses[following_index].roles
        ):
            following_clause = clauses[following_index]
            if _is_exact_identifier_boundary(following_clause):
                break
            following.extend(following_clause.subjects)
            following_index += 1
        return _dedupe_subjects((*trailing, *following))
    return ()


def _direct_role_subjects(
    clause: _Clause,
    category: str,
    role_position: int,
) -> tuple[tuple[int, str], ...]:
    if (
        clause.database_subjects
        or clause.chinese_page_subject
        or not clause.identifiers
    ):
        return clause.subjects
    matching_identifiers = tuple(
        identifier
        for identifier in clause.identifiers
        if identifier.category == category
    )
    if matching_identifiers:
        selected = matching_identifiers
    elif len(clause.identifiers) == 1:
        selected = clause.identifiers
    else:
        selected = (
            min(
                clause.identifiers,
                key=lambda identifier: (
                    _identifier_role_distance(identifier, role_position),
                    identifier.start,
                ),
            ),
        )
    return tuple(
        (identifier.start, _normalize_subject(identifier.value))
        for identifier in selected
    )


def _identifier_role_distance(
    identifier: _IdentifierSubject,
    role_position: int,
) -> int:
    if identifier.end <= role_position:
        return role_position - identifier.end
    if identifier.start >= role_position:
        return identifier.start - role_position
    return 0


def _dedupe_subjects(
    subjects: Iterable[tuple[int, str]],
) -> tuple[tuple[int, str], ...]:
    values: list[tuple[int, str]] = []
    seen: set[str] = set()
    for position, subject in sorted(subjects, key=lambda item: item[0]):
        if not subject or subject in seen:
            continue
        seen.add(subject)
        values.append((position, subject))
    return tuple(values)


def _first_category_term_position(query: str, category: str) -> int:
    return min(
        (_term_position(query, term) for term in _EXPLICIT_ROLE_TERMS[category]),
        default=len(query),
    )


def _term_position(query: str, term: str) -> int:
    if _contains_cjk(term):
        folded_query = query.casefold()
        folded_term = term.casefold()
        return (
            folded_query.find(folded_term)
            if folded_term in folded_query
            else len(query)
        )
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(term).replace(r'\ ', r'\s+')}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    match = pattern.search(query)
    return match.start() if match else len(query)


def _identifier_category(identifier: str) -> str | None:
    tokens = _camel_tokens(identifier)
    for category, suffix_sequences in _IDENTIFIER_SUFFIX_CATEGORIES:
        if any(
            len(tokens) >= len(sequence)
            and tokens[-len(sequence) :] == sequence
            for sequence in suffix_sequences
        ):
            return category
    return None


def _high_signal_subjects(
    query: str,
    *,
    role_positions: Iterable[int],
    identifiers: tuple[str, ...],
) -> tuple[str, ...]:
    encountered: list[tuple[int, str]] = []

    chinese_page = _CHINESE_PAGE_RE.search(query)
    if chinese_page:
        encountered.append((chinese_page.start(), chinese_page.group(0)))

    for match in _DATABASE_RE.finditer(query):
        encountered.append((match.start(), match.group(0)))

    for identifier in identifiers:
        position = query.find(identifier)
        encountered.append((position if position >= 0 else len(query), identifier))

    if not encountered:
        positions = tuple(role_positions)
        first_role = min(positions, default=len(query))
        raw_region = query[:first_role]
        if not _extract_generic_subjects(raw_region):
            raw_region = query[first_role:]
        for position, subject in _extract_generic_subjects(raw_region):
            encountered.append((position, subject))

    encountered.sort(key=lambda item: item[0])
    subjects: list[str] = []
    for _, raw_subject in encountered:
        subject = _normalize_subject(raw_subject)
        if subject and subject not in subjects:
            subjects.append(subject)
    return tuple(subjects)


def _extract_generic_subjects(value: str) -> list[tuple[int, str]]:
    values: list[tuple[int, str]] = []
    cursor = 0
    for segment in _CONJUNCTION_RE.split(value):
        segment_position = value.find(segment, cursor)
        cursor = max(cursor, segment_position + len(segment))
        cleaned = segment
        for terms in _EXPLICIT_ROLE_TERMS.values():
            for term in sorted(terms, key=len, reverse=True):
                cleaned = _remove_term(cleaned, term)
        tokens: list[tuple[str, str]] = []
        for token in re.findall(r"[^\s]+", cleaned):
            normalized = _normalize_subject(token)
            if not normalized or normalized.casefold() in _SUBJECT_STOP_WORDS:
                continue
            tokens.append((token, normalized))
        if tokens:
            subject = _normalize_subject(
                " ".join(normalized for _, normalized in tokens)
            )
            first_token_position = segment.casefold().find(
                tokens[0][0].casefold()
            )
            values.append(
                (
                    max(0, segment_position + max(0, first_token_position)),
                    subject,
                )
            )
    return values


def _remove_term(value: str, term: str) -> str:
    if _contains_cjk(term):
        return value.replace(term, " ")
    return re.sub(
        rf"(?<![A-Za-z0-9_]){re.escape(term).replace(r'\ ', r'\s+')}(?![A-Za-z0-9_])",
        " ",
        value,
        flags=re.IGNORECASE,
    )


def _derive_planner_specs(
    bundle: QueryBundle,
    candidates: tuple[ContextCandidate, ...],
    *,
    existing: Iterable[_NeedSpec],
) -> tuple[_NeedSpec, ...]:
    planner = bundle.planner
    if planner.status != "ok":
        return ()

    discarded = {
        _comparison_key(value)
        for value in planner.discarded_hints
        if isinstance(value, str)
    }
    seen = {_spec_key(spec) for spec in existing}
    specs: list[_NeedSpec] = []
    fields = (
        *planner.rewritten_queries,
        *planner.grep_keywords,
        *planner.symbol_hints,
    )
    for raw_value in fields:
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        if _comparison_key(raw_value) in discarded:
            continue
        subjects = _planner_subjects(raw_value)
        explicit_categories = _explicit_category_positions(raw_value)
        for subject in subjects:
            if _comparison_key(subject) in discarded:
                continue
            categories = tuple(
                category
                for category, _ in sorted(
                    explicit_categories.items(),
                    key=lambda item: (item[1], CONTEXT_GROUPS.index(item[0])),
                )
            )
            if not categories:
                categories = tuple(
                    candidate.group
                    for candidate in candidates
                    if _subject_matches_candidate_text(candidate, subject)
                )
            for category in categories:
                spec = _NeedSpec(
                    category,
                    (subject,),
                    False,
                    "planner_supported",
                )
                key = _spec_key(spec)
                if key in seen or not _is_grounded(spec, candidates):
                    continue
                seen.add(key)
                specs.append(spec)
    return tuple(specs)


def _planner_subjects(value: str) -> tuple[str, ...]:
    positions = _explicit_category_positions(value).values()
    subjects = _high_signal_subjects(
        value,
        role_positions=positions,
        identifiers=(),
    )
    if subjects:
        return subjects
    normalized = _normalize_subject(value)
    return (normalized,) if normalized else ()


def _subject_matches_candidate_text(
    candidate: ContextCandidate,
    subject: str,
) -> bool:
    return _subject_matches_fields(
        subject,
        (
            candidate.file_path,
            candidate.trusted_provenance_text,
            candidate.content,
        ),
    )


def _is_grounded(
    spec: _NeedSpec,
    candidates: tuple[ContextCandidate, ...],
) -> bool:
    provisional = EvidenceNeed(
        id="need:provisional",
        category=spec.category,
        subject_terms=spec.subject_terms,
        required=False,
        provenance="planner_supported",
        matched_item_ids=(),
    )
    return any(candidate_matches_need(candidate, provisional) for candidate in candidates)


def _derive_structural_specs(
    explicit: tuple[_NeedSpec, ...] | list[_NeedSpec],
    *,
    existing: Iterable[_NeedSpec],
) -> tuple[_NeedSpec, ...]:
    seen = {_spec_key(spec) for spec in existing}
    specs: list[_NeedSpec] = []
    for target_category in CONTEXT_GROUPS:
        if target_category == "supporting":
            continue
        for source in explicit:
            if target_category not in _STRUCTURAL_RECOMMENDATIONS[source.category]:
                continue
            spec = _NeedSpec(
                target_category,
                source.subject_terms,
                False,
                "structural_recommendation",
            )
            key = _spec_key(spec)
            if key in seen:
                continue
            seen.add(key)
            specs.append(spec)
    return tuple(specs)


def _materialize_needs(specs: Iterable[_NeedSpec]) -> tuple[EvidenceNeed, ...]:
    counts: dict[str, int] = {}
    needs: list[EvidenceNeed] = []
    for spec in specs:
        slug = "-".join(_slug_subject(term) for term in spec.subject_terms)
        base = f"need:{spec.category}:{slug or 'general'}"
        count = counts.get(base, 0) + 1
        counts[base] = count
        need_id = base if count == 1 else f"{base}:{count}"
        needs.append(
            EvidenceNeed(
                id=need_id,
                category=spec.category,
                subject_terms=spec.subject_terms,
                required=spec.required,
                provenance=spec.provenance,
                matched_item_ids=(),
            )
        )
    return tuple(needs)


def _normalize_subject(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.split())
    normalized = _strip_edge_punctuation(normalized)
    return normalized[:_MAX_SUBJECT_CODE_POINTS]


def _strip_edge_punctuation(value: str) -> str:
    start = 0
    end = len(value)
    while start < end and (
        value[start].isspace() or unicodedata.category(value[start]).startswith("P")
    ):
        start += 1
    while end > start and (
        value[end - 1].isspace()
        or unicodedata.category(value[end - 1]).startswith("P")
    ):
        end -= 1
    return value[start:end]


def _slug_subject(value: str) -> str:
    pieces: list[str] = []
    pending_separator = False
    for char in unicodedata.normalize("NFC", value).casefold():
        category = unicodedata.category(char)
        if category[0] in {"L", "M", "N", "S"}:
            if pending_separator and pieces:
                pieces.append("-")
            pieces.append(char)
            pending_separator = False
        else:
            pending_separator = True
    return "".join(pieces).strip("-")


def _spec_key(spec: _NeedSpec) -> tuple[str, tuple[str, ...]]:
    return (
        spec.category,
        tuple(_comparison_key(term) for term in spec.subject_terms),
    )


def _comparison_key(value: str) -> str:
    return _slug_subject(_normalize_subject(value))


def _subject_matches_fields(subject: str, fields: tuple[str, ...]) -> bool:
    return any(
        normalized_subject_match_span(field, subject) is not None
        for field in fields
    )


def _camel_tokens(value: str) -> tuple[str, ...]:
    _, camel_spans = _ascii_and_camel_token_spans(value)
    return tuple(token for token, _, _ in camel_spans)


def _ascii_and_camel_token_spans(
    value: str,
) -> tuple[
    tuple[tuple[str, int, int], ...],
    tuple[tuple[str, int, int], ...],
]:
    ascii_parts: list[tuple[str, int, int]] = []
    camel_parts: list[tuple[str, int, int]] = []
    for word_match in _ASCII_WORD_RE.finditer(value):
        word = word_match.group(0)
        ascii_parts.append((word.casefold(), word_match.start(), word_match.end()))
        split = tuple(_CAMEL_PART_RE.finditer(word))
        if not split:
            camel_parts.append(
                (word.casefold(), word_match.start(), word_match.end())
            )
            continue
        for part in split:
            camel_parts.append(
                (
                    part.group(0).casefold(),
                    word_match.start() + part.start(),
                    word_match.start() + part.end(),
                )
            )
    return tuple(ascii_parts), tuple(camel_parts)


def _token_sequence_spans(
    haystack: tuple[tuple[str, int, int], ...],
    needle: tuple[str, ...],
    *,
    first_only: bool,
) -> tuple[tuple[int, int], ...]:
    if not needle or len(needle) > len(haystack):
        return ()
    matches: list[tuple[int, int]] = []
    width = len(needle)
    for index in range(len(haystack) - width + 1):
        if tuple(token for token, _, _ in haystack[index : index + width]) == needle:
            matches.append((haystack[index][1], haystack[index + width - 1][2]))
            if first_only:
                break
    return tuple(matches)


def _casefold_offsets(value: str) -> tuple[int, ...]:
    offsets = [0]
    for character in value:
        offsets.append(offsets[-1] + len(character.casefold()))
    return tuple(offsets)


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


__all__ = (
    "EvidenceNeed",
    "MissingEvidence",
    "NextQuery",
    "candidate_matches_need",
    "confidence_reason_is_closed",
    "derive_evidence_needs",
    "derive_missing_evidence",
    "derive_next_queries",
    "derive_ready_confidence",
    "derive_readiness_confidence",
    "missing_evidence_reason",
    "next_query_purpose",
    "next_query_suffix",
    "next_query_text",
    "normalized_subject_match_span",
    "normalized_subject_match_spans",
    "protected_confidence_claim",
    "retained_item_matches_need",
)
