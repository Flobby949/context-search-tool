from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import Any

import pytest

from context_search_tool.context_pack import (
    ContextBudget,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    ContextPackOptions,
    EvidenceNeed,
    ReadinessConfidence,
    build_context_pack,
)
from context_search_tool.context_pack.roles import normalize_candidates
from context_search_tool.exploration.goals import (
    EXPLICIT_ROLE_CLASSES,
    exact_satisfied,
    freeze_goals,
    goal_is_satisfied,
    satisfied_goal_ids,
    unsatisfied_goals,
)
from context_search_tool.exploration.models import (
    MAX_FROZEN_GOALS,
    MAX_FUSED_ANCHORS,
    MAX_FUSED_RESULTS,
    MAX_PLANNED_PROBES,
    MAX_PROBE_SEED_PATHS,
    MAX_PROBE_TEXT_CODE_POINTS,
    MAX_RETRIEVAL_CALLS,
    MAX_FOLLOWUP_PROBES,
    EvidenceOrigin,
    ExploredContext,
    ExplorationError,
    ExplorationGoal,
    FrozenGoals,
    FusedEvidenceState,
    ProbeCandidate,
)
from context_search_tool.models import EvidenceAnchor, RetrievalResult
from context_search_tool.retrieval import QueryBundle


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/fixtures/p4_exploration/input_manifest.json"


def _result(
    path: str,
    *,
    content: str = "source",
    protected: bool = True,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=1.0,
        score_parts={"evidence_priority": 0 if protected else 1},
        reasons=["direct"],
        followup_keywords=[],
    )


def _anchor(path: str, kind: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content="anchor",
        score=1.0,
        score_parts={"anchor": 1.0},
        reasons=["anchor"],
        anchor_kind=kind,
    )


def _bundle(
    query: str,
    results: tuple[RetrievalResult, ...] = (),
    anchors: tuple[EvidenceAnchor, ...] = (),
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=[],
        results=list(results),
        followup_keywords=[],
        evidence_anchors=list(anchors),
    )


def _item(
    path: str,
    *,
    group: str,
    role: str,
    item_id: str = "item-0",
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
                start_line=1,
                end_line=1,
                content=content,
                content_bytes=len(content.encode("utf-8")),
                truncated=False,
            ),
        ),
    )


def _pack(
    needs: tuple[EvidenceNeed, ...] = (),
    items: tuple[ContextItem, ...] = (),
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
        status="ready",
        items=items,
        groups=groups,
        reading_order=tuple(item.id for item in items),
        evidence_needs=needs,
        missing_evidence=(),
        next_queries=(),
        omissions=(),
        confidence=ReadinessConfidence(level="medium", reasons=()),
        budget=ContextBudget(
            max_items=32,
            max_excerpts_per_item=2,
            max_excerpt_bytes=4096,
            max_item_content_bytes=8192,
            max_total_content_bytes=49152,
            max_pack_bytes=65536,
            included_items=len(items),
            included_excerpts=len(items),
            content_bytes=0,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=0,
            budget_exhausted=False,
        ),
    )


def _built_pack(bundle: QueryBundle) -> ContextPack:
    return build_context_pack(
        bundle,
        ContextPackOptions(
            max_items=1,
            max_excerpts_per_item=2,
            max_excerpt_bytes=4096,
            max_item_content_bytes=8192,
            max_total_content_bytes=49152,
            max_pack_bytes=65536,
            context_before_lines=8,
            context_after_lines=12,
        ),
    )


def _need(
    ordinal: int,
    category: str,
    *,
    required: bool,
    matched: bool,
) -> EvidenceNeed:
    return EvidenceNeed(
        id=f"need-{ordinal}",
        category=category,
        subject_terms=("owner",),
        required=required,
        provenance="explicit_query",
        matched_item_ids=("item-0",) if matched else (),
    )


def test_internal_model_fields_and_fixed_limits_are_final() -> None:
    assert [field.name for field in fields(ExplorationGoal)] == [
        "id",
        "kind",
        "category",
        "accepted_roles",
        "subject_terms",
        "required",
        "provenance",
        "initially_satisfied",
    ]
    assert [field.name for field in fields(FrozenGoals)] == [
        "initial_evidence_need_count",
        "candidate_goal_count",
        "goals",
        "omitted_goal_count",
    ]
    assert [field.name for field in fields(ProbeCandidate)] == [
        "query",
        "source",
        "purpose",
        "goal_ids",
        "seed_paths",
        "required",
        "goal_order",
        "source_rank",
    ]
    assert [field.name for field in fields(EvidenceOrigin)] == [
        "file_path",
        "round_index",
        "probe_id",
        "source_kind",
        "source_rank",
        "selection_reason",
        "goal_ids",
    ]
    assert [field.name for field in fields(FusedEvidenceState)] == [
        "bundle",
        "origins",
        "satisfied_goal_ids",
    ]
    assert [field.name for field in fields(ExploredContext)] == [
        "initial_bundle",
        "initial_pack",
        "fused_bundle",
        "final_pack",
        "trace",
    ]
    assert [field.name for field in fields(ExplorationError)] == ["code", "message"]
    assert (
        MAX_FOLLOWUP_PROBES,
        MAX_RETRIEVAL_CALLS,
        MAX_FROZEN_GOALS,
        MAX_PLANNED_PROBES,
        MAX_PROBE_TEXT_CODE_POINTS,
        MAX_PROBE_SEED_PATHS,
        MAX_FUSED_RESULTS,
        MAX_FUSED_ANCHORS,
    ) == (2, 3, 8, 8, 160, 3, 24, 8)


def test_internal_models_are_frozen() -> None:
    goal = ExplorationGoal(
        "g",
        "need",
        "tests",
        (),
        ("owner",),
        True,
        "context_need",
        False,
    )
    frozen = FrozenGoals(1, 1, (goal,), 0)
    probe = ProbeCandidate("owner test", "path_stem", "test", ("g",), (), True, 0, 0)
    origin = EvidenceOrigin("src/Owner.java", 0, "r0p0", "result", 0, "initial", ("g",))
    bundle = _bundle("owner")
    state = FusedEvidenceState(bundle, (origin,), ("g",))
    pack = _pack()
    explored = ExploredContext(bundle, pack, bundle, pack, "trace")
    error = ExplorationError()
    for instance, field_name in (
        (goal, "id"),
        (frozen, "candidate_goal_count"),
        (probe, "query"),
        (origin, "file_path"),
        (state, "satisfied_goal_ids"),
        (explored, "trace"),
        (error, "message"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field_name, "changed")
    assert str(error) == "Controlled exploration failed"


def test_goal_freeze_uses_complete_six_class_order() -> None:
    controller_path = "src/main/java/com/example/owner/OwnerController.java"
    bundle = _bundle(
        "OwnerController form",
        (_result(controller_path, content="class OwnerController {}"),),
    )
    pack = _pack(
        (
            _need(0, "tests", required=True, matched=False),
            _need(1, "entrypoints", required=True, matched=True),
            _need(2, "implementations", required=False, matched=False),
            _need(3, "configs_docs", required=False, matched=True),
        ),
        (_item(controller_path, group="entrypoints", role="entrypoint"),),
    )

    frozen = freeze_goals(bundle.query, bundle, pack)

    assert [
        (goal.provenance, goal.category, goal.required, goal.initially_satisfied)
        for goal in frozen.goals
    ] == [
        ("context_need", "tests", True, False),
        ("explicit_query_role", "entrypoints", True, False),
        ("context_need", "entrypoints", True, True),
        ("context_need", "implementations", False, False),
        ("structural_cluster", "related_types", False, False),
        ("context_need", "configs_docs", False, True),
    ]
    assert (frozen.initial_evidence_need_count, frozen.candidate_goal_count) == (4, 6)
    assert frozen.omitted_goal_count == 0


def test_all_needs_become_candidates_before_exact_eight_goal_cap() -> None:
    categories = (
        "entrypoints",
        "implementations",
        "related_types",
        "tests",
        "configs_docs",
    )
    needs = tuple(
        _need(index, categories[index % len(categories)], required=True, matched=False)
        for index in range(10)
    )

    frozen = freeze_goals("plain query", _bundle("plain query"), _pack(needs))

    assert frozen.initial_evidence_need_count == 10
    assert frozen.candidate_goal_count == 10
    assert len(frozen.goals) == MAX_FROZEN_GOALS
    assert frozen.omitted_goal_count == 2
    assert [goal.id for goal in frozen.goals] == [
        f"goal-need-{categories[index % len(categories)]}-{index}"
        for index in range(8)
    ]


def test_goal_ids_are_independent_of_source_content() -> None:
    path = "src/main/java/com/example/owner/OwnerController.java"
    pack = _pack(
        (_need(0, "entrypoints", required=True, matched=True),),
        (_item(path, group="entrypoints", role="entrypoint"),),
    )
    first = freeze_goals(
        "OwnerController",
        _bundle("OwnerController", (_result(path, content="FIRST"),)),
        pack,
    )
    second = freeze_goals(
        "OwnerController",
        _bundle("OwnerController", (_result(path, content="SECOND"),)),
        pack,
    )
    assert [goal.id for goal in first.goals] == [goal.id for goal in second.goals]


def test_satisfied_goals_remain_in_denominator_but_not_unsatisfied_work() -> None:
    needs = (
        _need(0, "entrypoints", required=True, matched=True),
        _need(1, "tests", required=False, matched=False),
    )
    frozen = freeze_goals("plain query", _bundle("plain query"), _pack(needs))
    assert len(frozen.goals) == 2
    assert [goal.category for goal in unsatisfied_goals(frozen)] == ["tests"]


def test_context_needs_suppress_duplicate_structural_categories() -> None:
    path = "src/main/java/com/example/owner/OwnerController.java"
    bundle = _bundle("OwnerController", (_result(path),))
    pack = _pack(
        (
            _need(0, "entrypoints", required=True, matched=True),
            _need(1, "implementations", required=False, matched=False),
            _need(2, "tests", required=False, matched=False),
        ),
        (_item(path, group="entrypoints", role="entrypoint"),),
    )

    frozen = freeze_goals(bundle.query, bundle, pack)

    structural_categories = [
        goal.category
        for goal in frozen.goals
        if goal.provenance == "structural_cluster"
    ]
    assert structural_categories == ["related_types"]


def test_freeze_api_has_no_followup_input_surface() -> None:
    assert tuple(inspect.signature(freeze_goals).parameters) == (
        "query",
        "initial_bundle",
        "initial_pack",
    )


@pytest.mark.parametrize(
    ("path", "content", "anchor_kind", "expected_role"),
    [
        ("templates/owner.html", "", None, "view"),
        ("src/views/Owner.vue", "", None, "view_page"),
        ("src/App.tsx", "", None, "layout_component"),
        ("backend/components/Widget.java", "", None, "component"),
        ("src/components/Widget.vue", "", None, "shared_component"),
        ("backend/state/owner.py", "", None, "state_store"),
        ("src/stores/owner.ts", "", None, "store"),
        ("tests/test_owner.py", "", None, "test"),
        ("deploy/Dockerfile", "", None, "deployment_config"),
        ("examples/settings.json", "", None, "config_example"),
        ("config/settings.json", "", None, "runtime_config"),
        ("vite.config.ts", "", None, "config"),
        ("evidence/pom.bin", "", "pom", "pom"),
        ("README.md", "", None, "doc"),
        ("controllers/OwnerController.java", "", None, "entrypoint"),
        ("routers/owner.py", "", None, "router"),
        ("commands/owner.py", "", None, "command"),
        ("handlers/owner.py", "", None, "handler"),
        ("src/router/index.ts", "", None, "route_config"),
        ("service/impl/OwnerServiceImpl.java", "", None, "service_impl"),
        ("backend/OwnerExecutor.java", "", None, "executor"),
        ("backend/engine.py", "", None, "engine"),
        ("middleware/auth.py", "", None, "middleware"),
        ("storage/owner.py", "", None, "storage"),
        ("service/owner.py", "", None, "service"),
        ("repositories/OwnerRepository.java", "", None, "repository"),
        ("adapters/owner.py", "", None, "source_adapter"),
        ("hooks/useOwner.ts", "", None, "composable"),
        ("scheduler/owner.py", "", None, "scheduler"),
        ("src/utils/owner.ts", "", None, "utility"),
    ],
)
def test_every_explicit_role_is_produced_by_current_classifier_stack(
    path: str,
    content: str,
    anchor_kind: str | None,
    expected_role: str,
) -> None:
    bundle = (
        _bundle("role", anchors=(_anchor(path, anchor_kind),))
        if anchor_kind is not None
        else _bundle("role", (_result(path, content=content),))
    )
    candidate = normalize_candidates(bundle)[0]
    assert candidate.role == expected_role
    assert any(
        expected_role in role_class.accepted_roles
        for role_class in EXPLICIT_ROLE_CLASSES
    )


def test_explicit_role_table_contains_only_classifier_producible_roles() -> None:
    produced = {
        "view",
        "view_page",
        "layout_component",
        "component",
        "shared_component",
        "state_store",
        "store",
        "test",
        "deployment_config",
        "config_example",
        "runtime_config",
        "config",
        "pom",
        "doc",
        "entrypoint",
        "router",
        "command",
        "handler",
        "route_config",
        "service_impl",
        "executor",
        "engine",
        "middleware",
        "storage",
        "service",
        "repository",
        "source_adapter",
        "composable",
        "scheduler",
        "utility",
    }
    assert {role for item in EXPLICIT_ROLE_CLASSES for role in item.accepted_roles} == produced


@pytest.mark.parametrize(
    ("assay_index", "path", "content"),
    [
        (0, "src/main/java/com/example/owner/OwnerController.java", "class OwnerController {}"),
        (1, "src/views/qrcode/QRCodeTool.vue", "<template>QRCode</template>"),
    ],
)
def test_frozen_java_and_frontend_queries_match_recorded_required_role_classes(
    assay_index: int,
    path: str,
    content: str,
) -> None:
    assay = json.loads(MANIFEST.read_text(encoding="utf-8"))["assays"][assay_index]
    bundle = _bundle(assay["query"], (_result(path, content=content),))
    frozen = freeze_goals(bundle.query, bundle, _built_pack(bundle))
    actual = [
        {
            "category": goal.category,
            "accepted_roles": list(goal.accepted_roles),
        }
        for goal in frozen.goals
        if goal.provenance == "explicit_query_role"
    ]
    expected = [
        {
            "category": item["category"],
            "accepted_roles": item["accepted_roles"],
        }
        for item in assay["expected_required_goal_classes"]
    ]
    assert actual == expected


def test_exact_satisfied_requires_identifier_protected_path_and_required_goals() -> None:
    path = "src/main/java/com/example/owner/OwnerController.java"
    exact_bundle = _bundle("OwnerController", (_result(path),))
    exact_goals = freeze_goals(
        exact_bundle.query,
        exact_bundle,
        _built_pack(exact_bundle),
    )
    assert exact_satisfied(exact_bundle.query, exact_bundle, exact_goals) is True

    test_bundle = _bundle("OwnerController test", (_result(path),))
    test_goals = freeze_goals(
        test_bundle.query,
        test_bundle,
        _built_pack(test_bundle),
    )
    assert exact_satisfied(test_bundle.query, test_bundle, test_goals) is False

    unprotected = _bundle("OwnerController", (_result(path, protected=False),))
    assert exact_satisfied(
        unprotected.query,
        unprotected,
        freeze_goals(unprotected.query, unprotected, _built_pack(unprotected)),
    ) is False


def test_role_goal_matches_across_nominal_group_and_need_matching_reuses_subjects() -> None:
    shared = _item(
        "src/components/Owner.vue",
        group="implementations",
        role="shared_component",
        content="Owner component",
    )
    role_goal = ExplorationGoal(
        "role",
        "role_gap",
        "supporting",
        ("shared_component",),
        ("owner",),
        True,
        "explicit_query_role",
        False,
    )
    need_goal = replace(
        role_goal,
        id="need",
        kind="need",
        category="implementations",
        accepted_roles=(),
        provenance="context_need",
    )
    pack = _pack(items=(shared,))

    assert goal_is_satisfied(role_goal, pack) is True
    assert goal_is_satisfied(need_goal, pack) is True
    frozen = FrozenGoals(2, 2, (role_goal, need_goal), 0)
    assert satisfied_goal_ids(frozen, pack) == ("role", "need")
