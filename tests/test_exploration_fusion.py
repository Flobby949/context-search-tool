from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextPack,
    ContextPackOptions,
    build_context_pack,
    canonical_context_pack_bytes,
)
from context_search_tool.exploration import fusion
from context_search_tool.exploration.goals import satisfied_goal_ids
from context_search_tool.exploration.models import (
    MAX_FUSED_ANCHORS,
    MAX_FUSED_RESULTS,
    EvidenceOrigin,
    ExplorationGoal,
    FrozenGoals,
    ProbeCandidate,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSummary,
    SemanticMatch,
)
from context_search_tool.retrieval import QueryBundle


OPTIONS = ContextPackOptions(
    max_items=32,
    max_excerpts_per_item=2,
    max_excerpt_bytes=4096,
    max_item_content_bytes=8192,
    max_total_content_bytes=49152,
    max_pack_bytes=65536,
    context_before_lines=8,
    context_after_lines=12,
)


def _result(
    path: str,
    content: str,
    *,
    protected: bool = False,
    score: float = 0.75,
    reason: str = "retrieval reason",
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=score,
        score_parts={"evidence_priority": 0 if protected else 2, "lexical": 0.4},
        reasons=[reason],
        followup_keywords=["local"],
        semantic_matches=[SemanticMatch("original", 0.8)],
    )


def _anchor(
    path: str,
    content: str,
    *,
    kind: str = "readme",
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=0.5,
        score_parts={"anchor": 0.5},
        reasons=["anchor reason"],
        anchor_kind=kind,
        semantic_matches=[SemanticMatch("planner:0", 0.6)],
    )


def _bundle(
    *,
    query: str = "alpha beta test",
    results: tuple[RetrievalResult, ...] = (),
    anchors: tuple[EvidenceAnchor, ...] = (),
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=["alpha", "beta"],
        results=list(results),
        followup_keywords=["top-level"],
        summary=RetrievalSummary(
            entry_points=["entry"],
            implementation=["implementation"],
            related_types=["type"],
            possibly_legacy=["legacy"],
        ),
        planner=QueryPlan(
            original_query=query,
            status="ok",
            rewritten_queries=["alpha test"],
        ),
        evidence_anchors=list(anchors),
        query_variants=[QueryVariant("original", query, "original")],
        variant_retrieval_status="complete",
    )


def _goal(goal_id: str, subject: str, *, required: bool = True) -> ExplorationGoal:
    return ExplorationGoal(
        id=goal_id,
        kind="need",
        category="tests",
        accepted_roles=(),
        subject_terms=(subject,),
        required=required,
        provenance="context_need",
        initially_satisfied=False,
    )


def _frozen(*goals: ExplorationGoal) -> FrozenGoals:
    return FrozenGoals(len(goals), len(goals), tuple(goals), 0)


def _probe(*goal_ids: str, purpose: str = "tests") -> ProbeCandidate:
    return ProbeCandidate(
        query="grounded test probe",
        source="indexed_symbol",
        purpose=purpose,
        goal_ids=tuple(goal_ids),
        seed_paths=("tests/test_subject.py",),
        required=True,
        goal_order=0,
        source_rank=1,
    )


def _pack(bundle: QueryBundle, options: ContextPackOptions = OPTIONS) -> ContextPack:
    return build_context_pack(bundle, options)


def _state(
    initial: QueryBundle,
    frozen: FrozenGoals,
    options: ContextPackOptions = OPTIONS,
):
    return fusion.initialize_fusion(initial, _pack(initial, options), frozen)


def _add(
    state,
    probe_bundle: QueryBundle,
    frozen: FrozenGoals,
    *,
    probe: ProbeCandidate | None = None,
    probe_id: str = "r1p0",
    options: ContextPackOptions = OPTIONS,
):
    return fusion.add_probe_evidence(
        state,
        probe_bundle,
        frozen,
        options,
        probe=probe or _probe(*(goal.id for goal in frozen.goals)),
        round_index=1,
        probe_id=probe_id,
    )


def test_initial_fusion_dedupes_by_kind_and_result_wins_cross_kind_collision() -> None:
    first = _result("tests/test_first.py", "alpha")
    duplicate = replace(first, content="must not replace first")
    second = _result("tests/test_second.py", "beta")
    collided_anchor = _anchor("tests/test_second.py", "anchor collision")
    anchor = _anchor("README.md", "alpha docs")
    duplicate_anchor = replace(anchor, content="must not replace anchor")
    initial = _bundle(
        results=(first, duplicate, second),
        anchors=(collided_anchor, anchor, duplicate_anchor),
    )
    before = copy.deepcopy(initial)

    state = _state(initial, _frozen())

    assert state.bundle.results == [first, second]
    assert state.bundle.evidence_anchors == [anchor]
    assert initial == before
    assert state.bundle.results is not initial.results
    assert state.bundle.results[0].score_parts is not first.score_parts
    assert state.origins == (
        EvidenceOrigin(
            "tests/test_first.py",
            0,
            "r0p0",
            "result",
            1,
            "retained_initial_evidence",
            (),
        ),
        EvidenceOrigin(
            "tests/test_second.py",
            0,
            "r0p0",
            "result",
            3,
            "retained_initial_evidence",
            (),
        ),
        EvidenceOrigin(
            "README.md",
            0,
            "r0p0",
            "evidence_anchor",
            2,
            "selected_evidence_anchor",
            (),
        ),
    )


def test_fusion_caps_results_and_anchors_exactly() -> None:
    initial = _bundle(
        results=tuple(
            _result(f"tests/test_result_{index:02}.py", "alpha")
            for index in range(MAX_FUSED_RESULTS + 2)
        ),
        anchors=tuple(
            _anchor(f"docs/anchor_{index:02}.md", "docs")
            for index in range(MAX_FUSED_ANCHORS + 2)
        ),
    )

    state = _state(initial, _frozen())

    assert len(state.bundle.results) == MAX_FUSED_RESULTS
    assert len(state.bundle.evidence_anchors) == MAX_FUSED_ANCHORS
    assert state.bundle.results[-1].file_path.as_posix() == "tests/test_result_23.py"
    assert state.bundle.evidence_anchors[-1].file_path.as_posix() == "docs/anchor_07.md"


def test_novel_paths_append_by_probe_rank_without_moving_initial_slots() -> None:
    initial = _bundle(
        results=(
            _result("tests/test_initial_0.py", "alpha"),
            _result("tests/test_initial_1.py", "alpha"),
        ),
        anchors=(_anchor("docs/initial.md", "alpha docs"),),
    )
    probe_bundle = _bundle(
        query="probe",
        results=(
            _result("tests/test_novel_1.py", "beta"),
            _result("tests/test_novel_2.py", "beta"),
        ),
        anchors=(
            _anchor("tests/test_novel_2.py", "result wins"),
            _anchor("docs/novel.md", "beta docs"),
        ),
    )
    state = _state(initial, _frozen())

    fused, _ = _add(state, probe_bundle, _frozen())

    assert [item.file_path.as_posix() for item in fused.bundle.results] == [
        "tests/test_initial_0.py",
        "tests/test_initial_1.py",
        "tests/test_novel_1.py",
        "tests/test_novel_2.py",
    ]
    assert [item.file_path.as_posix() for item in fused.bundle.evidence_anchors] == [
        "docs/initial.md",
        "docs/novel.md",
    ]
    origins = {origin.file_path: origin for origin in fused.origins}
    assert origins["tests/test_novel_1.py"].source_rank == 1
    assert origins["tests/test_novel_2.py"].source_rank == 2
    assert origins["docs/novel.md"].source_rank == 2


@pytest.mark.parametrize(
    ("protected", "old_content", "new_content"),
    [
        (True, "alpha", "alpha beta"),
        (False, "alpha", "alpha"),
        (False, "alpha", "beta"),
        (False, "alpha beta", "alpha gamma"),
    ],
    ids=("protected", "equal", "disjoint", "non-superset"),
)
def test_same_path_followup_does_not_replace_without_an_unprotected_proper_superset(
    protected: bool,
    old_content: str,
    new_content: str,
) -> None:
    path = "tests/test_subject.py"
    old = _result(path, old_content, protected=protected)
    initial = _bundle(results=(old,))
    goals = (_goal("goal-alpha", "alpha"), _goal("goal-beta", "beta"))
    if "gamma" in new_content:
        goals += (_goal("goal-gamma", "gamma"),)
    frozen = _frozen(*goals)
    state = _state(initial, frozen)

    fused, _ = _add(
        state,
        _bundle(query="probe", results=(_result(path, new_content),)),
        frozen,
    )

    assert fused.bundle.results[0] == old
    assert fused.origins[0].round_index == 0


def test_proper_superset_replacement_is_rejected_if_rebuilt_pack_loses_prior_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "tests/test_subject.py"
    initial = _bundle(results=(_result(path, "alpha"),))
    frozen = _frozen(_goal("goal-alpha", "alpha"), _goal("goal-beta", "beta"))
    state = _state(initial, frozen)
    real_build = fusion.build_context_pack

    def lossy_build(bundle: QueryBundle, options: ContextPackOptions) -> ContextPack:
        if any("beta" in result.content for result in bundle.results):
            return real_build(bundle, replace(options, max_items=0))
        return real_build(bundle, options)

    monkeypatch.setattr(fusion, "build_context_pack", lossy_build)

    fused, final_pack = _add(
        state,
        _bundle(query="probe", results=(_result(path, "alpha beta"),)),
        frozen,
    )

    assert fused.bundle.results[0].content == "alpha"
    assert fused.satisfied_goal_ids == ("goal-alpha",)
    assert satisfied_goal_ids(frozen, final_pack) == ("goal-alpha",)


def test_unprotected_proper_superset_replaces_and_adapts_followup_provenance() -> None:
    path = "tests/test_subject.py"
    initial = _bundle(results=(_result(path, "alpha"),))
    frozen = _frozen(
        _goal("goal-alpha", "alpha"),
        _goal("goal-beta", "beta", required=False),
    )
    state = _state(initial, frozen)
    followup = _result(
        path,
        "alpha beta",
        protected=True,
        score=0.625,
        reason="probe-local reason must be replaced",
    )
    probe_bundle = _bundle(query="probe", results=(followup,))
    before = copy.deepcopy(probe_bundle)

    fused, final_pack = _add(state, probe_bundle, frozen)

    winner = fused.bundle.results[0]
    assert winner.content == "alpha beta"
    assert winner.score == 0.625
    assert winner.score_parts == {"evidence_priority": 1.0, "lexical": 0.4}
    assert winner.reasons == ["exploration:r1p0:tests"]
    assert winner.semantic_matches == []
    assert probe_bundle == before
    assert fused.satisfied_goal_ids == ("goal-alpha", "goal-beta")
    assert satisfied_goal_ids(frozen, final_pack) == fused.satisfied_goal_ids
    assert fused.origins == (
        EvidenceOrigin(
            path,
            1,
            "r1p0",
            "result",
            1,
            "replaced_by_goal_covering_probe",
            ("goal-alpha", "goal-beta"),
        ),
    )


def test_followup_anchor_is_adapted_without_cross_query_score_merging() -> None:
    initial = _bundle(results=(_result("tests/test_initial.py", "alpha"),))
    frozen = _frozen()
    state = _state(initial, frozen)
    followup = _anchor("docs/followup.md", "beta docs")

    fused, _ = _add(
        state,
        _bundle(query="probe", anchors=(followup,)),
        frozen,
        probe=_probe(purpose="configs_docs"),
    )

    winner = fused.bundle.evidence_anchors[-1]
    assert winner.score == followup.score
    assert winner.score_parts == {"anchor": 0.5, "evidence_priority": 1.0}
    assert winner.reasons == ["exploration:r1p0:configs_docs"]
    assert winner.semantic_matches == []
    assert fused.origins[-1].selection_reason == "selected_evidence_anchor"


def test_synthetic_bundle_preserves_initial_top_level_fields_and_pack_is_canonical() -> None:
    initial = _bundle(results=(_result("tests/test_initial.py", "alpha"),))
    frozen = _frozen(_goal("goal-alpha", "alpha"), _goal("goal-beta", "beta"))
    state = _state(initial, frozen)

    fused, final_pack = _add(
        state,
        _bundle(
            query="must not escape into synthetic bundle",
            results=(_result("tests/test_beta.py", "beta"),),
        ),
        frozen,
    )

    assert fused.bundle.query == initial.query
    assert fused.bundle.expanded_tokens == initial.expanded_tokens
    assert fused.bundle.planner == initial.planner
    assert fused.bundle.query_variants == initial.query_variants
    assert fused.bundle.variant_retrieval_status == initial.variant_retrieval_status
    assert fused.bundle.summary == initial.summary
    assert fused.bundle.followup_keywords == initial.followup_keywords
    assert canonical_context_pack_bytes(final_pack) == canonical_context_pack_bytes(
        build_context_pack(fused.bundle, OPTIONS)
    )
    assert set(final_pack.groups) == set(CONTEXT_GROUPS)
    assert final_pack.budget.included_items <= OPTIONS.max_items
    assert final_pack.budget.content_bytes <= OPTIONS.max_total_content_bytes
    assert final_pack.budget.pack_bytes <= OPTIONS.max_pack_bytes
    assert fused.satisfied_goal_ids == ("goal-alpha", "goal-beta")
    assert frozen.goals == (
        _goal("goal-alpha", "alpha"),
        _goal("goal-beta", "beta"),
    )
