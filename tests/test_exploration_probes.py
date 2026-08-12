from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import exploration
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextBudget,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    EvidenceNeed,
    MissingEvidence,
    NextQuery,
    ReadinessConfidence,
)
from context_search_tool.exploration import probes
from context_search_tool.exploration.models import (
    MAX_PLANNED_PROBES,
    MAX_PROBE_SEED_PATHS,
    MAX_PROBE_TEXT_CODE_POINTS,
    ExplorationGoal,
    FrozenGoals,
    ProbeCandidate,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    QueryPlan,
    RetrievalResult,
    SourceFile,
    SymbolRef,
)
from context_search_tool.retrieval import QueryBundle
from context_search_tool.retrieval_scope import RetrievalScope, RetrievalScopeSnapshot
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    RetrievalTrace,
    TraceLimits,
    TraceQuery,
    TraceRank,
    TraceSelection,
    TraceStage,
)
from context_search_tool.sqlite_store import SQLiteStore


def _result(path: str, *, content: str = "source", start_line: int = 1) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=start_line,
        end_line=start_line + max(0, len(content.splitlines()) - 1),
        content=content,
        score=1.0,
        score_parts={"evidence_priority": 0},
        reasons=["direct"],
        followup_keywords=[],
    )


def _item(
    path: str,
    *,
    item_id: str = "item-0",
    group: str = "entrypoints",
    role: str = "entrypoint",
    content: str = "owner source",
) -> ContextItem:
    return ContextItem(
        id=item_id,
        file_path=path,
        group=group,
        role=role,
        classification_basis="path",
        source_kind="result",
        retrieval_rank=0,
        relevance_score=1.0,
        reasons=("direct",),
        matched_need_ids=(),
        excerpts=(
            ContextExcerpt(
                1,
                1,
                content,
                len(content.encode("utf-8")),
                False,
            ),
        ),
    )


def _pack(
    items: tuple[ContextItem, ...],
    *,
    needs: tuple[EvidenceNeed, ...] = (),
    next_queries: tuple[NextQuery, ...] = (),
) -> ContextPack:
    groups = {
        group: tuple(item.id for item in items if item.group == group)
        for group in (
            "entrypoints",
            "implementations",
            "related_types",
            "tests",
            "configs_docs",
            "supporting",
        )
    }
    return ContextPack(
        schema_version=2,
        status="partial",
        items=items,
        groups=groups,
        reading_order=tuple(item.id for item in items),
        evidence_needs=needs,
        missing_evidence=(),
        next_queries=next_queries,
        omissions=(),
        confidence=ReadinessConfidence("medium", ()),
        budget=ContextBudget(
            32,
            2,
            4096,
            8192,
            49152,
            65536,
            len(items),
            len(items),
            0,
            0,
            0,
            0,
            False,
        ),
    )


def _goal(
    goal_id: str,
    *,
    category: str = "tests",
    roles: tuple[str, ...] = ("test",),
    required: bool = True,
) -> ExplorationGoal:
    return ExplorationGoal(
        id=goal_id,
        kind="role_gap",
        category=category,
        accepted_roles=roles,
        subject_terms=("owner",),
        required=required,
        provenance="explicit_query_role",
        initially_satisfied=False,
    )


def _frozen(*goals: ExplorationGoal) -> FrozenGoals:
    return FrozenGoals(0, len(goals), tuple(goals), 0)


def _need_goal(
    category: str,
    subject_terms: tuple[str, ...],
    *,
    ordinal: int = 0,
) -> ExplorationGoal:
    return ExplorationGoal(
        id=f"goal-need-{category}-{ordinal}",
        kind="need",
        category=category,
        accepted_roles=(),
        subject_terms=subject_terms,
        required=True,
        provenance="context_need",
        initially_satisfied=False,
    )


def _selection(
    rank: int,
    path: str,
    chunk_id: str,
) -> TraceSelection:
    return TraceSelection(
        rank=rank,
        selection_kind="result",
        selection_reason="selected_within_result_limit",
        file_path=path,
        start_line=1,
        end_line=10,
        score=1.0,
        origin_chunk_ids=(chunk_id,),
        sources=("lexical",),
        variant_ids=("original",),
        rank_history=tuple(
            TraceRank(stage, rank, 1.0)
            for stage in (
                "ranking",
                "cohort_rerank",
                "dependency_promotion",
                "context_expansion",
                "final_selection",
            )
        ),
        adjustments=(),
        adjustment_omitted_count=0,
        reasons=("selected",),
    )


def _trace(*selections: TraceSelection, omitted: int = 0) -> RetrievalTrace:
    count = len(selections) + omitted
    return RetrievalTrace(
        schema_version=1,
        outcome="complete",
        termination_reason="completed",
        duration_ms=0,
        limits=TraceLimits(),
        query=TraceQuery(1, 1, "original_only"),
        source_counts=tuple((key, 0) for key in SOURCE_COUNT_KEYS),
        stages=(TraceStage("final_selection", count, count, count, 0),),
        final_selection_count=count,
        final_selection_omitted_count=omitted,
        final_selections=tuple(selections),
    )


def _source_file(path: str, *, language: str, metadata: dict[str, object]) -> SourceFile:
    return SourceFile(
        path=Path(path),
        language=language,
        sha256="0" * 64,
        size=100,
        mtime_ns=0,
        metadata=metadata,
    )


def _java_setup(tmp_path: Path) -> tuple[
    Path,
    SQLiteStore,
    QueryBundle,
    ContextPack,
    FrozenGoals,
    RetrievalTrace,
]:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = "src/main/java/com/example/owner/OwnerController.java"
    source_path = repo / path
    source_path.parent.mkdir(parents=True)
    source_path.write_text("class OwnerController {}", encoding="utf-8")
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-owner",
        file_path=Path(path),
        start_line=1,
        end_line=20,
        content=(
            "class OwnerController {\n"
            '  String literal = "ARBITRARY_LITERAL";\n'
            "  private static final String VIEWS_OWNER_FORM = "
            '"owners/createOrUpdateOwnerForm";\n'
            "}"
        ),
        chunk_type="symbol",
        symbols=[
            SymbolRef("OwnerController", "class", 1, 20, "java"),
            SymbolRef("VIEWS_OWNER_FORM", "constant", 3, 3, "java"),
        ],
        lexical_tokens=["owner"],
        metadata={
            "plugin": {"imports": ["ForbiddenChunkImport"]},
            "exception": "EXCEPTION_SECRET",
        },
    )
    store.replace_chunks(Path(path), [chunk])
    store.replace_signals(
        Path(path),
        [
            CodeSignal(
                "sig-endpoint",
                chunk.chunk_id,
                Path(path),
                "endpoint",
                "GET /owners/new",
                4,
                4,
                "java",
            ),
            CodeSignal(
                "sig-usage",
                chunk.chunk_id,
                Path(path),
                "usage",
                "ownerService.save",
                8,
                8,
                "java",
            ),
            CodeSignal(
                "sig-comment",
                chunk.chunk_id,
                Path(path),
                "comment",
                "COMMENT_SECRET",
                3,
                3,
                "java",
            ),
        ],
    )
    store.replace_relations(
        Path(path),
        [
            CodeRelation(
                "rel-owner-service",
                "sig-usage",
                "OwnerService.save",
                "calls",
                0.9,
            )
        ],
    )
    store.upsert_source_file(
        _source_file(
            path,
            language="java",
            metadata={
                "plugin": {
                    "imports": [
                        "com.example.owner.ApprovedImport",
                        "/private/ABSOLUTE_SECRET",
                        "$HOME.EnvironmentSecret",
                    ]
                },
                "header": "HEADER_SECRET",
            },
        )
    )
    bundle = QueryBundle(
        query="OwnerController owner flow",
        expanded_tokens=["owner"],
        results=[_result(path)],
        followup_keywords=[],
        planner=QueryPlan(
            original_query="OwnerController owner flow",
            discarded_hints=["DISCARDED_PLANNER_SECRET"],
        ),
    )
    pack = _pack(
        (_item(path),),
        needs=(
            EvidenceNeed(
                "need-test",
                "tests",
                ("owner",),
                True,
                "explicit_query",
                (),
            ),
        ),
        next_queries=(NextQuery("need-test", "owner test", "find test"),),
    )
    frozen = _frozen(
        _goal("goal-test"),
        _goal(
            "goal-implementation",
            category="implementations",
            roles=("service", "service_impl"),
            required=False,
        ),
    )
    trace = _trace(_selection(1, path, chunk.chunk_id))
    return repo, store, bundle, pack, frozen, trace


def test_planning_uses_only_approved_origin_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, store, bundle, pack, frozen, trace = _java_setup(tmp_path)
    monkeypatch.setenv("P4_ENV_SECRET", "ENVIRONMENT_SECRET")

    planned = probes.plan_probes(
        repo,
        bundle,
        trace,
        pack,
        frozen,
        store=store,
    )

    serialized = "\n".join(candidate.query for candidate in planned)
    assert planned
    assert set(candidate.source for candidate in planned) <= {
        "next_query",
        "relation_target",
        "indexed_symbol",
        "endpoint_or_route",
        "static_import",
        "path_stem",
    }
    assert "OwnerController test" in serialized
    assert "OwnerService.save" in serialized
    assert "ApprovedImport" in serialized
    for forbidden in (
        "ARBITRARY_LITERAL",
        "ForbiddenChunkImport",
        "EXCEPTION_SECRET",
        "COMMENT_SECRET",
        "DISCARDED_PLANNER_SECRET",
        "ABSOLUTE_SECRET",
        "EnvironmentSecret",
        "ENVIRONMENT_SECRET",
        "HEADER_SECRET",
    ):
        assert forbidden not in serialized
    assert all(len(candidate.query) <= MAX_PROBE_TEXT_CODE_POINTS for candidate in planned)
    assert all(len(candidate.seed_paths) <= MAX_PROBE_SEED_PATHS for candidate in planned)


def test_private_v5_probe_seeds_use_one_resolved_hop_and_reverse_tests(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize_v5()

    def chunk(chunk_id: str, path: str, content: str) -> DocumentChunk:
        return DocumentChunk(
            chunk_id,
            Path(path),
            1,
            4,
            content,
            "symbol",
            lexical_tokens=content.lower().split(),
            embedding_id=chunk_id,
        )

    def signal(
        signal_id: str,
        chunk_id: str,
        path: str,
        *,
        kind: str = "module",
        producer: str = "core_module",
        name: str | None = None,
    ) -> CodeSignal:
        return CodeSignal(
            signal_id,
            chunk_id,
            Path(path),
            kind,
            name or signal_id,
            1,
            4,
            "java",
            qualified_name=path if kind == "module" else f"demo.{signal_id}",
            producer=producer,
            recallable=kind != "module",
        )

    first = chunk("origin-first", "src/Owner.java", "class Owner")
    origin = chunk("origin-second", "src/Owner.java", "owner selected method")
    owner_module = signal(
        "owner-module",
        first.chunk_id,
        "src/Owner.java",
        name="Owner",
    )
    owner_method = signal(
        "owner-method",
        origin.chunk_id,
        "src/Owner.java",
        kind="method",
        producer="java_ast",
        name="ownerMethod",
    )
    target = chunk("target", "src/TargetService.java", "class TargetService")
    target_module = signal(
        "target-module",
        target.chunk_id,
        "src/TargetService.java",
        name="TargetService",
    )
    deep = chunk("deep", "src/DeepService.java", "class DeepService")
    deep_module = signal(
        "deep-module",
        deep.chunk_id,
        "src/DeepService.java",
        name="DeepService",
    )
    test_chunk = chunk("test", "src/test/OwnerTests.java", "class OwnerTests")
    test_module = signal(
        "test-module",
        test_chunk.chunk_id,
        "src/test/OwnerTests.java",
        name="OwnerTests",
    )

    def relation(
        relation_id: str,
        source: CodeSignal,
        target_signal: CodeSignal,
        kind: str,
    ) -> CodeRelation:
        return CodeRelation(
            relation_id,
            source.signal_id,
            target_signal.name,
            kind,
            0.9,
            target_kind=target_signal.kind,
            target_qualified_name=target_signal.qualified_name,
            target_signal_id=target_signal.signal_id,
            resolution="resolved_exact",
            producer="test_graph",
            producer_confidence=0.9,
            resolution_confidence=1.0,
        )

    store.replace_chunks(first.file_path, [first, origin])
    store.replace_graph_facts(
        first.file_path,
        [owner_module, owner_method],
        [relation("import", owner_module, target_module, "imports")],
    )
    store.replace_chunks(target.file_path, [target])
    store.replace_graph_facts(
        target.file_path,
        [target_module],
        [relation("deep", target_module, deep_module, "imports")],
    )
    store.replace_chunks(deep.file_path, [deep])
    store.replace_graph_facts(deep.file_path, [deep_module], [])
    store.replace_chunks(test_chunk.file_path, [test_chunk])
    store.replace_graph_facts(
        test_chunk.file_path,
        [test_module],
        [relation("tests", test_module, owner_module, "tests")],
    )
    store.mark_graph_ready(topology_fingerprint="a" * 64)

    path = origin.file_path.as_posix()
    bundle = QueryBundle("owner flow", ["owner"], [_result(path)], [])
    pack = _pack((_item(path),))
    frozen = _frozen(
        _goal("goal-test"),
        _goal(
            "goal-implementation",
            category="implementations",
            roles=("service", "service_impl"),
            required=False,
        ),
    )
    trace = _trace(_selection(1, path, origin.chunk_id))
    sessions: list[object] = []

    def session_factory():
        context = store.graph_read_session()
        sessions.append(context)
        return context

    planned = probes._plan_probes_v5(
        repo,
        bundle,
        trace,
        pack,
        frozen,
        store=store,
        graph_session_factory=session_factory,
    )

    serialized = "\n".join(candidate.query for candidate in planned)
    assert len(sessions) == 1
    assert "OwnerTests test" in serialized
    assert "TargetService service implementation" in serialized
    assert "DeepService" not in serialized
    assert {candidate.source for candidate in planned} >= {
        "relation_target",
        "static_import",
    }


def test_private_v5_scope_filters_excluded_graph_seed_names_and_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize_v5()

    def chunk(chunk_id: str, path: str) -> DocumentChunk:
        return DocumentChunk(
            chunk_id,
            Path(path),
            1,
            1,
            f"class {Path(path).stem}",
            "symbol",
            embedding_id=chunk_id,
        )

    def module(chunk_value: DocumentChunk) -> CodeSignal:
        return CodeSignal(
            f"signal-{chunk_value.chunk_id}",
            chunk_value.chunk_id,
            chunk_value.file_path,
            "module",
            chunk_value.file_path.stem,
            1,
            1,
            "java",
            qualified_name=chunk_value.file_path.as_posix(),
            producer="core_module",
        )

    origin = chunk("origin", "src/allowed/Owner.java")
    allowed = chunk("allowed", "src/allowed/AllowedService.java")
    blocked = chunk("blocked", "src/excluded/BlockedService.java")
    origin_signal = module(origin)
    allowed_signal = module(allowed)
    blocked_signal = module(blocked)

    def relation(target: CodeSignal) -> CodeRelation:
        return CodeRelation(
            f"relation-{target.signal_id}",
            origin_signal.signal_id,
            target.name,
            "imports",
            0.9,
            target_kind=target.kind,
            target_qualified_name=target.qualified_name,
            target_signal_id=target.signal_id,
            resolution="resolved_exact",
            producer="test_graph",
            producer_confidence=0.9,
            resolution_confidence=1.0,
        )

    store.replace_chunks(origin.file_path, [origin])
    store.replace_graph_facts(
        origin.file_path,
        [origin_signal],
        [relation(allowed_signal), relation(blocked_signal)],
    )
    for target, signal_value in (
        (allowed, allowed_signal),
        (blocked, blocked_signal),
    ):
        store.replace_chunks(target.file_path, [target])
        store.replace_graph_facts(target.file_path, [signal_value], [])
    for value in (origin, allowed, blocked):
        store.upsert_source_file(
            _source_file(
                value.file_path.as_posix(),
                language="java",
                metadata={},
            )
        )
    store.mark_graph_ready(topology_fingerprint="a" * 64)
    bundle = QueryBundle("owner service flow", ["owner", "service"], [_result(origin.file_path.as_posix())], [])
    pack = _pack((_item(origin.file_path.as_posix()),))
    frozen = _frozen(
        _goal(
            "goal-implementation",
            category="implementations",
            roles=("service", "service_impl"),
        )
    )

    planned = probes._plan_probes_v5(
        repo,
        bundle,
        _trace(_selection(1, origin.file_path.as_posix(), origin.chunk_id)),
        pack,
        frozen,
        store=store,
        scope=RetrievalScope(include_paths=("src/allowed/**",)),
    )

    serialized = "\n".join(candidate.query for candidate in planned)
    assert "AllowedService" in serialized
    assert "BlockedService" not in serialized
    assert all(
        path.startswith("src/allowed/")
        for candidate in planned
        for path in candidate.seed_paths
    )


def test_private_v5_stale_probe_fallback_stays_in_one_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize_v5()
    chunk = DocumentChunk(
        "origin",
        Path("src/Owner.txt"),
        1,
        1,
        "owner",
        "text",
        embedding_id="origin",
    )
    store.replace_chunks(chunk.file_path, [chunk])
    path = chunk.file_path.as_posix()
    bundle = QueryBundle("owner flow", ["owner"], [_result(path)], [])
    pack = _pack((_item(path),))
    frozen = _frozen(
        _goal(
            "goal-implementation",
            category="implementations",
            roles=("service", "service_impl"),
        )
    )
    trace = _trace(_selection(1, path, chunk.chunk_id))
    sessions: list[object] = []

    def session_factory():
        context = store.graph_read_session()
        sessions.append(context)
        return context

    def forbidden(*_args, **_kwargs):
        raise AssertionError("stale P4 fallback reopened SQLiteStore")

    monkeypatch.setattr(SQLiteStore, "chunks_for_ids", forbidden)
    monkeypatch.setattr(SQLiteStore, "signals_for_chunks", forbidden)
    monkeypatch.setattr(SQLiteStore, "relations_for_sources", forbidden)
    monkeypatch.setattr(SQLiteStore, "source_file_for_path", forbidden)

    planned = probes._plan_probes_v5(
        repo,
        bundle,
        trace,
        pack,
        frozen,
        store=store,
        graph_session_factory=session_factory,
    )

    assert len(sessions) == 1
    assert any(
        candidate.query == "Owner service implementation"
        and candidate.source == "path_stem"
        for candidate in planned
    )


def test_relation_symbol_route_import_path_and_next_query_priority_is_fixed(
) -> None:
    frozen = _frozen(
        _goal(
            "goal-implementation",
            category="implementations",
            roles=("service", "service_impl"),
        )
    )
    planned = probes.order_probe_candidates(
        tuple(
            ProbeCandidate(
                query=f"owner {source}",
                source=source,
                purpose="implementations",
                goal_ids=("goal-implementation",),
                seed_paths=(),
                required=True,
                goal_order=0,
                source_rank=1,
            )
            for source in reversed(
                (
                    "relation_target",
                    "indexed_symbol",
                    "endpoint_or_route",
                    "static_import",
                    "path_stem",
                    "next_query",
                )
            )
        ),
        frozen,
    )

    source_order = [candidate.source for candidate in planned]
    assert source_order == [
        "relation_target",
        "indexed_symbol",
        "endpoint_or_route",
        "static_import",
        "path_stem",
        "next_query",
    ]


@pytest.mark.parametrize(
    ("category", "seed", "expected"),
    [
        (
            "implementations",
            probes._Seed(
                "OwnerRepository",
                "relation_target",
                1,
                ("src/OwnerController.java", "src/OwnerRepository.java"),
            ),
            "OwnerRepository repository service implementation",
        ),
        (
            "related_types",
            probes._Seed(
                "Owner",
                "static_import",
                1,
                ("src/OwnerController.java", "src/Owner.java"),
                supported_categories=("related_types",),
            ),
            "Owner entity model DTO type",
        ),
        (
            "tests",
            probes._Seed(
                "OwnerControllerTests",
                "relation_target",
                1,
                ("src/OwnerController.java", "tests/OwnerControllerTests.java"),
                graph_test=True,
            ),
            "OwnerControllerTests integration test",
        ),
        (
            "configs_docs",
            probes._Seed(
                "application-mysql",
                "path_stem",
                1,
                ("src/main/resources/application-mysql.properties",),
            ),
            "application-mysql profile config properties yaml",
        ),
    ],
)
def test_missing_need_probe_combines_subject_with_typed_grounded_structure(
    category: str,
    seed: probes._Seed,
    expected: str,
) -> None:
    subject = "mysql" if category == "configs_docs" else "owner"

    candidate = probes._structured_missing_need_candidate(
        _need_goal(category, (subject,)),
        0,
        seed,
    )

    assert candidate is not None
    assert candidate.query == expected
    assert candidate.source == seed.source
    assert candidate.seed_paths == seed.seed_paths


def test_missing_need_discovery_is_bounded_path_symbol_backed_across_categories(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunks = (
        DocumentChunk(
            "owner-repository",
            Path("src/OwnerRepository.java"),
            1,
            1,
            "interface OwnerRepository",
            "symbol",
            symbols=[SymbolRef("OwnerRepository", "interface", 1, 1, "java")],
            lexical_tokens=["owner", "repository"],
        ),
        DocumentChunk(
            "owner-tests",
            Path("src/test/OwnerControllerTests.java"),
            1,
            1,
            "class OwnerControllerTests",
            "symbol",
            symbols=[SymbolRef("OwnerControllerTests", "class", 1, 1, "java")],
            lexical_tokens=["owner", "test"],
        ),
        DocumentChunk(
            "owner-type",
            Path("src/Owner.java"),
            1,
            1,
            "class Owner",
            "symbol",
            symbols=[SymbolRef("Owner", "class", 1, 1, "java")],
            lexical_tokens=["owner"],
        ),
        DocumentChunk(
            "mysql-config",
            Path("src/main/resources/application-mysql.properties"),
            1,
            1,
            "spring.datasource.url=jdbc:mysql",
            "config",
            lexical_tokens=["mysql", "datasource"],
        ),
    )
    for chunk in chunks:
        store.replace_chunks(chunk.file_path, [chunk])
    goals = (
        _need_goal("implementations", ("owner",), ordinal=0),
        _need_goal("tests", ("owner",), ordinal=1),
        _need_goal("related_types", ("owner",), ordinal=2),
        _need_goal("configs_docs", ("mysql",), ordinal=3),
    )

    seeds = probes._discover_structured_need_seeds(
        store,
        goals,
        frozenset(goal.id for goal in goals),
        RetrievalScopeSnapshot(scope=RetrievalScope()),
    )

    assert {seed.seed_paths[0] for seed in seeds} >= {
        "src/OwnerRepository.java",
        "src/test/OwnerControllerTests.java",
        "src/Owner.java",
        "src/main/resources/application-mysql.properties",
    }
    assert all(seed.source in {"indexed_symbol", "path_stem"} for seed in seeds)
    assert len(seeds) <= len(goals) * probes._STRUCTURAL_DISCOVERY_LIMIT * 2


def test_structural_discovery_filters_by_subject_before_bounded_category_scan(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    for index in range(probes._STRUCTURAL_DISCOVERY_SCAN_LIMIT + 1):
        chunk = DocumentChunk(
            f"noise-{index:02d}",
            Path(f"src/noise/ServiceImplementation{index}.java"),
            1,
            1,
            f"class ServiceImplementation{index}",
            "symbol",
            symbols=[
                SymbolRef(
                    f"ServiceImplementation{index}",
                    "class",
                    1,
                    1,
                    "java",
                )
            ],
            lexical_tokens=["service", "implementation"],
        )
        store.replace_chunks(chunk.file_path, [chunk])
    owner = DocumentChunk(
        "zz-owner-repository",
        Path("src/owner/OwnerRepository.java"),
        1,
        1,
        "interface OwnerRepository",
        "symbol",
        symbols=[SymbolRef("OwnerRepository", "interface", 1, 1, "java")],
        lexical_tokens=["owner", "repository"],
    )
    store.replace_chunks(owner.file_path, [owner])
    goal = _need_goal("implementations", ("owner",))

    seeds = probes._discover_structured_need_seeds(
        store,
        (goal,),
        frozenset((goal.id,)),
        RetrievalScopeSnapshot(scope=RetrievalScope()),
    )

    assert {seed.seed_paths[0] for seed in seeds} == {
        "src/owner/OwnerRepository.java"
    }


def test_structural_discovery_uses_category_only_to_rank_subject_matches(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    for chunk_id, path in (
        ("owner-details", "templates/owners/ownerDetails.html"),
        ("owner-form", "templates/owners/createOrUpdateOwnerForm.html"),
    ):
        chunk = DocumentChunk(
            chunk_id,
            Path(path),
            1,
            1,
            "<form></form>",
            "document",
            lexical_tokens=["owner", "form"],
        )
        store.replace_chunks(chunk.file_path, [chunk])
    goal = _goal(
        "goal-owner-view",
        category="entrypoints",
        roles=("view",),
    )

    seeds = probes._discover_structured_need_seeds(
        store,
        (goal,),
        frozenset(),
        RetrievalScopeSnapshot(scope=RetrievalScope()),
    )

    assert [seed.text for seed in seeds] == [
        "createOrUpdateOwnerForm",
        "ownerDetails",
    ]


def test_structural_discovery_rejects_test_files_for_implementation_need(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    test_chunk = DocumentChunk(
        "owner-service-tests",
        Path("src/test/OwnerServiceTests.java"),
        1,
        1,
        "class OwnerServiceTests",
        "symbol",
        symbols=[SymbolRef("OwnerServiceTests", "class", 1, 1, "java")],
        lexical_tokens=["owner", "service", "tests"],
    )
    store.replace_chunks(test_chunk.file_path, [test_chunk])
    goal = _need_goal("implementations", ("owner",))

    seeds = probes._discover_structured_need_seeds(
        store,
        (goal,),
        frozenset((goal.id,)),
        RetrievalScopeSnapshot(scope=RetrievalScope()),
    )

    assert seeds == ()


@pytest.mark.parametrize(
    ("category", "path", "symbol_name"),
    [
        ("tests", "src/Contest.java", "Contest"),
        ("implementations", "src/Serviceability.java", "Serviceability"),
        ("supporting", "src/Componentized.java", "Componentized"),
    ],
)
def test_structural_category_markers_require_identifier_boundaries(
    category: str,
    path: str,
    symbol_name: str,
) -> None:
    assert not probes._path_or_symbol_supports_category(
        category,
        path,
        None,
        symbol_name=symbol_name,
    )


def test_typescript_declaration_path_is_grounded_related_type() -> None:
    assert probes._path_or_symbol_supports_category(
        "related_types",
        "src/types/qrcode-reader.d.ts",
        None,
    )


@pytest.mark.parametrize(
    ("subjects", "seed"),
    [
        ((), probes._Seed("Owner", "path_stem", 1, ("src/Owner.java",))),
        (("所有者",), probes._Seed("Owner", "path_stem", 1, ("src/Owner.java",))),
        (("owner",), probes._Seed("Visit", "path_stem", 1, ("src/Visit.java",))),
        (("owner",), probes._Seed("owner test", "next_query", 1, ())),
    ],
    ids=(
        "no-subject",
        "non-ascii-subject",
        "unrelated-grounding",
        "user-facing-next-query",
    ),
)
def test_missing_need_probe_fails_closed_without_safe_subject_grounding(
    subjects: tuple[str, ...],
    seed: probes._Seed,
) -> None:
    assert probes._structured_missing_need_candidate(
        _need_goal("implementations", subjects),
        0,
        seed,
    ) is None


@pytest.mark.parametrize("noise", ("HomeownerRepository", "OwnershipRepository"))
def test_subject_grounding_requires_identifier_token_boundaries(noise: str) -> None:
    goal = _need_goal("implementations", ("owner",))
    assert probes._structured_missing_need_candidate(
        goal,
        0,
        probes._Seed(
            noise,
            "path_stem",
            1,
            (f"src/{noise}.java",),
        ),
    ) is None
    assert probes._structured_missing_need_candidate(
        goal,
        0,
        probes._Seed(
            "OwnerRepository",
            "path_stem",
            1,
            ("src/OwnerRepository.java",),
        ),
    ) is not None


def test_subject_grounding_preserves_explicit_postgres_aliases() -> None:
    for seed_text in ("PostgresConfiguration", "PostgreSQLConfiguration"):
        assert probes._seed_supports_subjects(
            probes._Seed(
                seed_text,
                "path_stem",
                1,
                (f"config/{seed_text}.yaml",),
            ),
            ("postgresql",),
        )


def test_structured_need_suffixes_cover_context_group_closed_set() -> None:
    assert set(probes._STRUCTURED_NEED_SUFFIXES) == set(CONTEXT_GROUPS)
    supporting = probes._structured_missing_need_candidate(
        _need_goal("supporting", ("owner",)),
        0,
        probes._Seed(
            "OwnerStore",
            "relation_target",
            1,
            ("src/OwnerStore.java",),
        ),
    )

    assert supporting is not None
    assert supporting.query == "OwnerStore service component store utility type"
    assert probes._structured_missing_need_candidate(
        _need_goal("unknown", ("owner",)),
        0,
        probes._Seed(
            "OwnerUnknown",
            "path_stem",
            1,
            ("src/OwnerUnknown.java",),
            supported_categories=("unknown",),
        ),
    ) is None


def test_overlapping_grounded_paths_combine_required_cross_category_gaps() -> None:
    implementation = _need_goal("implementations", ("QRCode",), ordinal=0)
    route = _goal(
        "goal-route",
        category="entrypoints",
        roles=("router", "route_config"),
    )
    frozen = _frozen(implementation, route)
    implementation_probe = ProbeCandidate(
        "qrcodeUtils repository service implementation",
        "static_import",
        "implementations",
        (implementation.id,),
        ("src/views/QRCodeTool.vue", "src/utils/qrcodeUtils.ts"),
        True,
        0,
        1,
    )
    route_probe = ProbeCandidate(
        "QRCodeTool route controller endpoint",
        "path_stem",
        "entrypoints",
        (route.id,),
        ("src/views/QRCodeTool.vue",),
        True,
        1,
        1,
    )

    composites = probes._grounded_required_goal_composites(
        (implementation_probe, route_probe),
        frozen,
    )

    assert len(composites) == 1
    assert composites[0].query == (
        "qrcodeUtils repository service implementation "
        "QRCodeTool route controller endpoint"
    )
    assert composites[0].goal_ids == (implementation.id, route.id)
    assert composites[0].seed_paths == (
        "src/views/QRCodeTool.vue",
        "src/utils/qrcodeUtils.ts",
    )


def test_need_planning_requires_consistent_missing_ledger_and_rejects_exact_query(
    tmp_path: Path,
) -> None:
    repo, store, bundle, pack, _, trace = _java_setup(tmp_path)
    need = EvidenceNeed(
        "need-owner-implementation",
        "implementations",
        ("owner",),
        True,
        "explicit_query",
        (),
    )
    goal = _need_goal("implementations", ("owner",))
    pack_with_need = replace(
        pack,
        evidence_needs=(need,),
        missing_evidence=(
            MissingEvidence(
                need.id,
                need.category,
                need.required,
                "required owner implementation evidence is missing from the bounded context",
            ),
        ),
    )

    planned = probes.plan_probes(
        repo,
        bundle,
        trace,
        pack_with_need,
        _frozen(goal),
        store=store,
    )

    assert planned
    assert planned[0].query == (
        "OwnerService.save repository service implementation"
    )
    assert all(candidate.source != "next_query" for candidate in planned)
    assert probes.plan_probes(
        repo,
        bundle,
        trace,
        replace(pack_with_need, missing_evidence=()),
        _frozen(goal),
        store=store,
    ) == ()
    assert probes.plan_probes(
        repo,
        replace(bundle, query="OwnerController"),
        trace,
        pack_with_need,
        _frozen(goal),
        store=store,
    ) == ()
    for exact_file_query in (
        "OwnerController.java",
        "src/main/java/com/example/owner/OwnerController.java",
    ):
        assert probes.plan_probes(
            repo,
            replace(bundle, query=exact_file_query),
            trace,
            pack_with_need,
            _frozen(goal),
            store=store,
        ) == ()


def test_multi_required_goal_composite_precedes_single_goal_candidates() -> None:
    implementation = _goal(
        "goal-implementation",
        category="implementations",
        roles=("service", "utility"),
    )
    related_type = _goal(
        "goal-type",
        category="related_types",
        roles=("type_decl",),
    )
    route = _goal(
        "goal-route",
        category="entrypoints",
        roles=("router", "route_config"),
    )
    frozen = _frozen(implementation, related_type, route)
    composite = probes._required_goal_composite(
        QueryBundle("QRCode page route service type", [], [], []),
        frozen,
    )

    assert composite is not None
    assert composite.query == (
        "QRCode page route service type service implementation "
        "DTO type entity model route controller endpoint"
    )
    assert composite.goal_ids == (
        "goal-implementation",
        "goal-type",
        "goal-route",
    )
    singles = tuple(
        ProbeCandidate(
            query=f"single {goal.id}",
            source="static_import" if index < 2 else "path_stem",
            purpose=goal.category,
            goal_ids=(goal.id,),
            seed_paths=(),
            required=True,
            goal_order=index,
            source_rank=1,
        )
        for index, goal in enumerate(frozen.goals)
    )

    assert probes.order_probe_candidates((*singles, composite), frozen)[0] == composite


def test_ready_v5_grounded_required_seeds_supersede_generic_composite() -> None:
    related_type = _goal(
        "goal-type",
        category="related_types",
        roles=("type_decl",),
    )
    route = _goal(
        "goal-route",
        category="entrypoints",
        roles=("router", "route_config"),
    )
    frozen = _frozen(related_type, route)
    bundle = QueryBundle(
        "orders page route type",
        [],
        [
            _result("src/views/OrdersView.vue"),
            _result("src/types/order.ts"),
        ],
        [],
    )
    graph_seed = probes._Seed(
        "order",
        "static_import",
        1,
        ("src/views/OrdersView.vue", "src/types/order.ts"),
    )
    route_seed = probes._Seed(
        "OrdersView",
        "path_stem",
        1,
        ("src/views/OrdersView.vue",),
    )

    assert probes._required_goal_composite_v5(
        bundle,
        frozen,
        (graph_seed, route_seed),
        ready_graph=True,
    ) is None
    assert probes._required_goal_composite_v5(
        bundle,
        frozen,
        (graph_seed,),
        ready_graph=True,
    ) is not None
    assert probes._required_goal_composite_v5(
        bundle,
        frozen,
        (route_seed,),
        ready_graph=True,
    ) is not None
    assert probes._required_goal_composite_v5(
        bundle,
        frozen,
        (graph_seed, route_seed),
        ready_graph=False,
    ) is not None
    assert probes._required_goal_composite_v5(
        QueryBundle(
            bundle.query,
            [],
            [_result("src/views/OrdersView.vue")],
            [],
        ),
        frozen,
        (graph_seed, route_seed),
        ready_graph=True,
    ) is not None


def test_view_goal_prefers_a_parser_recognized_view_constant_basename(
    tmp_path: Path,
) -> None:
    repo, store, bundle, pack, _, trace = _java_setup(tmp_path)
    frozen = _frozen(
        _goal(
            "goal-form",
            category="implementations",
            roles=("view",),
        )
    )

    planned = probes.plan_probes(repo, bundle, trace, pack, frozen, store=store)

    assert planned[0].query == "createOrUpdateOwnerForm form template view"


def test_view_constant_literal_seed_is_declaration_bound_and_repo_relative() -> None:
    symbol = SymbolRef("VIEWS_OWNER_FORM", "constant", 3, 3, "java")
    approved = DocumentChunk(
        "approved",
        Path("src/OwnerController.java"),
        1,
        4,
        (
            "class OwnerController {\n"
            '  String ignored = "ARBITRARY_LITERAL";\n'
            "  private static final String VIEWS_OWNER_FORM = "
            '"owners/createOrUpdateOwnerForm";\n'
            "}"
        ),
        "symbol",
    )

    assert probes._view_constant_literal_seed(approved, symbol) == (
        "createOrUpdateOwnerForm"
    )
    assert probes._view_constant_literal_seed(
        replace(
            approved,
            content=(
                "class OwnerController {\n"
                '  String ignored = "ARBITRARY_LITERAL";\n'
                "  // private static final String VIEWS_OWNER_FORM = "
                '"owners/commentSecret";\n'
                "}"
            ),
        ),
        symbol,
    ) is None
    assert probes._view_constant_literal_seed(
        replace(
            approved,
            content=(
                "class OwnerController {\n"
                '  String ignored = "ARBITRARY_LITERAL";\n'
                "  private static final String VIEWS_OWNER_FORM = "
                '"../outsideSecret";\n'
                "}"
            ),
        ),
        symbol,
    ) is None
    assert probes._view_constant_literal_seed(
        approved,
        replace(symbol, name="OWNER_SECRET"),
    ) is None


def test_single_required_view_goal_uses_grounded_composite_before_narrow_probe(
) -> None:
    form = _goal(
        "goal-form",
        category="implementations",
        roles=("view",),
    )
    test = _goal(
        "goal-test",
        category="tests",
        roles=("test",),
        required=False,
    )
    frozen = _frozen(form, test)
    seed = probes._Seed(
        "createOrUpdateOwnerForm",
        "indexed_symbol",
        1,
        ("src/OwnerController.java",),
    )

    composites = probes._single_required_view_composites((seed,), frozen)

    assert len(composites) == 1
    assert composites[0].query == (
        "createOrUpdateOwnerForm form template view test"
    )
    assert composites[0].goal_ids == ("goal-form", "goal-test")
    narrow = probes._candidate_from_seed(form, 0, seed, "form template view")
    assert narrow is not None
    assert probes.order_probe_candidates((*composites, narrow), frozen)[0] == (
        composites[0]
    )


def test_single_required_view_prefers_subject_compatible_template_path() -> None:
    form = _goal(
        "goal-form",
        category="entrypoints",
        roles=("view",),
    )
    test = _goal(
        "goal-test",
        category="tests",
        roles=("test",),
        required=False,
    )
    frozen = _frozen(form, test)
    method = probes._Seed(
        "initCreationForm",
        "indexed_symbol",
        1,
        ("src/OwnerController.java",),
    )
    template = probes._Seed(
        "createOrUpdateOwnerForm",
        "path_stem",
        2,
        ("src/main/resources/templates/owners/createOrUpdateOwnerForm.html",),
        supported_categories=("entrypoints",),
    )

    composites = probes._single_required_view_composites(
        (method, template),
        frozen,
    )

    assert [candidate.query for candidate in composites] == [
        "createOrUpdateOwnerForm form template view test"
    ]


def test_planning_fails_closed_on_omitted_or_missing_origin_provenance(
    tmp_path: Path,
) -> None:
    repo, store, bundle, pack, frozen, trace = _java_setup(tmp_path)
    omitted_trace = replace(
        trace,
        final_selection_count=2,
        final_selection_omitted_count=1,
    )
    assert probes.plan_probes(
        repo,
        bundle,
        omitted_trace,
        pack,
        frozen,
        store=store,
    ) == ()

    uncovered_pack = _pack(
        (_item("src/Other.java"),),
    )
    assert probes.plan_probes(
        repo,
        bundle,
        trace,
        uncovered_pack,
        frozen,
        store=store,
    ) == ()

    missing_selection = replace(
        trace.final_selections[0],
        origin_chunk_ids=("missing-chunk",),
    )
    missing_trace = replace(trace, final_selections=(missing_selection,))
    assert probes.plan_probes(
        repo,
        bundle,
        missing_trace,
        pack,
        frozen,
        store=store,
    ) == ()


def test_frontend_header_fallback_reads_at_most_three_selected_indexed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize()
    results: list[RetrievalResult] = []
    items: list[ContextItem] = []
    selections: list[TraceSelection] = []
    for index in range(4):
        view = f"src/views/Page{index}.vue"
        target = f"src/utils/tool{index}.ts"
        view_path = repo / view
        target_path = repo / target
        view_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        view_path.write_text(
            f'import tool from "../utils/tool{index}";\n' + "x" * 20_000,
            encoding="utf-8",
        )
        target_path.write_text("export default {};", encoding="utf-8")
        chunk_id = f"chunk-{index}"
        chunk = DocumentChunk(
            chunk_id,
            Path(view),
            20,
            30,
            "window without imports",
            "symbol",
        )
        store.replace_chunks(Path(view), [chunk])
        store.upsert_source_file(_source_file(view, language="vue", metadata={}))
        store.upsert_source_file(_source_file(target, language="typescript", metadata={}))
        results.append(_result(view, content="window without imports", start_line=20))
        items.append(
            _item(
                view,
                item_id=f"item-{index}",
                role="view_page",
            )
        )
        selections.append(_selection(index + 1, view, chunk_id))

    original = probes._read_frontend_header
    reads: list[str] = []

    def counted(repo_path: Path, relative_path: str) -> str | None:
        reads.append(relative_path)
        return original(repo_path, relative_path)

    monkeypatch.setattr(probes, "_read_frontend_header", counted)
    bundle = QueryBundle("owner service", [], results, [])
    planned = probes.plan_probes(
        repo,
        bundle,
        _trace(*selections),
        _pack(tuple(items)),
        _frozen(
            _goal(
                "goal-implementation",
                category="implementations",
                roles=("service", "utility"),
            )
        ),
        store=store,
    )

    assert reads == [f"src/views/Page{index}.vue" for index in range(3)]
    assert any(candidate.source == "static_import" for candidate in planned)
    assert all("tool3" not in candidate.query for candidate in planned)


def test_frontend_returned_imports_do_not_read_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    view = "src/views/Page.vue"
    target = "src/utils/tool.ts"
    (repo / view).parent.mkdir(parents=True)
    (repo / target).parent.mkdir(parents=True)
    (repo / view).write_text("source", encoding="utf-8")
    (repo / target).write_text("source", encoding="utf-8")
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    store.initialize()
    chunk = DocumentChunk("chunk", Path(view), 1, 4, "source", "symbol")
    store.replace_chunks(Path(view), [chunk])
    store.upsert_source_file(_source_file(view, language="vue", metadata={}))
    store.upsert_source_file(_source_file(target, language="typescript", metadata={}))
    bundle = QueryBundle(
        "owner service",
        [],
        [_result(view, content='import tool from "../utils/tool";\nsource')],
        [],
    )
    monkeypatch.setattr(
        probes,
        "_read_frontend_header",
        lambda *_args: pytest.fail("header fallback should not run"),
    )

    planned = probes.plan_probes(
        repo,
        bundle,
        _trace(_selection(1, view, "chunk")),
        _pack((_item(view, role="view_page"),)),
        _frozen(
            _goal(
                "goal-implementation",
                category="implementations",
                roles=("utility",),
            )
        ),
        store=store,
    )
    assert any("tool service implementation" in item.query for item in planned)


def test_p4_multiline_static_imports_ignore_comments_and_literals() -> None:
    content = """
const fake = `
import {
  COMMENT_SECRET,
} from '@/utils/template-secret'
`
/*
import {
  COMMENT_SECRET,
} from '@/utils/comment-secret'
*/
<!--
import {
  COMMENT_SECRET,
} from '@/utils/markup-secret'
-->
import single from './single'
import {
  generateQRCode,
  type QRCodeOptions,
} from '@/utils/qrcodeUtils'
"""

    assert probes._extract_probe_static_imports(content) == (
        "./single",
        "@/utils/qrcodeUtils",
    )


def test_frontend_header_read_is_bounded_regular_and_repo_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    header = repo / "src/Page.vue"
    header.parent.mkdir()
    header.write_bytes(b"a" * 20_000)
    assert len(probes._read_frontend_header(repo, "src/Page.vue").encode()) == 16_384
    assert probes._read_frontend_header(repo, "/private/Page.vue") is None
    assert probes._read_frontend_header(repo, "../Page.vue") is None

    outside = tmp_path / "outside.vue"
    outside.write_text("secret", encoding="utf-8")
    link = repo / "src/Link.vue"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert probes._read_frontend_header(repo, "src/Link.vue") is None


def test_probe_text_normalization_rejects_controls_and_trims_at_boundary() -> None:
    assert probes.normalize_probe_text(" owner   test ") == "owner test"
    assert probes.normalize_probe_text("owner\nSECRET") is None
    assert probes.normalize_probe_text("owner\x00SECRET") is None
    text = "word " * 50
    normalized = probes.normalize_probe_text(text)
    assert normalized is not None
    assert len(normalized) <= MAX_PROBE_TEXT_CODE_POINTS
    assert normalized.endswith("word")


def test_casefold_dedupe_preserves_first_provenance_and_unions_bounded_fields() -> None:
    first = ProbeCandidate(
        "Owner test",
        "indexed_symbol",
        "tests",
        ("g1",),
        ("src/Owner.java",),
        True,
        0,
        1,
    )
    duplicate = ProbeCandidate(
        "owner TEST",
        "next_query",
        "ignored",
        ("g2", "g1"),
        ("src/Test.java", "src/Other.java", "src/Fourth.java"),
        False,
        1,
        9,
    )

    deduped = probes.deduplicate_probe_candidates((first, duplicate))

    assert len(deduped) == 1
    assert deduped[0].source == "indexed_symbol"
    assert deduped[0].purpose == "tests"
    assert deduped[0].goal_ids == ("g1", "g2")
    assert deduped[0].seed_paths == (
        "src/Owner.java",
        "src/Test.java",
        "src/Other.java",
    )


def test_priority_fairness_represents_each_unsatisfied_goal_before_backfill() -> None:
    goals = _frozen(_goal("g1"), _goal("g2", category="implementations"))
    candidates = (
        ProbeCandidate("a", "relation_target", "tests", ("g1",), (), True, 0, 0),
        ProbeCandidate("b", "indexed_symbol", "tests", ("g1",), (), True, 0, 0),
        ProbeCandidate("c", "path_stem", "implementations", ("g2",), (), True, 1, 0),
    )

    ordered = probes.order_probe_candidates(candidates, goals)

    assert [candidate.query for candidate in ordered] == ["a", "c", "b"]
    assert len(ordered) <= MAX_PLANNED_PROBES


def test_stale_predicate_requires_every_candidate_goal_to_be_satisfied() -> None:
    candidate = ProbeCandidate(
        "owner test",
        "path_stem",
        "tests",
        ("g1", "g2"),
        (),
        True,
        0,
        0,
    )
    assert probes.probe_candidate_is_stale(candidate, {"g1"}) is False
    assert probes.probe_candidate_is_stale(candidate, {"g1", "g2"}) is True


def test_probe_module_does_not_read_environment_or_depend_on_package_init() -> None:
    source = Path(probes.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "getenv(" not in source
    assert exploration.__name__ == "context_search_tool.exploration"
