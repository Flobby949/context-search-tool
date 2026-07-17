from __future__ import annotations

import copy
import json
import math
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from context_search_tool.context_pack import CONTEXT_GROUPS
from context_search_tool.retrieval import evidence_anchor_top_k
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    ExplorationGoalRecord,
    ExplorationLimits,
    ExplorationProbe,
    ExplorationRound,
    ExplorationTrace,
    ExplorationTraceError,
    FinalEvidence,
    TraceLimits,
    canonical_exploration_trace_bytes,
    exploration_trace_payload,
)


def _source_counts(**values: int) -> tuple[tuple[str, int], ...]:
    return tuple((key, values.get(key, 0)) for key in SOURCE_COUNT_KEYS)


def _goals() -> tuple[ExplorationGoalRecord, ...]:
    return (
        ExplorationGoalRecord(
            id="goal-test",
            kind="need",
            category="tests",
            accepted_roles=(),
            required=True,
            provenance="context_need",
            initially_satisfied=True,
            finally_satisfied=True,
        ),
        ExplorationGoalRecord(
            id="goal-view",
            kind="role_gap",
            category="entrypoints",
            accepted_roles=("view", "view_page"),
            required=False,
            provenance="explicit_query_role",
            initially_satisfied=False,
            finally_satisfied=True,
        ),
    )


def _initial_probe(**changes: object) -> ExplorationProbe:
    probe = ExplorationProbe(
        id="r0p0",
        query="show src/Owner.java and tests",
        purpose="original_query",
        source="original",
        goal_ids=(),
        seed_paths=(),
        retrieval_outcome="complete",
        retrieval_termination_reason="completed",
        duration_ms=2,
        result_count=1,
        evidence_anchor_count=0,
        unique_path_count=1,
        duplicate_path_count=0,
        novel_path_count=1,
        newly_satisfied_goal_ids=("goal-test",),
        source_counts=_source_counts(lexical=1),
        final_selection_count=1,
    )
    return replace(probe, **changes)


def _followup_probe(**changes: object) -> ExplorationProbe:
    probe = ExplorationProbe(
        id="r1p0",
        query="OwnerForm form template view",
        purpose="find_missing_recommended_entrypoints",
        source="indexed_symbol",
        goal_ids=("goal-view",),
        seed_paths=("src/Owner.java",),
        retrieval_outcome="complete",
        retrieval_termination_reason="completed",
        duration_ms=3,
        result_count=1,
        evidence_anchor_count=0,
        unique_path_count=1,
        duplicate_path_count=0,
        novel_path_count=1,
        newly_satisfied_goal_ids=("goal-view",),
        source_counts=_source_counts(signal=1),
        final_selection_count=1,
    )
    return replace(probe, **changes)


def _rounds() -> tuple[ExplorationRound, ...]:
    return (
        ExplorationRound(
            round_index=0,
            kind="initial",
            duration_ms=3,
            input_path_count=0,
            output_path_count=1,
            novel_path_count=1,
            duplicate_path_count=0,
            newly_satisfied_goal_ids=("goal-test",),
            probes=(_initial_probe(),),
        ),
        ExplorationRound(
            round_index=1,
            kind="followup",
            duration_ms=4,
            input_path_count=1,
            output_path_count=2,
            novel_path_count=1,
            duplicate_path_count=0,
            newly_satisfied_goal_ids=("goal-view",),
            probes=(_followup_probe(),),
        ),
    )


def _final_evidence() -> tuple[FinalEvidence, ...]:
    return (
        FinalEvidence(
            item_id="item:0",
            file_path="tests/test_owner.py",
            source_round=0,
            probe_id="r0p0",
            probe_rank=1,
            goal_ids=("goal-test",),
            selection_reason="retained_initial_evidence",
        ),
        FinalEvidence(
            item_id="item:1",
            file_path="src/views/OwnerForm.vue",
            source_round=1,
            probe_id="r1p0",
            probe_rank=1,
            goal_ids=("goal-view",),
            selection_reason="added_novel_probe_evidence",
        ),
    )


def _trace(**changes: object) -> ExplorationTrace:
    trace = ExplorationTrace(
        schema_version=2,
        mode="exploration",
        outcome="complete",
        termination_reason="satisfied",
        duration_ms=10,
        limits=ExplorationLimits(effective_initial_top_k=2),
        initial_evidence_need_count=1,
        candidate_goal_count=2,
        retained_goal_count=2,
        omitted_goal_count=0,
        initial_satisfied_goal_count=1,
        final_satisfied_goal_count=2,
        planned_probe_count=1,
        executed_probe_count=1,
        stale_skipped_probe_count=0,
        unexecuted_probe_count=0,
        retrieval_call_count=2,
        goals=_goals(),
        rounds=_rounds(),
        final_evidence_count=2,
        final_evidence_omitted_count=0,
        final_evidence=_final_evidence(),
    )
    return replace(trace, **changes)


def test_exploration_trace_model_fields_are_exact_and_frozen() -> None:
    assert [field.name for field in fields(ExplorationLimits)] == [
        "max_rounds",
        "max_followup_probes",
        "max_retrieval_calls",
        "max_planned_probes",
        "max_goals",
        "max_probe_code_points",
        "max_seed_paths",
        "max_frontend_import_header_bytes",
        "max_frontend_import_paths",
        "effective_initial_top_k",
        "followup_top_k",
        "max_fused_results",
        "max_fused_anchors",
        "final_evidence_top_k",
    ]
    assert [field.name for field in fields(ExplorationGoalRecord)] == [
        "id",
        "kind",
        "category",
        "accepted_roles",
        "required",
        "provenance",
        "initially_satisfied",
        "finally_satisfied",
    ]
    assert [field.name for field in fields(ExplorationProbe)] == [
        "id",
        "query",
        "purpose",
        "source",
        "goal_ids",
        "seed_paths",
        "retrieval_outcome",
        "retrieval_termination_reason",
        "duration_ms",
        "result_count",
        "evidence_anchor_count",
        "unique_path_count",
        "duplicate_path_count",
        "novel_path_count",
        "newly_satisfied_goal_ids",
        "source_counts",
        "final_selection_count",
    ]
    assert [field.name for field in fields(ExplorationRound)] == [
        "round_index",
        "kind",
        "duration_ms",
        "input_path_count",
        "output_path_count",
        "novel_path_count",
        "duplicate_path_count",
        "newly_satisfied_goal_ids",
        "probes",
    ]
    assert [field.name for field in fields(FinalEvidence)] == [
        "item_id",
        "file_path",
        "source_round",
        "probe_id",
        "probe_rank",
        "goal_ids",
        "selection_reason",
    ]
    assert [field.name for field in fields(ExplorationTrace)] == [
        "schema_version",
        "mode",
        "outcome",
        "termination_reason",
        "duration_ms",
        "limits",
        "initial_evidence_need_count",
        "candidate_goal_count",
        "retained_goal_count",
        "omitted_goal_count",
        "initial_satisfied_goal_count",
        "final_satisfied_goal_count",
        "planned_probe_count",
        "executed_probe_count",
        "stale_skipped_probe_count",
        "unexecuted_probe_count",
        "retrieval_call_count",
        "goals",
        "rounds",
        "final_evidence_count",
        "final_evidence_omitted_count",
        "final_evidence",
    ]

    trace = _trace()
    with pytest.raises(FrozenInstanceError):
        trace.outcome = "empty"  # type: ignore[misc]


def test_exploration_limits_are_exact_and_cover_complete_v1_previews() -> None:
    limits = ExplorationLimits(effective_initial_top_k=12)
    assert tuple(getattr(limits, field.name) for field in fields(limits)) == (
        2,
        2,
        3,
        8,
        8,
        160,
        3,
        16_384,
        3,
        12,
        6,
        24,
        8,
        20,
    )
    assert 12 + evidence_anchor_top_k(12) == 16 <= TraceLimits().final_selection_top_k
    assert 6 + evidence_anchor_top_k(6) == 8 <= TraceLimits().final_selection_top_k


def test_payload_uses_exact_key_order_at_every_level() -> None:
    payload = exploration_trace_payload(_trace())
    assert tuple(payload) == tuple(field.name for field in fields(ExplorationTrace))
    assert tuple(payload["limits"]) == tuple(
        field.name for field in fields(ExplorationLimits)
    )
    assert tuple(payload["goals"][0]) == tuple(
        field.name for field in fields(ExplorationGoalRecord)
    )
    assert tuple(payload["rounds"][0]) == tuple(
        field.name for field in fields(ExplorationRound)
    )
    assert tuple(payload["rounds"][0]["probes"][0]) == tuple(
        field.name for field in fields(ExplorationProbe)
    )
    assert tuple(payload["rounds"][0]["probes"][0]["source_counts"]) == (
        SOURCE_COUNT_KEYS
    )
    assert tuple(payload["final_evidence"][0]) == tuple(
        field.name for field in fields(FinalEvidence)
    )


def test_canonical_bytes_are_compact_ordered_utf8_and_reject_non_models() -> None:
    trace = _trace()
    payload = exploration_trace_payload(trace)
    expected = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert canonical_exploration_trace_bytes(trace) == expected
    assert canonical_exploration_trace_bytes(trace).startswith(
        b'{"schema_version":2,"mode":"exploration"'
    )
    with pytest.raises(ExplorationTraceError):
        exploration_trace_payload(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ExplorationLimits(max_rounds=3),
        lambda: ExplorationLimits(effective_initial_top_k=0),
        lambda: replace(_goals()[0], category="unknown"),
        lambda: replace(_goals()[0], accepted_roles=("test", "test")),
        lambda: replace(
            _goals()[0],
            initially_satisfied=True,
            finally_satisfied=False,
        ),
        lambda: _followup_probe(source="untrusted_source"),
        lambda: _followup_probe(purpose="free form"),
        lambda: _followup_probe(seed_paths=("../escape.py",)),
        lambda: _followup_probe(query="x" * 161),
        lambda: _followup_probe(duration_ms=math.nan),
        lambda: _followup_probe(source_counts=tuple(reversed(_source_counts()))),
        lambda: _followup_probe(novel_path_count=0),
        lambda: _followup_probe(
            retrieval_outcome="failed",
            retrieval_termination_reason="query_error",
            result_count=1,
            unique_path_count=1,
            novel_path_count=1,
            final_selection_count=1,
        ),
    ],
)
def test_nested_models_reject_noncanonical_values(factory) -> None:
    with pytest.raises(ExplorationTraceError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _trace(outcome="empty", termination_reason="satisfied"),
        lambda: _trace(schema_version=1),
        lambda: _trace(mode="trace"),
        lambda: _trace(candidate_goal_count=3),
        lambda: _trace(initial_satisfied_goal_count=0),
        lambda: _trace(planned_probe_count=2),
        lambda: _trace(retrieval_call_count=3),
        lambda: _trace(goals=(_goals()[0], _goals()[0])),
        lambda: _trace(
            rounds=(
                _rounds()[0],
                replace(_rounds()[1], round_index=2),
            )
        ),
        lambda: _trace(
            rounds=(
                _rounds()[0],
                replace(_rounds()[1], output_path_count=3),
            )
        ),
        lambda: _trace(
            rounds=(
                _rounds()[0],
                replace(_rounds()[1], duplicate_path_count=1),
            )
        ),
        lambda: _trace(
            rounds=(
                _rounds()[0],
                replace(
                    _rounds()[1],
                    probes=(_followup_probe(id="r1p1"),),
                ),
            )
        ),
        lambda: _trace(
            final_evidence=(
                _final_evidence()[0],
                replace(_final_evidence()[1], goal_ids=("missing-goal",)),
            )
        ),
        lambda: _trace(final_evidence_count=3),
        lambda: _trace(
            final_evidence=(
                _final_evidence()[0],
                replace(
                    _final_evidence()[1],
                    file_path=_final_evidence()[0].file_path,
                ),
            )
        ),
    ],
)
def test_root_model_rejects_broken_cross_record_invariants(factory) -> None:
    with pytest.raises(ExplorationTraceError):
        factory()


def test_failed_probe_has_no_fabricated_v1_counts_or_gain() -> None:
    failed = _followup_probe(
        retrieval_outcome="failed",
        retrieval_termination_reason="provider_error",
        duration_ms=9,
        result_count=0,
        evidence_anchor_count=0,
        unique_path_count=0,
        duplicate_path_count=0,
        novel_path_count=0,
        newly_satisfied_goal_ids=(),
        source_counts=_source_counts(),
        final_selection_count=0,
    )
    assert failed.duration_ms == 9
    assert dict(failed.source_counts) == dict(_source_counts())


def test_privacy_validation_is_field_based_and_original_query_may_look_like_a_path() -> None:
    query = "检查 /absolute/not-a-structured-path ENVIRONMENT_SECRET"
    initial = _initial_probe(query=query)
    rounds = (replace(_rounds()[0], probes=(initial,)), _rounds()[1])
    payload = exploration_trace_payload(_trace(rounds=rounds))

    assert payload["rounds"][0]["probes"][0]["query"] == query
    forbidden_keys = {
        "content",
        "_context_content",
        "score",
        "score_parts",
        "subject_terms",
        "planner_prompt",
        "exception_text",
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)


def test_quality_normalization_changes_only_round_probe_and_top_durations() -> None:
    baseline = _trace()
    retimed_rounds = tuple(
        replace(
            round_record,
            duration_ms=round_record.duration_ms + 20,
            probes=tuple(
                replace(probe, duration_ms=probe.duration_ms + 10)
                for probe in round_record.probes
            ),
        )
        for round_record in baseline.rounds
    )
    retimed = replace(baseline, duration_ms=100, rounds=retimed_rounds)

    def normalized(trace: ExplorationTrace) -> dict[str, object]:
        payload = copy.deepcopy(exploration_trace_payload(trace))
        payload["duration_ms"] = 0
        for round_payload in payload["rounds"]:
            round_payload["duration_ms"] = 0
            for probe_payload in round_payload["probes"]:
                probe_payload["duration_ms"] = 0
        return payload

    assert canonical_exploration_trace_bytes(baseline) != (
        canonical_exploration_trace_bytes(retimed)
    )
    assert normalized(baseline) == normalized(retimed)
    changed = normalized(retimed)
    changed["rounds"][1]["probes"][0]["source_counts"]["signal"] = 2
    assert changed != normalized(baseline)


def test_categories_in_goal_ledger_are_the_context_pack_groups() -> None:
    assert {goal.category for goal in _trace().goals} <= set(CONTEXT_GROUPS)


def test_round_chronology_does_not_require_initial_goals_to_prefix_the_ledger() -> None:
    trace = _trace(goals=tuple(reversed(_goals())))

    assert trace.rounds[0].newly_satisfied_goal_ids == ("goal-test",)
    assert trace.rounds[1].newly_satisfied_goal_ids == ("goal-view",)
