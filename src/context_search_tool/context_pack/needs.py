"""Pure evidence-need derivation and candidate-scoped matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import TYPE_CHECKING, Iterable

from context_search_tool.context_pack.models import (
    CONTEXT_GROUPS,
    ContextCandidate,
    EvidenceNeed,
    MissingEvidence,
    NextQuery,
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
            "controller",
            "router",
            "route",
            "endpoint",
            "entrypoint",
            "form",
            "page",
            "view",
        ),
    ),
    (
        "implementations",
        (
            "implementation",
            "serviceimpl",
            "repository",
            "handler",
            "storage",
            "service",
            "impl",
        ),
    ),
    (
        "related_types",
        (
            "dto",
            "vo",
            "request",
            "response",
            "entity",
            "model",
            "record",
            "enum",
            "type",
        ),
    ),
    ("tests", ("integrationtests", "integrationtest", "tests", "test")),
    ("configs_docs", ("configuration", "properties", "config")),
)

_IDENTIFIER_ROLE_CATEGORIES = {
    "entrypoint": "entrypoints",
    "router": "entrypoints",
    "view": "entrypoints",
    "command": "entrypoints",
    "service": "implementations",
    "handler": "implementations",
    "repository": "implementations",
    "storage": "implementations",
    "data_type": "related_types",
}

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
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CAMEL_PART_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+"
)
_CHINESE_PAGE_RE = re.compile(r"[\u3400-\u9fff]+?(?:详情页|页面)")
_DATABASE_RE = re.compile(r"(?<![A-Za-z0-9])(?:mysql|postgresql)(?![A-Za-z0-9])", re.I)
_MAX_SUBJECT_CODE_POINTS = 64


@dataclass(frozen=True)
class _NeedSpec:
    category: str
    subject_terms: tuple[str, ...]
    required: bool
    provenance: str


def derive_evidence_needs(
    bundle: QueryBundle,
    *,
    candidates: tuple[ContextCandidate, ...] | Iterable[ContextCandidate],
) -> tuple[EvidenceNeed, ...]:
    """Derive ordered needs only from bounded in-memory query evidence."""
    query = bundle.query if isinstance(bundle.query, str) else ""
    query_intent = infer_query_intent(query, query.split())
    identifier_intent = infer_identifier_intent(query, tokenize_query(query))
    normalized_candidates = tuple(candidates)

    category_positions = _explicit_category_positions(query)
    identifier_categories = _ordered_identifier_categories(
        query,
        identifier_intent.identifiers,
    )
    for identifier, category, position in identifier_categories:
        previous = category_positions.get(category)
        if previous is None or position < previous:
            category_positions[category] = position

    # The shared inference calls intentionally receive only original-query data.
    # Their closed role outputs confirm categories already located by the table.
    _confirm_inferred_categories(
        category_positions,
        query,
        query_intent.target_roles,
        identifier_intent.role_hints,
    )

    subjects = _high_signal_subjects(
        query,
        role_positions=category_positions.values(),
        identifiers=identifier_intent.identifiers,
    )
    own_identifier_category = {
        identifier: category
        for identifier, category, _ in identifier_categories
    }

    explicit_specs: list[_NeedSpec] = []
    for category, _ in sorted(
        category_positions.items(),
        key=lambda item: (item[1], CONTEXT_GROUPS.index(item[0])),
    ):
        if subjects:
            for subject in subjects:
                provenance = (
                    "explicit_identifier"
                    if own_identifier_category.get(subject) == category
                    else "explicit_query"
                )
                explicit_specs.append(
                    _NeedSpec(category, (subject,), True, provenance)
                )
        else:
            explicit_specs.append(
                _NeedSpec(category, (), True, "explicit_query")
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


def _confirm_inferred_categories(
    positions: dict[str, int],
    query: str,
    target_roles: frozenset[str],
    identifier_roles: tuple[str, ...],
) -> None:
    inferred = {
        "entrypoint": "entrypoints",
        "implementation": "implementations",
        "test": "tests",
        "config": "configs_docs",
        "doc": "configs_docs",
    }
    for role in target_roles:
        category = inferred.get(role)
        if category in positions:
            positions[category] = min(
                positions[category],
                _first_category_term_position(query, category),
            )
    for role in identifier_roles:
        category = _IDENTIFIER_ROLE_CATEGORIES.get(role)
        if category in positions:
            positions[category] = min(
                positions[category],
                _first_category_term_position(query, category),
            )


def _explicit_category_positions(query: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    for category in CONTEXT_GROUPS:
        if category == "supporting":
            continue
        position = _first_category_term_position(query, category)
        if position < len(query):
            positions[category] = position
    return positions


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


def _ordered_identifier_categories(
    query: str,
    identifiers: tuple[str, ...],
) -> tuple[tuple[str, str, int], ...]:
    values: list[tuple[str, str, int]] = []
    for identifier in identifiers:
        category = _identifier_category(identifier)
        if category is None:
            continue
        position = query.find(identifier)
        values.append((identifier, category, position if position >= 0 else len(query)))
    values.sort(key=lambda value: (value[2], value[0]))
    return tuple(values)


def _identifier_category(identifier: str) -> str | None:
    folded = identifier.casefold()
    for category, suffixes in _IDENTIFIER_SUFFIX_CATEGORIES:
        if any(folded.endswith(suffix) for suffix in suffixes):
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
        tokens = []
        for token in re.findall(r"[^\s]+", cleaned):
            normalized = _normalize_subject(token)
            if not normalized or normalized.casefold() in _SUBJECT_STOP_WORDS:
                continue
            tokens.append(normalized)
        if tokens:
            subject = _normalize_subject(" ".join(tokens))
            values.append((max(0, segment_position), subject))
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
    normalized_subject = _normalize_subject(subject)
    if not normalized_subject:
        return False
    if _contains_cjk(normalized_subject):
        needle = unicodedata.normalize("NFC", normalized_subject).casefold()
        return any(needle in unicodedata.normalize("NFC", field).casefold() for field in fields)
    if normalized_subject.isascii():
        raw_subject = _ascii_tokens(normalized_subject)
        camel_subject = _camel_tokens(normalized_subject)
        if not raw_subject:
            return False
        return any(
            _contains_token_sequence(_ascii_tokens(field), raw_subject)
            or (
                camel_subject
                and _contains_token_sequence(_camel_tokens(field), camel_subject)
            )
            for field in fields
        )
    needle = unicodedata.normalize("NFC", normalized_subject).casefold()
    return any(needle in unicodedata.normalize("NFC", field).casefold() for field in fields)


def _ascii_tokens(value: str) -> tuple[str, ...]:
    return tuple(match.casefold() for match in _ASCII_WORD_RE.findall(value))


def _camel_tokens(value: str) -> tuple[str, ...]:
    parts: list[str] = []
    for word in _ASCII_WORD_RE.findall(value):
        split = _CAMEL_PART_RE.findall(word)
        parts.extend(part.casefold() for part in split or (word,))
    return tuple(parts)


def _contains_token_sequence(
    haystack: tuple[str, ...],
    needle: tuple[str, ...],
) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        haystack[index : index + width] == needle
        for index in range(len(haystack) - width + 1)
    )


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


__all__ = (
    "EvidenceNeed",
    "MissingEvidence",
    "NextQuery",
    "candidate_matches_need",
    "derive_evidence_needs",
)
