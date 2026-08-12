from __future__ import annotations

import logging
import re
import sqlite3
import stat
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable

from context_search_tool.exploration.goals import unsatisfied_goals
from context_search_tool.exploration.models import (
    MAX_FRONTEND_HEADER_BYTES,
    MAX_PLANNED_PROBES,
    MAX_PROBE_SEED_PATHS,
    MAX_PROBE_TEXT_CODE_POINTS,
    ExplorationGoal,
    FrozenGoals,
    ProbeCandidate,
)
from context_search_tool.frontend_roles import (
    extract_static_imports,
    resolve_frontend_import,
)
from context_search_tool.graph_contract import (
    MAX_EDGES_PER_SIGNAL_DIRECTION,
    effective_relation_confidence,
)
from context_search_tool.identifier_intent import infer_identifier_intent
from context_search_tool.paths import index_dir_for
from context_search_tool.query_intent import infer_query_intent
from context_search_tool.retrieval_core import relation_policy
from context_search_tool.retrieval_scope import (
    RetrievalScope,
    RetrievalScopeSnapshot,
    snapshot_retrieval_scope,
)
from context_search_tool.sqlite_store import GraphReadSession, SQLiteStore
from context_search_tool.tokenizer import tokenize_query

if TYPE_CHECKING:
    from context_search_tool.context_pack import ContextPack
    from context_search_tool.models import DocumentChunk, SymbolRef
    from context_search_tool.retrieval import QueryBundle
    from context_search_tool.retrieval_trace import RetrievalTrace, TraceSelection


_SOURCE_PRIORITY = {
    "relation_target": 0,
    "indexed_symbol": 1,
    "endpoint_or_route": 2,
    "static_import": 3,
    "path_stem": 4,
    "next_query": 5,
}
_ROUTE_ROLES = {"entrypoint", "router", "command", "handler", "route_config"}
_VIEW_ROLES = {"view", "view_page", "layout_component"}
_FRONTEND_SUFFIXES = {".astro", ".js", ".jsx", ".svelte", ".ts", ".tsx", ".vue"}
_IMPORT_GOAL_CATEGORIES = {"implementations", "related_types", "supporting"}
_RELATION_GOAL_CATEGORIES = {"implementations", "related_types", "supporting"}
_READY_GRAPH_SEED_SOURCES = {
    "relation_target",
    "endpoint_or_route",
    "static_import",
}
_MAX_SEEDS_PER_SOURCE = 32
_MAX_IMPORTS_PER_FILE = 16
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WHITESPACE_RE = re.compile(r"\s+")
_MULTILINE_NAMED_IMPORT_RE = re.compile(
    r"^[ \t]*(?P<keyword>import)[ \t]+(?:type[ \t]+)?\{"
    r"[A-Za-z0-9_$, \t\r\n]+\}[ \t\r\n]+from[ \t]+"
    r"(?P<quote>[\"'])(?P<specifier>[^\"'\r\n]+)(?P=quote)",
    re.MULTILINE,
)
_JAVA_VIEW_CONSTANT_RE = re.compile(
    r'^[ \t]*(?:(?:public|protected|private)[ \t]+)?static[ \t]+final[ \t]+'
    r'String[ \t]+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)[ \t]*=[ \t]*'
    r'"(?P<value>[A-Za-z0-9_./-]+)"[ \t]*;[ \t]*$'
)
_VIEW_CONSTANT_NAME_PARTS = {
    "FORM",
    "FORMS",
    "PAGE",
    "PAGES",
    "TEMPLATE",
    "TEMPLATES",
    "VIEW",
    "VIEWS",
}
_STRUCTURED_NEED_SUFFIXES = {
    "entrypoints": "controller route template view",
    "implementations": "repository service implementation",
    "related_types": "entity model DTO type",
    "tests": "integration test",
    "configs_docs": "profile config properties yaml",
    "supporting": "service component store utility type",
}
_STRUCTURAL_TERM_RE = re.compile(r"[^a-z0-9]+")
_STRUCTURAL_DISCOVERY_LIMIT = 8
_STRUCTURAL_DISCOVERY_SCAN_LIMIT = _STRUCTURAL_DISCOVERY_LIMIT * 8
_STRUCTURAL_SUBJECT_ALIASES = {
    "postgresql": ("postgresql", "postgres"),
    "postgres": ("postgres", "postgresql"),
}
_CONFIG_SUFFIXES = {
    ".env",
    ".ini",
    ".json",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
_VIEW_SUFFIXES = {".astro", ".html", ".htm", ".svelte", ".vue"}
_CATEGORY_MARKERS = {
    "entrypoints": ("controller", "route", "router", "template", "view", "form", "page"),
    "implementations": (
        "repository",
        "service",
        "implementation",
        "handler",
        "storage",
        "utility",
        "utils",
    ),
    "related_types": ("dto", "entity", "model", "record", "type", "types"),
    "tests": ("test", "tests", "spec", "specs"),
    "configs_docs": ("application", "config", "configuration", "profile", "readme", "docs"),
    "supporting": ("component", "store", "utility", "utils"),
}


@dataclass(frozen=True)
class _Seed:
    text: str
    source: str
    source_rank: int
    seed_paths: tuple[str, ...]
    complete_query: bool = False
    graph_test: bool = False
    supported_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class _OriginState:
    selections: tuple[TraceSelection, ...]
    chunks: tuple[DocumentChunk, ...]
    rank_by_chunk_id: dict[str, int]
    rank_by_path: dict[str, int]


def plan_probes(
    repo: Path,
    initial_bundle: QueryBundle,
    initial_trace: RetrievalTrace,
    initial_pack: ContextPack,
    frozen: FrozenGoals,
    *,
    store: SQLiteStore | None = None,
    scope: RetrievalScope | None = None,
) -> tuple[ProbeCandidate, ...]:
    goals = unsatisfied_goals(frozen)
    if not goals or initial_trace.outcome != "complete":
        return ()
    if initial_trace.final_selection_omitted_count != 0:
        return ()
    if _exact_target_query(initial_bundle.query):
        return ()

    repo = repo.resolve()
    active_store = store or SQLiteStore(index_dir_for(repo) / "index.sqlite")
    missing_goal_ids = _missing_need_goal_ids(initial_pack)
    try:
        scope_snapshot = snapshot_retrieval_scope(active_store, scope)
        origins = _load_origins(active_store, initial_trace, initial_pack)
        if origins is None:
            return ()
        seeds = _grounded_seeds(
            repo,
            active_store,
            initial_bundle,
            initial_pack,
            origins,
            include_view_literals=any(
                set(goal.accepted_roles).intersection(_VIEW_ROLES)
                for goal in goals
            ),
        )
        seeds = (
            *seeds,
            *_discover_structured_need_seeds(
                active_store,
                goals,
                missing_goal_ids,
                scope_snapshot,
            ),
        )
        seeds = _seeds_within_scope(seeds, scope_snapshot)
    except (KeyError, OSError, sqlite3.Error, UnicodeError, ValueError):
        return ()
    if not seeds:
        return ()

    raw: list[ProbeCandidate] = []
    goal_order = {goal.id: index for index, goal in enumerate(frozen.goals)}
    composite = (
        None
        if any(goal.id in missing_goal_ids for goal in goals)
        else _required_goal_composite(initial_bundle, frozen)
    )
    if composite is not None:
        raw.append(composite)
    raw.extend(_single_required_view_composites(seeds, frozen))
    for goal in goals:
        if goal.kind == "need":
            if goal.id not in missing_goal_ids:
                continue
            for seed in seeds:
                candidate = _structured_missing_need_candidate(
                    goal,
                    goal_order[goal.id],
                    seed,
                )
                if candidate is not None:
                    raw.append(candidate)
            continue
        suffix = _goal_suffix(goal)
        for seed in seeds:
            if (
                not _seed_supports_goal(seed, goal)
                or not _seed_is_subject_compatible(seed, goal)
            ):
                continue
            candidate = _candidate_from_seed(
                goal,
                goal_order[goal.id],
                seed,
                suffix,
            )
            if candidate is not None:
                raw.append(candidate)
        if _safe_structural_subjects(goal.subject_terms) is not None:
            raw.extend(
                _next_query_candidates(
                    initial_bundle,
                    initial_pack,
                    frozen,
                    goal,
                    goal_order[goal.id],
                    suffix,
                )
            )
    raw.extend(_grounded_required_goal_composites(tuple(raw), frozen))
    return order_probe_candidates(tuple(raw), frozen)


def _plan_probes_v5(
    repo: Path,
    initial_bundle: QueryBundle,
    initial_trace: RetrievalTrace,
    initial_pack: ContextPack,
    frozen: FrozenGoals,
    *,
    store: SQLiteStore | None = None,
    graph_session_factory=None,
    scope: RetrievalScope | None = None,
) -> tuple[ProbeCandidate, ...]:
    goals = unsatisfied_goals(frozen)
    if not goals or initial_trace.outcome != "complete":
        return ()
    if initial_trace.final_selection_omitted_count != 0:
        return ()
    if _exact_target_query(initial_bundle.query):
        return ()

    repo = repo.resolve()
    active_store = store or SQLiteStore(index_dir_for(repo) / "index.sqlite")
    missing_goal_ids = _missing_need_goal_ids(initial_pack)
    try:
        scope_snapshot = snapshot_retrieval_scope(active_store, scope)
        discovered_seeds = _discover_structured_need_seeds(
            active_store,
            goals,
            missing_goal_ids,
            scope_snapshot,
        )
    except (KeyError, OSError, sqlite3.Error, UnicodeError, ValueError):
        return ()
    session_context = (
        graph_session_factory()
        if graph_session_factory is not None
        else active_store.graph_read_session()
    )
    graph_fault: str | None = None
    ready_graph = False
    seeds: tuple[_Seed, ...] = ()
    try:
        with session_context as graph_session:
            graph_session.validate_ready_targets()
            origins = _load_origins(
                graph_session,
                initial_trace,
                initial_pack,
            )
            if origins is None:
                return ()
            if (
                graph_session.capability.status == "ready"
                and graph_session.graph_fault is None
            ):
                allow_tests = (
                    "test"
                    in infer_query_intent(
                        initial_bundle.query,
                        tokenize_query(initial_bundle.query),
                    ).target_roles
                    or any(
                        goal.category == "tests"
                        or "test" in goal.accepted_roles
                        for goal in goals
                    )
                )
                seeds = _ready_graph_seeds(
                    graph_session,
                    origins,
                    include_view_literals=any(
                        set(goal.accepted_roles).intersection(_VIEW_ROLES)
                        for goal in goals
                    ),
                    allow_tests=allow_tests,
                )
            if (
                graph_session.capability.status != "ready"
                or graph_session.graph_fault is not None
            ):
                seeds = _grounded_seeds(
                    repo,
                    graph_session,
                    initial_bundle,
                    initial_pack,
                    origins,
                    include_view_literals=any(
                        set(goal.accepted_roles).intersection(_VIEW_ROLES)
                        for goal in goals
                    ),
                )
            graph_fault = graph_session.graph_fault
            ready_graph = (
                graph_session.capability.status == "ready"
                and graph_fault is None
            )
            seeds = (*seeds, *discovered_seeds)
    except (KeyError, OSError, sqlite3.Error, UnicodeError, ValueError):
        return ()
    if graph_fault is not None:
        try:
            active_store.mark_graph_stale(graph_fault)
        except (OSError, sqlite3.Error):
            logging.getLogger(__name__).warning(
                "graph snapshot fault could not be persisted: %s",
                graph_fault,
            )
    seeds = _seeds_within_scope(seeds, scope_snapshot)
    if not seeds:
        return ()

    raw: list[ProbeCandidate] = []
    goal_order = {goal.id: index for index, goal in enumerate(frozen.goals)}
    composite = (
        None
        if any(goal.id in missing_goal_ids for goal in goals)
        else _required_goal_composite_v5(
            initial_bundle,
            frozen,
            seeds,
            ready_graph=ready_graph,
        )
    )
    if composite is not None:
        raw.append(composite)
    raw.extend(_single_required_view_composites(seeds, frozen))
    for goal in goals:
        if goal.kind == "need":
            if goal.id not in missing_goal_ids:
                continue
            for seed in seeds:
                candidate = _structured_missing_need_candidate(
                    goal,
                    goal_order[goal.id],
                    seed,
                )
                if candidate is not None:
                    raw.append(candidate)
            continue
        suffix = _goal_suffix(goal)
        for seed in seeds:
            if (
                not _seed_supports_goal(seed, goal)
                or not _seed_is_subject_compatible(seed, goal)
            ):
                continue
            candidate = _candidate_from_seed(
                goal,
                goal_order[goal.id],
                seed,
                suffix,
            )
            if candidate is not None:
                raw.append(candidate)
        if _safe_structural_subjects(goal.subject_terms) is not None:
            raw.extend(
                _next_query_candidates(
                    initial_bundle,
                    initial_pack,
                    frozen,
                    goal,
                    goal_order[goal.id],
                    suffix,
                )
            )
    raw.extend(_grounded_required_goal_composites(tuple(raw), frozen))
    return order_probe_candidates(tuple(raw), frozen)


def _missing_need_goal_ids(pack: ContextPack) -> frozenset[str]:
    missing = {
        (item.need_id, item.category, item.required)
        for item in pack.missing_evidence
    }
    return frozenset(
        f"goal-need-{need.category}-{index}"
        for index, need in enumerate(pack.evidence_needs)
        if not need.matched_item_ids
        and (need.id, need.category, need.required) in missing
    )


def _discover_structured_need_seeds(
    store: SQLiteStore,
    goals: tuple[ExplorationGoal, ...],
    missing_goal_ids: frozenset[str],
    scope: RetrievalScopeSnapshot,
) -> tuple[_Seed, ...]:
    seeds: list[_Seed] = []
    seen: set[tuple[str, str, str, str]] = set()
    scope_kwargs = (
        {}
        if scope.allowed_chunk_ids is None
        else {"allowed_chunk_ids": scope.allowed_chunk_ids}
    )
    for goal in goals:
        subjects = _safe_structural_subjects(goal.subject_terms)
        if not _goal_is_structurally_discoverable(
            goal,
            missing_goal_ids,
        ) or subjects is None:
            continue
        tokens = _structural_subject_tokens(subjects)
        if not tokens:
            continue
        matches = store.path_symbol_search(
            list(tokens),
            _STRUCTURAL_DISCOVERY_SCAN_LIMIT,
            **scope_kwargs,
        )
        chunks = store.chunks_for_ids([match.chunk_id for match in matches])
        ranked_chunks: list[
            tuple[int, float, str, str, tuple[_Seed, ...]]
        ] = []
        for match in matches:
            chunk = chunks.get(match.chunk_id)
            if chunk is None:
                continue
            path = chunk.file_path.as_posix()
            if not _relative_path(path):
                continue
            path_seed = _safe_seed(chunk.file_path.stem)
            chunk_seeds: list[_Seed] = []
            if (
                path_seed is not None
                and _path_or_symbol_supports_category(goal.category, path, None)
            ):
                seed = _Seed(
                    path_seed,
                    "path_stem",
                    0,
                    (path,),
                    supported_categories=(goal.category,),
                )
                if _seed_supports_subjects(seed, subjects):
                    chunk_seeds.append(seed)
            for symbol in chunk.symbols:
                symbol_seed = _safe_seed(symbol.name)
                if symbol_seed is None or not _path_or_symbol_supports_category(
                    goal.category,
                    path,
                    symbol.kind,
                    symbol_name=symbol.name,
                ):
                    continue
                seed = _Seed(
                    symbol_seed,
                    "indexed_symbol",
                    0,
                    (path,),
                    supported_categories=(goal.category,),
                )
                if _seed_supports_subjects(seed, subjects):
                    chunk_seeds.append(seed)
                    break
            if chunk_seeds:
                ranked_chunks.append(
                    (
                        -_category_match_score(goal.category, path, chunk_seeds),
                        -match.score,
                        path.casefold(),
                        match.chunk_id,
                        tuple(chunk_seeds),
                    )
                )
        for source_rank, ranked_chunk in enumerate(
            sorted(ranked_chunks)[:_STRUCTURAL_DISCOVERY_LIMIT],
            start=1,
        ):
            chunk_seeds = ranked_chunk[-1]
            for seed in chunk_seeds:
                _append_discovered_seed(
                    seeds,
                    seen,
                    replace(seed, source_rank=source_rank),
                    subjects,
                )
    return tuple(seeds)


def _goal_is_structurally_discoverable(
    goal: ExplorationGoal,
    missing_goal_ids: frozenset[str],
) -> bool:
    if goal.kind == "need":
        return goal.id in missing_goal_ids
    return (
        goal.kind == "role_gap"
        and goal.required
        and bool(set(goal.accepted_roles).intersection(_VIEW_ROLES))
    )


def _structural_subject_tokens(subjects: tuple[str, ...]) -> tuple[str, ...]:
    tokens: list[str] = []
    for subject in subjects:
        key = _structural_key(subject)
        aliases = _STRUCTURAL_SUBJECT_ALIASES.get(key, (subject,))
        for alias in aliases:
            for token in tokenize_query(alias):
                normalized = token.casefold()
                if normalized and normalized not in tokens:
                    tokens.append(normalized)
    return tuple(tokens)


def _path_or_symbol_supports_category(
    category: str,
    path: str,
    symbol_kind: str | None,
    *,
    symbol_name: str = "",
) -> bool:
    pure_path = PurePosixPath(path)
    structural_tokens = set(tokenize_query(" ".join((path, symbol_name))))
    if category != "tests" and structural_tokens.intersection(
        _CATEGORY_MARKERS["tests"]
    ):
        return False
    if category == "configs_docs":
        return (
            pure_path.suffix.casefold() in _CONFIG_SUFFIXES
            or bool(structural_tokens.intersection(_CATEGORY_MARKERS[category]))
        )
    if category == "entrypoints":
        return (
            pure_path.suffix.casefold() in _VIEW_SUFFIXES
            or bool(structural_tokens.intersection(_CATEGORY_MARKERS[category]))
        )
    if category == "related_types":
        return (
            path.casefold().endswith(".d.ts")
            or symbol_kind is not None
            and symbol_kind.casefold()
            in {"class", "data_type", "enum", "interface", "record", "struct", "type"}
        ) or bool(
            structural_tokens.intersection(_CATEGORY_MARKERS[category])
        )
    markers = _CATEGORY_MARKERS.get(category)
    return bool(markers) and bool(structural_tokens.intersection(markers))


def _category_match_score(
    category: str,
    path: str,
    seeds: list[_Seed],
) -> int:
    markers = _CATEGORY_MARKERS.get(category, ())
    tokens = set(
        tokenize_query(" ".join((path, *(seed.text for seed in seeds))))
    )
    return len(tokens.intersection(markers))


def _append_discovered_seed(
    seeds: list[_Seed],
    seen: set[tuple[str, str, str, str]],
    seed: _Seed,
    subjects: tuple[str, ...],
) -> bool:
    if not _seed_supports_subjects(seed, subjects):
        return False
    key = (
        seed.text.casefold(),
        seed.source,
        seed.seed_paths[0],
        seed.supported_categories[0],
    )
    if key in seen:
        return False
    seen.add(key)
    seeds.append(seed)
    return True


def _structured_missing_need_candidate(
    goal: ExplorationGoal,
    goal_order: int,
    seed: _Seed,
) -> ProbeCandidate | None:
    subjects = _safe_structural_subjects(goal.subject_terms)
    suffix = _STRUCTURED_NEED_SUFFIXES.get(goal.category)
    if (
        goal.kind != "need"
        or subjects is None
        or suffix is None
        or seed.source == "next_query"
        or not _seed_supports_goal(seed, goal)
        or not _grounded_seed_supports_need(seed, goal)
        or not _seed_supports_subjects(seed, subjects)
    ):
        return None

    seed_text = _safe_seed(seed.text)
    if seed_text is None:
        return None
    seed_key = _structural_key(seed_text)
    subject_prefix = tuple(
        subject
        for subject in subjects
        if _structural_key(subject) not in seed_key
    )
    query = normalize_probe_text(
        " ".join(
            (
                *subject_prefix,
                seed_text,
                suffix,
            )
        )
    )
    if query is None:
        return None
    return ProbeCandidate(
        query=query,
        source=seed.source,
        purpose=goal.category,
        goal_ids=(goal.id,),
        seed_paths=tuple(
            path for path in seed.seed_paths if _relative_path(path)
        )[:MAX_PROBE_SEED_PATHS],
        required=goal.required,
        goal_order=goal_order,
        source_rank=seed.source_rank,
    )


def _grounded_required_goal_composites(
    candidates: tuple[ProbeCandidate, ...],
    frozen: FrozenGoals,
) -> tuple[ProbeCandidate, ...]:
    required_ids = {
        goal.id
        for goal in frozen.goals
        if goal.required and not goal.initially_satisfied
    }
    if len(required_ids) < 2:
        return ()
    grounded = tuple(
        candidate
        for candidate in order_probe_candidates(candidates, frozen)
        if candidate.source != "next_query"
        and candidate.seed_paths
        and required_ids.intersection(candidate.goal_ids)
    )
    composites: list[ProbeCandidate] = []
    for left_index, left in enumerate(grounded):
        for right in grounded[left_index + 1 :]:
            if (
                {left.purpose, right.purpose}
                != {"entrypoints", "implementations"}
                or not set(left.seed_paths).intersection(right.seed_paths)
            ):
                continue
            merged_goal_ids = set((*left.goal_ids, *right.goal_ids))
            goal_ids = tuple(
                goal.id
                for goal in frozen.goals
                if goal.id in merged_goal_ids
            )
            if len(required_ids.intersection(goal_ids)) < 2:
                continue
            query = normalize_probe_text(" ".join((left.query, right.query)))
            if query is None:
                continue
            primary = min((left, right), key=_candidate_priority)
            composites.append(
                ProbeCandidate(
                    query=query,
                    source=primary.source,
                    purpose=primary.purpose,
                    goal_ids=goal_ids,
                    seed_paths=_ordered_union(
                        left.seed_paths,
                        right.seed_paths,
                        limit=MAX_PROBE_SEED_PATHS,
                    ),
                    required=True,
                    goal_order=min(left.goal_order, right.goal_order),
                    source_rank=min(left.source_rank, right.source_rank),
                )
            )
    return tuple(composites)


def _safe_structural_subjects(
    subject_terms: tuple[str, ...],
) -> tuple[str, ...] | None:
    if not subject_terms:
        return None
    subjects: list[str] = []
    for value in subject_terms:
        subject = _safe_seed(value)
        if subject is None or not subject.isascii():
            return None
        if not _structural_key(subject):
            return None
        subjects.append(subject)
    return tuple(subjects) if subjects else None


def _seed_is_subject_compatible(seed: _Seed, goal: ExplorationGoal) -> bool:
    if goal.kind != "need" and not set(goal.accepted_roles).intersection(
        _VIEW_ROLES
    ):
        return True
    subjects = _safe_structural_subjects(goal.subject_terms)
    return subjects is not None and _seed_supports_subjects(seed, subjects)


def _grounded_seed_supports_need(seed: _Seed, goal: ExplorationGoal) -> bool:
    if seed.supported_categories:
        return goal.category in seed.supported_categories
    if seed.graph_test:
        return goal.category == "tests"
    if seed.source in {"relation_target", "static_import"}:
        if goal.category in {"implementations", "supporting"}:
            return True
        return any(
            _path_or_symbol_supports_category(
                goal.category,
                path,
                None,
                symbol_name=seed.text,
            )
            for path in seed.seed_paths
        )
    if seed.source == "endpoint_or_route":
        return goal.category == "entrypoints"
    return any(
        _path_or_symbol_supports_category(
            goal.category,
            path,
            None,
            symbol_name=seed.text,
        )
        for path in seed.seed_paths
    )


def _seed_supports_subjects(seed: _Seed, subjects: tuple[str, ...]) -> bool:
    fields = tuple(
        segments
        for value in (
            seed.text,
            *(PurePosixPath(path).stem for path in seed.seed_paths),
        )
        if (segments := _identifier_segments(value))
    )
    return bool(fields) and all(
        any(
            _structural_key(alias) in field
            for alias in _STRUCTURAL_SUBJECT_ALIASES.get(subject_key, (subject_key,))
            for field in fields
        )
        for subject in subjects
        if (subject_key := _structural_key(subject))
    )


def _identifier_segments(value: str) -> frozenset[str]:
    tokens = tokenize_query(value)
    return frozenset(
        "".join(tokens[start:end])
        for start in range(len(tokens))
        for end in range(start + 1, len(tokens) + 1)
    )


def _seeds_within_scope(
    seeds: Iterable[_Seed],
    scope: RetrievalScopeSnapshot,
) -> tuple[_Seed, ...]:
    retained = tuple(seeds)
    if not scope.is_active:
        return retained
    allowed_paths = {
        file_path.as_posix()
        for _, file_path, _ in scope.allowed_rows
    }
    return tuple(
        seed
        for seed in retained
        if seed.seed_paths
        and all(path in allowed_paths for path in seed.seed_paths)
        and (
            seed.source not in {"relation_target", "static_import"}
            or len(set(seed.seed_paths)) >= 2
        )
    )


def _structural_key(value: str) -> str:
    return _STRUCTURAL_TERM_RE.sub("", value.casefold())


def _exact_target_query(query: str) -> bool:
    intent = infer_identifier_intent(query, tokenize_query(query))
    if intent.exact_identifier is not None:
        return True
    trimmed = query.strip()
    if not intent.file_hints or any(character.isspace() for character in trimmed):
        return False
    normalized = trimmed.replace("\\", "/").casefold()
    return any(
        normalized == hint or normalized.endswith(f"/{hint}")
        for hint in intent.file_hints
    )


def normalize_probe_text(value: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if any(unicodedata.category(character).startswith("C") for character in value):
        return None
    normalized = _WHITESPACE_RE.sub(" ", value).strip()
    if not normalized:
        return None
    if len(normalized) <= MAX_PROBE_TEXT_CODE_POINTS:
        return normalized
    bounded = normalized[:MAX_PROBE_TEXT_CODE_POINTS]
    if " " in bounded:
        at_boundary = bounded.rsplit(" ", 1)[0].rstrip()
        if at_boundary:
            bounded = at_boundary
    return bounded or None


def deduplicate_probe_candidates(
    candidates: Iterable[ProbeCandidate],
) -> tuple[ProbeCandidate, ...]:
    deduped: list[ProbeCandidate] = []
    positions: dict[str, int] = {}
    for candidate in candidates:
        key = candidate.query.casefold()
        existing_index = positions.get(key)
        if existing_index is None:
            positions[key] = len(deduped)
            deduped.append(candidate)
            continue
        existing = deduped[existing_index]
        deduped[existing_index] = replace(
            existing,
            goal_ids=_ordered_union(existing.goal_ids, candidate.goal_ids),
            seed_paths=_ordered_union(
                existing.seed_paths,
                candidate.seed_paths,
                limit=MAX_PROBE_SEED_PATHS,
            ),
        )
    return tuple(deduped)


def order_probe_candidates(
    candidates: Iterable[ProbeCandidate],
    frozen: FrozenGoals,
) -> tuple[ProbeCandidate, ...]:
    ranked = sorted(candidates, key=_candidate_priority)
    ranked = sorted(
        deduplicate_probe_candidates(ranked),
        key=_candidate_priority,
    )
    selected: list[ProbeCandidate] = []
    represented_goal_ids: set[str] = set()
    selected_queries: set[str] = set()
    for goal in frozen.goals:
        if goal.initially_satisfied or goal.id in represented_goal_ids:
            continue
        candidate = next(
            (
                item
                for item in ranked
                if goal.id in item.goal_ids
                and item.query.casefold() not in selected_queries
            ),
            None,
        )
        if candidate is None:
            continue
        selected.append(candidate)
        selected_queries.add(candidate.query.casefold())
        represented_goal_ids.update(candidate.goal_ids)
        if len(selected) == MAX_PLANNED_PROBES:
            return tuple(selected)

    for candidate in ranked:
        key = candidate.query.casefold()
        if key in selected_queries:
            continue
        selected.append(candidate)
        selected_queries.add(key)
        if len(selected) == MAX_PLANNED_PROBES:
            break
    return tuple(selected)


def probe_candidate_is_stale(
    candidate: ProbeCandidate,
    satisfied_goal_ids: set[str] | frozenset[str],
) -> bool:
    return bool(candidate.goal_ids) and all(
        goal_id in satisfied_goal_ids for goal_id in candidate.goal_ids
    )


def _required_goal_composite(
    bundle: QueryBundle,
    frozen: FrozenGoals,
) -> ProbeCandidate | None:
    goals = tuple(
        goal
        for goal in frozen.goals
        if goal.required and not goal.initially_satisfied
    )
    if len(goals) < 2:
        return None
    suffixes = _ordered_union(_goal_suffix(goal) for goal in goals)
    query = normalize_probe_text(" ".join((bundle.query, *suffixes)))
    if query is None:
        return None
    return ProbeCandidate(
        query=query,
        source="next_query",
        purpose=goals[0].category,
        goal_ids=tuple(goal.id for goal in goals),
        seed_paths=(),
        required=True,
        goal_order=next(
            index for index, goal in enumerate(frozen.goals) if goal.id == goals[0].id
        ),
        source_rank=0,
    )


def _ready_seeds_cover_required_goals(
    seeds: Iterable[_Seed],
    frozen: FrozenGoals,
) -> bool:
    required = tuple(
        goal
        for goal in frozen.goals
        if goal.required and not goal.initially_satisfied
    )
    if not required:
        return False
    retained_seeds = tuple(seeds)
    if not any(
        seed.source in _READY_GRAPH_SEED_SOURCES
        and any(_seed_supports_goal(seed, goal) for goal in required)
        for seed in retained_seeds
    ):
        return False
    return all(
        any(_seed_supports_goal(seed, goal) for seed in retained_seeds)
        for goal in required
    )


def _required_goal_composite_v5(
    bundle: QueryBundle,
    frozen: FrozenGoals,
    seeds: Iterable[_Seed],
    *,
    ready_graph: bool,
) -> ProbeCandidate | None:
    composite = _required_goal_composite(bundle, frozen)
    if (
        composite is not None
        and ready_graph
        and len(bundle.results) > 1
        and _ready_seeds_cover_required_goals(seeds, frozen)
    ):
        return None
    return composite


def _single_required_view_composites(
    seeds: Iterable[_Seed],
    frozen: FrozenGoals,
) -> tuple[ProbeCandidate, ...]:
    required = tuple(
        goal
        for goal in frozen.goals
        if goal.required and not goal.initially_satisfied
    )
    if len(required) != 1 or not set(required[0].accepted_roles).intersection(
        _VIEW_ROLES
    ):
        return ()
    required_goal = required[0]
    recommended = tuple(
        goal
        for goal in frozen.goals
        if not goal.required
        and not goal.initially_satisfied
    )
    goal_order = next(
        index
        for index, goal in enumerate(frozen.goals)
        if goal.id == required_goal.id
    )
    retained_seeds = tuple(seeds)
    view_path_seeds = tuple(
        seed
        for seed in retained_seeds
        if seed.source == "path_stem"
        and "entrypoints" in seed.supported_categories
        and any(
            PurePosixPath(path).suffix.casefold() in _VIEW_SUFFIXES
            for path in seed.seed_paths
        )
    )
    candidates: list[ProbeCandidate] = []
    for seed in view_path_seeds or retained_seeds:
        if (
            seed.source not in {"indexed_symbol", "path_stem"}
            or seed.complete_query
            or seed.source == "path_stem"
            and "entrypoints" not in seed.supported_categories
        ):
            continue
        if (
            not _seed_supports_goal(seed, required_goal)
            or not _seed_is_subject_compatible(seed, required_goal)
        ):
            continue
        supported = tuple(
            goal
            for goal in recommended
            if _seed_supports_goal(seed, goal)
            or (
                goal.category == "tests"
                and _seed_is_subject_compatible(seed, goal)
            )
        )
        if not supported:
            continue
        goals = (required_goal, *supported)
        suffixes = _ordered_union(_goal_suffix(goal) for goal in goals)
        query = normalize_probe_text(" ".join((seed.text, *suffixes)))
        if query is None:
            continue
        candidates.append(
            ProbeCandidate(
                query=query,
                source=seed.source,
                purpose=required_goal.category,
                goal_ids=tuple(goal.id for goal in goals),
                seed_paths=tuple(
                    path for path in seed.seed_paths if _relative_path(path)
                )[:MAX_PROBE_SEED_PATHS],
                required=True,
                goal_order=goal_order,
                source_rank=seed.source_rank,
            )
        )
    return tuple(candidates)


def _load_origins(
    store: SQLiteStore | GraphReadSession,
    trace: RetrievalTrace,
    pack: ContextPack,
) -> _OriginState | None:
    selection_by_path = {selection.file_path: selection for selection in trace.final_selections}
    selected_paths = tuple(item.file_path for item in pack.items)
    if not selected_paths or any(path not in selection_by_path for path in selected_paths):
        return None
    selections = tuple(selection_by_path[path] for path in selected_paths)
    chunk_ids = _ordered_union(
        *(selection.origin_chunk_ids for selection in selections)
    )
    chunks_by_id = store.chunks_for_ids(list(chunk_ids))
    if tuple(chunks_by_id) != chunk_ids:
        return None

    rank_by_chunk_id: dict[str, int] = {}
    rank_by_path: dict[str, int] = {}
    for selection in selections:
        rank_by_path[selection.file_path] = selection.rank
        for chunk_id in selection.origin_chunk_ids:
            chunk = chunks_by_id[chunk_id]
            if chunk.file_path.as_posix() != selection.file_path:
                return None
            rank_by_chunk_id[chunk_id] = min(
                rank_by_chunk_id.get(chunk_id, selection.rank),
                selection.rank,
            )
    return _OriginState(
        selections=selections,
        chunks=tuple(chunks_by_id[chunk_id] for chunk_id in chunk_ids),
        rank_by_chunk_id=rank_by_chunk_id,
        rank_by_path=rank_by_path,
    )


def _ready_graph_seeds(
    session: GraphReadSession,
    origins: _OriginState,
    *,
    include_view_literals: bool,
    allow_tests: bool,
) -> tuple[_Seed, ...]:
    symbols: list[_Seed] = []
    path_stems: list[_Seed] = []
    relation_targets: list[_Seed] = []
    endpoints: list[_Seed] = []
    imports: list[_Seed] = []

    ordered_chunks = sorted(
        origins.chunks,
        key=lambda chunk: (
            origins.rank_by_chunk_id[chunk.chunk_id],
            chunk.file_path.as_posix(),
            chunk.start_line,
            chunk.chunk_id,
        ),
    )
    for chunk in ordered_chunks:
        rank = origins.rank_by_chunk_id[chunk.chunk_id]
        seed_path = chunk.file_path.as_posix()
        if not _relative_path(seed_path):
            raise ValueError("origin path is not repository-relative")
        for symbol in chunk.symbols:
            seed = _safe_seed(symbol.name)
            if seed is not None:
                symbols.append(_Seed(seed, "indexed_symbol", rank, (seed_path,)))
            literal_seed = (
                _view_constant_literal_seed(chunk, symbol)
                if include_view_literals
                else None
            )
            if literal_seed is not None:
                symbols.append(
                    _Seed(literal_seed, "indexed_symbol", rank, (seed_path,))
                )
        stem = _safe_seed(chunk.file_path.stem)
        if stem is not None:
            path_stems.append(_Seed(stem, "path_stem", rank, (seed_path,)))

    seed_specs = [
        (chunk.chunk_id, index, 0)
        for index, chunk in enumerate(ordered_chunks)
    ]
    initial_signals = session.initial_graph_signals(
        seed_specs,
        limit=_MAX_SEEDS_PER_SOURCE + 1,
    )
    if len(initial_signals) > _MAX_SEEDS_PER_SOURCE:
        session.record_graph_truncation()
        initial_signals = initial_signals[:_MAX_SEEDS_PER_SOURCE]

    for signal, seed_rank, _source_priority in initial_signals:
        origin = ordered_chunks[seed_rank]
        rank = origins.rank_by_chunk_id[origin.chunk_id]
        seed_path = origin.file_path.as_posix()
        seed = _safe_seed(signal.name)
        if seed is not None:
            if signal.kind in {"endpoint", "route"}:
                endpoints.append(
                    _Seed(seed, "endpoint_or_route", rank, (seed_path,))
                )
            elif signal.kind == "usage":
                relation_targets.append(
                    _Seed(seed, "relation_target", rank, (seed_path,))
                )

        for direction, relations in (
            (
                "outgoing",
                session.outgoing_relations(
                    signal.signal_id,
                    limit=MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
                ),
            ),
            (
                "incoming",
                session.incoming_relations(
                    signal.signal_id,
                    limit=MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
                ),
            ),
        ):
            if len(relations) > MAX_EDGES_PER_SIGNAL_DIRECTION:
                session.record_graph_truncation()
                relations = relations[:MAX_EDGES_PER_SIGNAL_DIRECTION]
            for relation in relations:
                policy = relation_policy.RELATION_DIRECTIONS.get(relation.kind)
                if policy == "intent_gated_both":
                    admitted = allow_tests
                else:
                    admitted = policy == "both" or policy == direction
                if not admitted:
                    continue
                try:
                    confidence = effective_relation_confidence(
                        resolution=relation.resolution,
                        target_signal_id=relation.target_signal_id,
                        producer_confidence=relation.producer_confidence,
                        resolution_confidence=relation.resolution_confidence,
                    )
                except ValueError:
                    session.record_graph_fault("integrity_check_failed")
                    return ()
                if confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                    continue
                neighbor_id = (
                    relation.target_signal_id
                    if direction == "outgoing"
                    else relation.source_signal_id
                )
                neighbor = session.signal_for_id(neighbor_id)
                if neighbor is None or session.chunk_for_id(neighbor.chunk_id) is None:
                    session.record_graph_fault("dangling_target")
                    return ()
                neighbor_path = neighbor.file_path.as_posix()
                seed_paths = _ordered_union(
                    (seed_path,),
                    (neighbor_path,),
                    limit=MAX_PROBE_SEED_PATHS,
                )
                if relation.kind == "imports":
                    imported = _safe_seed(neighbor.file_path.stem)
                    if imported is not None and len(imports) < _MAX_SEEDS_PER_SOURCE:
                        imports.append(
                            _Seed(imported, "static_import", rank, seed_paths)
                        )
                    continue
                related = _safe_seed(neighbor.name)
                if (
                    related is not None
                    and len(relation_targets) < _MAX_SEEDS_PER_SOURCE
                ):
                    relation_targets.append(
                        _Seed(
                            related,
                            "relation_target",
                            rank,
                            seed_paths,
                            graph_test=relation.kind == "tests",
                        )
                    )

    return tuple(
        [
            *relation_targets[:_MAX_SEEDS_PER_SOURCE],
            *symbols[:_MAX_SEEDS_PER_SOURCE],
            *endpoints[:_MAX_SEEDS_PER_SOURCE],
            *imports[:_MAX_SEEDS_PER_SOURCE],
            *path_stems[:_MAX_SEEDS_PER_SOURCE],
        ]
    )


def _grounded_seeds(
    repo: Path,
    store: SQLiteStore | GraphReadSession,
    bundle: QueryBundle,
    pack: ContextPack,
    origins: _OriginState,
    *,
    include_view_literals: bool,
) -> tuple[_Seed, ...]:
    symbols: list[_Seed] = []
    path_stems: list[_Seed] = []
    relation_targets: list[_Seed] = []
    endpoints: list[_Seed] = []
    imports: list[_Seed] = []

    for chunk in origins.chunks:
        rank = origins.rank_by_chunk_id[chunk.chunk_id]
        seed_path = chunk.file_path.as_posix()
        if not _relative_path(seed_path):
            raise ValueError("origin path is not repository-relative")
        for symbol in chunk.symbols:
            seed = _safe_seed(symbol.name)
            if seed is not None:
                symbols.append(_Seed(seed, "indexed_symbol", rank, (seed_path,)))
            literal_seed = (
                _view_constant_literal_seed(chunk, symbol)
                if include_view_literals
                else None
            )
            if literal_seed is not None:
                symbols.append(
                    _Seed(literal_seed, "indexed_symbol", rank, (seed_path,))
                )

    signals_by_chunk = store.signals_for_chunks(
        [chunk.chunk_id for chunk in origins.chunks]
    )
    signal_ids: list[str] = []
    signal_rank: dict[str, int] = {}
    for chunk in origins.chunks:
        rank = origins.rank_by_chunk_id[chunk.chunk_id]
        for signal in signals_by_chunk.get(chunk.chunk_id, ()):
            signal_ids.append(signal.signal_id)
            signal_rank[signal.signal_id] = rank
            seed = _safe_seed(signal.name)
            if seed is None:
                continue
            seed_paths = (signal.file_path.as_posix(),)
            if signal.kind in {"endpoint", "route"}:
                endpoints.append(
                    _Seed(seed, "endpoint_or_route", rank, seed_paths)
                )
            elif signal.kind == "usage":
                relation_targets.append(
                    _Seed(seed, "relation_target", rank, seed_paths)
                )

    relations_by_source = store.relations_for_sources(signal_ids)
    for signal_id in signal_ids:
        for relation in relations_by_source.get(signal_id, ()):
            seed = _safe_seed(relation.target_name)
            if seed is None:
                continue
            source_paths = tuple(
                selection.file_path
                for selection in origins.selections
                if signal_id in {
                    signal.signal_id
                    for chunk_id in selection.origin_chunk_ids
                    for signal in signals_by_chunk.get(chunk_id, ())
                }
            )
            relation_targets.append(
                _Seed(
                    seed,
                    "relation_target",
                    signal_rank[signal_id],
                    source_paths[:MAX_PROBE_SEED_PATHS],
                )
            )

    for selection in origins.selections:
        stem = _safe_seed(PurePosixPath(selection.file_path).stem)
        if stem is not None:
            path_stems.append(
                _Seed(
                    stem,
                    "path_stem",
                    selection.rank,
                    (selection.file_path,),
                )
            )
        if selection.file_path.casefold().endswith(".java"):
            source_file = store.source_file_for_path(Path(selection.file_path))
            if source_file is None:
                raise ValueError("selected Java source is not indexed")
            plugin_metadata = source_file.metadata.get("plugin", {})
            java_imports = (
                plugin_metadata.get("imports", ())
                if isinstance(plugin_metadata, dict)
                else ()
            )
            if isinstance(java_imports, (list, tuple)):
                for imported in java_imports[:_MAX_IMPORTS_PER_FILE]:
                    if not isinstance(imported, str):
                        continue
                    grounded_import = _safe_seed(imported)
                    if grounded_import is None:
                        continue
                    seed = _safe_seed(grounded_import.rsplit(".", 1)[-1])
                    if seed is not None:
                        imports.append(
                            _Seed(
                                seed,
                                "static_import",
                                selection.rank,
                                (selection.file_path,),
                            )
                        )

    imports.extend(_frontend_import_seeds(repo, store, bundle, pack, origins))
    return tuple(
        [
            *relation_targets[:_MAX_SEEDS_PER_SOURCE],
            *symbols[:_MAX_SEEDS_PER_SOURCE],
            *endpoints[:_MAX_SEEDS_PER_SOURCE],
            *imports[:_MAX_SEEDS_PER_SOURCE],
            *path_stems[:_MAX_SEEDS_PER_SOURCE],
        ]
    )


def _frontend_import_seeds(
    repo: Path,
    store: SQLiteStore | GraphReadSession,
    bundle: QueryBundle,
    pack: ContextPack,
    origins: _OriginState,
) -> tuple[_Seed, ...]:
    windows = {
        item.file_path.as_posix(): (item.content, item.start_line)
        for item in (*bundle.results, *bundle.evidence_anchors)
    }
    seeds: list[_Seed] = []
    header_reads = 0
    for item in pack.items:
        suffix = PurePosixPath(item.file_path).suffix.casefold()
        if suffix not in _FRONTEND_SUFFIXES:
            continue
        if store.source_file_for_path(Path(item.file_path)) is None:
            raise ValueError("selected frontend source is not indexed")
        content, start_line = windows.get(item.file_path, ("", 2))
        specifiers = _extract_probe_static_imports(content)
        if not specifiers and start_line > 1 and header_reads < 3:
            header_reads += 1
            header = _read_frontend_header(repo, item.file_path)
            if header is not None:
                specifiers = _extract_probe_static_imports(header)
        rank = origins.rank_by_path[item.file_path]
        for specifier in specifiers[:_MAX_IMPORTS_PER_FILE]:
            resolved = resolve_frontend_import(repo, item.file_path, specifier)
            if resolved is None or not _relative_path(resolved):
                continue
            if store.source_file_for_path(Path(resolved)) is None:
                continue
            seed = _safe_seed(PurePosixPath(resolved).stem)
            if seed is not None:
                seeds.append(
                    _Seed(
                        seed,
                        "static_import",
                        rank,
                        (item.file_path, resolved),
                    )
                )
    return tuple(seeds)


def _extract_probe_static_imports(content: str) -> tuple[str, ...]:
    specifiers = list(extract_static_imports(content))
    seen = set(specifiers)
    code_positions = _javascript_code_positions(content)
    for match in _MULTILINE_NAMED_IMPORT_RE.finditer(content):
        if not code_positions[match.start("keyword")]:
            continue
        specifier = match.group("specifier")
        if specifier not in seen:
            seen.add(specifier)
            specifiers.append(specifier)
    return tuple(specifiers)


def _view_constant_literal_seed(
    chunk: DocumentChunk,
    symbol: SymbolRef,
) -> str | None:
    if (
        symbol.kind != "constant"
        or symbol.language.casefold() != "java"
        or symbol.start_line != symbol.end_line
    ):
        return None
    name_parts = set(re.split(r"[^A-Za-z0-9]+", symbol.name.upper()))
    if not name_parts.intersection(_VIEW_CONSTANT_NAME_PARTS):
        return None
    line_index = symbol.start_line - chunk.start_line
    lines = chunk.content.splitlines()
    if line_index < 0 or line_index >= len(lines):
        return None
    match = _JAVA_VIEW_CONSTANT_RE.fullmatch(lines[line_index])
    if match is None or match.group("name") != symbol.name:
        return None
    literal = match.group("value")
    if not _relative_path(literal):
        return None
    return _safe_seed(PurePosixPath(literal).name)


def _javascript_code_positions(content: str) -> bytearray:
    positions = bytearray(len(content))
    state = "code"
    index = 0
    while index < len(content):
        if state == "code":
            if content.startswith("//", index):
                state = "line_comment"
                index += 2
                continue
            if content.startswith("/*", index):
                state = "block_comment"
                index += 2
                continue
            if content.startswith("<!--", index):
                state = "html_comment"
                index += 4
                continue
            character = content[index]
            if character in {"'", '\"', "`"}:
                state = character
                index += 1
                continue
            positions[index] = 1
            index += 1
            continue
        if state == "line_comment":
            if content[index] in "\r\n":
                state = "code"
                continue
            index += 1
            continue
        if state == "block_comment":
            if content.startswith("*/", index):
                state = "code"
                index += 2
            else:
                index += 1
            continue
        if state == "html_comment":
            if content.startswith("-->", index):
                state = "code"
                index += 3
            else:
                index += 1
            continue
        if content[index] == "\\":
            index += 2
            continue
        if content[index] == state:
            state = "code"
        index += 1
    return positions


def _read_frontend_header(repo: Path, relative_path: str) -> str | None:
    if not _relative_path(relative_path):
        return None
    repo = repo.resolve()
    path = repo / relative_path
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return None
        resolved = path.resolve()
        if not resolved.is_relative_to(repo):
            return None
        with path.open("rb") as source:
            return source.read(MAX_FRONTEND_HEADER_BYTES).decode(
                "utf-8",
                errors="ignore",
            )
    except OSError:
        return None


def _next_query_candidates(
    bundle: QueryBundle,
    pack: ContextPack,
    frozen: FrozenGoals,
    goal: ExplorationGoal,
    goal_order: int,
    suffix: str,
) -> list[ProbeCandidate]:
    candidates: list[ProbeCandidate] = []
    need_goal_by_id = {
        need.id: f"goal-need-{need.category}-{index}"
        for index, need in enumerate(pack.evidence_needs)
    }
    retained_goal_ids = {item.id for item in frozen.goals}
    for source_rank, item in enumerate(pack.next_queries, start=1):
        if need_goal_by_id.get(item.need_id) != goal.id:
            continue
        if goal.id not in retained_goal_ids:
            continue
        candidate = _candidate_from_seed(
            goal,
            goal_order,
            _Seed(item.query, "next_query", source_rank, (), True),
            suffix,
        )
        if candidate is not None:
            candidates.append(candidate)

    fallback_seeds = [*goal.subject_terms, bundle.query]
    for source_rank, value in enumerate(fallback_seeds, start=len(pack.next_queries) + 1):
        seed = _safe_seed(value)
        if seed is None:
            continue
        candidate = _candidate_from_seed(
            goal,
            goal_order,
            _Seed(seed, "next_query", source_rank, ()),
            suffix,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_from_seed(
    goal: ExplorationGoal,
    goal_order: int,
    seed: _Seed,
    suffix: str,
) -> ProbeCandidate | None:
    query = normalize_probe_text(
        seed.text if seed.complete_query else f"{seed.text} {suffix}"
    )
    if query is None:
        return None
    seed_paths = tuple(path for path in seed.seed_paths if _relative_path(path))
    return ProbeCandidate(
        query=query,
        source=seed.source,
        purpose=goal.category,
        goal_ids=(goal.id,),
        seed_paths=seed_paths[:MAX_PROBE_SEED_PATHS],
        required=goal.required,
        goal_order=goal_order,
        source_rank=seed.source_rank,
    )


def _seed_supports_goal(seed: _Seed, goal: ExplorationGoal) -> bool:
    if (
        seed.supported_categories
        and goal.category not in seed.supported_categories
    ):
        return False
    if seed.graph_test:
        return goal.category == "tests" or "test" in goal.accepted_roles
    if seed.source == "relation_target":
        if set(goal.accepted_roles).intersection(_VIEW_ROLES | _ROUTE_ROLES):
            return False
        return goal.category in _RELATION_GOAL_CATEGORIES
    if seed.source == "endpoint_or_route":
        return bool(set(goal.accepted_roles).intersection(_ROUTE_ROLES))
    if seed.source == "static_import":
        return goal.category in _IMPORT_GOAL_CATEGORIES
    if seed.source == "indexed_symbol" and set(goal.accepted_roles).intersection(
        _VIEW_ROLES
    ):
        symbol = seed.text.casefold()
        return any(term in symbol for term in ("form", "page", "template", "view"))
    return True


def _goal_suffix(goal: ExplorationGoal) -> str:
    roles = set(goal.accepted_roles)
    if roles.intersection(_VIEW_ROLES):
        return "form template view"
    if roles.intersection(_ROUTE_ROLES):
        return "route controller endpoint"
    if goal.category == "tests" or "test" in roles:
        return "test"
    if goal.category == "implementations":
        if roles and roles <= {"state_store", "store"}:
            return "store state"
        return "service implementation"
    if goal.category == "related_types":
        return "DTO type entity model"
    if goal.category == "configs_docs":
        if roles == {"doc"}:
            return "documentation readme"
        return "config properties yaml"
    if goal.category == "supporting":
        return "service store utility type"
    return "controller route entrypoint"


def _candidate_priority(candidate: ProbeCandidate) -> tuple[object, ...]:
    return (
        0 if candidate.required else 1,
        candidate.goal_order,
        -len(candidate.goal_ids),
        _SOURCE_PRIORITY[candidate.source],
        candidate.source_rank,
        candidate.query.casefold(),
        candidate.query,
    )


def _safe_seed(value: str) -> str | None:
    normalized = normalize_probe_text(value)
    if normalized is None:
        return None
    if (
        normalized.startswith(("/", "\\", "~"))
        or _WINDOWS_DRIVE_RE.match(normalized)
        or "$" in normalized
        or ".." in normalized.replace("\\", "/").split("/")
    ):
        return None
    return normalized


def _relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
    )


def _ordered_union(
    *groups: Iterable[str],
    limit: int | None = None,
) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
            if limit is not None and len(values) == limit:
                return tuple(values)
    return tuple(values)
