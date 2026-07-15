import copy
import json
from collections import Counter
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_search_tool import context_pack
from context_search_tool.config import (
    DEFAULT_CONFIG,
    IndexConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.context_pack import (
    BUDGET_EXCEEDED_ERROR,
    CONTEXT_GROUPS,
    DUPLICATE_ITEM_ERROR,
    INVALID_CLASSIFICATION_ERROR,
    INVALID_REFERENCE_ERROR,
    NON_JSON_ERROR,
    ContextBudget,
    ContextPack,
    ContextPackError,
    ContextPackOptions,
    MissingEvidence,
    NextQuery,
    ReadinessConfidence,
    resolve_context_pack_options,
)
from context_search_tool.context_pack import builder as context_pack_v2_builder
from context_search_tool.context_pack import models as context_pack_v2_models
from context_search_tool.context_pack import roles as context_pack_v2_roles
from context_search_tool.context_pack import serialization as context_pack_v2_serialization
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.identifier_intent import infer_identifier_intent
from context_search_tool.query_intent import infer_query_intent
from context_search_tool.retrieval import QueryBundle
from context_search_tool.tokenizer import tokenize_query


class _RaisingEquality:
    def __eq__(self, other: object) -> bool:
        raise ValueError("comparison must not run")


class _StringSubclass(str):
    pass


class _UnhashableString(str):
    __hash__ = None


class _TupleSubclass(tuple):
    pass


class _ListSubclass(list):
    pass


class _DictSubclass(dict):
    pass


def result(
    path: str,
    *,
    content: str = "source",
    evidence_priority: float | None = 0.0,
) -> RetrievalResult:
    score_parts = {}
    if evidence_priority is not None:
        score_parts["evidence_priority"] = evidence_priority
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=2,
        content=content,
        score=1.0,
        score_parts=score_parts,
        reasons=["fixture"],
        followup_keywords=[],
    )


def anchor(path: str, kind: str, *, content: str = "anchor") -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=2,
        content=content,
        score=0.5,
        score_parts={},
        reasons=["fixture anchor"],
        anchor_kind=kind,
    )


def options(max_results: int = 12, max_anchors: int = 4) -> ContextPackOptions:
    return ContextPackOptions(
        max_results=max_results,
        max_evidence_anchors=max_anchors,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=200_000,
    )


def query_bundle(
    results: list[RetrievalResult] | None = None,
    *,
    query: str = "fixture query",
    expanded_tokens: list[str] | None = None,
    evidence_anchors: list[EvidenceAnchor] | None = None,
    summary: RetrievalSummary | None = None,
    planner: QueryPlan | None = None,
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=list(expanded_tokens or ()),
        results=list(results or ()),
        followup_keywords=[],
        summary=summary if summary is not None else RetrievalSummary(),
        planner=planner if planner is not None else QueryPlan.disabled_default(),
        evidence_anchors=list(evidence_anchors or ()),
    )


def missing_categories(pack: ContextPack, *, required: bool) -> tuple[str, ...]:
    return tuple(
        evidence.category
        for evidence in pack.missing_evidence
        if evidence.required is required
    )


def one_result_per_context_group() -> list[RetrievalResult]:
    return [
        result("src/main/controller/AppController.java"),
        result("src/services/app.py"),
        result("src/main/dto/AppDto.java"),
        result("tests/test_app.py"),
        result("README.md"),
        result("src/plain.py"),
    ]


def test_resolve_context_pack_options_uses_effective_config_window() -> None:
    config = ToolConfig(
        index=IndexConfig(max_full_file_bytes=123_456),
        retrieval=RetrievalConfig(
            final_top_k=12,
            context_before_lines=8,
            context_after_lines=12,
        ),
    )

    options = resolve_context_pack_options(
        config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=4,
    )

    assert options == ContextPackOptions(
        max_results=12,
        max_evidence_anchors=4,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=123_456,
    )


def test_resolve_context_pack_options_clamps_negative_config_window() -> None:
    config = ToolConfig(
        retrieval=RetrievalConfig(
            context_before_lines=-3,
            context_after_lines=-7,
        ),
    )

    options = resolve_context_pack_options(
        config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0


def test_resolve_context_pack_options_applies_symmetric_override() -> None:
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=0,
        full_file=True,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0
    assert options.full_file is True


def test_resolve_context_pack_options_clamps_negative_symmetric_override() -> None:
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=-5,
        full_file=False,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0


@pytest.mark.parametrize(
    ("path", "content", "expected_group", "expected_role"),
    [
        ("tests/test_app.py", "source", "tests", "test"),
        ("deploy/docker-compose.yml", "source", "configs_docs", "deployment_config"),
        ("examples/settings.yaml", "source", "configs_docs", "config_example"),
        ("config/settings.yaml", "source", "configs_docs", "runtime_config"),
        ("vite.config.ts", "source", "configs_docs", "config"),
        ("README.md", "source", "configs_docs", "doc"),
        ("src/main/controller/AppController.java", "source", "entrypoints", "entrypoint"),
        ("server/router/routes.py", "source", "entrypoints", "router"),
        ("src/commands/run.rs", "source", "entrypoints", "command"),
        ("src/handlers/upload.go", "source", "entrypoints", "handler"),
        ("server/views/home.py", "source", "entrypoints", "view"),
        (
            "src/main/service/impl/AppServiceImpl.java",
            "source",
            "implementations",
            "service_impl",
        ),
        ("src/main/service/PageQueryExecutor.java", "source", "implementations", "executor"),
        ("src/engine.rs", "source", "implementations", "engine"),
        ("src/middleware/auth.py", "source", "implementations", "middleware"),
        ("src/storage/local.py", "source", "implementations", "storage"),
        ("server/services/api.py", "source", "implementations", "service"),
        ("src/repository/user.py", "source", "implementations", "repository"),
        ("src/adapters/github.py", "source", "implementations", "source_adapter"),
        ("backend/state/session.py", "source", "implementations", "state_store"),
        ("backend/hooks/use_auth.py", "source", "implementations", "composable"),
        ("src/jobs/task_scheduler.py", "source", "implementations", "scheduler"),
        ("src/main/dto/AppDto.java", "source", "related_types", "data_type"),
        (
            "src/main/service/AppService.java",
            "interface AppService {}",
            "related_types",
            "service_interface",
        ),
        ("generated/output.json", "source", "supporting", "generated_output"),
        ("Cargo.lock", "source", "supporting", "lockfile"),
    ],
)
def test_build_context_pack_classifies_every_closed_path_role(
    path: str,
    content: str,
    expected_group: str,
    expected_role: str,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result(path, content=content)]),
        options(),
    )

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == (
        expected_group,
        expected_role,
        "path_role",
    )


@pytest.mark.parametrize(
    ("path", "expected_group", "expected_role"),
    [
        ("src/router/index.ts", "entrypoints", "route_config"),
        ("src/views/Home.vue", "entrypoints", "view_page"),
        ("src/layouts/MainLayout.vue", "entrypoints", "layout_component"),
        ("src/services/api.ts", "implementations", "service"),
        ("src/utils/format.ts", "implementations", "utility"),
        ("src/stores/app.ts", "implementations", "store"),
        ("src/components/Widget.tsx", "implementations", "shared_component"),
        ("src/types/app.d.ts", "related_types", "type_decl"),
        ("bun.lockb", "supporting", "lockfile"),
        ("temp/buildProbe.js", "supporting", "scratch_temp"),
    ],
)
def test_build_context_pack_classifies_every_closed_frontend_role(
    path: str,
    expected_group: str,
    expected_role: str,
) -> None:
    pack = context_pack.build_context_pack(query_bundle([result(path)]), options())

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == (
        expected_group,
        expected_role,
        "frontend_role",
    )


@pytest.mark.parametrize(
    ("path", "expected_role"),
    [
        ("tests/test_app.py", "test"),
        ("deploy/docker-compose.yml", "deployment_config"),
        ("examples/settings.yaml", "config_example"),
        ("config/settings.yaml", "runtime_config"),
        ("src/router/vite.config.ts", "config"),
        ("README.md", "doc"),
    ],
)
def test_generic_path_roles_take_precedence_without_frontend_classification(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected_role: str,
) -> None:
    def fail_frontend_classification(_: str) -> None:
        pytest.fail("frontend classification must not run for generic path roles")

    monkeypatch.setattr(
        context_pack,
        "classify_frontend_role",
        fail_frontend_classification,
    )

    pack = context_pack.build_context_pack(query_bundle([result(path)]), options())

    item = pack.items[0]
    assert (item.role, item.classification_basis) == (expected_role, "path_role")


@pytest.mark.parametrize(
    ("path", "expected_role"),
    [
        ("src/plain.py", "source"),
        ("src/components/Widget.py", "component"),
    ],
)
def test_source_and_component_use_narrow_fallbacks(path: str, expected_role: str) -> None:
    pack = context_pack.build_context_pack(query_bundle([result(path)]), options())

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == (
        "supporting",
        expected_role,
        "fallback",
    )


def test_unknown_path_role_is_rejected_before_known_frontend_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        context_pack,
        "classify_path_role",
        lambda path, content: SimpleNamespace(name="unknown"),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            query_bundle([result("src/router/index.ts")]),
            options(),
        )

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


def test_unknown_frontend_role_is_rejected_for_known_source_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        context_pack,
        "classify_frontend_role",
        lambda path: SimpleNamespace(name="unknown"),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            query_bundle([result("src/plain.py")]),
            options(),
        )

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


@pytest.mark.parametrize(
    ("path", "summary", "expected"),
    [
        (
            "src/Checkout.py",
            RetrievalSummary(entry_points=["CHECKOUT"]),
            ("entrypoints", "summary_entrypoint", "retrieval_summary"),
        ),
        (
            "src/components/Widget.py",
            RetrievalSummary(entry_points=["widget"]),
            ("entrypoints", "summary_entrypoint", "retrieval_summary"),
        ),
        (
            "src/Worker.py",
            RetrievalSummary(implementation=["worker"]),
            ("implementations", "summary_implementation", "retrieval_summary"),
        ),
        (
            "src/Worker.py",
            RetrievalSummary(implementation=["WORKER.run"]),
            ("implementations", "summary_implementation", "retrieval_summary"),
        ),
        (
            "src/Dto.py",
            RetrievalSummary(related_types=["dto"]),
            ("related_types", "summary_related_type", "retrieval_summary"),
        ),
    ],
)
def test_summary_ownership_uses_case_insensitive_narrow_stem_matching(
    path: str,
    summary: RetrievalSummary,
    expected: tuple[str, str, str],
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result(path)], summary=summary),
        options(),
    )

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == expected


def test_summary_ownership_collision_prefers_entrypoint_then_implementation() -> None:
    all_matches = RetrievalSummary(
        entry_points=["owner"],
        implementation=["owner.run"],
        related_types=["OWNER"],
    )
    implementation_and_type = RetrievalSummary(
        implementation=["owner.run"],
        related_types=["OWNER"],
    )

    entrypoint_pack = context_pack.build_context_pack(
        query_bundle([result("src/Owner.py")], summary=all_matches),
        options(),
    )
    implementation_pack = context_pack.build_context_pack(
        query_bundle([result("src/Owner.py")], summary=implementation_and_type),
        options(),
    )

    assert entrypoint_pack.items[0].role == "summary_entrypoint"
    assert implementation_pack.items[0].role == "summary_implementation"


@pytest.mark.parametrize(
    "summary",
    [
        RetrievalSummary(entry_points=["Plain.run"]),
        RetrievalSummary(implementation=["NotPlain.run"]),
        RetrievalSummary(implementation=["PlainExtra.run"]),
        RetrievalSummary(related_types=["Plain.Dto"]),
    ],
)
def test_summary_ownership_rejects_broad_or_partial_stem_matches(
    summary: RetrievalSummary,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/Plain.py")], summary=summary),
        options(),
    )

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == (
        "supporting",
        "source",
        "fallback",
    )


def test_summary_ownership_does_not_override_a_mapped_path_role() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/services/Owner.py")],
            summary=RetrievalSummary(entry_points=["owner"]),
        ),
        options(),
    )

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == (
        "implementations",
        "service",
        "path_role",
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("readme", ("configs_docs", "readme", "anchor_kind")),
        ("risks", ("configs_docs", "risks", "anchor_kind")),
        ("pom", ("configs_docs", "pom", "anchor_kind")),
        ("config", ("supporting", "evidence_anchor", "fallback")),
        ("", ("supporting", "evidence_anchor", "fallback")),
    ],
)
def test_evidence_anchor_classification_uses_only_anchor_kind(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    expected: tuple[str, str, str],
) -> None:
    def fail_result_classifier(*args: object) -> None:
        pytest.fail("result classifiers must not run for evidence anchors")

    monkeypatch.setattr(context_pack, "classify_path_role", fail_result_classifier)
    monkeypatch.setattr(context_pack, "classify_frontend_role", fail_result_classifier)

    pack = context_pack.build_context_pack(
        query_bundle(evidence_anchors=[anchor("src/router/index.ts", kind)]),
        options(),
    )

    item = pack.items[0]
    assert (item.group, item.role, item.classification_basis) == expected


def test_build_context_pack_preserves_source_shape_and_fixed_group_order() -> None:
    raw_results = [
        replace(result("src/plain.py"), start_line=3, end_line=9),
        replace(
            result("src/main/controller/AppController.java"),
            start_line=10,
            end_line=20,
        ),
    ]
    raw_anchors = [
        replace(anchor("docs/README.md", "readme"), start_line=4, end_line=6),
        replace(anchor("notes/other.txt", "", content="other"), start_line=7, end_line=8),
    ]
    bundle = query_bundle(raw_results, evidence_anchors=raw_anchors)

    pack = context_pack.build_context_pack(bundle, options())

    assert [
        (
            item.id,
            item.source,
            item.source_index,
            item.file_path,
            item.start_line,
            item.end_line,
        )
        for item in pack.items
    ] == [
        ("result:0", "result", 0, "src/plain.py", 3, 9),
        (
            "result:1",
            "result",
            1,
            "src/main/controller/AppController.java",
            10,
            20,
        ),
        ("anchor:0", "anchor", 0, "docs/README.md", 4, 6),
        ("anchor:1", "anchor", 1, "notes/other.txt", 7, 8),
    ]
    assert tuple(pack.groups) == CONTEXT_GROUPS
    assert pack.groups == {
        "entrypoints": ("result:1",),
        "implementations": (),
        "related_types": (),
        "tests": (),
        "configs_docs": ("anchor:0",),
        "supporting": ("result:0", "anchor:1"),
    }
    assert pack.reading_order == (
        "result:1",
        "anchor:0",
        "result:0",
        "anchor:1",
    )
    item_ids = [item.id for item in pack.items]
    assert Counter(item_id for ids in pack.groups.values() for item_id in ids) == Counter(item_ids)
    assert Counter(pack.reading_order) == Counter(item_ids)


def test_groups_filter_source_order_with_results_before_anchors() -> None:
    bundle = query_bundle(
        [
            result("README.md"),
            result("src/first.py"),
            result("docs/setup.md"),
            result("src/second.py"),
        ],
        evidence_anchors=[
            anchor("a", "readme"),
            anchor("b", "other"),
            anchor("c", "risks"),
            anchor("d", "other"),
        ],
    )

    pack = context_pack.build_context_pack(bundle, options(max_anchors=4))

    assert pack.groups["configs_docs"] == (
        "result:0",
        "result:2",
        "anchor:0",
        "anchor:2",
    )
    assert pack.groups["supporting"] == (
        "result:1",
        "result:3",
        "anchor:1",
        "anchor:3",
    )
    assert pack.reading_order == tuple(
        item_id
        for group in CONTEXT_GROUPS
        for item_id in pack.groups[group]
    )


def test_empty_and_nonempty_packs_without_expected_groups_use_final_state() -> None:
    empty_pack = context_pack.build_context_pack(query_bundle(), options())
    ready_pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")]),
        options(),
    )

    assert empty_pack.status == "empty"
    assert empty_pack.missing_evidence == (
        MissingEvidence(
            category="results",
            required=True,
            reason="no result or evidence anchor is present in the bounded result set",
        ),
    )
    assert empty_pack.next_queries == ()
    assert empty_pack.confidence == ReadinessConfidence(
        level="none",
        reasons=("no result or evidence anchor is present",),
    )
    assert ready_pack.status == "ready"
    assert ready_pack.missing_evidence == ()
    assert ready_pack.next_queries == ()
    assert ready_pack.confidence == ReadinessConfidence(
        level="high",
        reasons=(
            "all required evidence groups are present",
            "protected original direct evidence is present",
        ),
    )


@pytest.mark.parametrize(
    ("query", "expected_required"),
    [
        ("controller route", ("entrypoints",)),
        ("service repository", ("implementations",)),
        ("Pinia store component", ("implementations",)),
        ("WorkspaceDto", ("related_types",)),
        ("workspace test file", ("tests",)),
        ("Docker deployment config file", ("configs_docs",)),
        (
            "configuration page save logic",
            ("entrypoints", "implementations"),
        ),
        ("form save", ()),
    ],
)
def test_build_context_pack_derives_explicit_required_groups_from_raw_query(
    query: str,
    expected_required: tuple[str, ...],
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query=query),
        options(),
    )

    assert missing_categories(pack, required=True) == expected_required


@pytest.mark.parametrize(
    ("role_hint", "expected_group"),
    [
        ("controller", "entrypoints"),
        ("router", "entrypoints"),
        ("command", "entrypoints"),
        ("view", "entrypoints"),
        ("page", "entrypoints"),
        ("store", "implementations"),
        ("composable", "implementations"),
        ("hook", "implementations"),
        ("service", "implementations"),
        ("handler", "implementations"),
        ("middleware", "implementations"),
        ("repository", "implementations"),
        ("source", "implementations"),
        ("adapter", "implementations"),
        ("client", "implementations"),
        ("storage", "implementations"),
        ("component", "implementations"),
        ("engine", "implementations"),
        ("dto", "related_types"),
        ("entity", "related_types"),
        ("model", "related_types"),
        ("type", "related_types"),
    ],
)
def test_build_context_pack_admits_each_identifier_role_hint(
    role_hint: str,
    expected_group: str,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query=f"find {role_hint}"),
        options(),
    )

    assert missing_categories(pack, required=True) == (expected_group,)


def test_build_context_pack_deduplicates_surface_and_identifier_requirements() -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query="controller router"),
        options(),
    )

    assert missing_categories(pack, required=True) == ("entrypoints",)
    assert sum(
        evidence.category == "entrypoints" and evidence.required
        for evidence in pack.missing_evidence
    ) == 1


def test_build_context_pack_infers_each_raw_query_intent_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_calls: list[tuple[str, list[str]]] = []
    identifier_calls: list[tuple[str, list[str]]] = []

    def capture_query_intent(query: str, tokens: list[str]):
        query_calls.append((query, tokens))
        return infer_query_intent(query, tokens)

    def capture_identifier_intent(query: str, tokens: list[str]):
        identifier_calls.append((query, tokens))
        return infer_identifier_intent(query, tokens)

    monkeypatch.setattr(
        context_pack,
        "infer_query_intent",
        capture_query_intent,
        raising=False,
    )
    monkeypatch.setattr(
        context_pack,
        "infer_identifier_intent",
        capture_identifier_intent,
        raising=False,
    )
    bundle = query_bundle(
        [result("src/main/controller/AppController.java")],
        query="WorkspaceController",
        expanded_tokens=["controller", "service", "dto"],
    )

    context_pack.build_context_pack(bundle, options())

    assert query_calls == [(bundle.query, bundle.query.split())]
    assert identifier_calls == [(bundle.query, tokenize_query(bundle.query))]


def test_generated_tokens_do_not_create_required_or_recommended_groups() -> None:
    planner = QueryPlan(
        original_query="WorkspaceController",
        rewritten_queries=["controller service dto"],
        grep_keywords=["service", "dto"],
        symbol_hints=["ControllerServiceDto"],
        discarded_hints=["service repository dto"],
        intent="symbol_lookup",
        status="ok",
    )
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/main/controller/WorkspaceController.java")],
            query="WorkspaceController",
            expanded_tokens=["controller", "service", "dto"],
            planner=planner,
        ),
        options(),
    )

    assert pack.status == "ready"
    assert pack.missing_evidence == ()


def test_identifier_and_file_hints_without_roles_do_not_promote_groups() -> None:
    planner = QueryPlan(
        original_query="OpaqueWidget src/opaque.py",
        intent="symbol_lookup",
        status="ok",
    )
    supporting_pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="OpaqueWidget src/opaque.py",
            planner=planner,
        ),
        options(),
    )
    all_groups_pack = context_pack.build_context_pack(
        query_bundle(
            one_result_per_context_group(),
            query="OpaqueWidget src/opaque.py",
            planner=planner,
        ),
        options(),
    )

    assert missing_categories(supporting_pack, required=True) == ()
    assert all_groups_pack.missing_evidence == ()
    assert all_groups_pack.reading_order == tuple(
        f"result:{index}" for index in range(6)
    )


def test_configuration_page_logic_does_not_require_or_promote_configs_docs() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            one_result_per_context_group(),
            query="configuration page save logic",
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == ()
    assert pack.reading_order == tuple(f"result:{index}" for index in range(6))


@pytest.mark.parametrize(
    ("planner_intent", "expected_required", "expected_recommended"),
    [
        (
            "feature_lookup",
            ("entrypoints", "implementations"),
            ("related_types", "tests"),
        ),
        (
            "data_flow",
            ("entrypoints", "implementations"),
            ("related_types", "tests"),
        ),
        (
            "bug_trace",
            ("entrypoints", "implementations"),
            ("related_types", "tests"),
        ),
        (
            "endpoint_lookup",
            ("entrypoints",),
            ("implementations", "tests"),
        ),
        ("symbol_lookup", (), ()),
        ("unknown", (), ()),
    ],
)
def test_successful_planner_intent_derives_required_and_recommended_groups(
    planner_intent: str,
    expected_required: tuple[str, ...],
    expected_recommended: tuple[str, ...],
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent=planner_intent,
                status="ok",
            ),
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == expected_required
    assert missing_categories(pack, required=False) == expected_recommended


@pytest.mark.parametrize("status", ["disabled", "fallback"])
def test_unsuccessful_planner_status_contributes_no_groups(status: str) -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent="feature_lookup",
                status=status,
            ),
        ),
        options(),
    )

    assert pack.missing_evidence == ()


def test_explicit_required_suppresses_only_planner_required_fallback() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="controller",
            planner=QueryPlan(
                original_query="controller",
                intent="feature_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == ("entrypoints",)
    assert missing_categories(pack, required=False) == (
        "implementations",
        "related_types",
        "tests",
    )


def test_planner_only_required_groups_do_not_promote_reading_order() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            one_result_per_context_group(),
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent="bug_trace",
                status="ok",
            ),
        ),
        options(),
    )

    assert pack.reading_order == tuple(f"result:{index}" for index in range(6))


@pytest.mark.parametrize(
    "source_path",
    [
        "src/main/controller/AppController.java",
        "src/services/app.py",
    ],
)
def test_successful_non_unknown_planner_prevents_present_group_fallback(
    source_path: str,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result(source_path)],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent="symbol_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert pack.missing_evidence == ()


@pytest.mark.parametrize(
    ("status", "intent"),
    [
        ("disabled", "feature_lookup"),
        ("fallback", "feature_lookup"),
        ("ok", "unknown"),
    ],
)
@pytest.mark.parametrize(
    ("source_path", "expected_recommended"),
    [
        ("src/main/controller/AppController.java", "implementations"),
        ("src/services/app.py", "entrypoints"),
    ],
)
def test_no_successful_non_unknown_planner_allows_present_group_fallback(
    status: str,
    intent: str,
    source_path: str,
    expected_recommended: str,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result(source_path)],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent=intent,
                status=status,
            ),
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == ()
    assert missing_categories(pack, required=False) == (expected_recommended,)


def test_recommendations_remove_required_groups_and_exclude_supporting() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="service",
            planner=QueryPlan(
                original_query="service",
                intent="endpoint_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == ("implementations",)
    assert missing_categories(pack, required=False) == ("tests",)
    assert all(
        evidence.category != "supporting" for evidence in pack.missing_evidence
    )


def test_missing_required_evidence_makes_nonempty_pack_partial() -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query="service"),
        options(),
    )

    assert pack.status == "partial"
    assert pack.missing_evidence == (
        MissingEvidence(
            category="implementations",
            required=True,
            reason=(
                "required evidence for implementations is missing from the "
                "bounded result set"
            ),
        ),
    )


def test_missing_recommended_evidence_keeps_nonempty_pack_ready() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/main/controller/AppController.java")],
            query="controller",
        ),
        options(),
    )

    assert pack.status == "ready"
    assert pack.missing_evidence == (
        MissingEvidence(
            category="implementations",
            required=False,
            reason=(
                "recommended evidence for implementations is missing from the "
                "bounded result set"
            ),
        ),
        MissingEvidence(
            category="tests",
            required=False,
            reason=(
                "recommended evidence for tests is missing from the bounded "
                "result set"
            ),
        ),
    )


def test_missing_evidence_orders_required_before_recommended_by_fixed_group() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="service controller",
            planner=QueryPlan(
                original_query="service controller",
                intent="feature_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert tuple(
        (evidence.category, evidence.required)
        for evidence in pack.missing_evidence
    ) == (
        ("entrypoints", True),
        ("implementations", True),
        ("related_types", False),
        ("tests", False),
    )


def test_empty_pack_does_not_apply_structural_evidence_gaps() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            query="controller",
            planner=QueryPlan(
                original_query="controller",
                intent="feature_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert pack.status == "empty"
    assert pack.items == ()
    assert pack.groups == {group: () for group in CONTEXT_GROUPS}
    assert pack.missing_evidence == (
        MissingEvidence(
            category="results",
            required=True,
            reason="no result or evidence anchor is present in the bounded result set",
        ),
    )
    assert pack.reading_order == ()
    assert pack.next_queries == ()
    assert pack.confidence == ReadinessConfidence(
        level="none",
        reasons=("no result or evidence anchor is present",),
    )
    assert pack.budget.included_results == 0
    assert pack.budget.included_evidence_anchors == 0
    assert pack.budget.content_bytes == 0


_NEXT_QUERY_CATEGORY_CASES = [
    pytest.param(
        "controller",
        ("implementation", "related_types", "entry_points"),
        "find_entrypoints",
        "controller route entrypoint",
        id="entrypoints",
    ),
    pytest.param(
        "service",
        ("entry_points", "related_types", "implementation"),
        "find_implementations",
        "service implementation",
        id="implementations",
    ),
    pytest.param(
        "WorkspaceDto",
        ("implementation", "entry_points", "related_types"),
        "find_related_types",
        "dto model type",
        id="related-types",
    ),
    pytest.param(
        "workspace test file",
        ("implementation", "entry_points", "related_types"),
        "find_tests",
        "test",
        id="tests",
    ),
    pytest.param(
        "Docker deployment config file",
        ("entry_points", "implementation", "related_types"),
        "find_configs_docs",
        "config documentation",
        id="configs-docs",
    ),
]


@pytest.mark.parametrize(
    ("query", "priorities", "purpose", "suffix"),
    _NEXT_QUERY_CATEGORY_CASES,
)
def test_next_query_prefers_priority_two_when_one_is_empty_and_three_has_seed(
    query: str,
    priorities: tuple[str, str, str],
    purpose: str,
    suffix: str,
) -> None:
    first_priority, second_priority, third_priority = priorities
    summary = RetrievalSummary()
    setattr(summary, first_priority, [])
    setattr(summary, second_priority, ["\t", "  Priority2\u2003Seed  ", "Ignored"])
    setattr(summary, third_priority, ["Priority3Seed"])

    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query=query, summary=summary),
        options(),
    )

    suggestion = next(item for item in pack.next_queries if item.purpose == purpose)
    assert suggestion.query == f"Priority2 Seed {suffix}"
    assert suggestion.reason == next(
        item.reason
        for item in pack.missing_evidence
        if item.category
        == {
            "find_entrypoints": "entrypoints",
            "find_implementations": "implementations",
            "find_related_types": "related_types",
            "find_tests": "tests",
            "find_configs_docs": "configs_docs",
        }[purpose]
    )


@pytest.mark.parametrize(
    ("query", "priorities", "purpose", "suffix"),
    _NEXT_QUERY_CATEGORY_CASES,
)
def test_next_query_prefers_priority_one_when_all_summary_priorities_have_seeds(
    query: str,
    priorities: tuple[str, str, str],
    purpose: str,
    suffix: str,
) -> None:
    summary = RetrievalSummary()
    for index, field_name in enumerate(priorities, start=1):
        setattr(summary, field_name, [f"Priority{index}Seed"])

    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query=query, summary=summary),
        options(),
    )

    suggestion = next(item for item in pack.next_queries if item.purpose == purpose)
    assert suggestion.query == f"Priority1Seed {suffix}"


@pytest.mark.parametrize(
    ("query", "priorities", "purpose", "suffix"),
    _NEXT_QUERY_CATEGORY_CASES,
)
def test_next_query_uses_priority_three_when_first_two_have_no_safe_seed(
    query: str,
    priorities: tuple[str, str, str],
    purpose: str,
    suffix: str,
) -> None:
    first_priority, second_priority, third_priority = priorities
    summary = RetrievalSummary()
    setattr(summary, first_priority, [" \t "])
    setattr(summary, second_priority, ["\n"])
    setattr(summary, third_priority, ["Priority3Seed"])

    pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")], query=query, summary=summary),
        options(),
    )

    suggestion = next(item for item in pack.next_queries if item.purpose == purpose)
    assert suggestion.query == f"Priority3Seed {suffix}"


def test_next_query_falls_back_to_first_ranked_result_stem() -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("src/FallbackSeed.py")], query="service"),
        options(),
    )

    assert pack.next_queries == (
        NextQuery(
            query="FallbackSeed service implementation",
            purpose="find_implementations",
            reason=pack.missing_evidence[0].reason,
        ),
    )


def test_next_query_falls_back_to_original_query_for_anchor_only_bundle() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            query="  controller\u00a0route  ",
            evidence_anchors=[anchor("notes/other.txt", "other")],
        ),
        options(),
    )

    assert pack.status == "partial"
    assert pack.next_queries[0].query == (
        "controller route controller route entrypoint"
    )
    assert all("other" not in item.query for item in pack.next_queries)


def test_next_query_collapses_all_unicode_whitespace() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="service",
            summary=RetrievalSummary(
                entry_points=["\u2002Alpha\n\tBeta\u00a0Gamma\u2003"],
            ),
        ),
        options(),
    )

    assert pack.next_queries[0].query == "Alpha Beta Gamma service implementation"


def test_next_query_omits_empty_normalized_fallback_seed() -> None:
    pack = context_pack.build_context_pack(
        query_bundle([result("   ")], query="service"),
        options(),
    )

    assert missing_categories(pack, required=True) == ("implementations",)
    assert pack.next_queries == ()


def test_next_query_deduplicates_without_trying_an_alternate_seed() -> None:
    bundle = query_bundle(
        [result("src/plain.py")],
        summary=RetrievalSummary(entry_points=["  Same\tSeed  ", "Alternate"]),
    )
    missing = (
        MissingEvidence("implementations", True, "first reason"),
        MissingEvidence("implementations", False, "second reason"),
    )

    suggestions = context_pack._build_next_queries(bundle, missing)

    assert suggestions == (
        NextQuery(
            query="Same Seed service implementation",
            purpose="find_implementations",
            reason="first reason",
        ),
    )
    assert all("Alternate" not in item.query for item in suggestions)


def test_next_query_dedupe_key_casefolds_and_normalizes_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeds = iter(("Same Seed", "same\tseed"))
    monkeypatch.setattr(
        context_pack,
        "_select_next_query_seed",
        lambda bundle, fields: next(seeds),
    )
    missing = (
        MissingEvidence("implementations", True, "first reason"),
        MissingEvidence("implementations", False, "second reason"),
    )

    suggestions = context_pack._build_next_queries(query_bundle(), missing)

    assert suggestions == (
        NextQuery(
            query="Same Seed service implementation",
            purpose="find_implementations",
            reason="first reason",
        ),
    )


def test_next_queries_stop_after_three_unique_suggestions_in_missing_order() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/Seed.py")],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent="feature_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert tuple(item.purpose for item in pack.next_queries) == (
        "find_entrypoints",
        "find_implementations",
        "find_related_types",
    )
    assert tuple(item.reason for item in pack.next_queries) == tuple(
        item.reason for item in pack.missing_evidence[:3]
    )


def test_next_query_preserves_full_suffix_at_exact_160_code_point_bound() -> None:
    suffix = "service implementation"
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="service",
            summary=RetrievalSummary(entry_points=["界" * 500]),
        ),
        options(),
    )

    query = pack.next_queries[0].query
    assert len(query) == 160
    assert query.endswith(f" {suffix}")


def test_results_and_supporting_missing_categories_have_no_query_rule() -> None:
    bundle = query_bundle([result("src/Seed.py")])

    suggestions = context_pack._build_next_queries(
        bundle,
        (
            MissingEvidence("results", True, "results reason"),
            MissingEvidence("supporting", True, "supporting reason"),
        ),
    )

    assert suggestions == ()


def test_next_queries_ignore_generated_and_discarded_retrieval_hints() -> None:
    secret_values = {
        "EXPANDED_SECRET",
        "FOLLOWUP_SECRET",
        "REWRITE_SECRET",
        "GREP_SECRET",
        "SYMBOL_SECRET",
        "DISCARDED_SECRET",
    }
    bundle = query_bundle(
        [result("src/SafeSeed.py")],
        query="service",
        expanded_tokens=["EXPANDED_SECRET"],
        planner=QueryPlan(
            original_query="service",
            rewritten_queries=["REWRITE_SECRET"],
            grep_keywords=["GREP_SECRET"],
            symbol_hints=["SYMBOL_SECRET"],
            discarded_hints=["DISCARDED_SECRET"],
            intent="symbol_lookup",
            status="ok",
        ),
    )
    bundle = replace(bundle, followup_keywords=["FOLLOWUP_SECRET"])

    pack = context_pack.build_context_pack(bundle, options())

    assert pack.next_queries[0].query == "SafeSeed service implementation"
    assert not any(
        secret in suggestion.query
        for secret in secret_values
        for suggestion in pack.next_queries
    )


@pytest.mark.parametrize(
    ("evidence_priority", "expected_level", "protected_reason"),
    [
        (1.0, "medium", "protected original direct evidence is absent"),
        (None, "medium", "protected original direct evidence is absent"),
        (False, "medium", "protected original direct evidence is absent"),
        (0, "high", "protected original direct evidence is present"),
        (0.0, "high", "protected original direct evidence is present"),
    ],
)
def test_readiness_confidence_uses_only_exact_numeric_zero_direct_diagnostic(
    evidence_priority: float | bool | None,
    expected_level: str,
    protected_reason: str,
) -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py", evidence_priority=evidence_priority)],
            query="opaque",
        ),
        options(),
    )

    assert pack.confidence == ReadinessConfidence(
        level=expected_level,
        reasons=(
            "all required evidence groups are present",
            protected_reason,
        ),
    )


def test_protected_direct_evidence_depends_on_value_not_score_parts_dict_type() -> None:
    raw_result = replace(
        result("src/plain.py"),
        score_parts=_DictSubclass({"evidence_priority": 0}),
    )

    pack = context_pack.build_context_pack(
        query_bundle([raw_result], query="opaque"),
        options(),
    )

    assert pack.confidence.level == "high"


def test_anchor_only_zero_diagnostic_does_not_count_as_protected_direct_evidence() -> None:
    zero_anchor = replace(
        anchor("notes/other.txt", "other"),
        score_parts={"evidence_priority": 0},
    )

    pack = context_pack.build_context_pack(
        query_bundle(query="opaque", evidence_anchors=[zero_anchor]),
        options(),
    )

    assert pack.status == "ready"
    assert pack.confidence == ReadinessConfidence(
        level="medium",
        reasons=(
            "all required evidence groups are present",
            "protected original direct evidence is absent",
        ),
    )


def test_required_gap_forces_low_confidence_with_ordered_reasons() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/plain.py")],
            query="opaque",
            planner=QueryPlan(
                original_query="opaque",
                intent="feature_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert pack.confidence == ReadinessConfidence(
        level="low",
        reasons=(
            "required evidence is missing: entrypoints, implementations",
            "recommended evidence is missing: related_types, tests",
            "protected original direct evidence is present",
        ),
    )


def test_present_required_and_recommended_states_have_exact_ordered_reasons() -> None:
    bundle = query_bundle(
        one_result_per_context_group()[:4],
        query="opaque",
        planner=QueryPlan(
            original_query="opaque",
            intent="feature_lookup",
            status="ok",
        ),
    )

    pack = context_pack.build_context_pack(bundle, options())

    assert pack.confidence == ReadinessConfidence(
        level="high",
        reasons=(
            "all required evidence groups are present",
            "all recommended evidence groups are present",
            "protected original direct evidence is present",
        ),
    )


def test_endpoint_query_with_protected_entrypoint_and_recommended_gaps_is_medium() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/main/controller/AppController.java")],
            query="controller",
        ),
        options(),
    )

    assert missing_categories(pack, required=False) == ("implementations", "tests")
    assert pack.confidence == ReadinessConfidence(
        level="medium",
        reasons=(
            "all required evidence groups are present",
            "recommended evidence is missing: implementations, tests",
            "protected original direct evidence is present",
        ),
    )


def test_identifier_hinted_entrypoint_without_surface_recommendations_reaches_high() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/main/controller/WorkspaceController.java")],
            query="WorkspaceController",
            planner=QueryPlan(
                original_query="WorkspaceController",
                intent="symbol_lookup",
                status="ok",
            ),
        ),
        options(),
    )

    assert pack.missing_evidence == ()
    assert pack.confidence.level == "high"
    assert pack.confidence.reasons == (
        "all required evidence groups are present",
        "protected original direct evidence is present",
    )


def test_recommended_gap_is_medium_even_with_no_required_gap() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            [result("src/main/controller/AppController.java")],
            query="opaque",
        ),
        options(),
    )

    assert missing_categories(pack, required=True) == ()
    assert missing_categories(pack, required=False) == ("implementations",)
    assert pack.confidence.level == "medium"


def test_explicit_tests_requirement_promotes_tests_before_fixed_remaining_groups() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            one_result_per_context_group(),
            query="workspace test file",
        ),
        options(),
    )

    assert pack.reading_order == (
        "result:3",
        "result:0",
        "result:1",
        "result:2",
        "result:4",
        "result:5",
    )
    assert tuple(item.id for item in pack.items) == tuple(
        f"result:{index}" for index in range(6)
    )
    assert pack.groups == {
        "entrypoints": ("result:0",),
        "implementations": ("result:1",),
        "related_types": ("result:2",),
        "tests": ("result:3",),
        "configs_docs": ("result:4",),
        "supporting": ("result:5",),
    }


def test_multiple_explicit_promotions_preserve_fixed_v1_relative_order() -> None:
    pack = context_pack.build_context_pack(
        query_bundle(
            one_result_per_context_group(),
            query="workspace test file controller",
        ),
        options(),
    )

    assert pack.reading_order == (
        "result:0",
        "result:3",
        "result:1",
        "result:2",
        "result:4",
        "result:5",
    )


def test_budget_uses_actual_counts_options_and_utf8_content_bytes() -> None:
    selected_options = replace(
        options(max_results=2, max_anchors=2),
        context_before_lines=3,
        context_after_lines=5,
        full_file=True,
        max_full_file_bytes=321_000,
    )
    bundle = query_bundle(
        [
            result("src/first.py", content="汉字"),
            result("src/second.py", content="plain"),
        ],
        evidence_anchors=[
            anchor("README.md", "readme", content="风险"),
            anchor("pom.xml", "pom", content="anchor"),
        ],
    )

    pack = context_pack.build_context_pack(bundle, selected_options)

    expected_content_bytes = sum(
        len(item.content.encode("utf-8"))
        for item in [*bundle.results, *bundle.evidence_anchors]
    )
    assert pack.budget == ContextBudget(
        max_results=2,
        max_evidence_anchors=2,
        max_items=4,
        included_results=2,
        included_evidence_anchors=2,
        content_bytes=expected_content_bytes,
        context_before_lines=3,
        context_after_lines=5,
        full_file=True,
        max_full_file_bytes=321_000,
    )
    assert pack.budget.max_items == (
        pack.budget.max_results + pack.budget.max_evidence_anchors
    )


@pytest.mark.parametrize(
    ("result_count", "anchor_count", "max_results", "max_anchors"),
    [
        (2, 0, 1, 4),
        (0, 2, 12, 1),
    ],
)
def test_build_context_pack_rejects_over_budget_source_counts(
    result_count: int,
    anchor_count: int,
    max_results: int,
    max_anchors: int,
) -> None:
    bundle = query_bundle(
        [result(f"src/{index}.py") for index in range(result_count)],
        evidence_anchors=[
            anchor(f"anchor/{index}", "other") for index in range(anchor_count)
        ],
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            bundle,
            options(max_results=max_results, max_anchors=max_anchors),
        )

    assert str(exc_info.value) == BUDGET_EXCEEDED_ERROR


def test_build_context_pack_does_not_mutate_bundle_source_lists() -> None:
    raw_result = result("src/plain.py")
    raw_anchor = anchor("README.md", "readme")
    bundle = query_bundle([raw_result], evidence_anchors=[raw_anchor])
    result_snapshot = list(bundle.results)
    anchor_snapshot = list(bundle.evidence_anchors)

    context_pack.build_context_pack(bundle, options())

    assert bundle.results == result_snapshot
    assert bundle.evidence_anchors == anchor_snapshot
    assert bundle.results[0] is raw_result
    assert bundle.evidence_anchors[0] is raw_anchor


def test_resolve_context_item_returns_exact_raw_result_and_anchor() -> None:
    raw_result = result("src/plain.py")
    raw_anchor = anchor("README.md", "readme")
    bundle = query_bundle([raw_result], evidence_anchors=[raw_anchor])
    pack = context_pack.build_context_pack(bundle, options())

    assert context_pack.resolve_context_item(bundle, pack.items[0]) is raw_result
    assert context_pack.resolve_context_item(bundle, pack.items[1]) is raw_anchor


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda item: replace(item, source="RESULT"), id="source"),
        pytest.param(lambda item: replace(item, source_index=True), id="bool-index"),
        pytest.param(lambda item: replace(item, source_index=-1), id="negative-index"),
        pytest.param(lambda item: replace(item, source_index=99), id="out-of-range-index"),
        pytest.param(lambda item: replace(item, id="result:99"), id="nonexistent-id"),
        pytest.param(
            lambda item: replace(item, file_path="private/offending-path.py"),
            id="path-mismatch",
        ),
        pytest.param(lambda item: replace(item, start_line=2), id="start-mismatch"),
        pytest.param(lambda item: replace(item, end_line=3), id="end-mismatch"),
        pytest.param(
            lambda item: replace(item, file_path=Path("src/plain.py")),
            id="path-type",
        ),
    ],
)
def test_resolve_context_item_maps_every_invalid_reference_to_fixed_error(mutate) -> None:
    bundle, pack = single_result_pack()

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.resolve_context_item(bundle, mutate(pack.items[0]))

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR
    assert "offending-path" not in str(exc_info.value)


def test_context_pack_payload_has_exact_json_native_schema_v1() -> None:
    bundle = query_bundle(
        [result("src/main/controller/AppController.java")],
        query="controller",
        evidence_anchors=[anchor("README.md", "readme")],
    )
    pack = context_pack.build_context_pack(bundle, options())

    payload = context_pack.context_pack_payload(bundle, pack)

    assert tuple(payload) == (
        "schema_version",
        "status",
        "items",
        "groups",
        "reading_order",
        "missing_evidence",
        "next_queries",
        "confidence",
        "budget",
    )
    assert isinstance(payload["items"], list)
    assert all(
        tuple(item) == (
            "id",
            "source",
            "source_index",
            "file_path",
            "start_line",
            "end_line",
            "group",
            "role",
            "classification_basis",
        )
        for item in payload["items"]
    )
    assert tuple(payload["groups"]) == CONTEXT_GROUPS
    assert all(type(value) is list for value in payload["groups"].values())
    assert type(payload["reading_order"]) is list
    assert type(payload["missing_evidence"]) is list
    assert all(
        tuple(item) == ("category", "required", "reason")
        for item in payload["missing_evidence"]
    )
    assert type(payload["next_queries"]) is list
    assert all(
        tuple(item) == ("query", "purpose", "reason")
        for item in payload["next_queries"]
    )
    assert tuple(payload["confidence"]) == ("level", "reasons")
    assert type(payload["confidence"]["reasons"]) is list
    assert tuple(payload["budget"]) == (
        "max_results",
        "max_evidence_anchors",
        "max_items",
        "included_results",
        "included_evidence_anchors",
        "content_bytes",
        "context_before_lines",
        "context_after_lines",
        "full_file",
        "max_full_file_bytes",
    )
    serialized = json.dumps(payload, allow_nan=False)
    for forbidden in (
        "score",
        "score_parts",
        "semantic_matches",
        "followup_keywords",
        "truncated",
    ):
        assert forbidden not in serialized


def test_context_pack_payload_dereferences_no_content_or_ranking_metadata() -> None:
    bundle = query_bundle(
        [result("src/plain.py", content="PRIVATE CONTENT")],
        evidence_anchors=[anchor("README.md", "readme", content="ANCHOR CONTENT")],
    )
    bundle.results[0].score_parts["secret_score_part"] = 9.0
    pack = context_pack.build_context_pack(bundle, options())

    serialized = json.dumps(
        context_pack.context_pack_payload(bundle, pack),
        allow_nan=False,
    )

    assert "PRIVATE CONTENT" not in serialized
    assert "ANCHOR CONTENT" not in serialized
    assert "secret_score_part" not in serialized
    assert "fixture anchor" not in serialized


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        pytest.param(
            lambda pack: replace(
                pack,
                items=(pack.items[0], replace(pack.items[1], id=pack.items[0].id)),
            ),
            DUPLICATE_ITEM_ERROR,
            id="duplicate-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], id="result:99"), *pack.items[1:]),
            ),
            INVALID_REFERENCE_ERROR,
            id="nonexistent-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], source_index=99), *pack.items[1:]),
            ),
            INVALID_REFERENCE_ERROR,
            id="out-of-range-index",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(pack.items[0], file_path="private/offending-path.py"),
                    *pack.items[1:],
                ),
            ),
            INVALID_REFERENCE_ERROR,
            id="repeated-source-mismatch",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], group="implementations"), *pack.items[1:]),
            ),
            INVALID_CLASSIFICATION_ERROR,
            id="classification-group",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], role="entrypoint"), *pack.items[1:]),
            ),
            INVALID_CLASSIFICATION_ERROR,
            id="classification-role",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(pack.items[0], classification_basis="path_role"),
                    *pack.items[1:],
                ),
            ),
            INVALID_CLASSIFICATION_ERROR,
            id="classification-basis",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(
                    pack.budget,
                    included_results=pack.budget.included_results + 1,
                ),
            ),
            BUDGET_EXCEEDED_ERROR,
            id="over-budget-count",
        ),
    ],
)
def test_context_pack_payload_revalidates_structural_contract(
    mutate,
    expected_error: str,
) -> None:
    bundle = query_bundle([result("src/first.py"), result("src/second.py")])
    pack = context_pack.build_context_pack(bundle, options())

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.context_pack_payload(bundle, mutate(pack))

    assert str(exc_info.value) == expected_error
    assert "offending-path" not in str(exc_info.value)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(pack, schema_version=(1,)),
            id="tuple-scalar",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], file_path=Path("src/plain.py")),),
            ),
            id="path",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], start_line=float("nan")),),
            ),
            id="nan",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, max_results=float("inf")),
            ),
            id="infinity",
        ),
        pytest.param(
            lambda pack: replace(pack, groups={**pack.groups, 1: ()}),
            id="non-string-dict-key",
        ),
        pytest.param(
            lambda pack: replace(pack, status=object()),
            id="arbitrary-object",
        ),
    ],
)
def test_context_pack_payload_maps_materialized_non_json_values_to_fixed_error(
    mutate,
) -> None:
    bundle, pack = single_result_pack()

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.context_pack_payload(bundle, mutate(pack))

    assert str(exc_info.value) == NON_JSON_ERROR


def test_context_pack_payload_rejects_non_context_pack_before_materialization() -> None:
    bundle, _ = single_result_pack()

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.context_pack_payload(bundle, object())

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


@pytest.mark.parametrize("container_type", ["list", "dict"])
def test_context_pack_payload_maps_cyclic_json_container_to_fixed_error(
    container_type: str,
) -> None:
    bundle, pack = single_result_pack()
    if container_type == "list":
        cyclic_list: list[object] = []
        cyclic_list.append(cyclic_list)
        cyclic: object = cyclic_list
    else:
        cyclic_dict: dict[str, object] = {}
        cyclic_dict["self"] = cyclic_dict
        cyclic = cyclic_dict

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.context_pack_payload(
            bundle,
            replace(pack, status=cyclic),
        )

    assert str(exc_info.value) == NON_JSON_ERROR


def test_payload_validation_preserves_specific_error_for_json_native_corruption() -> None:
    bundle, pack = single_result_pack()

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.context_pack_payload(
            bundle,
            replace(pack, schema_version=True),
        )

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_tampered_next_queries_and_confidence() -> None:
    bundle = query_bundle([result("src/plain.py")], query="service")
    pack = context_pack.build_context_pack(bundle, options())
    malformed_packs = (
        replace(
            pack,
            next_queries=(replace(pack.next_queries[0], query="fabricated"),),
        ),
        replace(pack, confidence=replace(pack.confidence, level="high")),
        replace(
            pack,
            next_queries=(replace(pack.next_queries[0], purpose="unknown"),),
        ),
        replace(pack, confidence=replace(pack.confidence, level="certain")),
    )

    for malformed in malformed_packs:
        with pytest.raises(ContextPackError) as exc_info:
            context_pack._validate_context_pack(bundle, malformed)
        assert str(exc_info.value) == INVALID_REFERENCE_ERROR


@pytest.mark.parametrize("category", ["results", "supporting"])
def test_validator_rejects_nonempty_results_or_supporting_gap(category: str) -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        status="partial",
        missing_evidence=(MissingEvidence(category, True, "fabricated"),),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_requires_exact_empty_results_record() -> None:
    bundle = query_bundle()
    pack = context_pack.build_context_pack(bundle, options())

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(
            bundle,
            replace(pack, missing_evidence=()),
        )

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_direct_payload_validation_derives_intent_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = query_bundle([result("src/plain.py")], query="service")
    pack = context_pack.build_context_pack(bundle, options())
    query_calls = 0
    identifier_calls = 0

    def capture_query_intent(query: str, tokens: list[str]):
        nonlocal query_calls
        query_calls += 1
        return infer_query_intent(query, tokens)

    def capture_identifier_intent(query: str, tokens: list[str]):
        nonlocal identifier_calls
        identifier_calls += 1
        return infer_identifier_intent(query, tokens)

    monkeypatch.setattr(context_pack, "infer_query_intent", capture_query_intent)
    monkeypatch.setattr(context_pack, "infer_identifier_intent", capture_identifier_intent)

    context_pack.context_pack_payload(bundle, pack)

    assert (query_calls, identifier_calls) == (1, 1)


def test_build_and_payload_remain_io_free_for_nonexistent_full_file_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = query_bundle(
        [result("definitely/missing/WorkspaceController.java")],
        query="WorkspaceController",
    )

    def fail_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("ContextPack must not perform filesystem I/O")

    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)
    monkeypatch.setattr(Path, "read_bytes", fail_io)

    pack = context_pack.build_context_pack(
        bundle,
        replace(options(), full_file=True),
    )
    payload = context_pack.context_pack_payload(bundle, pack)

    assert payload["items"][0]["file_path"] == (
        "definitely/missing/WorkspaceController.java"
    )
    assert "QueryBundle" not in context_pack.__dict__
    assert "RetrievalResult" not in context_pack.__dict__
    assert "EvidenceAnchor" not in context_pack.__dict__


def single_result_pack() -> tuple[QueryBundle, ContextPack]:
    bundle = query_bundle([result("src/plain.py")])
    return bundle, context_pack.build_context_pack(bundle, options())


def test_validator_maps_duplicate_item_ids_to_bounded_error() -> None:
    bundle = query_bundle([result("src/first.py"), result("src/second.py")])
    pack = context_pack.build_context_pack(bundle, options())
    malformed = replace(
        pack,
        items=(pack.items[0], replace(pack.items[1], id=pack.items[0].id)),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == DUPLICATE_ITEM_ERROR


def test_validator_maps_out_of_range_source_index_to_bounded_error() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        items=(replace(pack.items[0], source_index=99),),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_maps_inconsistent_repeated_source_fields_to_bounded_error() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        items=(replace(pack.items[0], file_path="private/offending-path.py"),),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR
    assert "offending-path" not in str(exc_info.value)


def test_validator_maps_missing_group_reference_to_bounded_error() -> None:
    bundle, pack = single_result_pack()
    malformed_groups = dict(pack.groups)
    malformed_groups["supporting"] = ()
    malformed = replace(pack, groups=malformed_groups)

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_maps_inconsistent_reading_order_to_bounded_error() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(pack, reading_order=())

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_fabricated_tests_first_reading_order() -> None:
    bundle = query_bundle(one_result_per_context_group(), query="opaque")
    pack = context_pack.build_context_pack(bundle, options())
    malformed = replace(
        pack,
        reading_order=(
            "result:3",
            "result:0",
            "result:1",
            "result:2",
            "result:4",
            "result:5",
        ),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_fabricated_canonical_required_gap() -> None:
    bundle = query_bundle([result("src/plain.py")], query="opaque")
    pack = context_pack.build_context_pack(bundle, options())
    malformed = replace(
        pack,
        status="partial",
        missing_evidence=(
            MissingEvidence(
                category="entrypoints",
                required=True,
                reason=(
                    "required evidence for entrypoints is missing from the "
                    "bounded result set"
                ),
            ),
        ),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_partial_status_without_missing_required_evidence() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(pack, status="partial")

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_noncanonical_missing_evidence_reason() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        missing_evidence=(
            MissingEvidence(
                category="tests",
                required=False,
                reason="tests are absent from the repository",
            ),
        ),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_wrong_valid_looking_classification_triple() -> None:
    bundle, pack = single_result_pack()
    malformed_item = replace(pack.items[0], group="implementations")
    malformed_groups = {
        group: (malformed_item.id,) if group == "implementations" else ()
        for group in CONTEXT_GROUPS
    }
    malformed = replace(
        pack,
        items=(malformed_item,),
        groups=malformed_groups,
        reading_order=(malformed_item.id,),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


def test_validator_rejects_reordered_group_keys() -> None:
    bundle, pack = single_result_pack()
    reordered_groups = {
        group: pack.groups[group]
        for group in reversed(CONTEXT_GROUPS)
    }
    malformed = replace(pack, groups=reordered_groups)

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_validator_rejects_malformed_source_derived_budget() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        budget=replace(pack.budget, content_bytes=pack.budget.content_bytes + 1),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == BUDGET_EXCEEDED_ERROR


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(pack, schema_version=True),
            id="bool-schema-version",
        ),
        pytest.param(
            lambda pack: replace(pack, schema_version=1.0),
            id="float-schema-version",
        ),
        pytest.param(
            lambda pack: replace(pack, schema_version=_RaisingEquality()),
            id="raising-schema-equality",
        ),
        pytest.param(
            lambda pack: replace(pack, items=list(pack.items)),
            id="list-items",
        ),
        pytest.param(
            lambda pack: replace(pack, items=_TupleSubclass(pack.items)),
            id="tuple-subclass-items",
        ),
        pytest.param(
            lambda pack: replace(pack, groups=_DictSubclass(pack.groups)),
            id="dict-subclass-groups",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                groups={
                    group: (
                        _TupleSubclass(item_ids)
                        if group == "supporting"
                        else item_ids
                    )
                    for group, item_ids in pack.groups.items()
                },
            ),
            id="tuple-subclass-group-value",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                groups={
                    _StringSubclass(group): item_ids
                    for group, item_ids in pack.groups.items()
                },
            ),
            id="string-subclass-group-key",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                reading_order=_TupleSubclass(pack.reading_order),
            ),
            id="tuple-subclass-reading-order",
        ),
    ],
)
def test_validator_rejects_malformed_top_level_structural_shapes(mutate) -> None:
    bundle, pack = single_result_pack()
    malformed = mutate(pack)

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("id", _StringSubclass("result:0"), INVALID_REFERENCE_ERROR),
        ("source", _StringSubclass("result"), INVALID_REFERENCE_ERROR),
        ("file_path", _StringSubclass("src/plain.py"), INVALID_REFERENCE_ERROR),
        ("file_path", _RaisingEquality(), INVALID_REFERENCE_ERROR),
        ("start_line", True, INVALID_REFERENCE_ERROR),
        ("end_line", 2.0, INVALID_REFERENCE_ERROR),
        ("group", _StringSubclass("supporting"), INVALID_CLASSIFICATION_ERROR),
        ("role", _StringSubclass("source"), INVALID_CLASSIFICATION_ERROR),
        (
            "classification_basis",
            _StringSubclass("fallback"),
            INVALID_CLASSIFICATION_ERROR,
        ),
    ],
)
def test_validator_rejects_malformed_item_structural_fields(
    field: str,
    value: object,
    expected_error: str,
) -> None:
    bundle, pack = single_result_pack()
    malformed_item = replace(pack.items[0], **{field: value})
    malformed = replace(pack, items=(malformed_item,))

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == expected_error


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_results", 12.0),
        ("max_evidence_anchors", 4.0),
        ("max_items", 16.0),
        ("included_results", True),
        ("included_evidence_anchors", False),
        ("content_bytes", 6.0),
        ("context_before_lines", 8.0),
        ("context_after_lines", 12.0),
        ("max_full_file_bytes", 200_000.0),
        ("full_file", 0),
    ],
)
def test_validator_rejects_coercive_budget_field_types(
    field: str,
    value: object,
) -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        budget=replace(pack.budget, **{field: value}),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == BUDGET_EXCEEDED_ERROR


def test_validator_rejects_budget_lookalike_container() -> None:
    bundle, pack = single_result_pack()
    malformed = replace(
        pack,
        budget=SimpleNamespace(**vars(pack.budget)),
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack._validate_context_pack(bundle, malformed)

    assert str(exc_info.value) == BUDGET_EXCEEDED_ERROR


@pytest.mark.parametrize(
    "anchor_kind",
    [
        pytest.param(None, id="none"),
        pytest.param(1, id="integer"),
        pytest.param([], id="unhashable-list"),
        pytest.param(
            _UnhashableString("other"),
            id="unhashable-string-subclass",
        ),
    ],
)
def test_build_context_pack_rejects_non_string_anchor_kind(
    anchor_kind: object,
) -> None:
    malformed_anchor = replace(
        anchor("anchor", "other"),
        anchor_kind=anchor_kind,
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            query_bundle(evidence_anchors=[malformed_anchor]),
            options(),
        )

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


@pytest.mark.parametrize(
    "summary_field",
    ["entry_points", "implementation", "related_types"],
)
@pytest.mark.parametrize(
    "collection",
    [
        pytest.param(None, id="none"),
        pytest.param(1, id="integer"),
        pytest.param("Plain", id="string"),
        pytest.param(("Plain",), id="tuple"),
        pytest.param(_ListSubclass(["Plain"]), id="list-subclass"),
    ],
)
def test_build_context_pack_rejects_non_list_inspected_summary_fields(
    summary_field: str,
    collection: object,
) -> None:
    summary = replace(
        RetrievalSummary(),
        **{summary_field: collection},
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            query_bundle([result("src/Plain.py")], summary=summary),
            options(),
        )

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


@pytest.mark.parametrize(
    ("summary_field", "entry"),
    [
        ("entry_points", None),
        ("implementation", 1),
        ("related_types", []),
        ("entry_points", _StringSubclass("Plain")),
        ("implementation", _StringSubclass("Plain.run")),
        ("related_types", _StringSubclass("Plain")),
    ],
)
def test_build_context_pack_rejects_non_string_inspected_summary_entries(
    summary_field: str,
    entry: object,
) -> None:
    summary = replace(
        RetrievalSummary(),
        **{summary_field: [entry]},
    )

    with pytest.raises(ContextPackError) as exc_info:
        context_pack.build_context_pack(
            query_bundle([result("src/Plain.py")], summary=summary),
            options(),
        )

    assert str(exc_info.value) == INVALID_CLASSIFICATION_ERROR


def _v2_modules():
    return (
        context_pack_v2_models,
        context_pack_v2_builder,
        context_pack_v2_serialization,
    )


def _v2_result(
    path: str,
    *,
    content: str = "source",
    score: float = 0.75,
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
    spans: tuple[object, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=Path(path),
        start_line=3,
        end_line=8,
        content=content,
        score=score,
        score_parts=score_parts if score_parts is not None else {},
        reasons=reasons if reasons is not None else ["fixture result"],
        spans=spans,
    )


def _v2_anchor(
    path: str,
    kind: str,
    *,
    content: str = "anchor",
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=Path(path),
        start_line=10,
        end_line=12,
        content=content,
        score=0.5,
        score_parts=score_parts if score_parts is not None else {},
        reasons=reasons if reasons is not None else ["fixture anchor"],
        anchor_kind=kind,
    )


def _v2_bundle(
    results: list[SimpleNamespace] | None = None,
    anchors: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        results=list(results or ()),
        evidence_anchors=list(anchors or ()),
    )


def test_v2_normalize_result_preserves_bounded_public_candidate_metadata() -> None:
    score_parts = _DictSubclass({"evidence_priority": 0, "semantic": 0.75})
    spans = (object(), object())
    raw_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="@Entity\npublic class Owner {}",
        score_parts=score_parts,
        reasons=["direct", "direct", "semantic", "path", "signal", "ignored"],
        spans=spans,
    )

    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([raw_result])
    )

    assert candidates == (
        context_pack_v2_models.ContextCandidate(
            key="src/main/java/com/example/Owner.java",
            file_path="src/main/java/com/example/Owner.java",
            start_line=3,
            end_line=8,
            content="@Entity\npublic class Owner {}",
            group="related_types",
            role="data_type",
            classification_basis="content",
            source_kind="result",
            retrieval_rank=0,
            source_order=0,
            relevance_score=0.75,
            reasons=("direct", "semantic", "path", "signal"),
            score_parts={"evidence_priority": 0, "semantic": 0.75},
            spans=spans,
            trusted_provenance_text=(
                "src/main/java/com/example/Owner.java\n"
                "direct\nsemantic\npath\nsignal"
            ),
            protected_direct=True,
        ),
    )
    assert candidates[0].score_parts is not score_parts


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "src/main/controller/AppController.java",
            "class AppController {}",
            ("entrypoints", "entrypoint", "path"),
        ),
        (
            "src/main/service/impl/AppServiceImpl.java",
            "class AppServiceImpl {}",
            ("implementations", "service_impl", "path"),
        ),
        (
            "src/main/service/AppService.java",
            "interface AppService {}",
            ("related_types", "service_interface", "content"),
        ),
        (
            "src/main/resources/application.yml",
            "spring.main.banner-mode=off",
            ("configs_docs", "runtime_config", "path"),
        ),
        (
            "tests/test_app.py",
            "def test_app(): pass",
            ("tests", "test", "path"),
        ),
        (
            "src/plain.py",
            "source",
            ("supporting", "source", "fallback"),
        ),
    ],
)
def test_v2_normalize_maps_shared_roles_to_closed_groups(
    path: str,
    content: str,
    expected: tuple[str, str, str],
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path, content=content)])
    )[0]

    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == expected
    assert candidate.group in context_pack_v2_models.CONTEXT_GROUPS


def test_v2_normalize_preserves_shared_basis_for_unmapped_non_frontend_role() -> None:
    path = "backend/components/Widget.java"
    shared_role = context_pack_v2_roles.classify_path_role(Path(path))

    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path)])
    )[0]

    assert (shared_role.name, shared_role.basis) == ("component", "path")
    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == ("supporting", shared_role.name, shared_role.basis)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/router/index.ts", ("entrypoints", "route_config", "path")),
        (
            "src/components/Widget.vue",
            ("implementations", "shared_component", "path"),
        ),
        ("src/App.tsx", ("entrypoints", "layout_component", "path")),
        ("src/utils/format.ts", ("implementations", "utility", "path")),
    ],
)
def test_v2_normalize_preserves_v1_frontend_precedence(
    path: str,
    expected: tuple[str, str, str],
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path)])
    )[0]

    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == expected


@pytest.mark.parametrize(
    ("score_parts", "expected"),
    [
        ({"evidence_priority": False}, False),
        ({"evidence_priority": True}, False),
        ({"evidence_priority": 0}, True),
        ({"evidence_priority": 0.0}, True),
        ({"evidence_priority": 1}, False),
        ({}, False),
    ],
)
def test_v2_protected_direct_requires_non_bool_numeric_zero(
    score_parts: dict[str, float],
    expected: bool,
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result("src/plain.py", score_parts=score_parts)])
    )[0]

    assert candidate.protected_direct is expected


def test_v2_anchor_uses_shared_classification_before_bounded_kind_fallback() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            anchors=[
                _v2_anchor(
                    "src/main/resources/application.yml",
                    "readme",
                    score_parts={"anchor": 1.0},
                ),
                _v2_anchor("evidence/readme.bin", "readme"),
                _v2_anchor("evidence/risks.bin", "risks"),
                _v2_anchor("evidence/pom.bin", "pom"),
                _v2_anchor("evidence/other.bin", "other"),
                _v2_anchor(
                    "src/main/java/com/example/Owner.java",
                    "other",
                    content="@Entity\npublic class Owner {}",
                ),
            ]
        )
    )

    assert [
        (
            candidate.group,
            candidate.role,
            candidate.classification_basis,
            candidate.source_kind,
            candidate.retrieval_rank,
            candidate.source_order,
            candidate.relevance_score,
            candidate.spans,
            candidate.protected_direct,
        )
        for candidate in candidates
    ] == [
        ("configs_docs", "runtime_config", "path", "evidence_anchor", None, 0, None, (), False),
        ("configs_docs", "readme", "fallback", "evidence_anchor", None, 1, None, (), False),
        ("configs_docs", "risks", "fallback", "evidence_anchor", None, 2, None, (), False),
        ("configs_docs", "pom", "fallback", "evidence_anchor", None, 3, None, (), False),
        ("supporting", "evidence_anchor", "fallback", "evidence_anchor", None, 4, None, (), False),
        ("related_types", "data_type", "content", "evidence_anchor", None, 5, None, (), False),
    ]
    assert candidates[0].score_parts == {"anchor": 1.0}


def test_v2_normalize_deduplicates_paths_and_promotes_only_fallback_result_role() -> None:
    first_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="public class Owner {}",
        reasons=["result reason", "shared"],
        spans=("result span",),
    )
    duplicate_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="SECOND RESULT CONTENT",
        reasons=["shared", "duplicate result"],
    )
    promoting_anchor = _v2_anchor(
        "src/main/java/com/example/Owner.java",
        "other",
        content="@Entity\npublic class Owner {}",
        reasons=["anchor reason", "ignored fifth"],
    )
    service_result = _v2_result(
        "src/main/java/com/example/service/AppService.java",
        content="class AppService {}",
        reasons=["service result"],
    )
    non_promoting_anchor = _v2_anchor(
        "src/main/java/com/example/service/AppService.java",
        "readme",
        content="@Entity\npublic class AppService {}",
        reasons=["service anchor"],
    )

    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [first_result, duplicate_result, service_result],
            [promoting_anchor, non_promoting_anchor],
        )
    )

    assert len(candidates) == 2
    promoted, service = candidates
    assert (
        promoted.source_kind,
        promoted.content,
        promoted.retrieval_rank,
        promoted.relevance_score,
        promoted.spans,
        promoted.group,
        promoted.role,
        promoted.classification_basis,
        promoted.reasons,
    ) == (
        "result",
        "public class Owner {}",
        0,
        0.75,
        ("result span",),
        "related_types",
        "data_type",
        "content",
        ("result reason", "shared", "duplicate result", "anchor reason"),
    )
    assert promoted.trusted_provenance_text.endswith(
        "result reason\nshared\nduplicate result\nanchor reason"
    )
    assert (service.group, service.role, service.classification_basis) == (
        "implementations",
        "service",
        "path",
    )
    assert service.reasons == ("service result", "service anchor")


def test_v2_duplicate_results_preserve_first_result_classification() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [
                _v2_result(
                    "src/main/java/com/example/Owner.java",
                    content="public class Owner {}",
                ),
                _v2_result(
                    "src/main/java/com/example/Owner.java",
                    content="@Entity\npublic class Owner {}",
                ),
            ]
        )
    )

    assert len(candidates) == 1
    assert (
        candidates[0].group,
        candidates[0].role,
        candidates[0].classification_basis,
    ) == ("supporting", "source", "fallback")


def test_v2_normalize_orders_results_then_unique_anchors_with_case_sensitive_keys() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [
                _v2_result("src/File.py"),
                _v2_result("src/file.py"),
            ],
            [
                _v2_anchor("src/File.py", "other"),
                _v2_anchor("README.md", "readme"),
            ],
        )
    )

    assert [candidate.key for candidate in candidates] == [
        "src/File.py",
        "src/file.py",
        "README.md",
    ]
    assert [candidate.file_path for candidate in candidates] == [
        "src/File.py",
        "src/file.py",
        "README.md",
    ]
    assert [candidate.source_order for candidate in candidates] == [0, 1, 1]
    assert [candidate.retrieval_rank for candidate in candidates] == [0, 1, None]


def test_v2_normalize_candidates_performs_no_path_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*args: object, **kwargs: object) -> None:
        pytest.fail("candidate normalization must not perform path I/O")

    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)
    bundle = _v2_bundle(
        [_v2_result("src/plain.py")],
        [_v2_anchor("README.md", "readme")],
    )

    candidates = context_pack_v2_roles.normalize_candidates(bundle)

    assert len(candidates) == 2


def _v2_pack(content: str = "核心实现\n"):
    models, _, _ = _v2_modules()
    content_bytes = len(content.encode("utf-8"))
    excerpt = models.ContextExcerpt(
        start_line=10,
        end_line=11,
        content=content,
        content_bytes=content_bytes,
        truncated=False,
    )
    item = models.ContextItem(
        id="item:0",
        file_path="src/核心.py",
        group="implementations",
        role="implementation",
        classification_basis="content",
        source_kind="result",
        retrieval_rank=0,
        relevance_score=0.75,
        reasons=("direct Unicode match ✓",),
        matched_need_ids=("need:implementation",),
        excerpts=(excerpt,),
    )
    evidence_needs = (
        models.EvidenceNeed(
            id="need:implementation",
            category="implementations",
            subject_terms=("核心",),
            required=True,
            provenance="explicit_query",
            matched_item_ids=("item:0",),
        ),
        models.EvidenceNeed(
            id="need:tests",
            category="tests",
            subject_terms=("核心",),
            required=True,
            provenance="explicit_query",
            matched_item_ids=(),
        ),
    )
    groups = {
        group: (("item:0",) if group == "implementations" else ())
        for group in models.CONTEXT_GROUPS
    }
    return models.ContextPack(
        schema_version=models.CONTEXT_PACK_SCHEMA_VERSION,
        status="partial",
        items=(item,),
        groups=groups,
        reading_order=("item:0",),
        evidence_needs=evidence_needs,
        missing_evidence=(
            models.MissingEvidence(
                need_id="need:tests",
                category="tests",
                required=True,
                reason=(
                    "required 核心 test evidence is missing from the bounded context"
                ),
            ),
        ),
        next_queries=(
            models.NextQuery(
                need_id="need:tests",
                query="核心 test",
                purpose="find missing required test evidence",
            ),
        ),
        omissions=(
            models.Omission(
                file_path="tests/legacy_test.py",
                group="tests",
                reason=(
                    "lower priority than selected evidence under the context budget"
                ),
                matched_need_ids=("need:tests",),
            ),
        ),
        confidence=models.ReadinessConfidence(
            level="low",
            reasons=("required evidence is missing",),
        ),
        budget=models.ContextBudget(
            max_items=12,
            max_excerpts_per_item=2,
            max_excerpt_bytes=max(4096, content_bytes),
            max_item_content_bytes=max(8192, content_bytes),
            max_total_content_bytes=max(49_152, content_bytes),
            max_pack_bytes=65_536,
            included_items=1,
            included_excerpts=1,
            content_bytes=content_bytes,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=1,
            budget_exhausted=True,
        ),
    )


def _v2_ready_pack():
    models, _, _ = _v2_modules()
    pack = _v2_pack()
    return replace(
        pack,
        status="ready",
        evidence_needs=(pack.evidence_needs[0],),
        missing_evidence=(),
        next_queries=(),
        omissions=(),
        confidence=models.ReadinessConfidence(
            level="high",
            reasons=(
                "all required evidence is selected",
                "protected original-direct evidence is present",
            ),
        ),
        budget=replace(
            pack.budget,
            omitted_item_count=0,
            budget_exhausted=False,
        ),
    )


def test_v2_schema_constants_error_and_frozen_record_fields_are_exact() -> None:
    models, _, _ = _v2_modules()
    expected_fields = {
        "ContextExcerpt": (
            "start_line",
            "end_line",
            "content",
            "content_bytes",
            "truncated",
        ),
        "ContextItem": (
            "id",
            "file_path",
            "group",
            "role",
            "classification_basis",
            "source_kind",
            "retrieval_rank",
            "relevance_score",
            "reasons",
            "matched_need_ids",
            "excerpts",
        ),
        "EvidenceNeed": (
            "id",
            "category",
            "subject_terms",
            "required",
            "provenance",
            "matched_item_ids",
        ),
        "MissingEvidence": ("need_id", "category", "required", "reason"),
        "NextQuery": ("need_id", "query", "purpose"),
        "Omission": ("file_path", "group", "reason", "matched_need_ids"),
        "ReadinessConfidence": ("level", "reasons"),
        "ContextBudget": (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
            "included_items",
            "included_excerpts",
            "content_bytes",
            "pack_bytes",
            "truncated_item_count",
            "omitted_item_count",
            "budget_exhausted",
        ),
        "ContextPack": (
            "schema_version",
            "status",
            "items",
            "groups",
            "reading_order",
            "evidence_needs",
            "missing_evidence",
            "next_queries",
            "omissions",
            "confidence",
            "budget",
        ),
        "ContextCandidate": (
            "key",
            "file_path",
            "start_line",
            "end_line",
            "content",
            "group",
            "role",
            "classification_basis",
            "source_kind",
            "retrieval_rank",
            "source_order",
            "relevance_score",
            "reasons",
            "score_parts",
            "spans",
            "trusted_provenance_text",
            "protected_direct",
        ),
        "ExcerptWindow": (
            "start_line",
            "end_line",
            "required_need_ids",
            "recommended_need_ids",
            "score",
            "protected_direct",
        ),
        "ContextPackOptions": (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
            "context_before_lines",
            "context_after_lines",
        ),
    }

    assert models.CONTEXT_PACK_SCHEMA_VERSION == 2
    assert models.CONTEXT_GROUPS == (
        "entrypoints",
        "implementations",
        "related_types",
        "tests",
        "configs_docs",
        "supporting",
    )
    for name, expected in expected_fields.items():
        assert tuple(field.name for field in fields(getattr(models, name))) == expected

    pack = _v2_pack()
    with pytest.raises(FrozenInstanceError):
        pack.status = "ready"

    error = models.ContextPackError("invalid_context_options", "fixed message")
    assert error.code == "invalid_context_options"
    assert error.message == "fixed message"
    assert str(error) == "fixed message"
    assert models.ContextPackError is not ContextPackError
    assert context_pack.CONTEXT_PACK_SCHEMA_VERSION == 1


def test_v2_candidate_key_and_retrieval_rank_annotations_are_exact() -> None:
    models, _, _ = _v2_modules()

    assert models.ContextItem.__annotations__["retrieval_rank"] == "int | None"
    assert models.ContextCandidate.__annotations__["key"] == "str"
    assert models.ContextCandidate.__annotations__["retrieval_rank"] == "int | None"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field in (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
        )
        for value in (True, 1.0, 0, -1)
    ],
)
def test_v2_resolver_rejects_invalid_configured_context_values(
    field: str,
    value: object,
) -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    context = replace(config_module.ContextConfig(), **{field: value})

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(
            ToolConfig(context=context),
            context_lines=None,
            max_evidence_anchors=4,
        )

    assert exc_info.value.code == "invalid_context_options"
    assert exc_info.value.message == f"context.{field} must be a positive integer"
    assert str(exc_info.value) == exc_info.value.message


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"max_excerpt_bytes": 8193},
            "context.max_excerpt_bytes must not exceed max_item_content_bytes",
        ),
        (
            {"max_item_content_bytes": 49_153},
            "context.max_item_content_bytes must not exceed max_total_content_bytes",
        ),
        (
            {"max_total_content_bytes": 65_536},
            "context.max_total_content_bytes must be less than max_pack_bytes",
        ),
    ],
)
def test_v2_resolver_rejects_invalid_configured_context_order(
    changes: dict[str, int],
    message: str,
) -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    context = replace(config_module.ContextConfig(), **changes)

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(
            ToolConfig(context=context),
            context_lines=None,
            max_evidence_anchors=4,
        )

    assert (exc_info.value.code, exc_info.value.message) == (
        "invalid_context_options",
        message,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_items": True}, "max_items must be a positive integer"),
        ({"max_items": 1.0}, "max_items must be a positive integer"),
        ({"max_items": 0}, "max_items must be a positive integer"),
        ({"max_items": -1}, "max_items must be a positive integer"),
        (
            {"max_pack_bytes": True},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_pack_bytes": 4096.0},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_pack_bytes": 4095},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_evidence_anchors": True},
            "max_evidence_anchors must be a non-negative integer",
        ),
        (
            {"max_evidence_anchors": 1.0},
            "max_evidence_anchors must be a non-negative integer",
        ),
        (
            {"max_evidence_anchors": -1},
            "max_evidence_anchors must be a non-negative integer",
        ),
    ],
)
def test_v2_resolver_rejects_invalid_request_and_internal_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    models, builder, _ = _v2_modules()
    call_kwargs = {
        "context_lines": None,
        "max_evidence_anchors": 4,
        **kwargs,
    }

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(ToolConfig(), **call_kwargs)

    assert (exc_info.value.code, exc_info.value.message) == (
        "invalid_context_options",
        message,
    )


def test_v2_resolver_applies_request_ceiling_and_cascading_content_caps() -> None:
    models, builder, _ = _v2_modules()

    resolved = builder.resolve_context_pack_options(
        ToolConfig(),
        context_lines=None,
        max_evidence_anchors=4,
        max_items=20,
        max_pack_bytes=4096,
    )

    assert resolved == models.ContextPackOptions(
        max_items=12,
        max_excerpts_per_item=2,
        max_excerpt_bytes=4095,
        max_item_content_bytes=4095,
        max_total_content_bytes=4095,
        max_pack_bytes=4096,
        context_before_lines=8,
        context_after_lines=12,
    )


def test_v2_resolver_caps_items_by_raw_candidate_count_and_clamps_window() -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    config = ToolConfig(
        retrieval=RetrievalConfig(
            final_top_k=5,
            context_before_lines=-3,
            context_after_lines=-7,
        ),
        context=replace(config_module.ContextConfig(), max_items=50),
    )

    configured_window = builder.resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=2,
        max_items=20,
    )
    request_window = builder.resolve_context_pack_options(
        config,
        context_lines=-9,
        max_evidence_anchors=2,
        max_items=20,
    )

    assert configured_window.max_items == 7
    assert (
        configured_window.context_before_lines,
        configured_window.context_after_lines,
    ) == (0, 0)
    assert (
        request_window.context_before_lines,
        request_window.context_after_lines,
    ) == (0, 0)
    assert isinstance(configured_window, models.ContextPackOptions)


def test_v2_resolver_clamps_negative_raw_candidate_cap_to_zero() -> None:
    _, builder, _ = _v2_modules()

    resolved = builder.resolve_context_pack_options(
        ToolConfig(retrieval=RetrievalConfig(final_top_k=-2)),
        context_lines=None,
        max_evidence_anchors=1,
    )

    assert resolved.max_items == 0


def test_v2_payload_has_exact_top_level_and_nested_keys() -> None:
    models, _, serialization = _v2_modules()

    payload = serialization.context_pack_payload(_v2_pack())

    assert tuple(payload) == (
        "schema_version",
        "status",
        "items",
        "groups",
        "reading_order",
        "evidence_needs",
        "missing_evidence",
        "next_queries",
        "omissions",
        "confidence",
        "budget",
    )
    assert tuple(payload["items"][0]) == (
        "id",
        "file_path",
        "group",
        "role",
        "classification_basis",
        "source_kind",
        "retrieval_rank",
        "relevance_score",
        "reasons",
        "matched_need_ids",
        "excerpts",
    )
    assert tuple(payload["items"][0]["excerpts"][0]) == (
        "start_line",
        "end_line",
        "content",
        "content_bytes",
        "truncated",
    )
    assert tuple(payload["groups"]) == models.CONTEXT_GROUPS
    assert tuple(payload["evidence_needs"][0]) == (
        "id",
        "category",
        "subject_terms",
        "required",
        "provenance",
        "matched_item_ids",
    )
    assert tuple(payload["missing_evidence"][0]) == (
        "need_id",
        "category",
        "required",
        "reason",
    )
    assert tuple(payload["next_queries"][0]) == ("need_id", "query", "purpose")
    assert tuple(payload["omissions"][0]) == (
        "file_path",
        "group",
        "reason",
        "matched_need_ids",
    )
    assert tuple(payload["confidence"]) == ("level", "reasons")
    assert tuple(payload["budget"]) == (
        "max_items",
        "max_excerpts_per_item",
        "max_excerpt_bytes",
        "max_item_content_bytes",
        "max_total_content_bytes",
        "max_pack_bytes",
        "included_items",
        "included_excerpts",
        "content_bytes",
        "pack_bytes",
        "truncated_item_count",
        "omitted_item_count",
        "budget_exhausted",
    )
    assert all(type(item) is dict for item in payload["items"])
    assert all(type(item_ids) is list for item_ids in payload["groups"].values())
    assert payload["schema_version"] == 2


def test_v2_serialization_accepts_evidence_anchor_without_retrieval_rank() -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()
    anchor_item = replace(
        pack.items[0],
        source_kind="evidence_anchor",
        retrieval_rank=None,
        relevance_score=None,
    )

    payload = serialization.context_pack_payload(
        replace(pack, items=(anchor_item,))
    )

    assert payload["items"][0]["source_kind"] == "evidence_anchor"
    assert payload["items"][0]["retrieval_rank"] is None
    assert payload["items"][0]["relevance_score"] is None


@pytest.mark.parametrize(
    ("source_kind", "retrieval_rank", "relevance_score"),
    [
        pytest.param("result", 0, None, id="result-without-score"),
        pytest.param(
            "evidence_anchor",
            None,
            0.75,
            id="evidence-anchor-with-score",
        ),
    ],
)
def test_v2_serialization_rejects_source_kind_score_mismatches(
    source_kind: str,
    retrieval_rank: int | None,
    relevance_score: float | None,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    malformed_item = replace(
        pack.items[0],
        source_kind=source_kind,
        retrieval_rank=retrieval_rank,
        relevance_score=relevance_score,
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(
            replace(pack, items=(malformed_item,))
        )

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_canonical_serialization_is_unicode_native_deterministic_and_self_sized(
) -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()

    payload = serialization.context_pack_payload(pack)
    first = serialization.canonical_context_pack_bytes(pack)
    second = serialization.canonical_context_pack_bytes(pack)
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert first == second == canonical_payload
    assert "核心".encode("utf-8") in first
    assert payload["budget"]["pack_bytes"] == len(first)
    assert json.loads(first)["budget"]["pack_bytes"] == len(first)
    assert pack.budget.pack_bytes == 0


def test_v2_canonical_serialization_self_sizes_across_digit_width_boundary() -> None:
    _, _, serialization = _v2_modules()
    target_size = 10_000
    padding = target_size - len(serialization.canonical_context_pack_bytes(_v2_pack()))
    encoded = b""

    for _ in range(8):
        encoded = serialization.canonical_context_pack_bytes(_v2_pack("x" * padding))
        if target_size <= len(encoded) < target_size + 10:
            break
        padding += target_size - len(encoded)

    embedded_size = json.loads(encoded)["budget"]["pack_bytes"]
    assert target_size <= len(encoded) < target_size + 10
    assert embedded_size == len(encoded)
    assert len(str(embedded_size)) == 5


def test_v2_canonical_serialization_accepts_payload_without_mutating_it() -> None:
    _, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_pack())
    payload["budget"]["pack_bytes"] = 0
    original = copy.deepcopy(payload)

    encoded = serialization.canonical_context_pack_bytes(payload)

    assert payload == original
    assert json.loads(encoded)["budget"]["pack_bytes"] == len(encoded)


def test_v2_serialization_accepts_configured_pack_ceiling_below_request_floor() -> None:
    from context_search_tool import config as config_module

    _, builder, serialization = _v2_modules()
    options = builder.resolve_context_pack_options(
        ToolConfig(
            context=config_module.ContextConfig(
                max_excerpt_bytes=512,
                max_item_content_bytes=1024,
                max_total_content_bytes=2048,
                max_pack_bytes=3000,
            )
        ),
        context_lines=None,
        max_evidence_anchors=4,
    )
    pack = _v2_pack()
    budget = replace(
        pack.budget,
        max_items=options.max_items,
        max_excerpts_per_item=options.max_excerpts_per_item,
        max_excerpt_bytes=options.max_excerpt_bytes,
        max_item_content_bytes=options.max_item_content_bytes,
        max_total_content_bytes=options.max_total_content_bytes,
        max_pack_bytes=options.max_pack_bytes,
    )

    payload = serialization.context_pack_payload(replace(pack, budget=budget))

    assert payload["budget"]["pack_bytes"] < 3000


def test_v2_serialization_accepts_zero_effective_item_capacity() -> None:
    models, builder, serialization = _v2_modules()
    options = builder.resolve_context_pack_options(
        ToolConfig(retrieval=RetrievalConfig(final_top_k=0)),
        context_lines=None,
        max_evidence_anchors=0,
    )
    pack = models.ContextPack(
        schema_version=models.CONTEXT_PACK_SCHEMA_VERSION,
        status="empty",
        items=(),
        groups={group: () for group in models.CONTEXT_GROUPS},
        reading_order=(),
        evidence_needs=(),
        missing_evidence=(),
        next_queries=(),
        omissions=(),
        confidence=models.ReadinessConfidence(
            level="none",
            reasons=("no usable retrieval evidence",),
        ),
        budget=models.ContextBudget(
            max_items=options.max_items,
            max_excerpts_per_item=options.max_excerpts_per_item,
            max_excerpt_bytes=options.max_excerpt_bytes,
            max_item_content_bytes=options.max_item_content_bytes,
            max_total_content_bytes=options.max_total_content_bytes,
            max_pack_bytes=options.max_pack_bytes,
            included_items=0,
            included_excerpts=0,
            content_bytes=0,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=0,
            budget_exhausted=False,
        ),
    )

    payload = serialization.context_pack_payload(pack)

    assert options.max_items == 0
    assert payload["budget"]["max_items"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(pack, status="ready"),
            id="status-not-derived-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                status="ready",
                missing_evidence=(),
                next_queries=(),
            ),
            id="missing-records-not-exhaustive-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], matched_need_ids=()),),
            ),
            id="need-item-links-not-bidirectional-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                confidence=replace(
                    pack.confidence,
                    reasons=("recommended tests are missing",),
                ),
            ),
            id="confidence-reasons-not-derived",
        ),
    ],
)
def test_v2_serialization_rejects_inconsistent_derived_semantic_states(mutate) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "fault",
    [
        "category_mismatch",
        "linked_item_without_excerpt",
        "subject_not_visible",
        "subjects_split_across_excerpts",
    ],
)
def test_v2_serialization_revalidates_every_semantic_need_item_link(
    fault: str,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    item = pack.items[0]
    need = pack.evidence_needs[0]
    budget = pack.budget

    if fault == "category_mismatch":
        need = replace(need, category="tests")
    elif fault == "linked_item_without_excerpt":
        item = replace(item, excerpts=())
        budget = replace(budget, included_excerpts=0, content_bytes=0)
    elif fault == "subject_not_visible":
        need = replace(need, subject_terms=("not-visible",))
    else:
        first = replace(
            item.excerpts[0],
            start_line=10,
            end_line=10,
            content="first-subject\n",
            content_bytes=len("first-subject\n".encode("utf-8")),
        )
        second = replace(
            item.excerpts[0],
            start_line=11,
            end_line=11,
            content="second-subject\n",
            content_bytes=len("second-subject\n".encode("utf-8")),
        )
        item = replace(item, excerpts=(first, second))
        need = replace(
            need,
            subject_terms=("first-subject", "second-subject"),
        )
        budget = replace(
            budget,
            included_excerpts=2,
            content_bytes=first.content_bytes + second.content_bytes,
        )

    malformed = replace(
        pack,
        items=(item,),
        evidence_needs=(need, pack.evidence_needs[1]),
        budget=budget,
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    ("level", "reasons", "recommended_missing"),
    [
        (
            "high",
            ["all required evidence is selected"],
            False,
        ),
        (
            "medium",
            ["all required evidence is selected"],
            False,
        ),
        (
            "high",
            [
                "all required evidence is selected",
                "recommended tests are missing",
            ],
            True,
        ),
        (
            "medium",
            [
                "all required evidence is selected",
                "protected original-direct evidence is present",
                "protected original-direct evidence is absent",
            ],
            False,
        ),
        (
            "medium",
            [
                "all required evidence is selected",
                "protected original-direct evidence is present",
                "recommended tests are missing",
            ],
            True,
        ),
    ],
)
def test_v2_serialization_enforces_exact_self_describing_ready_confidence(
    level: str,
    reasons: list[str],
    recommended_missing: bool,
) -> None:
    models, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_ready_pack())
    payload["budget"]["pack_bytes"] = 0
    if recommended_missing:
        payload["evidence_needs"].append(
            {
                "id": "need:tests",
                "category": "tests",
                "subject_terms": ["核心"],
                "required": False,
                "provenance": "structural_recommendation",
                "matched_item_ids": [],
            }
        )
        payload["missing_evidence"].append(
            {
                "need_id": "need:tests",
                "category": "tests",
                "required": False,
                "reason": (
                    "recommended 核心 test evidence is missing "
                    "from the bounded context"
                ),
            }
        )
    payload["confidence"] = {"level": level, "reasons": reasons}

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.canonical_context_pack_bytes(payload)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_protected_present_confidence_requires_a_selected_result() -> None:
    models, _, serialization = _v2_modules()
    result_pack = _v2_ready_pack()
    result_payload = serialization.context_pack_payload(result_pack)
    anchor_item = replace(
        result_pack.items[0],
        source_kind="evidence_anchor",
        retrieval_rank=None,
        relevance_score=None,
    )
    anchor_pack = replace(
        result_pack,
        items=(anchor_item,),
        confidence=models.ReadinessConfidence(
            level="medium",
            reasons=(
                "all required evidence is selected",
                "protected original-direct evidence is absent",
            ),
        ),
    )
    anchor_payload = serialization.context_pack_payload(anchor_pack)
    forged = replace(
        anchor_pack,
        confidence=result_pack.confidence,
        budget=replace(anchor_pack.budget, pack_bytes=0),
    )

    assert result_payload["confidence"]["level"] == "high"
    assert anchor_payload["confidence"]["level"] == "medium"
    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(forged)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(
                pack,
                groups={**pack.groups, "implementations": ()},
            ),
            id="missing-group-membership",
        ),
        pytest.param(
            lambda pack: replace(pack, reading_order=()),
            id="missing-reading-order-membership",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                groups={
                    group: (("item:0",) if group == "supporting" else ())
                    for group in pack.groups
                },
            ),
            id="wrong-group-membership",
        ),
    ],
)
def test_v2_serialization_requires_complete_consistent_item_references(
    mutate,
) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda pack: replace(pack, status="READY"), id="status"),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], classification_basis="path_role"),),
            ),
            id="classification-basis",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], role="invented_role"),),
            ),
            id="role",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], source_kind="anchor"),),
            ),
            id="source-kind",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(pack.items[0], source_kind="evidence_anchor"),
                ),
            ),
            id="evidence-anchor-with-result-rank",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                evidence_needs=(
                    replace(pack.evidence_needs[0], provenance="query"),
                    pack.evidence_needs[1],
                ),
            ),
            id="provenance",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                confidence=replace(pack.confidence, level="certain"),
            ),
            id="confidence-level",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], relevance_score=float("nan")),),
            ),
            id="nan-score",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    pack.items[0],
                    replace(pack.items[0], file_path="src/duplicate.py"),
                ),
            ),
            id="duplicate-item-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                evidence_needs=(
                    pack.evidence_needs[0],
                    replace(
                        pack.evidence_needs[1],
                        id=pack.evidence_needs[0].id,
                    ),
                ),
            ),
            id="duplicate-need-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(
                        pack.items[0],
                        excerpts=(
                            replace(
                                pack.items[0].excerpts[0],
                                start_line=12,
                                end_line=11,
                            ),
                        ),
                    ),
                ),
            ),
            id="reversed-excerpt",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], reasons=["not a tuple"]),),
            ),
            id="non-json-contract-shape",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], reasons=(object(),)),),
            ),
            id="non-json-value",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], matched_need_ids=("need:missing",)),),
            ),
            id="missing-need-reference",
        ),
        pytest.param(
            lambda pack: replace(pack, reading_order=("item:missing",)),
            id="missing-item-reference",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(
                        pack.items[0],
                        excerpts=(
                            replace(
                                pack.items[0].excerpts[0],
                                content_bytes=(
                                    pack.items[0].excerpts[0].content_bytes + 1
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            id="excerpt-byte-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(
                    pack.budget,
                    content_bytes=pack.budget.content_bytes + 1,
                ),
            ),
            id="budget-byte-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, included_items=2),
            ),
            id="budget-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=True),
            ),
            id="bool-pack-bytes",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=-1),
            ),
            id="negative-pack-bytes",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=1),
            ),
            id="canonical-byte-mismatch",
        ),
    ],
)
def test_v2_serialization_rejects_malformed_records_with_fixed_error(mutate) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert exc_info.value.code == "context_failed"
    assert exc_info.value.message == "Context pack construction failed"
    assert str(exc_info.value) == "Context pack construction failed"


def test_v2_canonical_serialization_rejects_malformed_payload_keys() -> None:
    models, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_pack())
    payload["items"][0]["unexpected"] = "value"

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.canonical_context_pack_bytes(payload)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_omitted_count_may_exceed_compacted_public_preview() -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()

    payload = serialization.context_pack_payload(
        replace(
            pack,
            omissions=(),
            budget=replace(pack.budget, omitted_item_count=7),
        )
    )

    assert payload["omissions"] == []
    assert payload["budget"]["omitted_item_count"] == 7


@pytest.mark.parametrize(
    ("max_items", "omitted_item_count", "preview_count"),
    [(0, 1, 1), (1, 2, 2)],
)
def test_v2_serialization_caps_omission_preview_by_item_and_total_counts(
    max_items: int,
    omitted_item_count: int,
    preview_count: int,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    needs = tuple(
        replace(need, matched_item_ids=())
        for need in pack.evidence_needs
    )
    malformed = replace(
        pack,
        items=(),
        groups={group: () for group in models.CONTEXT_GROUPS},
        reading_order=(),
        evidence_needs=needs,
        missing_evidence=(
            models.MissingEvidence(
                need_id="need:implementation",
                category="implementations",
                required=True,
                reason=(
                    "required 核心 implementation evidence is missing "
                    "from the bounded context"
                ),
            ),
            pack.missing_evidence[0],
        ),
        next_queries=(),
        omissions=tuple(
            models.Omission(
                file_path=f"src/omitted-{index}.py",
                group="implementations",
                reason=(
                    "lower priority than selected evidence under the context budget"
                ),
                matched_need_ids=("need:implementation",),
            )
            for index in range(preview_count)
        ),
        budget=replace(
            pack.budget,
            max_items=max_items,
            included_items=0,
            included_excerpts=0,
            content_bytes=0,
            truncated_item_count=0,
            omitted_item_count=omitted_item_count,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_serialization_rejects_duplicate_source_lines_with_consistent_totals() -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    excerpt = pack.items[0].excerpts[0]
    overlapping = replace(excerpt, start_line=11, end_line=12)
    item = replace(pack.items[0], excerpts=(excerpt, overlapping))
    malformed = replace(
        pack,
        items=(item,),
        budget=replace(
            pack.budget,
            included_excerpts=2,
            content_bytes=excerpt.content_bytes * 2,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_serialization_rejects_duplicate_file_items_with_consistent_indexes() -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    duplicate = replace(
        pack.items[0],
        id="item:1",
        matched_need_ids=(),
    )
    malformed = replace(
        pack,
        items=(pack.items[0], duplicate),
        groups={
            group: (("item:0", "item:1") if group == "implementations" else ())
            for group in models.CONTEXT_GROUPS
        },
        reading_order=("item:0", "item:1"),
        budget=replace(
            pack.budget,
            included_items=2,
            included_excerpts=2,
            content_bytes=pack.budget.content_bytes * 2,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )
