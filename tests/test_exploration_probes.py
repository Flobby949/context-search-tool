from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import exploration
from context_search_tool.context_pack import (
    ContextBudget,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    EvidenceNeed,
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
        content='class OwnerController { String literal = "ARBITRARY_LITERAL"; }',
        chunk_type="symbol",
        symbols=[
            SymbolRef("OwnerController", "class", 1, 20, "java"),
            SymbolRef("VIEWS_OWNER_FORM", "constant", 2, 2, "java"),
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


def test_view_goal_prefers_a_parser_recognized_view_symbol(tmp_path: Path) -> None:
    repo, store, bundle, pack, _, trace = _java_setup(tmp_path)
    frozen = _frozen(
        _goal(
            "goal-form",
            category="implementations",
            roles=("view",),
        )
    )

    planned = probes.plan_probes(repo, bundle, trace, pack, frozen, store=store)

    assert planned[0].query == "VIEWS_OWNER_FORM form template view"


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
