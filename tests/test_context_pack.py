from collections import Counter
from dataclasses import replace
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
    ContextBudget,
    ContextPack,
    ContextPackError,
    ContextPackOptions,
    resolve_context_pack_options,
)
from context_search_tool.models import EvidenceAnchor, RetrievalResult, RetrievalSummary
from context_search_tool.retrieval import QueryBundle


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
    evidence_anchors: list[EvidenceAnchor] | None = None,
    summary: RetrievalSummary | None = None,
) -> QueryBundle:
    return QueryBundle(
        query="fixture query",
        expanded_tokens=[],
        results=list(results or ()),
        followup_keywords=[],
        summary=summary if summary is not None else RetrievalSummary(),
        evidence_anchors=list(evidence_anchors or ()),
    )


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


def test_empty_and_nonempty_packs_use_temporary_task_two_scaffold() -> None:
    empty_pack = context_pack.build_context_pack(query_bundle(), options())
    ready_pack = context_pack.build_context_pack(
        query_bundle([result("src/plain.py")]),
        options(),
    )

    assert empty_pack.status == "empty"
    assert empty_pack.missing_evidence == ()
    assert empty_pack.next_queries == ()
    assert (empty_pack.confidence.level, empty_pack.confidence.reasons) == ("none", ())
    assert ready_pack.status == "ready"
    assert ready_pack.missing_evidence == ()
    assert ready_pack.next_queries == ()
    assert (ready_pack.confidence.level, ready_pack.confidence.reasons) == ("medium", ())


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
