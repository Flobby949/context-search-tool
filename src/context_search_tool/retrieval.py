from __future__ import annotations

import logging
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from context_search_tool.chunker import expand_lines
from context_search_tool.config import ToolConfig
from context_search_tool.embeddings import provider_from_config
from context_search_tool.frontend_roles import (
    classify_frontend_role,
    extract_static_imports,
    frontend_candidate_scope_enabled,
    frontend_score_parts,
    resolve_frontend_import,
)
from context_search_tool.identifier_intent import IdentifierIntent, infer_identifier_intent
from context_search_tool.manifest import assert_manifest_compatible
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSpan,
    RetrievalSummary,
    SemanticMatch,
)
from context_search_tool.path_roles import PathRole, classify_path_role
from context_search_tool.paths import index_dir_for
from context_search_tool.project_scope import (
    QueryScope,
    infer_query_scope,
    project_scope_rerank_adjustment,
    project_scope_score_parts,
    project_units_from_chunk_metadata,
)
from context_search_tool.query_intent import QueryIntent, infer_query_intent
from context_search_tool.query_planner import (
    QueryPlanner,
    build_query_variants,
    expand_query_plan_tokens,
    planner_from_config,
    planner_hint_tokens,
)
from context_search_tool.repo_profile import build_repo_profile
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query
from context_search_tool.vector_store import NumpyVectorStore


logger = logging.getLogger(__name__)

MAX_EXPANSION_DEPTH = 3
MAX_EXPANSION_CANDIDATES = 1000
_MIN_RELATION_CONFIDENCE = 0.5
_RELATION_SCORE_DECAY = 0.8

_CJK_SEQUENCE_RE = re.compile(r"[㐀-鿿]{2,}")
_DIRECT_FRAGMENT_RE = re.compile(r"[A-Za-z0-9_./:@-]{3,}")
_DIRECT_TEXT_TOP_K_MULTIPLIER = 3
_NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES = {
    "doc": 0.45,
    "test": 0.25,
    "deployment_config": 0.35,
    "config_example": 0.35,
    "runtime_config": 0.25,
    "config": 0.20,
    "generated_output": 0.45,
    "lockfile": 0.35,
}
_ROUTE_EXACT_MATCH_BOOST = 0.35
_ROUTE_PREFIX_MATCH_BOOST = 0.12
_ROUTE_SIBLING_PENALTY = 0.18
_ROUTE_MISMATCH_PENALTY = 0.30
_ROUTE_TAIL_CONTEXT_MATCH_BOOST = 0.22
_JAVA_CONTEXT_MIN_TOKEN_OVERLAP = 2
_JAVA_METHOD_CONTEXT_MATCH_BOOST = 0.14
_JAVA_FIELD_CONTEXT_MATCH_BOOST = 0.12
_JAVA_EXECUTOR_CONTEXT_BOOST = 0.10
_SPRING_PATH_ENDPOINT_BOOST = 0.45
_SPRING_PATH_SERVICE_BOOST = 0.30
_SPRING_PATH_SERVICE_INTERFACE_BOOST = 0.10
_SPRING_PATH_EXECUTOR_BOOST = 0.28
_SPRING_PATH_MAX_DEPTH = 2
_JAVA_CONTEXT_STRUCTURAL_TOKENS = {
    "src",
    "main",
    "test",
    "java",
    "com",
    "org",
    "net",
}
_SOURCE_SUFFIXES = {
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".py", ".pyw",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".c", ".h",
    ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".cs", ".swift",
    ".php", ".rb", ".lua", ".dart", ".sh", ".bash", ".zsh", ".fish",
}
_FRONTEND_ENTRYPOINT_NAMES = {"main.ts", "main.tsx", "main.js", "main.jsx"}
_TEMPLATE_SUFFIXES = {".html", ".vue", ".svelte"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst"}
_CONFIG_SUFFIXES = {
    ".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".properties", ".env", ".xml",
}
_SEMANTIC_SCORE_WEIGHT = 0.55
_PLANNER_SEMANTIC_WEIGHT = 0.85
_RERANK_SORT_DECIMALS = 3
_INDEXED_LOCKFILE_NAMES = {
    "cargo.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "yarn.lock",
}
_LOCKFILE_QUERY_TOKENS = {
    "dependencies",
    "dependency",
    "lock",
    "lockfile",
    "lockfiles",
    "package",
    "packages",
    "version",
    "versions",
}
_FRONTEND_IMPORT_SCAN_TOP_K = 10
_FRONTEND_IMPORT_SCAN_FILE_LIMIT = 3
_FRONTEND_IMPORT_MAX_FILE_BYTES = 50_000
_FRONTEND_IMPORT_SUPPORT_BOOST = 0.30
_FRONTEND_IMPORT_ANCHOR_EPSILON = 10 ** -_RERANK_SORT_DECIMALS
_FRONTEND_IMPORT_ANCHOR_ROLES = {
    "view_page",
    "layout_component",
    "shared_component",
}
_FRONTEND_IMPORT_SUPPORT_ROLES = {
    "service",
    "utility",
    "store",
    "type_decl",
    "shared_component",
}
_SPAN_SOURCE_KEYS = (
    "path_symbol",
    "lexical",
    "semantic",
    "planner_semantic",
    "signal",
    "planner_hint",
    "anchor_expansion",
    "relation",
)


@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    query_variants: list[QueryVariant] = field(default_factory=list)
    variant_retrieval_status: str = "original_only"


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
class _ChunkRole:
    name: str
    priority: int
    boost: float
    penalty: float = 0.0


@dataclass(frozen=True)
class _GenericFileRole:
    name: str
    noise_level: str
    source_boost: float = 0.0
    penalty: float = 0.0
    penalty_key: str = ""


@dataclass(frozen=True)
class _RelationSeed:
    score: float
    planner_seeded: bool
    original_seeded: bool


@dataclass(frozen=True)
class _SpringPathImplementor:
    interface_name: str
    simple_name: str
    is_qualified: bool
    chunk_id: str


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


def query_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
) -> QueryBundle:
    repo = repo.resolve()
    original_tokens = _dedupe(tokenize_query(query))
    tokens = original_tokens
    plan = QueryPlan(original_query=query)
    query_variants = [QueryVariant("original", " ".join(query.split()), "original")]
    variant_retrieval_status = "original_only"
    index_dir = index_dir_for(repo)
    db_path = index_dir / "index.sqlite"
    if not db_path.exists():
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )

    assert_manifest_compatible(repo, config)

    store = SQLiteStore(db_path)
    try:
        deleted_ids = store.deleted_chunk_ids()
    except sqlite3.Error:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )

    query_planner = planner or planner_from_config(config.query_planner)
    repo_profile = build_repo_profile(store)
    plan = query_planner.plan(query, repo_profile=repo_profile)
    query_variants, discarded_variants = build_query_variants(
        query,
        plan,
        config.query_planner.max_rewritten_queries,
    )
    if discarded_variants:
        plan = replace(
            plan,
            discarded_hints=_ordered_unique(
                [*plan.discarded_hints, *discarded_variants]
            ),
        )
    tokens = expand_query_plan_tokens(query, plan)
    hint_tokens = (
        planner_hint_tokens(original_tokens, tokens) if plan.status == "ok" else []
    )
    initial_candidates, query_variants, variant_retrieval_status = _initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        query_variants,
        config,
        deleted_ids,
    )
    signal_candidates = _signal_candidates(store, original_tokens, config)
    planner_candidates = _planner_hint_candidates(store, hint_tokens, config)
    direct_candidates = _merge_candidates(
        [*initial_candidates, *signal_candidates, *planner_candidates]
    )
    anchor_candidates = _anchor_expansion_candidates(
        store,
        list(direct_candidates.values()),
        config,
        query=query,
        tokens=original_tokens,
    )
    relation_seed_candidates = _merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
        ]
    )
    relation_candidates = _relation_expansion_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    candidates = _merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
            *relation_candidates,
        ]
    )
    if not candidates:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )

    ranked_chunks = _rank_chunks(store, candidates, original_tokens, query)
    ranked_chunks = _apply_frontend_import_cohort_rerank(repo, ranked_chunks, query)
    expanded = _expand_ranked_chunks(repo, ranked_chunks, config, context_lines, full_file)
    visible_results, evidence_anchors = _split_code_results_and_evidence_anchors(
        expanded,
        final_top_k=config.retrieval.final_top_k,
        anchor_top_k=evidence_anchor_top_k(config.retrieval.final_top_k),
    )
    summary, result_reasons = _summarize_results(store, visible_results)
    results = [
        RetrievalResult(
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            content=item.content,
            score=item.rerank_score,
            score_parts={
                **item.score_parts,
                "combined_score": item.score,
                "rerank_score": item.rerank_score,
                "evidence_priority": float(item.evidence_priority),
            },
            reasons=_dedupe(item.reasons + result_reasons[index]),
            followup_keywords=item.followup_keywords,
            semantic_matches=item.semantic_matches,
            spans=item.spans,
        )
        for index, item in enumerate(visible_results)
    ]
    return QueryBundle(
        query=query,
        expanded_tokens=tokens,
        results=results,
        followup_keywords=_followup_keywords(results),
        summary=summary,
        planner=plan,
        evidence_anchors=evidence_anchors,
        query_variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
    )


def _split_code_results_and_evidence_anchors(
    expanded: list[_ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
) -> tuple[list[_ExpandedResult], list[EvidenceAnchor]]:
    code_results: list[_ExpandedResult] = []
    evidence_anchors: list[EvidenceAnchor] = []
    seen_anchor_keys: set[tuple[str, Path]] = set()

    for item in expanded:
        anchor_kind = _evidence_anchor_kind(item.file_path)
        if anchor_kind:
            anchor_key = (anchor_kind, item.file_path)
            if anchor_key in seen_anchor_keys:
                continue
            seen_anchor_keys.add(anchor_key)
            if len(evidence_anchors) < anchor_top_k:
                evidence_anchors.append(_evidence_anchor_from_expanded(item, anchor_kind))
            continue

        if len(code_results) < final_top_k:
            code_results.append(item)

    return code_results, evidence_anchors


def _evidence_anchor_from_expanded(
    item: _ExpandedResult,
    anchor_kind: str,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=item.file_path,
        start_line=item.start_line,
        end_line=item.end_line,
        content=item.content,
        score=item.rerank_score,
        score_parts={
            **item.score_parts,
            "combined_score": item.score,
            "rerank_score": item.rerank_score,
            "evidence_priority": float(item.evidence_priority),
        },
        reasons=item.reasons,
        anchor_kind=anchor_kind,
        semantic_matches=item.semantic_matches,
    )


def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))


def _summarize_results(
    store: SQLiteStore,
    visible_results: list[_ExpandedResult],
) -> tuple[RetrievalSummary, list[list[str]]]:
    summary = RetrievalSummary()
    result_reasons: list[list[str]] = []

    for item in visible_results:
        entry_points: list[str] = []
        impl: list[str] = []
        related: list[str] = []
        legacy: list[str] = []
        chunk_reasons: list[str] = []

        for chunk_id in item.chunk_ids:
            try:
                chunk = store.chunk_for_id(chunk_id)
            except KeyError:
                continue
            try:
                signals = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signals = []

            has_endpoint_signal = any(signal.kind == "endpoint" for signal in signals)
            has_usage_signal = any(signal.kind == "usage" for signal in signals)
            has_relation_support = _chunk_has_relation_support(store, chunk, signals)

            (
                chunk_entry,
                chunk_impl,
                chunk_related,
                chunk_legacy,
            ) = _summarize_chunk(chunk, signals, has_relation_support)

            chunk_has_support = (
                has_endpoint_signal or has_usage_signal or has_relation_support
            )
            legacy_names = set(chunk_legacy)
            entry_points.extend(chunk_entry)
            impl.extend(chunk_impl)
            if chunk_has_support:
                related.extend(chunk_related)
            else:
                related.extend([name for name in chunk_related if name not in legacy_names])
                legacy.extend(chunk_legacy)
            chunk_reasons.extend(
                _reasons_for_chunk(
                    signals,
                    chunk_impl,
                    chunk_legacy,
                    has_relation_support,
                    has_endpoint_signal,
                    has_usage_signal,
                )
            )

        result_reasons.append(_dedupe(chunk_reasons))
        summary.entry_points.extend(entry_points)
        summary.implementation.extend(impl)
        summary.related_types.extend(related)
        summary.possibly_legacy.extend(legacy)

    summary.entry_points = _ordered_unique(summary.entry_points)
    summary.implementation = _ordered_unique(summary.implementation)
    summary.related_types = _ordered_unique(summary.related_types)
    summary.possibly_legacy = _ordered_unique(summary.possibly_legacy)
    summary.entry_points.sort()
    summary.implementation.sort()
    summary.related_types.sort()
    summary.possibly_legacy.sort()
    return summary, result_reasons


def _summarize_chunk(
    chunk: DocumentChunk,
    signals: list,
    has_relation_support: bool,
) -> tuple[list[str], list[str], list[str], list[str]]:
    symbol_names = [symbol.name for symbol in chunk.symbols]
    endpoint: list[str] = []
    implementation: list[str] = []
    related_types: list[str] = []
    legacy: list[str] = []

    endpoint_signals = [signal.name for signal in signals if signal.kind == "endpoint"]
    if endpoint_signals:
        endpoint.extend(_ordered_unique(endpoint_signals))
    elif _is_controller_name(chunk.file_path.stem) or any(
        _is_controller_name(name) for name in symbol_names
    ):
        endpoint.append(_primary_chunk_name(chunk))

    names = _ordered_unique(
        [signal.name for signal in signals] + symbol_names + [_primary_chunk_name(chunk)]
    )
    method_impl_names = [
        name for name in names if _is_implementation_name(name) and "." in name
    ]
    if method_impl_names:
        implementation.extend(method_impl_names)
    else:
        implementation.extend(
            [name for name in names if _is_implementation_name(name) and "." not in name]
        )
    related_types.extend([name for name in names if _is_related_type_name(name)])

    if not endpoint and not has_relation_support and not implementation:
        legacy.extend([name for name in related_types if name])
    if has_relation_support and implementation and not any(
        "." in item for item in implementation
    ):
        implementation.extend([_primary_chunk_name(chunk)])

    return (
        _ordered_unique(endpoint),
        _ordered_unique(implementation),
        _ordered_unique(related_types),
        _ordered_unique(legacy),
    )


def _reasons_for_chunk(
    signals: list,
    impl_names: list[str],
    legacy_names: list[str],
    has_relation_support: bool,
    has_endpoint_signal: bool,
    has_usage_signal: bool,
) -> list[str]:
    reasons: list[str] = []
    if any(signal.kind == "endpoint" for signal in signals):
        reasons.append("endpoint signal match")
    if any(signal.kind == "comment" for signal in signals):
        reasons.append("comment signal match")
    if has_relation_support and impl_names:
        reasons.append("implementation chain match")
    if legacy_names and not has_relation_support and not has_usage_signal and not has_endpoint_signal:
        reasons.append("possibly legacy: no active usage signal found")
    return reasons


def _chunk_has_relation_support(
    store: SQLiteStore,
    chunk: DocumentChunk,
    signals: list[CodeSignal],
) -> bool:
    signal_ids = [signal.signal_id for signal in signals]
    for signal_id in signal_ids:
        try:
            if store.relations_for_source(signal_id):
                return True
        except sqlite3.Error:
            continue

    relation_targets = _ordered_unique(
        [chunk.file_path.stem] + [signal.name for signal in signals]
    )
    for target_name in relation_targets:
        try:
            if store.relations_targeting(target_name):
                return True
        except sqlite3.Error:
            continue

    return False


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value)
    return ordered


def _primary_chunk_name(chunk: DocumentChunk) -> str:
    if chunk.file_path.stem:
        return chunk.file_path.stem
    return ""


def _is_controller_name(value: str) -> bool:
    return value.lower().endswith("controller")


def _is_implementation_name(value: str) -> bool:
    lowered = value.lower()
    if "." in lowered:
        owner, _ = lowered.split(".", 1)
        if owner.endswith(("serviceimpl", "service", "impl")):
            return True
        return _is_implementation_name(owner)
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "service",
            "serviceimpl",
            "impl",
            "executor",
            "exe",
            "gateway",
            "mapper",
            "repository",
        )
    )


def _direct_text_probes(query: str, original_tokens: list[str]) -> list[str]:
    probes: list[str] = []
    stripped = query.strip()
    if stripped:
        probes.append(stripped)

    for part in re.split(r"\s+", stripped):
        if part and part != stripped:
            probes.append(part)

    for match in _CJK_SEQUENCE_RE.finditer(query):
        segment = match.group(0)
        probes.append(segment)
        chars = list(segment)
        for size in (2, 3):
            if len(chars) < size:
                continue
            for index in range(0, len(chars) - size + 1):
                probes.append("".join(chars[index : index + size]))

    for match in _DIRECT_FRAGMENT_RE.finditer(query):
        probes.append(match.group(0))

    for token in original_tokens:
        if len(token) >= 3 or _CJK_SEQUENCE_RE.search(token):
            probes.append(token)

    return _dedupe(probes)


def _direct_text_candidates(
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    limit = max(
        config.retrieval.lexical_top_k,
        config.retrieval.final_top_k * _DIRECT_TEXT_TOP_K_MULTIPLIER,
    )
    return store.direct_text_search(
        _direct_text_probes(query, original_tokens),
        limit,
    )


def _is_related_type_name(value: str) -> bool:
    lowered = value.lower()
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "dto",
            "vo",
            "request",
            "response",
            "query",
            "querytype",
            "domain",
            "type",
            "enum",
            "entity",
            "model",
            "bean",
        )
    ) or "domain" in lowered


def _initial_candidates(
    index_dir: Path,
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    query_variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    semantic_candidates, executed_variants, status = _semantic_candidates(
        index_dir,
        query_variants,
        config,
        deleted_ids,
    )
    return [
        *semantic_candidates,
        *_lexical_candidates(store, original_tokens, config.retrieval.lexical_top_k),
        *store.path_symbol_search(original_tokens, config.retrieval.lexical_top_k),
        *_direct_text_candidates(store, query, original_tokens, config),
    ], executed_variants, status


def _semantic_candidates(
    index_dir: Path,
    variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    provider = provider_from_config(config.embedding)
    vector_store = NumpyVectorStore(index_dir)
    try:
        vectors = provider.embed_texts([variant.text for variant in variants])
        if len(vectors) != len(variants):
            raise ValueError(
                "embedding response count does not match query variant count"
            )
        executed_variants = variants
        status = "hybrid" if len(variants) > 1 else "original_only"
    except Exception:
        if len(variants) == 1:
            raise
        executed_variants = variants[:1]
        vectors = provider.embed_texts(
            [variant.text for variant in executed_variants]
        )
        if len(vectors) != 1:
            raise ValueError("embedding response count does not match original query")
        status = "embedding_fallback"

    candidates: list[RetrievalCandidate] = []
    for variant, vector in zip(executed_variants, vectors):
        source = "semantic" if variant.source == "original" else "planner_semantic"
        for item in vector_store.search(
            vector,
            config.retrieval.semantic_top_k,
            deleted_ids,
        ):
            candidates.append(
                RetrievalCandidate(
                    chunk_id=item.chunk_id,
                    score=item.score,
                    source=source,
                    score_parts={source: item.score},
                    semantic_matches=[SemanticMatch(variant.variant_id, item.score)],
                )
            )
    return candidates, executed_variants, status


def _signal_candidates(
    store: SQLiteStore,
    tokens: list[str],
    config: ToolConfig,
    planner_hint: bool = False,
) -> list[RetrievalCandidate]:
    limit = max(
        config.retrieval.semantic_top_k,
        config.retrieval.lexical_top_k,
        config.retrieval.final_top_k,
    )
    source = "planner_signal" if planner_hint else "signal"
    score_key = "planner_signal" if planner_hint else "signal"
    candidates: list[RetrievalCandidate] = []
    for signal in store.signal_search(tokens, limit):
        score = _signal_score(signal.name, signal.tokens, signal.metadata, tokens)
        if score <= 0:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=signal.chunk_id,
                score=score,
                source=source,
                score_parts={score_key: score},
            )
        )
    return candidates


def _planner_hint_candidates(
    store: SQLiteStore,
    hint_tokens: list[str],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    if not hint_tokens:
        return []
    path_symbol = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_path_symbol",
            score_parts={"planner_path_symbol": item.score},
        )
        for item in store.path_symbol_search(
            hint_tokens,
            config.retrieval.lexical_top_k,
        )
    ]
    lexical = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_lexical",
            score_parts={"planner_lexical": item.score},
        )
        for item in _lexical_candidates(
            store,
            hint_tokens,
            config.retrieval.lexical_top_k,
        )
    ]
    signals = _signal_candidates(store, hint_tokens, config, planner_hint=True)
    return [*lexical, *path_symbol, *signals]


def _anchor_expansion_candidates(
    store: SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
    query: str = "",
    tokens: list[str] | None = None,
) -> list[RetrievalCandidate]:
    direct_seeds = [
        candidate
        for candidate in seed_candidates
        if candidate.score_parts.get("direct_text", 0.0) > 0
    ]
    if not direct_seeds:
        return []

    limit = max(config.retrieval.final_top_k * 3, config.retrieval.final_top_k)
    expanded: dict[str, RetrievalCandidate] = {}
    seed_ids = {candidate.chunk_id for candidate in direct_seeds}
    query_tokens = tokens or []

    for candidate in sorted(
        direct_seeds,
        key=lambda item: (
            -item.score_parts.get("direct_text", item.score),
            item.chunk_id,
        ),
    ):
        try:
            anchor_chunk = store.chunk_for_id(candidate.chunk_id)
        except KeyError:
            continue
        anchor_score = _bounded_score(
            candidate.score_parts.get("direct_text", candidate.score)
        )
        _add_same_file_anchor_candidates(
            store,
            expanded,
            seed_ids,
            anchor_chunk,
            anchor_score,
            limit,
            query,
            query_tokens,
        )
        if _is_document_or_config_anchor(anchor_chunk.file_path):
            _add_directory_anchor_candidates(
                store,
                expanded,
                seed_ids,
                anchor_chunk,
                anchor_score,
                limit,
            )
        if len(expanded) >= limit:
            break

    return list(expanded.values())


def _add_same_file_anchor_candidates(
    store: SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
    query: str,
    tokens: list[str],
) -> None:
    score = anchor_score * 0.80
    for chunk in store.chunks_for_file(anchor_chunk.file_path, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _should_skip_same_file_anchor_candidate(chunk, query, tokens):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "same_file_anchor",
        )
        if len(expanded) >= limit:
            return


def _should_skip_same_file_anchor_candidate(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> bool:
    role = _generic_file_role(chunk, query, tokens)
    return role.name == "generated_schema" or (
        role.name == "template" and role.penalty > 0
    )


def _add_directory_anchor_candidates(
    store: SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
) -> None:
    score = anchor_score * 0.55
    for chunk in store.chunks_in_directory(anchor_chunk.file_path.parent, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _is_document_or_config_anchor(chunk.file_path):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "directory_anchor",
        )
        if len(expanded) >= limit:
            return


def _put_anchor_candidate(
    expanded: dict[str, RetrievalCandidate],
    chunk_id: str,
    score: float,
    anchor_key: str,
) -> None:
    existing = expanded.get(chunk_id)
    if existing is not None and existing.score >= score:
        return
    score_parts = {
        "anchored_relation": score,
        "original_relation": score,
        anchor_key: score,
    }
    expanded[chunk_id] = RetrievalCandidate(
        chunk_id=chunk_id,
        score=score,
        source="anchored_relation",
        score_parts=score_parts,
    )


def _is_document_or_config_anchor(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".md", ".yml", ".yaml", ".json", ".properties"}


def _evidence_anchor_kind(path: Path) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() == ".md" and stem.startswith("readme"):
        return "readme"
    if path.suffix.lower() == ".md" and stem.startswith("risks"):
        return "risks"
    if name == "pom.xml":
        return "pom"
    return ""


def _is_readme_document(path: Path) -> bool:
    return path.suffix.lower() == ".md" and path.stem.lower().startswith("readme")


def _relation_expansion_candidates(
    store: SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    if not seed_candidates:
        return []

    source_limit = max(
        config.retrieval.semantic_top_k
        + config.retrieval.lexical_top_k
        + config.retrieval.final_top_k,
        config.retrieval.final_top_k,
    )
    if source_limit <= 0:
        return []

    expanded_by_chunk: dict[str, RetrievalCandidate] = {}
    seen_chunks = {candidate.chunk_id for candidate in seed_candidates}
    seed_scores = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    visited_signals: set[str] = set()
    frontier: list[tuple[str, float, int, bool, bool]] = []
    ordered_seed_candidates = sorted(
        seed_candidates,
        key=lambda item: (
            _relation_seed_source_priority(item.score_parts),
            -seed_scores[item.chunk_id].score,
            item.chunk_id,
        ),
    )[:source_limit]
    seed_chunk_ids = [
        candidate.chunk_id
        for candidate in ordered_seed_candidates
        if seed_scores[candidate.chunk_id].score > 0
    ]
    seed_signals_by_chunk = store.signals_for_chunks(seed_chunk_ids)

    for candidate in ordered_seed_candidates:
        relation_seed = seed_scores[candidate.chunk_id]
        if relation_seed.score <= 0:
            continue
        for signal in seed_signals_by_chunk.get(candidate.chunk_id, []):
            if signal.signal_id in visited_signals:
                continue
            visited_signals.add(signal.signal_id)
            frontier.append(
                (
                    signal.signal_id,
                    relation_seed.score,
                    0,
                    relation_seed.planner_seeded,
                    relation_seed.original_seeded,
                )
            )

    while frontier:
        active_frontier = [
            source for source in frontier if source[2] < MAX_EXPANSION_DEPTH
        ]
        if not active_frontier:
            break

        relations_by_source = store.relations_for_sources(
            [source_signal_id for source_signal_id, *_ in active_frontier]
        )
        relation_steps: list[tuple[str, float, int, bool, bool]] = []
        target_names: list[str] = []
        for (
            source_signal_id,
            current_score,
            depth,
            planner_seeded,
            original_seeded,
        ) in active_frontier:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < _MIN_RELATION_CONFIDENCE:
                    continue
                next_score = (
                    current_score * relation.confidence * _RELATION_SCORE_DECAY
                )
                relation_steps.append(
                    (
                        relation.target_name,
                        next_score,
                        next_depth,
                        planner_seeded,
                        original_seeded,
                    )
                )
                target_names.append(relation.target_name)

        if not relation_steps:
            break

        remaining = MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
        if remaining <= 0:
            _log_expansion_limit()
            return sorted(
                expanded_by_chunk.values(),
                key=lambda candidate: (-candidate.score, candidate.chunk_id),
            )
        chunks_by_target = store.chunks_matching_signal_or_symbols(
            target_names,
            remaining,
        )
        reached_chunk_ids: list[str] = []
        signal_seed_by_chunk: dict[str, tuple[float, int, bool, bool]] = {}
        for (
            target_name,
            next_score,
            next_depth,
            planner_seeded,
            original_seeded,
        ) in relation_steps:
            remaining = MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
            if remaining <= 0:
                _log_expansion_limit()
                return sorted(
                    expanded_by_chunk.values(),
                    key=lambda candidate: (-candidate.score, candidate.chunk_id),
                )

            for chunk in chunks_by_target.get(target_name, [])[:remaining]:
                existing = expanded_by_chunk.get(chunk.chunk_id)
                seed_score = seed_scores.get(
                    chunk.chunk_id,
                    _RelationSeed(0.0, False, False),
                ).score
                should_add_relation = (
                    chunk.chunk_id not in seed_scores or next_score > seed_score
                )
                if should_add_relation and (
                    existing is None or next_score > existing.score
                ):
                    score_parts = {"relation": next_score}
                    if planner_seeded:
                        score_parts["planner_relation"] = next_score
                    if original_seeded:
                        score_parts["original_relation"] = next_score
                    expanded_by_chunk[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=next_score,
                        source="relation",
                        score_parts=score_parts,
                    )

                if chunk.chunk_id not in seen_chunks:
                    seen_chunks.add(chunk.chunk_id)
                    if len(expanded_by_chunk) >= MAX_EXPANSION_CANDIDATES:
                        _log_expansion_limit()
                        return sorted(
                            expanded_by_chunk.values(),
                            key=lambda candidate: (
                                -candidate.score,
                                candidate.chunk_id,
                            ),
                        )

                next_signal_seed = (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                )
                existing_signal_seed = signal_seed_by_chunk.get(chunk.chunk_id)
                if existing_signal_seed is None:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed
                    reached_chunk_ids.append(chunk.chunk_id)
                elif next_score > existing_signal_seed[0]:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed

        next_frontier: list[tuple[str, float, int, bool, bool]] = []
        if reached_chunk_ids:
            signals_by_chunk = store.signals_for_chunks(reached_chunk_ids)
            for chunk_id in reached_chunk_ids:
                (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                ) = signal_seed_by_chunk[chunk_id]
                for signal in signals_by_chunk.get(chunk_id, []):
                    if signal.signal_id in visited_signals:
                        continue
                    visited_signals.add(signal.signal_id)
                    next_frontier.append(
                        (
                            signal.signal_id,
                            next_score,
                            next_depth,
                            planner_seeded,
                            original_seeded,
                        )
                    )
        frontier = next_frontier

    return sorted(
        expanded_by_chunk.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk_id),
    )


def _candidate_base_score(candidate: RetrievalCandidate) -> float:
    return _bounded_score(max(candidate.score, *candidate.score_parts.values(), 0.0))


def _relation_seed_source_priority(score_parts: dict[str, float]) -> int:
    if score_parts.get("relation", 0.0) > 0:
        return 0
    if score_parts.get("signal", 0.0) > 0:
        return 1
    if score_parts.get("direct_text", 0.0) > 0:
        return 2
    if max(
        score_parts.get("anchored_relation", 0.0),
        score_parts.get("same_file_anchor", 0.0),
        score_parts.get("directory_anchor", 0.0),
    ) > 0:
        return 3
    if score_parts.get("planner_signal", 0.0) > 0:
        return 4
    return 5


def _candidate_relation_seed(candidate: RetrievalCandidate) -> _RelationSeed:
    relation_score = candidate.score_parts.get("relation", 0.0)
    if relation_score > 0:
        planner_seeded = candidate.score_parts.get("planner_relation", 0.0) > 0
        original_seeded = candidate.score_parts.get("original_relation", 0.0) > 0
        if not planner_seeded and not original_seeded:
            original_seeded = True
        return _RelationSeed(
            _bounded_score(relation_score),
            planner_seeded,
            original_seeded,
        )

    signal_score = candidate.score_parts.get("signal", 0.0)
    planner_signal_score = candidate.score_parts.get("planner_signal", 0.0)
    if signal_score > 0:
        return _RelationSeed(
            _bounded_score(signal_score),
            planner_signal_score > 0,
            True,
        )

    direct_text_score = candidate.score_parts.get("direct_text", 0.0)
    if direct_text_score > 0:
        return _RelationSeed(
            _bounded_score(direct_text_score),
            False,
            True,
        )

    anchored_score = max(
        candidate.score_parts.get("anchored_relation", 0.0),
        candidate.score_parts.get("same_file_anchor", 0.0),
        candidate.score_parts.get("directory_anchor", 0.0),
    )
    if anchored_score > 0:
        return _RelationSeed(
            _bounded_score(anchored_score),
            False,
            True,
        )

    if planner_signal_score > 0:
        return _RelationSeed(
            _bounded_score(planner_signal_score) * 0.65,
            True,
            False,
        )

    return _RelationSeed(0.0, False, False)


def _log_expansion_limit() -> None:
    logger.warning(
        "relation expansion hit candidate limit (%s); returning partial candidates",
        MAX_EXPANSION_CANDIDATES,
    )


def _merge_candidates(
    candidates: list[RetrievalCandidate],
) -> dict[str, RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.chunk_id)
        score_parts = _normalized_score_parts(candidate)
        if existing is None:
            merged[candidate.chunk_id] = RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=candidate.score,
                source=candidate.source,
                score_parts=score_parts,
                semantic_matches=candidate.semantic_matches,
            )
            continue

        merged[candidate.chunk_id] = RetrievalCandidate(
            chunk_id=candidate.chunk_id,
            score=max(existing.score, candidate.score),
            source=f"{existing.source},{candidate.source}",
            score_parts=_merge_score_parts(existing.score_parts, score_parts),
            semantic_matches=_merge_semantic_matches(
                existing.semantic_matches,
                candidate.semantic_matches,
            ),
        )
    return merged


def _merge_semantic_matches(
    left: list[SemanticMatch],
    right: list[SemanticMatch],
) -> list[SemanticMatch]:
    by_variant: dict[str, SemanticMatch] = {}
    for match in [*left, *right]:
        existing = by_variant.get(match.variant_id)
        if existing is None or match.score > existing.score:
            by_variant[match.variant_id] = match
    return sorted(by_variant.values(), key=_semantic_match_sort_key)


def _semantic_match_sort_key(match: SemanticMatch) -> tuple[int, int, str]:
    if match.variant_id == "original":
        return (0, 0, "")
    prefix, separator, raw_index = match.variant_id.partition(":")
    if prefix == "planner" and separator and raw_index.isdigit():
        return (1, int(raw_index), "")
    return (2, 0, match.variant_id)


def _rank_chunks(
    store: SQLiteStore,
    candidates: dict[str, RetrievalCandidate],
    tokens: list[str],
    query: str,
) -> list[_RankedChunk]:
    # First pass: compute scores and build ranked list
    ranked: list[_RankedChunk] = []
    all_combined_scores: list[float] = []
    signal_cache: dict[str, list[CodeSignal]] = {}
    query_route = _query_route(query)
    candidate_chunks = store.chunks_for_ids(list(candidates))
    project_units = project_units_from_chunk_metadata(tuple(candidate_chunks.values()))
    query_scope = infer_query_scope(query, tokens, project_units)
    identifier_intent = infer_identifier_intent(query, tokens)
    query_intent = infer_query_intent(query, tokens)
    frontend_enabled = frontend_candidate_scope_enabled(
        chunk.file_path for chunk in candidate_chunks.values()
    )
    spring_path_parts = _spring_path_score_parts(
        store,
        candidate_chunks,
        query_route,
    )
    java_context_tokens = _java_context_query_tokens(tokens, query_route)

    def signals_for_ranked_chunk(chunk_id: str) -> list[CodeSignal]:
        if chunk_id not in signal_cache:
            try:
                signal_cache[chunk_id] = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signal_cache[chunk_id] = []
        return signal_cache[chunk_id]

    for candidate in candidates.values():
        chunk = candidate_chunks.get(candidate.chunk_id)
        if chunk is None:
            continue
        signals: list[CodeSignal] | None = None

        def get_signals() -> list[CodeSignal]:
            nonlocal signals
            if signals is None:
                signals = signals_for_ranked_chunk(candidate.chunk_id)
            return signals

        score_parts = _merge_score_parts(
            dict(candidate.score_parts),
            spring_path_parts.get(candidate.chunk_id, {}),
        )
        coverage = _token_coverage(tokens, chunk)
        if coverage:
            score_parts["token_coverage"] = coverage

        plugin_boost = _plugin_boost(chunk)
        route_boost = _route_boost(chunk, query, tokens)
        plugin_boost += route_boost
        if plugin_boost:
            score_parts["plugin_boost"] = plugin_boost
        if route_boost:
            score_parts["route_boost"] = route_boost

        score_parts = _merge_score_parts(
            score_parts,
            _generic_noise_score_parts(chunk, query, tokens),
        )
        path_role = classify_path_role(chunk.file_path, chunk.content)
        score_parts = _merge_score_parts(
            score_parts,
            _query_intent_score_parts(path_role, query_intent),
        )
        penalty = abs(min(score_parts.get("penalty", 0.0), 0.0))

        if query_route and _chunk_looks_route_relevant(
            chunk,
            tokens,
            query_route,
            route_boost=route_boost,
        ):
            route_score_parts = _route_score_parts(
                get_signals(),
                query,
                query_route=query_route,
            )
            score_parts.update(route_score_parts)

        role = _chunk_role(chunk)
        if query_route:
            score_parts.update(_route_tail_context_score_parts(chunk, query_route, role))
        if _should_apply_java_context_score(chunk, java_context_tokens, role, penalty):
            score_parts.update(
                _java_context_score_parts(get_signals(), java_context_tokens, role)
            )

        score_parts = _merge_score_parts(
            score_parts,
            project_scope_score_parts(
                chunk,
                query_scope,
                project_unit_count=len(project_units),
            ),
        )
        score_parts = _merge_score_parts(
            score_parts,
            _frontend_entrypoint_scope_score_parts(chunk, query_scope, score_parts),
        )
        score_parts = _merge_score_parts(
            score_parts,
            _identifier_intent_score_parts(chunk, identifier_intent, path_role),
        )
        score_parts = _merge_score_parts(
            score_parts,
            frontend_score_parts(chunk.file_path, query, enabled=frontend_enabled),
        )

        score_parts = _with_effective_semantic(score_parts)
        score = _combined_score(score_parts)
        all_combined_scores.append(score)
        has_signal_evidence = score_parts.get("signal", 0.0) > 0
        rank_tier_signals = get_signals() if has_signal_evidence else None

        # Precompute flags for rerank scoring
        flags = {
            'has_endpoint_signal': has_signal_evidence and any(
                signal.kind == "endpoint" for signal in rank_tier_signals or []
            ),
            'is_controller': penalty == 0 and 'controller' in chunk.file_path.as_posix().lower(),
            'has_relation_support': score_parts.get("original_relation", 0.0) > 0 or score_parts.get("planner_relation", 0.0) > 0,
            'role_name': role.name,
            'role_priority': role.priority,
        }

        ranked.append({
            'chunk': chunk,
            'score': score,
            'score_parts': score_parts,
            'flags': flags,
            'role': role,
            'path_role': path_role,
            'signals': rank_tier_signals,
        })

    # Normalize all combined scores
    normalized_scores = normalize_score(all_combined_scores)

    # Update ranked items with normalized scores and compute unclamped rerank scores
    for i, item in enumerate(ranked):
        normalized_score = normalized_scores[i]
        evidence_class = _evidence_class(item['score_parts'])
        evidence_priority = _evidence_priority(evidence_class)

        # Compute unclamped rerank score
        rerank_score = _rerank_score(
            normalized_score,
            item['score_parts'],
            item['chunk'],
            item['flags'],
            item['role'],
            path_role=item['path_role'],
            query_intent=query_intent,
            planner_ceiling=None,
        )

        item['normalized_score'] = normalized_score
        item['pre_ceiling_rerank_score'] = rerank_score
        item['rerank_score'] = rerank_score
        item['evidence_class'] = evidence_class
        item['evidence_priority'] = evidence_priority

    strong_direct_results = [
        r for r in ranked
        if _has_strong_original_direct_evidence(r['score_parts'])
    ]
    # Prefer business-chain anchors, but preserve exact detail-only queries.
    ceiling_anchor_results = [
        r for r in strong_direct_results
        if r['role'].name not in {"handler", "constant_or_config"}
    ] or strong_direct_results

    # Compute planner_ceiling from strong direct results
    if ceiling_anchor_results:
        planner_ceiling = min(r['rerank_score'] for r in ceiling_anchor_results) * (1.0 - 1e-6)
    else:
        planner_ceiling = None

    # Second pass: apply ceiling clamp to non-strong evidence classes
    for item in ranked:
        item["was_ceiling_clamped"] = (
            item["evidence_class"] in _CLAMPED_EVIDENCE_CLASSES
            and planner_ceiling is not None
            and item["rerank_score"] > planner_ceiling
        )
        if item["was_ceiling_clamped"]:
            item["rerank_score"] = planner_ceiling

        score_parts = item['score_parts']
        score_parts["combined_score"] = float(item['score'])
        score_parts["rerank_score"] = float(item['rerank_score'])
        score_parts["evidence_priority"] = float(item['evidence_priority'])
        score_parts["role_priority"] = float(item['role'].priority)
        score_parts["role_boost"] = (
            0.0
            if _has_project_scope_mismatch(score_parts)
            else float(item['role'].boost)
        )

    # Cohort coherence: in multi-unit repos, demote candidates outside the
    # Top1 anchor's project unit so cross-unit lexical or call-reference
    # matches do not interleave with the anchor's cohort. The anchor is the
    # prerank Top1 by rerank_score; it is never penalized, so Top1 is stable.
    # Conservative: skipped for mixed-scope queries and for chunks lacking
    # explicit project metadata. Does not enter _combined_score.
    if len(project_units) > 1:
        anchor_item = max(ranked, key=lambda item: item['rerank_score'])
        anchor_unit = _chunk_project_unit(anchor_item['chunk'])
        if anchor_unit and not _query_scope_is_mixed(query_scope):
            for item in ranked:
                if item is anchor_item:
                    continue
                candidate_unit = _chunk_project_unit(item['chunk'])
                if candidate_unit and candidate_unit != anchor_unit:
                    item['rerank_score'] -= _COHORT_MISMATCH_PENALTY
                    cohort_parts = item['score_parts']
                    cohort_parts["cohort_mismatch_penalty"] = -_COHORT_MISMATCH_PENALTY
                    cohort_parts["rerank_score"] = float(item['rerank_score'])

    # Build final _RankedChunk objects
    final_ranked = [
        _RankedChunk(
            chunk=item['chunk'],
            score=item['score'],
            score_parts=item['score_parts'],
            reasons=_reasons(item['score_parts'], query),
            rank_tier=_rank_tier(store, item['chunk'], item['score_parts'], item['signals']),
            rerank_score=item['rerank_score'],
            evidence_class=item['evidence_class'],
            evidence_priority=item['evidence_priority'],
            semantic_matches=candidates[item['chunk'].chunk_id].semantic_matches,
            pre_ceiling_rerank_score=item['pre_ceiling_rerank_score'],
            was_ceiling_clamped=item['was_ceiling_clamped'],
        )
        for item in ranked
    ]

    return sorted(
        final_ranked,
        key=_ranked_chunk_sort_key,
    )


def _ranked_chunk_sort_key(
    item: _RankedChunk,
) -> tuple[float, int, int, float, float, float, float, str, int, str]:
    return (
        -round(item.rerank_score, _RERANK_SORT_DECIMALS),
        item.evidence_priority,
        0 if item.was_ceiling_clamped else 1,
        -(item.pre_ceiling_rerank_score if item.was_ceiling_clamped else 0.0),
        item.score_parts.get("role_priority", 99.0),
        -item.rerank_score,
        -item.score,
        item.chunk.file_path.as_posix(),
        item.chunk.start_line,
        item.chunk.chunk_id,
    )


def _apply_frontend_import_cohort_rerank(
    repo: Path,
    ranked_chunks: list[_RankedChunk],
    query: str,
) -> list[_RankedChunk]:
    import_anchor_scores: dict[str, float] = {}
    files_read = 0

    for ranked in ranked_chunks[:_FRONTEND_IMPORT_SCAN_TOP_K]:
        if files_read >= _FRONTEND_IMPORT_SCAN_FILE_LIMIT:
            break
        anchor_role = classify_frontend_role(ranked.chunk.file_path).name
        if anchor_role not in _FRONTEND_IMPORT_ANCHOR_ROLES:
            continue

        try:
            content = _read_frontend_import_anchor(repo / ranked.chunk.file_path)
        except OSError:
            continue

        files_read += 1
        anchor_path = ranked.chunk.file_path.as_posix()
        for specifier in extract_static_imports(content):
            resolved = resolve_frontend_import(repo, ranked.chunk.file_path, specifier)
            if resolved and resolved != anchor_path:
                import_anchor_scores[resolved] = max(
                    ranked.rerank_score,
                    import_anchor_scores.get(resolved, float("-inf")),
                )

    if not import_anchor_scores:
        return ranked_chunks

    adjusted: list[_RankedChunk] = []
    for ranked in ranked_chunks:
        path = ranked.chunk.file_path.as_posix()
        role = classify_frontend_role(ranked.chunk.file_path).name
        if path not in import_anchor_scores or role not in _FRONTEND_IMPORT_SUPPORT_ROLES:
            adjusted.append(ranked)
            continue

        score_parts = dict(ranked.score_parts)
        existing_boost = score_parts.get("frontend_import_support_boost", 0.0)
        boost_delta = max(0.0, _FRONTEND_IMPORT_SUPPORT_BOOST - existing_boost)
        if boost_delta <= 0:
            adjusted.append(ranked)
            continue

        anchor_ceiling = import_anchor_scores[path] - _FRONTEND_IMPORT_ANCHOR_EPSILON
        rerank_score = min(ranked.rerank_score + boost_delta, anchor_ceiling)
        applied_boost = rerank_score - ranked.rerank_score
        if applied_boost <= 0:
            adjusted.append(ranked)
            continue

        score_parts["frontend_import_support_boost"] = applied_boost
        score_parts["rerank_score"] = rerank_score
        adjusted.append(
            _RankedChunk(
                chunk=ranked.chunk,
                score=ranked.score,
                score_parts=score_parts,
                reasons=_reasons(score_parts, query),
                rank_tier=ranked.rank_tier,
                rerank_score=rerank_score,
                evidence_class=ranked.evidence_class,
                evidence_priority=ranked.evidence_priority,
                semantic_matches=ranked.semantic_matches,
                pre_ceiling_rerank_score=ranked.pre_ceiling_rerank_score,
                was_ceiling_clamped=ranked.was_ceiling_clamped,
            )
        )

    return sorted(adjusted, key=_ranked_chunk_sort_key)


def _read_frontend_import_anchor(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(_FRONTEND_IMPORT_MAX_FILE_BYTES).decode(
            "utf-8",
            errors="replace",
        )


def _expand_ranked_chunks(
    repo: Path,
    ranked_chunks: list[_RankedChunk],
    config: ToolConfig,
    context_lines: int | None,
    full_file: bool,
) -> list[_ExpandedResult]:
    expanded: list[_ExpandedResult] = []
    for ranked in ranked_chunks:
        source_path = repo / ranked.chunk.file_path
        try:
            file_size = source_path.stat().st_size
            file_content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            file_content = ranked.chunk.content
            file_size = len(file_content.encode("utf-8"))

        lines = file_content.splitlines()
        if full_file and file_size <= config.index.max_full_file_bytes:
            start_line = 1
            end_line = len(lines)
            content = file_content
        else:
            before, after = _context_window(config, context_lines)
            start_line, end_line, content = expand_lines(
                lines,
                ranked.chunk.start_line,
                ranked.chunk.end_line,
                before,
                after,
            )
        if full_file:
            end_line, content = _cap_content_bytes(
                content,
                start_line,
                config.index.max_full_file_bytes,
            )

        expanded.append(
            _ExpandedResult(
                chunk_ids=[ranked.chunk.chunk_id],
                file_path=ranked.chunk.file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                score=ranked.score,
                score_parts=ranked.score_parts,
                reasons=ranked.reasons,
                followup_keywords=ranked.chunk.lexical_tokens,
                rank_tier=ranked.rank_tier,
                rerank_score=ranked.rerank_score,
                evidence_class=ranked.evidence_class,
                evidence_priority=ranked.evidence_priority,
                semantic_matches=ranked.semantic_matches,
                pre_ceiling_rerank_score=ranked.pre_ceiling_rerank_score,
                was_ceiling_clamped=ranked.was_ceiling_clamped,
                spans=_normalize_spans(
                    (
                        RetrievalSpan(
                            start_line=ranked.chunk.start_line,
                            end_line=ranked.chunk.end_line,
                            score=(
                                ranked.rerank_score
                                if math.isfinite(ranked.rerank_score)
                                else 0.0
                            ),
                            sources=_span_sources(ranked.score_parts),
                        ),
                    ),
                    start_line,
                    end_line,
                ),
            )
        )

    merged = _merge_overlapping_results(expanded)
    if not full_file:
        return merged
    return [
        _cap_expanded_result(result, config.index.max_full_file_bytes)
        for result in merged
    ]


def _lexical_candidates(
    store: SQLiteStore,
    tokens: list[str],
    limit: int,
) -> list[RetrievalCandidate]:
    exact = store.lexical_search(tokens, limit)
    if exact or not tokens or limit <= 0:
        return exact

    scores: dict[str, float] = {}
    for token in tokens:
        for candidate in store.lexical_search([token], limit):
            scores[candidate.chunk_id] = (
                scores.get(candidate.chunk_id, 0.0) + candidate.score
            )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        RetrievalCandidate(
            chunk_id=chunk_id,
            score=score,
            source="lexical",
            score_parts={"lexical": score},
        )
        for chunk_id, score in ranked[:limit]
    ]


def _signal_score(
    name: str,
    signal_tokens: list[str],
    metadata: dict[str, object],
    query_tokens: list[str],
) -> float:
    normalized = [token.lower() for token in query_tokens if token]
    if not normalized:
        return 0.0

    name_text = name.lower()
    token_set = {token.lower() for token in signal_tokens}
    metadata_text = _metadata_text(metadata)
    path_tokens: set[str] = set()
    path_value = metadata.get("path")
    if isinstance(path_value, str):
        path_tokens = set(tokenize_query(path_value))
        path_text = path_value.lower()
    else:
        path_text = ""

    score = 0.0
    for token in normalized:
        token_score = 0.0
        if token in name_text:
            token_score = max(token_score, 1.0)
        if token in token_set:
            token_score = max(token_score, 1.0)
        if token in metadata_text:
            token_score = max(token_score, 1.0)
        if token in path_tokens or token in path_text:
            token_score = max(token_score, 0.9)
        score += token_score
    return score / len(normalized)


def _metadata_text(metadata: dict[str, object]) -> str:
    values: list[str] = []
    for key, value in metadata.items():
        values.append(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (int, float, bool)):
            values.append(str(value))
        elif value is not None:
            values.append(str(value))
    return " ".join(values).lower()


def _cap_content_bytes(
    content: str,
    start_line: int,
    max_bytes: int,
) -> tuple[int, str]:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return _end_line_for_content(start_line, content), content
    if max_bytes <= 0:
        return start_line, ""

    trimmed = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return _end_line_for_content(start_line, trimmed), trimmed


def _cap_expanded_result(
    result: _ExpandedResult,
    max_bytes: int,
) -> _ExpandedResult:
    end_line, content = _cap_content_bytes(
        result.content,
        result.start_line,
        max_bytes,
    )
    return _ExpandedResult(
        chunk_ids=result.chunk_ids,
        file_path=result.file_path,
        start_line=result.start_line,
        end_line=end_line,
        content=content,
        score=result.score,
        score_parts=result.score_parts,
        reasons=result.reasons,
        followup_keywords=result.followup_keywords,
        rank_tier=result.rank_tier,
        rerank_score=result.rerank_score,
        evidence_class=result.evidence_class,
        evidence_priority=result.evidence_priority,
        semantic_matches=result.semantic_matches,
        pre_ceiling_rerank_score=result.pre_ceiling_rerank_score,
        was_ceiling_clamped=result.was_ceiling_clamped,
        spans=_normalize_spans(result.spans, result.start_line, end_line),
    )


def _end_line_for_content(start_line: int, content: str) -> int:
    if not content:
        return start_line
    return start_line + max(0, len(content.splitlines()) - 1)


def _merge_overlapping_results(results: list[_ExpandedResult]) -> list[_ExpandedResult]:
    by_file: dict[Path, list[_ExpandedResult]] = {}
    for result in results:
        by_file.setdefault(result.file_path, []).append(result)

    merged: list[_ExpandedResult] = []
    for file_path, file_results in by_file.items():
        sorted_results = sorted(
            file_results,
            key=lambda item: (item.start_line, item.end_line, -item.score),
        )
        current: _ExpandedResult | None = None
        for result in sorted_results:
            if current is None:
                current = result
                continue
            if result.start_line <= current.end_line + 1:
                current = _merge_expanded_result(current, result)
                continue
            merged.append(current)
            current = result
        if current is not None:
            merged.append(current)

    return sorted(
        merged,
        key=_expanded_result_sort_key,
    )


def _expanded_result_sort_key(
    item: _ExpandedResult,
) -> tuple[float, int, int, float, float, float, float, str, int]:
    return (
        -round(item.rerank_score, _RERANK_SORT_DECIMALS),
        item.evidence_priority,
        0 if item.was_ceiling_clamped else 1,
        -(item.pre_ceiling_rerank_score if item.was_ceiling_clamped else 0.0),
        item.score_parts.get("role_priority", 99.0),
        -item.rerank_score,
        -item.score,
        item.file_path.as_posix(),
        item.start_line,
    )


def _merge_expanded_result(
    left: _ExpandedResult,
    right: _ExpandedResult,
) -> _ExpandedResult:
    left_lines = left.content.splitlines()
    right_lines = right.content.splitlines()
    overlap = max(0, left.end_line - right.start_line + 1)
    content_lines = [*left_lines, *right_lines[overlap:]]

    winner = min(left, right, key=_expanded_result_sort_key)

    # Merge score_parts: max for most fields, winner value for rerank-related fields
    merged_score_parts = _merge_score_parts(left.score_parts, right.score_parts)
    merged_score_parts["rerank_score"] = winner.rerank_score
    # evidence_priority is smaller-is-better, so use winner's value
    merged_score_parts["evidence_priority"] = float(winner.evidence_priority)
    for key in (
        "role_priority",
        "role_boost",
        "role_penalty",
        "file_hint_match_boost",
        "role_exact_match_boost",
        "identifier_exact_match_boost",
        "path_role_hint_boost",
        "path_role_mismatch_penalty",
        "impl_match_boost",
        "relation_role_boost",
        "relation_detail_penalty",
        "frontend_import_support_boost",
    ):
        if key in winner.score_parts:
            merged_score_parts[key] = winner.score_parts[key]
        else:
            merged_score_parts.pop(key, None)

    start_line = min(left.start_line, right.start_line)
    end_line = max(left.end_line, right.end_line)
    return _ExpandedResult(
        chunk_ids=_dedupe([*left.chunk_ids, *right.chunk_ids]),
        file_path=left.file_path,
        start_line=start_line,
        end_line=end_line,
        content="\n".join(content_lines),
        score=max(left.score, right.score),
        score_parts=merged_score_parts,
        reasons=winner.reasons,
        followup_keywords=_dedupe([*left.followup_keywords, *right.followup_keywords]),
        rank_tier=min(left.rank_tier, right.rank_tier),
        rerank_score=winner.rerank_score,
        evidence_class=winner.evidence_class,
        evidence_priority=winner.evidence_priority,
        semantic_matches=_merge_semantic_matches(
            left.semantic_matches,
            right.semantic_matches,
        ),
        pre_ceiling_rerank_score=winner.pre_ceiling_rerank_score,
        was_ceiling_clamped=winner.was_ceiling_clamped,
        spans=_normalize_spans(
            (*left.spans, *right.spans),
            start_line,
            end_line,
        ),
    )


def _span_sources(score_parts: dict[str, float]) -> tuple[str, ...]:
    sources = tuple(
        key for key in _SPAN_SOURCE_KEYS if score_parts.get(key, 0.0) > 0.0
    )
    return sources or ("ranked",)


def _normalize_spans(
    spans: tuple[RetrievalSpan, ...],
    start_line: int,
    end_line: int,
) -> tuple[RetrievalSpan, ...]:
    visible_end = max(start_line, end_line)
    normalized: list[RetrievalSpan] = []
    for span in spans:
        span_start = min(max(span.start_line, start_line), visible_end)
        span_end = min(max(span.end_line, span_start), visible_end)
        normalized.append(
            RetrievalSpan(
                start_line=span_start,
                end_line=span_end,
                score=span.score if math.isfinite(span.score) else 0.0,
                sources=span.sources or ("ranked",),
            )
        )

    ordered = sorted(
        normalized,
        key=lambda span: (
            span.start_line,
            span.end_line,
            -span.score,
            span.sources,
        ),
    )
    deduplicated: list[RetrievalSpan] = []
    seen_windows: set[tuple[int, int]] = set()
    for span in ordered:
        window = (span.start_line, span.end_line)
        if window in seen_windows:
            continue
        seen_windows.add(window)
        deduplicated.append(span)
    return tuple(deduplicated)


def _normalized_score_parts(candidate: RetrievalCandidate) -> dict[str, float]:
    if candidate.source == "semantic":
        return {"semantic": candidate.score_parts.get("semantic", candidate.score)}
    if candidate.source == "planner_semantic":
        return {
            "planner_semantic": candidate.score_parts.get(
                "planner_semantic",
                candidate.score,
            )
        }
    if candidate.source == "lexical":
        return {
            "lexical": candidate.score_parts.get(
                "lexical",
                candidate.score_parts.get("fts", candidate.score),
            )
        }
    if candidate.source == "path_symbol":
        return {
            "path_symbol": candidate.score_parts.get("path_symbol", candidate.score)
        }
    return dict(candidate.score_parts)


def _merge_score_parts(
    left: dict[str, float],
    right: dict[str, float],
) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        if key == "penalty" or key.endswith("_penalty"):
            merged[key] = min(merged.get(key, value), value)
        else:
            merged[key] = max(merged.get(key, value), value)
    return merged


def _chunk_role(chunk: DocumentChunk) -> _ChunkRole:
    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    haystack = f"{path} {names} {content}"
    path_and_names = f"{path} {names}"

    if _is_test_path(path):
        return _ChunkRole("generic", 5, 0.0)
    if "controller" in path or "controller" in names:
        return _ChunkRole("entrypoint", 0, 0.18)
    if "/service/impl/" in path or "serviceimpl" in path_and_names:
        return _ChunkRole("service_impl", 1, 0.12)
    class_names = [chunk.file_path.stem.lower(), *(symbol.name.lower() for symbol in chunk.symbols)]
    if any(name.endswith(("queryexe", "qryexe", "executor", "queryexecutor", "exe")) for name in class_names):
        return _ChunkRole("executor", 2, 0.12)
    if any(token in path for token in ("/dto/", "/vo/", "/query/", "/entity/")):
        return _ChunkRole("data_type", 3, 0.04)
    if "/service/" in path and "interface " in content:
        return _ChunkRole("service_interface", 4, 0.06)
    if "/service/" in path:
        return _ChunkRole("service", 2, 0.0)
    if "/mapper/" in path or "mapper" in names:
        return _ChunkRole("mapper", 4, 0.03)
    if any(token in haystack for token in ("handler", "listener", "callback", "connector", "webhook")):
        return _ChunkRole("handler", 5, 0.0, 0.10)
    if any(token in haystack for token in ("constant", "config", "buildermanager", "parambuilder")):
        return _ChunkRole("constant_or_config", 6, 0.0, 0.12)
    return _ChunkRole("generic", 5, 0.0)


def _with_effective_semantic(score_parts: dict[str, float]) -> dict[str, float]:
    updated = dict(score_parts)
    original_exists = "semantic" in updated
    planner_exists = "planner_semantic" in updated
    if not original_exists and not planner_exists:
        return updated

    adjusted_planner: float | None = None
    if planner_exists:
        planner_score = updated["planner_semantic"]
        adjusted_planner = planner_score * _PLANNER_SEMANTIC_WEIGHT if planner_score > 0 else planner_score

    if original_exists and adjusted_planner is not None:
        effective = max(updated["semantic"], adjusted_planner)
    elif original_exists:
        effective = updated["semantic"]
    else:
        assert adjusted_planner is not None
        effective = adjusted_planner
    updated["effective_semantic"] = effective
    return updated


def _combined_score(score_parts: dict[str, float]) -> float:
    return (
        score_parts.get("effective_semantic", score_parts.get("semantic", 0.0))
        * _SEMANTIC_SCORE_WEIGHT
        + (score_parts.get("lexical", 0.0) * 0.25)
        + (min(score_parts.get("path_symbol", 0.0), 5.0) / 5.0 * 0.15)
        + (score_parts.get("planner_lexical", 0.0) * 0.12)
        + (
            min(score_parts.get("planner_path_symbol", 0.0), 5.0)
            / 5.0
            * 0.07
        )
        + _bounded_score(score_parts.get("signal", 0.0))
        + (_bounded_score(score_parts.get("planner_signal", 0.0)) * 0.65)
        + _bounded_score(score_parts.get("relation", 0.0))
        + _bounded_score(score_parts.get("original_relation", 0.0))
        + _bounded_score(score_parts.get("planner_relation", 0.0))
        + (_bounded_score(score_parts.get("anchored_relation", 0.0)) * 0.75)
        + (score_parts.get("token_coverage", 0.0) * 0.20)
        + (_bounded_score(score_parts.get("direct_text", 0.0)) * 0.45)  # High weight for literal text matches in comments/strings
        + score_parts.get("plugin_boost", 0.0)
        + score_parts.get("route_exact_match", 0.0)
        + score_parts.get("route_prefix_match", 0.0)
        + score_parts.get("route_sibling_penalty", 0.0)
        + score_parts.get("route_mismatch_penalty", 0.0)
        + score_parts.get("route_tail_context_match", 0.0)
        + score_parts.get("java_method_context_match", 0.0)
        + score_parts.get("java_field_context_match", 0.0)
        + score_parts.get("java_executor_context_boost", 0.0)
        + score_parts.get("spring_path_endpoint_match", 0.0)
        + score_parts.get("spring_path_service_match", 0.0)
        + score_parts.get("spring_path_service_interface_match", 0.0)
        + score_parts.get("spring_path_executor_match", 0.0)
        + score_parts.get("file_role_source_boost", 0.0)
        + score_parts.get("frontend_entrypoint_boost", 0.0)
        + score_parts.get("frontend_support_boost", 0.0)
        + score_parts.get("frontend_support_name_match_boost", 0.0)
        + score_parts.get("penalty", 0.0)
    )


def _bounded_score(score: float) -> float:
    return min(max(score, 0.0), 1.0)


# Thresholds for strong evidence classification
_STRONG_SEMANTIC_EVIDENCE = 0.35
_STRONG_LEXICAL_EVIDENCE = 0.25
_STRONG_PATH_SYMBOL_EVIDENCE = 1.0
_STRONG_SIGNAL_EVIDENCE = 0.5

_CLAMPED_EVIDENCE_CLASSES = {
    "weak_original_direct",
    "original_relation",
    "planner_direct",
    "planner_relation",
    "weak_or_generic",
}


def _has_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains direct original query evidence.

    This is similar to _has_original_query_evidence but excludes original_relation.
    Used to distinguish direct matches from relation-only expansion results.

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any direct evidence exists (semantic, lexical, path_symbol, signal, token_coverage, direct_text)
    """
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "semantic",
            "lexical",
            "path_symbol",
            "signal",
            "token_coverage",
            "direct_text",
        )
    )


def _has_planner_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains direct planner evidence (excluding planner_relation).

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any planner direct evidence exists
    """
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "planner_semantic",
            "planner_lexical",
            "planner_signal",
            "planner_path_symbol",
        )
    )


def _has_strong_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains strong original direct evidence.

    Used to compute dynamic planner_ceiling. Strong evidence means at least one
    of the direct signals exceeds its threshold.

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any strong evidence threshold is met
    """
    token_coverage = score_parts.get("token_coverage", 0.0)
    corroborated_text_match = token_coverage >= 0.2 and (
        score_parts.get("semantic", 0.0) >= _STRONG_SEMANTIC_EVIDENCE
        or score_parts.get("lexical", 0.0) >= _STRONG_LEXICAL_EVIDENCE
    )
    return (
        corroborated_text_match
        or score_parts.get("path_symbol", 0.0) >= _STRONG_PATH_SYMBOL_EVIDENCE
        or score_parts.get("signal", 0.0) >= _STRONG_SIGNAL_EVIDENCE
        or token_coverage >= 0.5
        or score_parts.get("direct_text", 0.0) >= 0.60
    )


def _has_weak_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    return (
        _has_original_direct_evidence(score_parts)
        and not _has_strong_original_direct_evidence(score_parts)
    )


def _evidence_class(score_parts: dict[str, float]) -> str:
    """
    Classify evidence type using the established decision order.

    Decision order:
    1. original_direct: has strong direct original evidence
    2. weak_original_direct: has weak direct original evidence
    3. planner_direct: has planner direct evidence
    4. original_relation: has original_relation score only
    5. planner_relation: has planner_relation score only
    6. weak_or_generic: fallback for everything else

    Args:
        score_parts: Dictionary of score components

    Returns:
        Evidence class string
    """
    if _has_strong_original_direct_evidence(score_parts):
        return "original_direct"
    if _has_weak_original_direct_evidence(score_parts):
        return "weak_original_direct"
    if _has_planner_direct_evidence(score_parts):
        return "planner_direct"
    if score_parts.get("original_relation", 0.0) > 0:
        return "original_relation"
    if score_parts.get("planner_relation", 0.0) > 0:
        return "planner_relation"
    return "weak_or_generic"


def _evidence_priority(evidence_class: str) -> int:
    """
    Map evidence class to numeric priority (0 is highest priority).

    Args:
        evidence_class: Evidence class string from _evidence_class

    Returns:
        Priority value 0-4
    """
    priority_map = {
        "original_direct": 0,
        "weak_original_direct": 1,
        "planner_direct": 1,
        "original_relation": 2,
        "planner_relation": 3,
        "weak_or_generic": 4,
    }
    return priority_map.get(evidence_class, 4)


def normalize_score(scores: list[float]) -> list[float]:
    """
    Normalize scores to [0, 1] range using max normalization.

    Args:
        scores: List of raw scores

    Returns:
        List of normalized scores in [0, 1] range
    """
    if not scores:
        return []

    # Handle NaN/inf values by clipping to 0.0
    cleaned_scores = []
    for s in scores:
        if s != s or s == float('inf') or s == float('-inf'):  # NaN or inf check
            cleaned_scores.append(0.0)
        else:
            cleaned_scores.append(s)

    max_score = max(cleaned_scores)

    if max_score <= 0.0:
        return [0.0] * len(cleaned_scores)

    if len(cleaned_scores) == 1:
        return [1.0]

    return [max(s, 0.0) / max_score for s in cleaned_scores]


def _generic_hint_penalty(chunk: DocumentChunk, score_parts: dict[str, float]) -> float:
    """
    Return penalty for generic symbols that match too broadly.

    Generic patterns include: Service, Controller, Manager, message, device.
    These often get weak lexical/path matches but aren't semantically relevant.

    Args:
        chunk: The document chunk to check
        score_parts: Score components (unused but kept for future extension)

    Returns:
        Penalty value (e.g., 0.1 for generic symbols, 0.0 otherwise)
    """
    generic_patterns = [
        "Service",
        "Controller",
        "Manager",
        "message",
        "device",
    ]

    content_lower = chunk.content.lower()
    path_str = str(chunk.file_path).lower()

    for pattern in generic_patterns:
        if pattern.lower() in content_lower or pattern.lower() in path_str:
            return 0.1

    return 0.0


def _rerank_score(
    normalized_score: float,
    score_parts: dict[str, float],
    chunk: DocumentChunk,
    flags: dict,
    role: _ChunkRole,
    *,
    path_role: PathRole | None = None,
    query_intent: QueryIntent = QueryIntent(),
    planner_ceiling: float | None,
) -> float:
    """
    Compute rerank score with boosts, penalties, and ceiling clamp.

    Formula:
        rerank_score = normalized_score
            + original_direct_boost (strong direct +0.2, weak direct +0.05)
            + endpoint_or_controller_boost (if endpoint or controller)
            + implementation_chain_boost (if has relation support)
            + role_boost
            - role_penalty
            - non_source_artifact_penalty
            - planner_only_penalty (if planner-only, no original evidence)
            - relation_only_penalty (if only relation, no direct evidence)
            - generic_hint_penalty

    Then apply ceiling clamp for non-strong evidence classes if planner_ceiling is set.

    Args:
        normalized_score: Normalized combined score
        score_parts: Score components dictionary
        chunk: The document chunk
        flags: Precomputed flags dict with keys:
            - has_endpoint_signal: bool
            - is_controller: bool
            - has_relation_support: bool
        role: Role classification with boost/penalty metadata
        path_role: Optional artifact/source role for display demotion
        query_intent: Inferred query intent used for artifact escapes
        planner_ceiling: Optional ceiling for planner/relation evidence classes

    Returns:
        Final rerank score
    """
    rerank_score = normalized_score
    has_project_scope_mismatch = _has_project_scope_mismatch(score_parts)

    # Boosts
    if score_parts.get("penalty", 0.0) < 0:
        pass
    elif _has_strong_original_direct_evidence(score_parts):
        rerank_score += 0.2
    elif _has_weak_original_direct_evidence(score_parts):
        rerank_score += 0.05

    if (
        not has_project_scope_mismatch
        and (
            flags.get("has_endpoint_signal", False)
            or flags.get("is_controller", False)
        )
    ):
        rerank_score += 0.15

    if not has_project_scope_mismatch and flags.get("has_relation_support", False):
        rerank_score += 0.1

    if not has_project_scope_mismatch:
        rerank_score += role.boost
        if role.boost:
            score_parts["role_boost"] = role.boost
    role_penalty = (
        0.0
        if _has_explicit_handler_path_evidence(role, score_parts)
        else role.penalty
    )
    if role_penalty:
        rerank_score -= role_penalty
        score_parts["role_penalty"] = -role_penalty

    artifact_penalty = _non_source_artifact_display_penalty(
        path_role,
        query_intent,
        score_parts,
    )
    if artifact_penalty:
        rerank_score -= artifact_penalty
        score_parts["non_source_artifact_penalty"] = -artifact_penalty
        score_parts[
            f"artifact_display_{path_role.name}_penalty"
        ] = -artifact_penalty

    role_exact_boost = 0.0
    if not has_project_scope_mismatch:
        role_exact_boost = _role_exact_match_boost(role, score_parts)
    if role_exact_boost:
        rerank_score += role_exact_boost
        score_parts["role_exact_match_boost"] = role_exact_boost

    file_hint_boost = 0.0
    if not has_project_scope_mismatch:
        file_hint_boost = _file_hint_match_boost(score_parts)
    if file_hint_boost:
        rerank_score += file_hint_boost
        score_parts["file_hint_match_boost"] = file_hint_boost

    if not has_project_scope_mismatch:
        if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
            rerank_score += score_parts["identifier_exact_match_boost"]
        if score_parts.get("path_role_hint_boost", 0.0) > 0:
            rerank_score += score_parts["path_role_hint_boost"]
        if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
            rerank_score += score_parts["path_role_mismatch_penalty"]

    rerank_score += _route_rerank_adjustment(score_parts)
    rerank_score += score_parts.get("route_tail_context_match", 0.0)
    rerank_score += _spring_path_rerank_adjustment(score_parts)
    rerank_score += project_scope_rerank_adjustment(score_parts)
    if not has_project_scope_mismatch:
        rerank_score += _frontend_entrypoint_rerank_adjustment(score_parts)
        rerank_score += _frontend_support_name_rerank_adjustment(score_parts)
    if not has_project_scope_mismatch:
        rerank_score += _query_intent_rerank_adjustment(score_parts)

    if (
        not has_project_scope_mismatch
        and role.name == "service_impl"
        and score_parts.get("path_symbol", 0.0) >= 1.0
        and score_parts.get("token_coverage", 0.0) >= 0.25
    ):
        rerank_score += 0.18
        score_parts["impl_match_boost"] = 0.18

    if (
        not has_project_scope_mismatch
        and flags.get("has_relation_support", False)
        and role.name in {
            "service_impl",
            "executor",
            "data_type",
            "service_interface",
            "mapper",
        }
    ):
        rerank_score += 0.08
        score_parts["relation_role_boost"] = 0.08
    if flags.get("has_relation_support", False) and role.name in {
        "handler",
        "constant_or_config",
    }:
        rerank_score -= 0.06
        score_parts["relation_detail_penalty"] = -0.06

    # Penalties (only apply when there's a ceiling from strong direct evidence)
    if planner_ceiling is not None:
        if _is_planner_hint_only(score_parts):
            rerank_score -= 0.3

        if not _has_original_direct_evidence(score_parts) and (
            score_parts.get("original_relation", 0.0) > 0 or score_parts.get("planner_relation", 0.0) > 0
        ):
            rerank_score -= 0.2

        rerank_score -= _generic_hint_penalty(chunk, score_parts)

    # Apply ceiling clamp for non-strong evidence
    evidence_class = _evidence_class(score_parts)
    if (
        evidence_class in _CLAMPED_EVIDENCE_CLASSES
        and planner_ceiling is not None
    ):
        rerank_score = min(rerank_score, planner_ceiling)

    return rerank_score


def _has_project_scope_mismatch(score_parts: dict[str, float]) -> bool:
    return score_parts.get("project_scope_mismatch_penalty", 0.0) < 0


def _frontend_entrypoint_rerank_adjustment(score_parts: dict[str, float]) -> float:
    boost = score_parts.get("frontend_entrypoint_boost", 0.0)
    if boost <= 0.0:
        return 0.0
    if (
        score_parts.get("token_coverage", 0.0) >= 0.50
        or score_parts.get("path_symbol", 0.0) >= 3.0
        or score_parts.get("direct_text", 0.0) >= 0.75
    ):
        return boost
    return 0.0


def _frontend_support_name_rerank_adjustment(score_parts: dict[str, float]) -> float:
    boost = score_parts.get("frontend_support_name_match_boost", 0.0)
    if boost <= 0.0:
        return 0.0
    if (
        score_parts.get("token_coverage", 0.0) >= 0.50
        or score_parts.get("path_symbol", 0.0) >= 3.0
        or score_parts.get("direct_text", 0.0) >= 0.75
    ):
        return boost
    return 0.0


_COHORT_MISMATCH_PENALTY = 0.05


def _chunk_project_unit(chunk: DocumentChunk) -> str:
    return str(chunk.metadata.get("project_name", ""))


def _query_scope_is_mixed(query_scope: QueryScope) -> bool:
    return (
        len(query_scope.project_names) > 1
        or len(query_scope.kinds) > 1
        or len(query_scope.path_prefixes) > 1
    )


def _role_exact_match_boost(
    role: _ChunkRole,
    score_parts: dict[str, float],
) -> float:
    path_symbol = score_parts.get("path_symbol", 0.0)
    token_coverage = score_parts.get("token_coverage", 0.0)
    if role.name == "entrypoint" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.12
    if role.name == "service_impl" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.35
    if role.name == "service" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.35
    if role.name == "data_type" and path_symbol >= 2.0 and token_coverage >= 0.2:
        return 0.24
    if _has_explicit_handler_path_evidence(role, score_parts):
        return 0.08
    return 0.0


_LOGIC_OPERATION_NAMES = {"save", "update", "delete", "download", "scan", "generate", "retry"}
_LOGIC_PATH_ROLES = {
    "entrypoint",
    "router",
    "service",
    "service_impl",
    "service_interface",
    "executor",
    "handler",
    "middleware",
    "repository",
    "source_adapter",
    "storage",
    "command",
    "engine",
    "scheduler",
    "state_store",
    "composable",
    "view",
    "component",
}
_CONFIG_ARTIFACT_ROLES = {
    "deployment_config",
    "config_example",
    "runtime_config",
    "lockfile",
}
_LOGIC_TARGET_ROLES = {"entrypoint", "implementation", "ui"}


def _query_intent_score_parts(
    path_role: PathRole,
    intent: QueryIntent,
) -> dict[str, float]:
    if intent.confidence == 0:
        return {}

    parts: dict[str, float] = {}
    operation_query = bool(
        intent.operations.intersection(_LOGIC_OPERATION_NAMES)
        and (intent.target_roles or intent.artifact_roles)
    )
    logic_operation_query = bool(
        intent.operations.intersection(_LOGIC_OPERATION_NAMES)
        and intent.target_roles.intersection(_LOGIC_TARGET_ROLES)
    )
    wants_deployment = "deploy" in intent.target_roles and intent.wants_artifact
    wants_docs = "doc" in intent.target_roles and intent.wants_artifact
    wants_tests = "test" in intent.target_roles and intent.wants_artifact

    if logic_operation_query and path_role.name in _LOGIC_PATH_ROLES:
        parts["query_operation_logic_boost"] = 0.10

    if "config" in intent.target_roles and path_role.name in {
        "entrypoint",
        "router",
        "service",
        "service_impl",
        "handler",
        "state_store",
        "composable",
        "view",
        "component",
    }:
        parts["config_logic_boost"] = 0.12

    if wants_deployment and path_role.name == "deployment_config":
        parts["deployment_config_boost"] = 0.18

    if wants_docs and path_role.name == "doc":
        parts["doc_artifact_boost"] = 0.12

    if wants_tests and path_role.name == "test":
        parts["test_artifact_boost"] = 0.12

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in _CONFIG_ARTIFACT_ROLES
    ):
        parts["penalty"] = -0.35
        parts["config_artifact_penalty"] = -0.35

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name == "generated_output"
    ):
        parts["penalty"] = -0.45
        parts["generated_output_penalty"] = -0.45

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in {"doc", "test"}
    ):
        parts["penalty"] = -0.20
        parts[f"{path_role.name}_artifact_penalty"] = -0.20

    return parts


def _non_source_artifact_display_penalty(
    path_role: PathRole | None,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> float:
    if path_role is None:
        return 0.0
    penalty = _NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES.get(path_role.name, 0.0)
    if not penalty:
        return 0.0
    if path_role.name == "config" and score_parts.get("file_role_source_boost", 0.0) > 0:
        return 0.0
    if _artifact_role_is_requested(path_role.name, intent, score_parts):
        return 0.0
    return penalty


def _artifact_role_is_requested(
    path_role_name: str,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> bool:
    if _has_explicit_artifact_file_hint(score_parts):
        return True
    if path_role_name == "doc":
        return "doc" in intent.target_roles and intent.wants_artifact
    if path_role_name == "test":
        return "test" in intent.target_roles and intent.wants_artifact
    if path_role_name in {
        "config",
        "runtime_config",
        "config_example",
        "deployment_config",
    }:
        return bool(
            intent.wants_artifact
            and intent.target_roles.intersection({"config", "deploy"})
        )
    if path_role_name == "lockfile":
        return bool(
            score_parts.get("explicit_lockfile_query", 0.0) > 0
            or (
                intent.wants_artifact
                and "config_artifact" in intent.artifact_roles
            )
        )
    if path_role_name == "generated_output":
        return bool(
            intent.wants_artifact
            and "generated_artifact" in intent.artifact_roles
        )
    return False


def _has_explicit_artifact_file_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "explicit_artifact_file_hint",
            "file_hint_match_boost",
            "project_file_hint_boost",
            "project_path_hint_boost",
            "path_role_hint_boost",
        )
    )


def _query_intent_rerank_adjustment(score_parts: dict[str, float]) -> float:
    if not _has_query_intent_rerank_evidence(score_parts):
        return 0.0
    return (
        score_parts.get("query_operation_logic_boost", 0.0)
        + score_parts.get("config_logic_boost", 0.0)
        + score_parts.get("deployment_config_boost", 0.0)
        + score_parts.get("doc_artifact_boost", 0.0)
        + score_parts.get("test_artifact_boost", 0.0)
    )


def _has_query_intent_rerank_evidence(score_parts: dict[str, float]) -> bool:
    return (
        score_parts.get("token_coverage", 0.0) >= 0.35
        or score_parts.get("path_symbol", 0.0) >= 1.5
        or score_parts.get("direct_text", 0.0) >= 0.55
        or score_parts.get("lexical", 0.0) >= 0.35
    )


def _identifier_intent_score_parts(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
    path_role: PathRole,
) -> dict[str, float]:
    parts: dict[str, float] = {}
    identifier_score = _identifier_exact_match_score(chunk, intent)
    if identifier_score:
        parts["identifier_exact_match_boost"] = identifier_score

    explicit_file_hint_score = _explicit_artifact_file_hint_score(chunk, intent)
    if explicit_file_hint_score:
        parts["explicit_artifact_file_hint"] = explicit_file_hint_score

    role_score = _path_role_hint_score(path_role, intent)
    if role_score:
        parts["path_role_hint_boost"] = role_score

    if _strong_role_mismatch(path_role, intent, identifier_score):
        parts["path_role_mismatch_penalty"] = -0.08

    return parts


def _frontend_entrypoint_scope_score_parts(
    chunk: DocumentChunk,
    query_scope,
    score_parts: dict[str, float],
) -> dict[str, float]:
    if "frontend" not in query_scope.kinds:
        return {}
    if _has_project_scope_mismatch(score_parts):
        return {}
    if not any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "project_scope_boost",
            "project_kind_boost",
            "project_language_boost",
            "project_path_hint_boost",
        )
    ):
        return {}

    path = chunk.file_path.as_posix().lower()
    if chunk.file_path.name.lower() not in _FRONTEND_ENTRYPOINT_NAMES:
        return {}
    if not (path.startswith("src/") or "/src/" in path):
        return {}
    if (
        score_parts.get("path_symbol", 0.0) < 1.0
        or score_parts.get("direct_text", 0.0) < 0.60
        or score_parts.get("token_coverage", 0.0) < 0.50
    ):
        return {}

    return {"path_role_hint_boost": 0.14}


def _identifier_exact_match_score(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> float:
    if not intent.identifiers and not intent.file_hints:
        return 0.0

    path_text = chunk.file_path.as_posix().lower()
    stem_text = chunk.file_path.stem.lower()
    content_text = chunk.content.lower()
    symbol_names = {symbol.name.lower() for symbol in chunk.symbols}
    score = 0.0

    for file_hint in intent.file_hints:
        normalized = file_hint.lower()
        if normalized in path_text:
            score = max(score, 0.40)
        elif normalized in content_text:
            score = max(score, 0.30)

    matched_identifiers = 0
    for identifier in intent.identifiers:
        normalized = identifier.lower()
        if normalized in symbol_names or normalized == stem_text or normalized in path_text:
            matched_identifiers += 1
            score = max(score, 0.30)
        elif normalized in content_text:
            matched_identifiers += 1
            score = max(score, 0.20)

    if matched_identifiers > 1:
        repeated_identifier_bonus = 0.05 * (matched_identifiers - 1)
        if matched_identifiers > 2:
            repeated_identifier_bonus += 0.05
        score += min(0.15, repeated_identifier_bonus)

    return min(score, 0.40)


def _explicit_artifact_file_hint_score(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> float:
    for file_hint in intent.file_hints:
        normalized = file_hint.lower()
        if normalized and normalized in chunk.file_path.as_posix().lower():
            return 0.40
    return 0.0


def _path_role_hint_score(path_role: PathRole, intent: IdentifierIntent) -> float:
    if _path_role_matches_intent(path_role, intent.role_hints):
        if path_role.name == "service_interface":
            return 0.08
        return 0.14
    return 0.0


def _path_role_matches_intent(path_role: PathRole, role_hints: tuple[str, ...]) -> bool:
    if path_role.name in role_hints:
        return True
    compatible_hints = {
        "service_impl": {"service"},
        "service_interface": {"service"},
    }
    return bool(compatible_hints.get(path_role.name, set()).intersection(role_hints))


def _strong_role_mismatch(
    path_role: PathRole,
    intent: IdentifierIntent,
    identifier_score: float,
) -> bool:
    if identifier_score > 0:
        return False
    if not intent.role_hints:
        return False
    high_confidence_roles = {
        "state_store",
        "composable",
        "command",
        "engine",
        "handler",
        "middleware",
        "service",
        "repository",
        "source_adapter",
        "storage",
    }
    return (
        bool(set(intent.role_hints).intersection(high_confidence_roles))
        and not _path_role_matches_intent(path_role, intent.role_hints)
    )


def _file_hint_match_boost(score_parts: dict[str, float]) -> float:
    if (
        _has_explicit_file_hint(score_parts)
        and score_parts.get("path_symbol", 0.0) >= 4.0
        and score_parts.get("token_coverage", 0.0) >= 0.5
        and score_parts.get("direct_text", 0.0) >= 0.60
    ):
        return 0.40
    return 0.0


def _has_explicit_file_hint(score_parts: dict[str, float]) -> bool:
    return (
        score_parts.get("project_path_hint_boost", 0.0) > 0
        or score_parts.get("project_file_hint_boost", 0.0) > 0
    )


def _has_explicit_handler_path_evidence(
    role: _ChunkRole,
    score_parts: dict[str, float],
) -> bool:
    return (
        role.name == "handler"
        and _has_explicit_file_hint(score_parts)
        and score_parts.get("path_symbol", 0.0) >= 4.0
        and score_parts.get("token_coverage", 0.0) >= 0.5
        and score_parts.get("direct_text", 0.0) >= 0.60
    )


def _route_rerank_adjustment(score_parts: dict[str, float]) -> float:
    if score_parts.get("route_exact_match", 0.0) > 0:
        return score_parts["route_exact_match"]
    if score_parts.get("route_prefix_match", 0.0) > 0:
        return score_parts["route_prefix_match"]
    if score_parts.get("route_sibling_penalty", 0.0) < 0:
        return score_parts["route_sibling_penalty"]
    if score_parts.get("route_mismatch_penalty", 0.0) < 0:
        return score_parts["route_mismatch_penalty"]
    return 0.0


def _spring_path_rerank_adjustment(score_parts: dict[str, float]) -> float:
    return (
        score_parts.get("spring_path_endpoint_match", 0.0)
        + score_parts.get("spring_path_service_match", 0.0)
        + score_parts.get("spring_path_service_interface_match", 0.0)
        + score_parts.get("spring_path_executor_match", 0.0)
    )


def _rank_tier(
    store: SQLiteStore,
    chunk: DocumentChunk,
    score_parts: dict[str, float],
    signals: list[CodeSignal] | None = None,
) -> int:
    has_signal_evidence = score_parts.get("signal", 0.0) > 0
    has_endpoint_signal = False
    if has_signal_evidence:
        has_endpoint_signal = (
            any(signal.kind == "endpoint" for signal in signals)
            if signals is not None
            else _chunk_has_signal_kind(store, chunk.chunk_id, "endpoint")
        )

    if has_signal_evidence and has_endpoint_signal:
        base_tier = 0
    elif score_parts.get("relation", 0.0) > 0:
        base_tier = 1
    elif has_signal_evidence:
        base_tier = 2
    elif score_parts.get("direct_text", 0.0) > 0:
        base_tier = 2
    else:
        base_tier = 3

    if _is_planner_hint_only(score_parts):
        return base_tier + 1
    return base_tier


def _has_planner_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "planner_semantic",
            "planner_lexical",
            "planner_path_symbol",
            "planner_signal",
            "planner_relation",
        )
    )


def _has_original_query_evidence(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "semantic",
            "lexical",
            "path_symbol",
            "signal",
            "token_coverage",
            "original_relation",
            "direct_text",
        )
    )


def _is_planner_hint_only(score_parts: dict[str, float]) -> bool:
    return _has_planner_hint(score_parts) and not _has_original_query_evidence(
        score_parts
    )


def _chunk_has_signal_kind(store: SQLiteStore, chunk_id: str, kind: str) -> bool:
    try:
        return any(signal.kind == kind for signal in store.signals_for_chunk(chunk_id))
    except sqlite3.Error:
        return False


def _token_coverage(tokens: list[str], chunk: DocumentChunk) -> float:
    if not tokens:
        return 0.0

    haystack = set(chunk.lexical_tokens)
    haystack.update(tokenize_query(chunk.content))
    matches = sum(1 for token in tokens if token.lower() in haystack)
    return matches / len(tokens)


def _plugin_boost(chunk: DocumentChunk) -> float:
    if chunk.metadata.get("language") == "java":
        return 0.03
    return 0.0


def _query_route(query: str) -> str:
    for part in re.split(r"\s+", query.strip()):
        cleaned = part.strip().strip("`'\".,;:()[]{}")
        if cleaned.startswith("/"):
            return _normalize_route(cleaned)
    return ""


def _normalize_route(value: str) -> str:
    cleaned = value.strip().strip("`'\".,;:()[]{}")
    if not cleaned:
        return ""
    cleaned = "/" + cleaned.strip("/")
    return re.sub(r"/+", "/", cleaned)


def _route_segments(route: str) -> list[str]:
    return [segment for segment in route.strip("/").split("/") if segment]


def _has_route_segment_suffix(endpoint_route: str, query_route: str) -> bool:
    endpoint_segments = _route_segments(endpoint_route)
    query_segments = _route_segments(query_route)
    if len(endpoint_segments) <= len(query_segments):
        return False
    return endpoint_segments[-len(query_segments) :] == query_segments


def _route_token_overlap(route: str, query_tokens: set[str]) -> int:
    route_tokens = {
        token.lower()
        for segment in _route_segments(route)
        for token in tokenize_query(segment)
        if token
    }
    return len(route_tokens.intersection(query_tokens))


def _chunk_local_tokens(chunk: DocumentChunk) -> set[str]:
    tokens = {token.lower() for token in chunk.lexical_tokens if token}
    tokens.update(_chunk_symbolic_tokens(chunk))
    return tokens


def _chunk_symbolic_tokens(chunk: DocumentChunk) -> set[str]:
    tokens: set[str] = set()
    for part in chunk.file_path.parts:
        tokens.update(token.lower() for token in tokenize_query(part) if token)
    for symbol in chunk.symbols:
        tokens.update(token.lower() for token in tokenize_query(symbol.name) if token)
    tokens.update(token.lower() for token in tokenize_query(chunk.content) if token)
    return tokens


def _chunk_declared_name_has_tokens(
    chunk: DocumentChunk,
    required_tokens: set[str],
) -> bool:
    name_tokens = {token.lower() for token in tokenize_query(chunk.file_path.stem) if token}
    if required_tokens.issubset(name_tokens):
        return True
    for symbol in chunk.symbols:
        name_tokens = {
            token.lower() for token in tokenize_query(symbol.name) if token
        }
        if required_tokens.issubset(name_tokens):
            return True
    return False


def _chunk_looks_route_relevant(
    chunk: DocumentChunk,
    query_tokens: list[str],
    query_route: str,
    route_boost: float = 0.0,
) -> bool:
    if route_boost:
        return True

    normalized_query_tokens = {token.lower() for token in query_tokens if token}
    if not normalized_query_tokens:
        return False
    min_overlap = min(2, len(normalized_query_tokens))

    route_values = [
        _normalize_route(token)
        for token in chunk.lexical_tokens
        if token.startswith("/")
    ]
    route_values.extend(_normalize_route(match.group(0)) for match in re.finditer(r"/[A-Za-z0-9_./:@-]+", chunk.content))
    for route in route_values:
        if not route:
            continue
        if (
            route == query_route
            or query_route.startswith(route + "/")
            or route.startswith(query_route + "/")
            or _has_route_segment_suffix(route, query_route)
        ):
            return True
        if _route_token_overlap(route, normalized_query_tokens) >= min_overlap:
            return True

    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    routeish = (
        "controller" in path
        or "controller" in names
        or "requestmapping" in content
        or "getmapping" in content
        or "postmapping" in content
        or "putmapping" in content
        or "deletemapping" in content
        or "patchmapping" in content
    )
    return routeish and len(_chunk_local_tokens(chunk).intersection(normalized_query_tokens)) >= min_overlap


def _route_score_parts(
    signals: list[CodeSignal],
    query: str,
    query_route: str | None = None,
) -> dict[str, float]:
    if query_route is None:
        query_route = _query_route(query)
    if not query_route:
        return {}

    parts: dict[str, float] = {}
    has_endpoint_route = False
    has_exact_match = False
    has_prefix_match = False
    has_sibling_match = False
    for signal in signals:
        if signal.kind != "endpoint":
            continue
        path = signal.metadata.get("path")
        if not isinstance(path, str):
            continue
        has_endpoint_route = True
        endpoint_route = _normalize_route(path)
        if endpoint_route == query_route:
            has_exact_match = True
            continue
        if _has_route_segment_suffix(endpoint_route, query_route):
            has_sibling_match = True
            continue
        if query_route.startswith(endpoint_route + "/"):
            has_prefix_match = True
    if has_exact_match:
        parts["route_exact_match"] = _ROUTE_EXACT_MATCH_BOOST
    elif has_prefix_match:
        parts["route_prefix_match"] = _ROUTE_PREFIX_MATCH_BOOST
    elif has_sibling_match:
        parts["route_sibling_penalty"] = -_ROUTE_SIBLING_PENALTY
    elif has_endpoint_route:
        parts["route_mismatch_penalty"] = -_ROUTE_MISMATCH_PENALTY
    return parts


def _spring_path_score_parts(
    store: SQLiteStore,
    candidate_chunks: dict[str, DocumentChunk],
    query_route: str,
) -> dict[str, dict[str, float]]:
    if not query_route or not candidate_chunks:
        return {}

    try:
        signals_by_chunk = store.signals_for_chunks(list(candidate_chunks))
    except sqlite3.Error:
        return {}

    parts_by_chunk: dict[str, dict[str, float]] = {}
    visited_signal_depths: dict[str, int] = {}
    frontier: list[tuple[str, int]] = []
    implementors_by_interface = _spring_path_candidate_implementors_by_interface(
        store,
        candidate_chunks,
        signals_by_chunk,
    )

    for chunk_id, signals in signals_by_chunk.items():
        for signal in signals:
            if signal.kind != "endpoint":
                continue
            path = signal.metadata.get("path")
            if not isinstance(path, str) or _normalize_route(path) != query_route:
                continue
            parts_by_chunk[chunk_id] = _merge_score_parts(
                parts_by_chunk.get(chunk_id, {}),
                {"spring_path_endpoint_match": _SPRING_PATH_ENDPOINT_BOOST},
            )
            existing_depth = visited_signal_depths.get(signal.signal_id)
            if existing_depth is not None and existing_depth <= 0:
                continue
            visited_signal_depths[signal.signal_id] = 0
            frontier.append((signal.signal_id, 0))

    while frontier:
        active_frontier = [
            (source_signal_id, depth)
            for source_signal_id, depth in frontier
            if depth < _SPRING_PATH_MAX_DEPTH
        ]
        if not active_frontier:
            break

        try:
            relations_by_source = store.relations_for_sources(
                [source_signal_id for source_signal_id, _ in active_frontier]
            )
        except sqlite3.Error:
            break

        relation_steps: list[tuple[str, int]] = []
        target_names: list[str] = []
        for source_signal_id, depth in active_frontier:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < _MIN_RELATION_CONFIDENCE:
                    continue
                relation_steps.append((relation.target_name, next_depth))
                target_names.append(relation.target_name)

        if not relation_steps:
            break

        try:
            chunks_by_target = store.chunks_matching_signal_or_symbols(
                target_names,
                MAX_EXPANSION_CANDIDATES,
            )
        except sqlite3.Error:
            break

        next_signal_depths: dict[str, int] = {}
        for target_name, depth in relation_steps:
            for chunk in _spring_path_direct_chunks_for_target(
                chunks_by_target.get(target_name, []),
                target_name,
                candidate_chunks,
                signals_by_chunk,
            ):
                role = _chunk_role(chunk)
                _add_spring_path_reached_chunk(
                    chunk,
                    depth,
                    parts_by_chunk,
                )
                for signal_id in _spring_path_matching_signal_ids(
                    signals_by_chunk.get(chunk.chunk_id, []),
                    target_name,
                    allow_impl_owner=role.name == "service_impl",
                ):
                    _set_min_signal_depth(next_signal_depths, signal_id, depth)

            for chunk_id in _spring_path_implementor_chunk_ids(
                implementors_by_interface,
                target_name,
            ):
                chunk = candidate_chunks.get(chunk_id)
                if chunk is None:
                    continue
                _add_spring_path_reached_chunk(
                    chunk,
                    depth,
                    parts_by_chunk,
                )
                for signal_id in _spring_path_matching_signal_ids(
                    signals_by_chunk.get(chunk_id, []),
                    target_name,
                    allow_impl_owner=True,
                ):
                    _set_min_signal_depth(next_signal_depths, signal_id, depth)

        next_frontier: list[tuple[str, int]] = []
        for signal_id, depth in next_signal_depths.items():
            if depth >= _SPRING_PATH_MAX_DEPTH:
                continue
            existing_depth = visited_signal_depths.get(signal_id)
            if existing_depth is not None and existing_depth <= depth:
                continue
            visited_signal_depths[signal_id] = depth
            next_frontier.append((signal_id, depth))
        frontier = next_frontier

    return parts_by_chunk


def _spring_path_candidate_implementors_by_interface(
    store: SQLiteStore,
    candidate_chunks: dict[str, DocumentChunk],
    signals_by_chunk: dict[str, list[CodeSignal]],
) -> list[_SpringPathImplementor]:
    signal_chunk_ids: dict[str, str] = {}
    source_signal_ids: list[str] = []
    for chunk_id, chunk in candidate_chunks.items():
        if _chunk_role(chunk).name != "service_impl":
            continue
        for signal in signals_by_chunk.get(chunk_id, []):
            signal_chunk_ids[signal.signal_id] = chunk_id
            source_signal_ids.append(signal.signal_id)

    if not source_signal_ids:
        return []

    try:
        relations_by_source = store.relations_for_sources(source_signal_ids)
    except sqlite3.Error:
        return []

    implementors: list[_SpringPathImplementor] = []
    seen: set[tuple[str, str]] = set()
    for source_signal_id, relations in relations_by_source.items():
        chunk_id = signal_chunk_ids.get(source_signal_id)
        if chunk_id is None:
            continue
        for relation in relations:
            if (
                relation.kind != "implements"
                or relation.confidence < _MIN_RELATION_CONFIDENCE
            ):
                continue
            interface_name = relation.target_name.strip()
            if not interface_name:
                continue
            key = (interface_name, chunk_id)
            if key in seen:
                continue
            seen.add(key)
            implementors.append(
                _SpringPathImplementor(
                    interface_name=interface_name,
                    simple_name=_spring_path_simple_name(interface_name),
                    is_qualified=_spring_path_name_is_qualified(interface_name),
                    chunk_id=chunk_id,
                )
            )
    return implementors


def _spring_path_direct_chunks_for_target(
    reached_chunks: list[DocumentChunk],
    target_name: str,
    candidate_chunks: dict[str, DocumentChunk],
    signals_by_chunk: dict[str, list[CodeSignal]],
) -> list[DocumentChunk]:
    exact_chunks: list[DocumentChunk] = []
    fallback_chunks: list[DocumentChunk] = []
    for reached_chunk in reached_chunks:
        chunk = candidate_chunks.get(reached_chunk.chunk_id)
        if chunk is None:
            continue
        signals = signals_by_chunk.get(chunk.chunk_id, [])
        if _spring_path_chunk_has_exact_target_match(chunk, signals, target_name):
            exact_chunks.append(chunk)
            continue
        if _chunk_role(chunk).name != "service_impl":
            continue
        if _spring_path_matching_signal_ids(
            signals,
            target_name,
            allow_impl_owner=True,
        ):
            fallback_chunks.append(chunk)

    if exact_chunks:
        return _dedupe_chunks(exact_chunks)

    fallback_chunks = _dedupe_chunks(fallback_chunks)
    if len(fallback_chunks) == 1:
        return fallback_chunks
    return []


def _spring_path_chunk_has_exact_target_match(
    chunk: DocumentChunk,
    signals: list[CodeSignal],
    target_name: str,
) -> bool:
    if any(signal.name == target_name for signal in signals):
        return True
    return any(symbol.name == target_name for symbol in chunk.symbols)


def _dedupe_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    seen: set[str] = set()
    deduped: list[DocumentChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _add_spring_path_reached_chunk(
    chunk: DocumentChunk,
    depth: int,
    parts_by_chunk: dict[str, dict[str, float]],
) -> None:
    role_parts = _spring_path_role_score_parts(_chunk_role(chunk), depth)
    if role_parts:
        parts_by_chunk[chunk.chunk_id] = _merge_score_parts(
            parts_by_chunk.get(chunk.chunk_id, {}),
            role_parts,
        )


def _spring_path_implementor_chunk_ids(
    implementors: list[_SpringPathImplementor],
    target_name: str,
) -> list[str]:
    owner_name = _spring_path_target_owner_name(target_name)
    if not owner_name:
        return []

    owner_is_qualified = _spring_path_name_is_qualified(owner_name)
    if owner_is_qualified:
        exact_matches = [
            implementor.chunk_id
            for implementor in implementors
            if implementor.is_qualified and implementor.interface_name == owner_name
        ]
        if exact_matches:
            return _dedupe(exact_matches)

    simple_name = _spring_path_simple_name(owner_name)
    simple_matches = [
        implementor.chunk_id
        for implementor in implementors
        if implementor.simple_name == simple_name
        and (not owner_is_qualified or not implementor.is_qualified)
    ]
    chunk_ids = _dedupe(simple_matches)
    if len(chunk_ids) == 1:
        return chunk_ids
    return []


def _spring_path_matching_signal_ids(
    signals: list[CodeSignal],
    target_name: str,
    *,
    allow_impl_owner: bool,
) -> list[str]:
    target_member = _spring_path_member_target(target_name)
    matching_signal_ids: list[str] = []
    for signal in signals:
        if not signal.signal_id:
            continue
        if target_member is None:
            if signal.name == target_name:
                matching_signal_ids.append(signal.signal_id)
            continue

        signal_member = _spring_path_member_target(signal.name)
        if signal_member is None:
            continue
        target_owner, target_method = target_member
        signal_owner, signal_method = signal_member
        if signal_method != target_method:
            continue
        if _spring_path_owner_matches(
            signal_owner,
            target_owner,
            allow_impl_owner=allow_impl_owner,
        ):
            matching_signal_ids.append(signal.signal_id)
    return _dedupe(matching_signal_ids)


def _spring_path_member_target(name: str) -> tuple[str, str] | None:
    stripped = name.strip()
    if "." not in stripped:
        return None
    owner_name, member_name = stripped.rsplit(".", 1)
    if not owner_name or not member_name or member_name[:1].isupper():
        return None
    return owner_name, member_name


def _spring_path_target_owner_name(target_name: str) -> str:
    member_target = _spring_path_member_target(target_name)
    if member_target is not None:
        return member_target[0]
    return target_name.strip()


def _spring_path_owner_matches(
    signal_owner: str,
    target_owner: str,
    *,
    allow_impl_owner: bool,
) -> bool:
    if signal_owner == target_owner:
        return True

    signal_simple = _spring_path_simple_name(signal_owner)
    target_simple = _spring_path_simple_name(target_owner)
    if signal_simple == target_simple:
        return True
    return allow_impl_owner and signal_simple == f"{target_simple}Impl"


def _spring_path_simple_name(name: str) -> str:
    return name.strip().rsplit(".", 1)[-1]


def _spring_path_name_is_qualified(name: str) -> bool:
    return "." in name.strip()


def _set_min_signal_depth(
    signal_depths: dict[str, int],
    signal_id: str,
    depth: int,
) -> None:
    existing_depth = signal_depths.get(signal_id)
    if existing_depth is None or depth < existing_depth:
        signal_depths[signal_id] = depth


def _spring_path_role_score_parts(
    role: _ChunkRole,
    depth: int,
) -> dict[str, float]:
    if depth == 1 and role.name == "service_impl":
        return {"spring_path_service_match": _SPRING_PATH_SERVICE_BOOST}
    if depth == 1 and role.name == "service_interface":
        return {
            "spring_path_service_interface_match": (
                _SPRING_PATH_SERVICE_INTERFACE_BOOST
            )
        }
    if depth in {1, 2} and role.name == "executor":
        return {"spring_path_executor_match": _SPRING_PATH_EXECUTOR_BOOST}
    return {}


def _route_tail_context_score_parts(
    chunk: DocumentChunk,
    query_route: str,
    role: _ChunkRole,
) -> dict[str, float]:
    if role.name != "executor":
        return {}
    segments = _route_segments(query_route)
    if not segments:
        return {}
    tail_tokens = {
        token.lower()
        for token in tokenize_query(segments[-1])
        if token and token.lower() not in _JAVA_CONTEXT_STRUCTURAL_TOKENS
    }
    if len(tail_tokens) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return {}
    if _chunk_declared_name_has_tokens(chunk, tail_tokens):
        return {"route_tail_context_match": _ROUTE_TAIL_CONTEXT_MATCH_BOOST}
    return {}


def _java_context_query_tokens(query_tokens: list[str], query_route: str) -> list[str]:
    if not query_route:
        return query_tokens

    route_tokens = {
        token.lower()
        for segment in _route_segments(query_route)
        for token in tokenize_query(segment)
        if token
    }
    if not route_tokens:
        return query_tokens

    non_route_tokens = [
        token for token in query_tokens if token and token.lower() not in route_tokens
    ]
    if len({token.lower() for token in non_route_tokens}) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return []
    return non_route_tokens


def _java_context_score_parts(
    signals: list[CodeSignal],
    query_tokens: list[str],
    role: _ChunkRole,
) -> dict[str, float]:
    normalized_query = {token.lower() for token in query_tokens if token}
    if not normalized_query:
        return {}

    parts: dict[str, float] = {}
    for signal in signals:
        if signal.kind not in {"method", "field"}:
            continue
        signal_tokens = {token.lower() for token in signal.tokens if token}
        overlap = normalized_query.intersection(signal_tokens)
        if len(overlap) >= _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
            if signal.kind == "method":
                parts["java_method_context_match"] = max(
                    parts.get("java_method_context_match", 0.0),
                    _JAVA_METHOD_CONTEXT_MATCH_BOOST,
                )
            if signal.kind == "field":
                parts["java_field_context_match"] = max(
                    parts.get("java_field_context_match", 0.0),
                    _JAVA_FIELD_CONTEXT_MATCH_BOOST,
                )
            if role.name == "executor":
                parts["java_executor_context_boost"] = max(
                    parts.get("java_executor_context_boost", 0.0),
                    _JAVA_EXECUTOR_CONTEXT_BOOST,
                )
    return parts


def _should_apply_java_context_score(
    chunk: DocumentChunk,
    query_tokens: list[str],
    role: _ChunkRole,
    penalty: float,
) -> bool:
    if not query_tokens or penalty:
        return False
    if chunk.metadata.get("language") != "java" and chunk.file_path.suffix.lower() != ".java":
        return False
    if _java_context_local_token_overlap(chunk, query_tokens) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return False
    if role.name in {"executor", "data_type"}:
        return True
    if role.name != "generic":
        return False
    return _java_chunk_suggests_helper_or_filter(chunk)


def _java_context_local_token_overlap(
    chunk: DocumentChunk,
    query_tokens: list[str],
) -> int:
    normalized_query = {
        token.lower()
        for token in query_tokens
        if token and token.lower() not in _JAVA_CONTEXT_STRUCTURAL_TOKENS
    }
    if not normalized_query:
        return 0
    return len(normalized_query.intersection(_chunk_local_tokens(chunk)))


def _java_chunk_suggests_helper_or_filter(chunk: DocumentChunk) -> bool:
    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    haystack = f"{path} {names} {content}"
    return "helper" in haystack or "filter" in haystack


def _route_boost(chunk: DocumentChunk, query: str, tokens: list[str]) -> float:
    if "/" not in query or not tokens:
        return 0.0
    query_route = _query_route(query)
    query_tokens = set(tokens)
    for token in chunk.lexical_tokens:
        if not token.startswith("/"):
            continue
        if query_route:
            route = _normalize_route(token)
            if route == query_route or query_route.startswith(route + "/"):
                return 0.12
            continue
        if query_tokens.intersection(tokenize_query(token)):
            return 0.12
    return 0.0


def _looks_implementation_query(query: str, tokens: list[str]) -> bool:
    if "/" in query:
        return True
    implementation_terms = {
        "handler", "middleware", "command", "engine", "service", "controller",
        "storage", "upload", "delete", "apply", "restore", "invoke", "route",
        "function", "class", "method",
    }
    return bool({token.lower() for token in tokens}.intersection(implementation_terms))


def _has_explicit_lockfile_query(tokens: list[str], name: str) -> bool:
    token_set = {token.lower() for token in tokens}
    if token_set & _LOCKFILE_QUERY_TOKENS:
        return True
    return name == "go.sum" and (
        "gosum" in token_set or {"go", "sum"}.issubset(token_set)
    )


def _is_generated_schema_path(path: str, suffix: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if "generated" in parts:
        return True
    if "gen" not in parts:
        return False
    return suffix in {".json", ".yml", ".yaml"} or "schema" in path


def _generic_file_role(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> _GenericFileRole:
    path = chunk.file_path.as_posix().lower()
    suffix = chunk.file_path.suffix.lower()
    name = chunk.file_path.name.lower()
    is_implementation_query = _looks_implementation_query(query, tokens)

    if _is_test_path(path) or chunk.metadata.get("is_test"):
        return _GenericFileRole("test", "high", penalty=0.10, penalty_key="test_penalty")
    if chunk.metadata.get("is_generated") or _is_generated_schema_path(path, suffix):
        return _GenericFileRole(
            "generated_schema",
            "high",
            penalty=0.20,
            penalty_key="generated_schema_penalty",
        )
    if name in _INDEXED_LOCKFILE_NAMES:
        penalty = 0.0 if _has_explicit_lockfile_query(tokens, name) else 0.20
        return _GenericFileRole(
            "lockfile",
            "high",
            penalty=penalty,
            penalty_key="lockfile_penalty" if penalty else "",
        )
    if suffix in _TEMPLATE_SUFFIXES:
        if classify_frontend_role(chunk.file_path).name in {
            "view_page",
            "layout_component",
            "shared_component",
        }:
            return _GenericFileRole("source", "none", source_boost=0.03)
        penalty = 0.08 if is_implementation_query else 0.0
        return _GenericFileRole(
            "template",
            "medium" if penalty else "low",
            penalty=penalty,
            penalty_key="template_penalty" if penalty else "",
        )
    if suffix in _DOC_SUFFIXES:
        penalty = 0.03 if is_implementation_query else 0.0
        return _GenericFileRole(
            "doc",
            "low",
            penalty=penalty,
            penalty_key="doc_penalty" if penalty else "",
        )
    if suffix in _CONFIG_SUFFIXES:
        penalty = 0.03 if is_implementation_query else 0.0
        return _GenericFileRole(
            "config",
            "low",
            penalty=penalty,
            penalty_key="config_penalty" if penalty else "",
        )
    if suffix in _SOURCE_SUFFIXES:
        return _GenericFileRole("source", "none", source_boost=0.03)
    return _GenericFileRole("unknown", "none")


def _generic_noise_score_parts(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> dict[str, float]:
    path = chunk.file_path.as_posix().lower()
    suffix = chunk.file_path.suffix.lower()
    name = chunk.file_path.name.lower()
    parts: dict[str, float] = {}

    legacy_penalty = _generated_or_test_penalty(chunk)
    if legacy_penalty:
        parts["penalty"] = -legacy_penalty
    if _is_test_path(path) or chunk.metadata.get("is_test"):
        parts = _merge_score_parts(
            parts,
            {"penalty": -0.10, "test_penalty": -0.10},
        )
    if chunk.metadata.get("is_generated") or _is_generated_schema_path(path, suffix):
        parts = _merge_score_parts(
            parts,
            {"penalty": -0.20, "generated_schema_penalty": -0.20},
        )
    if name in _INDEXED_LOCKFILE_NAMES:
        if _has_explicit_lockfile_query(tokens, name):
            parts["explicit_lockfile_query"] = 1.0
        else:
            parts = _merge_score_parts(
                parts,
                {"penalty": -0.20, "lockfile_penalty": -0.20},
            )

    role = _generic_file_role(chunk, query, tokens)
    role_parts: dict[str, float] = {}
    if role.penalty and role.penalty_key:
        role_parts["penalty"] = -role.penalty
        role_parts[role.penalty_key] = -role.penalty
    if role.source_boost:
        role_parts["file_role_source_boost"] = role.source_boost
    return _merge_score_parts(parts, role_parts)


def _generated_or_test_penalty(chunk: DocumentChunk) -> float:
    path = chunk.file_path.as_posix().lower()
    penalties: list[float] = []
    if chunk.metadata.get("is_generated") or "generated" in path:
        penalties.append(0.20)
    if chunk.metadata.get("is_test") or "/test/" in path or path.endswith("test.java"):
        penalties.append(0.10)
    return max(penalties, default=0.0)


def _is_test_path(path: str) -> bool:
    return "/test/" in path or path.endswith("test.java")


def _reasons(score_parts: dict[str, float], query: str) -> list[str]:
    reasons: list[str] = []
    if score_parts.get("rerank_score"):
        evidence_class = _evidence_class(score_parts)
        reasons.append(f"rerank_score={score_parts['rerank_score']:.2f} ({evidence_class})")
    if score_parts.get("semantic", 0.0) > 0:
        reasons.append("semantic match")
    if score_parts.get("lexical", 0.0) > 0:
        reasons.append("lexical match")
    if score_parts.get("path_symbol", 0.0) > 0:
        reasons.append("path/symbol match")
    if score_parts.get("signal", 0.0) > 0:
        reasons.append("signal match")
    if score_parts.get("relation", 0.0) > 0:
        reasons.append("relation expansion")
    if score_parts.get("direct_text", 0.0) > 0:
        reasons.append("direct text match")
    if score_parts.get("anchored_relation", 0.0) > 0:
        reasons.append("evidence-anchored expansion")
    if score_parts.get("same_file_anchor", 0.0) > 0:
        reasons.append("same-file anchor")
    if score_parts.get("directory_anchor", 0.0) > 0:
        reasons.append("directory anchor")
    if score_parts.get("planner_semantic", 0.0) > 0:
        reasons.append("planner semantic match")
    if _has_planner_hint(score_parts):
        reasons.append("planner hint match")
    if score_parts.get("role_boost", 0.0) > 0:
        reasons.append("business role boost")
    if score_parts.get("role_penalty", 0.0) < 0:
        reasons.append("detail role penalty")
    if score_parts.get("file_hint_match_boost", 0.0) > 0:
        reasons.append("explicit file hint match")
    if score_parts.get("role_exact_match_boost", 0.0) > 0:
        reasons.append("role exact match boost")
    if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
        reasons.append("explicit identifier match")
    if score_parts.get("path_role_hint_boost", 0.0) > 0:
        reasons.append("path role hint match")
    if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
        reasons.append("path role mismatch penalty")
    if score_parts.get("cohort_mismatch_penalty", 0.0) < 0:
        reasons.append("cross-project cohort mismatch penalty")
    if score_parts.get("impl_match_boost", 0.0) > 0:
        reasons.append("service implementation exact match boost")
    if score_parts.get("relation_role_boost", 0.0) > 0:
        reasons.append("relation chain role boost")
    if score_parts.get("relation_detail_penalty", 0.0) < 0:
        reasons.append("relation detail penalty")
    if score_parts.get("token_coverage", 0.0) > 0:
        reasons.append("token coverage")
    if score_parts.get("route_exact_match", 0.0) > 0:
        reasons.append("exact Spring route match")
    if score_parts.get("route_prefix_match", 0.0) > 0:
        reasons.append("Spring route prefix match")
    if score_parts.get("route_sibling_penalty", 0.0) < 0:
        reasons.append("sibling Spring route penalty")
    if score_parts.get("route_mismatch_penalty", 0.0) < 0:
        reasons.append("non-matching Spring route penalty")
    if score_parts.get("route_tail_context_match", 0.0) > 0:
        reasons.append("Spring route tail context match")
    if score_parts.get("java_method_context_match", 0.0) > 0:
        reasons.append("java method context match")
    if score_parts.get("java_field_context_match", 0.0) > 0:
        reasons.append("java field context match")
    if score_parts.get("java_executor_context_boost", 0.0) > 0:
        reasons.append("java executor context boost")
    if score_parts.get("spring_path_endpoint_match", 0.0) > 0:
        reasons.append("Spring endpoint path graph match")
    if score_parts.get("spring_path_service_match", 0.0) > 0:
        reasons.append("Spring service path graph match")
    if score_parts.get("spring_path_service_interface_match", 0.0) > 0:
        reasons.append("Spring service interface path graph match")
    if score_parts.get("spring_path_executor_match", 0.0) > 0:
        reasons.append("Spring executor path graph match")
    if score_parts.get("project_scope_boost", 0.0) > 0:
        reasons.append("project scope match")
    if score_parts.get("project_kind_boost", 0.0) > 0:
        reasons.append("project kind match")
    if score_parts.get("project_language_boost", 0.0) > 0:
        reasons.append("project language match")
    if score_parts.get("project_path_hint_boost", 0.0) > 0:
        reasons.append("project path hint match")
    if score_parts.get("project_file_hint_boost", 0.0) > 0:
        reasons.append("project file hint match")
    if score_parts.get("project_scope_mismatch_penalty", 0.0) < 0:
        reasons.append("project scope mismatch penalty")
    if "/" in query and score_parts.get("route_boost", 0.0) > 0:
        reasons.append("route token match")
    elif score_parts.get("plugin_boost", 0.0) > 0:
        reasons.append("java plugin boost")
    if score_parts.get("file_role_source_boost", 0.0) > 0:
        reasons.append("source file role boost")
    if score_parts.get("frontend_entrypoint_boost", 0.0) > 0:
        reasons.append("frontend entrypoint boost")
    if score_parts.get("frontend_support_boost", 0.0) > 0:
        reasons.append("frontend support boost")
    if score_parts.get("frontend_support_name_match_boost", 0.0) > 0:
        reasons.append("frontend support name match boost")
    if score_parts.get("frontend_import_support_boost", 0.0) > 0:
        reasons.append("frontend import support boost")
    if score_parts.get("frontend_lockfile_penalty", 0.0) < 0:
        reasons.append("frontend lockfile penalty")
    if score_parts.get("frontend_scratch_temp_penalty", 0.0) < 0:
        reasons.append("frontend scratch temp penalty")
    if score_parts.get("frontend_type_decl_penalty", 0.0) < 0:
        reasons.append("frontend type declaration penalty")
    if score_parts.get("query_operation_logic_boost", 0.0) > 0:
        reasons.append("query operation logic boost")
    if score_parts.get("config_logic_boost", 0.0) > 0:
        reasons.append("config logic boost")
    if score_parts.get("deployment_config_boost", 0.0) > 0:
        reasons.append("deployment config boost")
    if score_parts.get("config_artifact_penalty", 0.0) < 0:
        reasons.append("config artifact penalty")
    if score_parts.get("generated_output_penalty", 0.0) < 0:
        reasons.append("generated output penalty")
    if score_parts.get("doc_artifact_penalty", 0.0) < 0:
        reasons.append("doc artifact penalty")
    if score_parts.get("test_artifact_penalty", 0.0) < 0:
        reasons.append("test artifact penalty")
    if score_parts.get("generated_schema_penalty", 0.0) < 0:
        reasons.append("generated schema penalty")
    if score_parts.get("lockfile_penalty", 0.0) < 0:
        reasons.append("lockfile penalty")
    if score_parts.get("template_penalty", 0.0) < 0:
        reasons.append("template penalty")
    if score_parts.get("config_penalty", 0.0) < 0:
        reasons.append("config penalty")
    if score_parts.get("doc_penalty", 0.0) < 0:
        reasons.append("doc penalty")
    if score_parts.get("test_penalty", 0.0) < 0:
        reasons.append("test penalty")
    if score_parts.get("penalty", 0.0) < 0:
        reasons.append("generated/test penalty")
    return reasons


def _context_window(
    config: ToolConfig,
    context_lines: int | None,
) -> tuple[int, int]:
    if context_lines is not None:
        bounded = max(0, context_lines)
        return bounded, bounded
    return (
        max(0, config.retrieval.context_before_lines),
        max(0, config.retrieval.context_after_lines),
    )


def _followup_keywords(results: list[RetrievalResult]) -> list[str]:
    counts: Counter[str] = Counter()
    for result in results:
        counts.update(token for token in result.followup_keywords if token)
    return [
        token
        for token, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:12]
    ]


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
