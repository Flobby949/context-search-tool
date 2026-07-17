from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import requests

from context_search_tool.config import ToolConfig
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextPack,
    ContextPackOptions,
    build_context_pack,
)
from context_search_tool.exploration.fusion import (
    add_probe_evidence,
    initialize_fusion,
)
from context_search_tool.exploration.goals import (
    exact_satisfied,
    freeze_goals,
)
from context_search_tool.exploration.models import (
    MAX_FOLLOWUP_PROBES,
    EvidenceOrigin,
    ExploredContext,
    ExplorationError,
    FrozenGoals,
    FusedEvidenceState,
    ProbeCandidate,
)
from context_search_tool.exploration.options import (
    followup_config,
    resolve_explore_config,
    validate_library_explore_options,
)
from context_search_tool.exploration.probes import (
    _plan_probes_v5,
    probe_candidate_is_stale,
)
from context_search_tool.query_planner import DisabledQueryPlanner
from context_search_tool.retrieval import QueryBundle, trace_repository
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    ExplorationGoalRecord,
    ExplorationLimits,
    ExplorationProbe,
    ExplorationRound,
    ExplorationTrace,
    FinalEvidence,
    RetrievalTrace,
)

if TYPE_CHECKING:
    from context_search_tool.query_planner import QueryPlanner


_Clock = Callable[[], int]

# Kept as an injected seam for runner tests; public exploration is v5-only.
plan_probes = _plan_probes_v5


def explore_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    pack_options: ContextPackOptions,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
    *,
    clock_ns=None,
) -> ExploredContext:
    validate_library_explore_options(
        config,
        pack_options,
        context_lines=context_lines,
        full_file=full_file,
    )
    initial_config, _, effective_initial_top_k = resolve_explore_config(
        config,
        final_top_k=None,
    )
    clock: _Clock = clock_ns or time.perf_counter_ns
    started_ns = clock()

    initial_traced = trace_repository(
        repo,
        query,
        initial_config,
        context_lines=context_lines,
        full_file=full_file,
        planner=planner,
        clock_ns=clock,
    )
    try:
        return _explore_after_initial(
            repo=repo,
            query=query,
            initial_config=initial_config,
            pack_options=pack_options,
            context_lines=context_lines,
            full_file=full_file,
            effective_initial_top_k=effective_initial_top_k,
            initial_bundle=initial_traced.bundle,
            initial_trace=initial_traced.trace,
            clock=clock,
            started_ns=started_ns,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except ExplorationError:
        raise
    except Exception as exc:
        raise ExplorationError() from exc


def _explore_after_initial(
    *,
    repo: Path,
    query: str,
    initial_config: ToolConfig,
    pack_options: ContextPackOptions,
    context_lines: int | None,
    full_file: bool,
    effective_initial_top_k: int,
    initial_bundle: QueryBundle,
    initial_trace: RetrievalTrace,
    clock: _Clock,
    started_ns: int,
) -> ExploredContext:
    initial_bundle_snapshot = copy.deepcopy(initial_bundle)
    initial_pack = copy.deepcopy(
        build_context_pack(initial_bundle_snapshot, pack_options)
    )
    frozen = freeze_goals(query, initial_bundle_snapshot, initial_pack)
    state = initialize_fusion(initial_bundle_snapshot, initial_pack, frozen)
    final_pack = copy.deepcopy(initial_pack)
    initial_satisfied_ids = tuple(
        goal.id for goal in frozen.goals if goal.initially_satisfied
    )
    initial_probe = _normal_probe_record(
        probe_id="r0p0",
        query=query,
        purpose="original_query",
        source="original",
        goal_ids=(),
        seed_paths=(),
        bundle=initial_bundle_snapshot,
        trace=initial_trace,
        existing_paths=frozenset(),
        newly_satisfied_goal_ids=initial_satisfied_ids,
    )
    initial_round = ExplorationRound(
        round_index=0,
        kind="initial",
        duration_ms=initial_trace.duration_ms,
        input_path_count=0,
        output_path_count=len(_bundle_paths(state.bundle)),
        novel_path_count=len(_bundle_paths(state.bundle)),
        duplicate_path_count=0,
        newly_satisfied_goal_ids=initial_satisfied_ids,
        probes=(initial_probe,),
    )

    initial_stop = _initial_stop(
        initial_trace,
        initial_bundle_snapshot,
        pack_options,
        query,
        frozen,
        state,
    )
    if initial_stop is not None:
        outcome, reason = initial_stop
        return _finish(
            initial_bundle=initial_bundle_snapshot,
            initial_pack=initial_pack,
            state=state,
            final_pack=final_pack,
            frozen=frozen,
            planned=(),
            probe_records=(),
            stale_skipped=0,
            outcome=outcome,
            termination_reason=reason,
            effective_initial_top_k=effective_initial_top_k,
            initial_round=initial_round,
            followup_started_ns=None,
            clock=clock,
            started_ns=started_ns,
        )

    if initial_trace.final_selection_omitted_count:
        return _finish(
            initial_bundle=initial_bundle_snapshot,
            initial_pack=initial_pack,
            state=state,
            final_pack=final_pack,
            frozen=frozen,
            planned=(),
            probe_records=(),
            stale_skipped=0,
            outcome="complete",
            termination_reason="no_grounded_probe",
            effective_initial_top_k=effective_initial_top_k,
            initial_round=initial_round,
            followup_started_ns=None,
            clock=clock,
            started_ns=started_ns,
        )

    planned = plan_probes(
        repo,
        initial_bundle_snapshot,
        initial_trace,
        initial_pack,
        frozen,
    )
    if not planned:
        return _finish(
            initial_bundle=initial_bundle_snapshot,
            initial_pack=initial_pack,
            state=state,
            final_pack=final_pack,
            frozen=frozen,
            planned=(),
            probe_records=(),
            stale_skipped=0,
            outcome="complete",
            termination_reason="no_grounded_probe",
            effective_initial_top_k=effective_initial_top_k,
            initial_round=initial_round,
            followup_started_ns=None,
            clock=clock,
            started_ns=started_ns,
        )

    followup_started_ns = clock()
    followup = followup_config(initial_config)
    disabled_planner = DisabledQueryPlanner()
    probe_records: list[ExplorationProbe] = []
    stale_skipped = 0
    outcome = "complete"
    termination_reason: str | None = None

    for candidate in planned:
        if len(probe_records) == MAX_FOLLOWUP_PROBES:
            break
        if probe_candidate_is_stale(candidate, set(state.satisfied_goal_ids)):
            stale_skipped += 1
            continue

        probe_id = f"r1p{len(probe_records)}"
        before_paths = _bundle_paths(state.bundle)
        probe_started_ns = clock()
        try:
            traced = trace_repository(
                repo,
                candidate.query,
                followup,
                context_lines=context_lines,
                full_file=full_file,
                planner=disabled_planner,
                clock_ns=clock,
            )
        except ValueError:
            probe_records.append(
                _failed_probe_record(
                    candidate,
                    probe_id,
                    "query_error",
                    _elapsed_ms(probe_started_ns, clock()),
                )
            )
            outcome = "partial"
            termination_reason = "followup_query_failed"
            break
        except requests.HTTPError:
            probe_records.append(
                _failed_probe_record(
                    candidate,
                    probe_id,
                    "provider_error",
                    _elapsed_ms(probe_started_ns, clock()),
                )
            )
            outcome = "partial"
            termination_reason = "followup_query_failed"
            break

        returned_paths = _bundle_paths(traced.bundle)
        duplicate_count = len(returned_paths.intersection(before_paths))
        novel_count = len(returned_paths.difference(before_paths))
        failed_normally = traced.trace.outcome == "partial" or (
            traced.trace.outcome == "empty"
            and traced.trace.termination_reason == "missing_index"
        )
        omitted = traced.trace.final_selection_omitted_count != 0
        previous_satisfied = set(state.satisfied_goal_ids)
        newly_satisfied: tuple[str, ...] = ()

        if not failed_normally and not omitted and traced.trace.outcome == "complete":
            state, final_pack = add_probe_evidence(
                state,
                traced.bundle,
                frozen,
                pack_options,
                probe=candidate,
                round_index=1,
                probe_id=probe_id,
            )
            newly_satisfied = tuple(
                goal.id
                for goal in frozen.goals
                if goal.id in state.satisfied_goal_ids
                and goal.id not in previous_satisfied
            )

        probe_records.append(
            _normal_probe_record(
                probe_id=probe_id,
                query=candidate.query,
                purpose=_trace_purpose(candidate),
                source=candidate.source,
                goal_ids=candidate.goal_ids,
                seed_paths=candidate.seed_paths,
                bundle=traced.bundle,
                trace=traced.trace,
                existing_paths=before_paths,
                newly_satisfied_goal_ids=newly_satisfied,
            )
        )
        if failed_normally or omitted:
            outcome = "partial"
            termination_reason = "followup_query_failed"
            break
        if _satisfied(frozen, state, final_pack):
            termination_reason = "satisfied"
            break
        duplicate_ratio = (
            None
            if not returned_paths
            else duplicate_count / len(returned_paths)
        )
        if not newly_satisfied and (
            novel_count == 0
            or duplicate_ratio is not None
            and duplicate_ratio >= 0.80
        ):
            termination_reason = "no_marginal_gain"
            break

    if termination_reason is None:
        termination_reason = "probe_budget_exhausted"

    return _finish(
        initial_bundle=initial_bundle_snapshot,
        initial_pack=initial_pack,
        state=state,
        final_pack=final_pack,
        frozen=frozen,
        planned=planned,
        probe_records=tuple(probe_records),
        stale_skipped=stale_skipped,
        outcome=outcome,
        termination_reason=termination_reason,
        effective_initial_top_k=effective_initial_top_k,
        initial_round=initial_round,
        followup_started_ns=followup_started_ns,
        clock=clock,
        started_ns=started_ns,
    )


def _initial_stop(
    trace: RetrievalTrace,
    bundle: QueryBundle,
    pack_options: ContextPackOptions,
    query: str,
    frozen: FrozenGoals,
    state: FusedEvidenceState,
) -> tuple[str, str] | None:
    if (trace.outcome, trace.termination_reason) == ("empty", "missing_index"):
        return "empty", "initial_missing_index"
    if (trace.outcome, trace.termination_reason) == ("empty", "no_candidates") or (
        trace.outcome == "complete" and not _bundle_paths(bundle)
    ):
        return "empty", "initial_empty"
    if trace.outcome == "partial":
        return "partial", "initial_retrieval_incomplete"
    if pack_options.max_items == 0:
        return "complete", "context_budget_zero"
    if exact_satisfied(query, bundle, frozen):
        return "complete", "exact_satisfied"
    if len(state.satisfied_goal_ids) == len(frozen.goals):
        return "complete", "initial_satisfied"
    return None


def _satisfied(
    frozen: FrozenGoals,
    state: FusedEvidenceState,
    _pack: ContextPack,
) -> bool:
    satisfied = set(state.satisfied_goal_ids)
    if len(satisfied) == len(frozen.goals):
        return True
    required = {goal.id for goal in frozen.goals if goal.required}
    return bool(required) and required.issubset(satisfied)


def _finish(
    *,
    initial_bundle: QueryBundle,
    initial_pack: ContextPack,
    state: FusedEvidenceState,
    final_pack: ContextPack,
    frozen: FrozenGoals,
    planned: tuple[ProbeCandidate, ...],
    probe_records: tuple[ExplorationProbe, ...],
    stale_skipped: int,
    outcome: str,
    termination_reason: str,
    effective_initial_top_k: int,
    initial_round: ExplorationRound,
    followup_started_ns: int | None,
    clock: _Clock,
    started_ns: int,
) -> ExploredContext:
    ended_ns = clock()
    rounds: tuple[ExplorationRound, ...] = (initial_round,)
    if probe_records:
        initial_paths = initial_round.output_path_count
        final_paths = len(_bundle_paths(state.bundle))
        newly_satisfied = _goal_ordered_union(
            frozen,
            *(probe.newly_satisfied_goal_ids for probe in probe_records),
        )
        rounds += (
            ExplorationRound(
                round_index=1,
                kind="followup",
                duration_ms=_elapsed_ms(followup_started_ns, ended_ns),
                input_path_count=initial_paths,
                output_path_count=final_paths,
                novel_path_count=final_paths - initial_paths,
                duplicate_path_count=sum(
                    probe.duplicate_path_count for probe in probe_records
                ),
                newly_satisfied_goal_ids=newly_satisfied,
                probes=probe_records,
            ),
        )
    final_satisfied = set(state.satisfied_goal_ids)
    goals = tuple(
        ExplorationGoalRecord(
            id=goal.id,
            kind=goal.kind,
            category=goal.category,
            accepted_roles=goal.accepted_roles,
            required=goal.required,
            provenance=goal.provenance,
            initially_satisfied=goal.initially_satisfied,
            finally_satisfied=goal.id in final_satisfied,
        )
        for goal in frozen.goals
    )
    final_evidence, omitted_evidence = _final_evidence(
        final_pack,
        state.origins,
    )
    executed = len(probe_records)
    unexecuted = len(planned) - executed - stale_skipped
    trace = ExplorationTrace(
        schema_version=2,
        mode="exploration",
        outcome=outcome,
        termination_reason=termination_reason,
        duration_ms=_elapsed_ms(started_ns, ended_ns),
        limits=ExplorationLimits(
            effective_initial_top_k=effective_initial_top_k
        ),
        initial_evidence_need_count=frozen.initial_evidence_need_count,
        candidate_goal_count=frozen.candidate_goal_count,
        retained_goal_count=len(frozen.goals),
        omitted_goal_count=frozen.omitted_goal_count,
        initial_satisfied_goal_count=sum(
            goal.initially_satisfied for goal in frozen.goals
        ),
        final_satisfied_goal_count=len(final_satisfied),
        planned_probe_count=len(planned),
        executed_probe_count=executed,
        stale_skipped_probe_count=stale_skipped,
        unexecuted_probe_count=unexecuted,
        retrieval_call_count=1 + executed,
        goals=goals,
        rounds=rounds,
        final_evidence_count=len(final_pack.items),
        final_evidence_omitted_count=omitted_evidence,
        final_evidence=final_evidence,
    )
    return ExploredContext(
        initial_bundle=initial_bundle,
        initial_pack=initial_pack,
        fused_bundle=state.bundle,
        final_pack=final_pack,
        trace=trace,
    )


def _normal_probe_record(
    *,
    probe_id: str,
    query: str,
    purpose: str,
    source: str,
    goal_ids: tuple[str, ...],
    seed_paths: tuple[str, ...],
    bundle: QueryBundle,
    trace: RetrievalTrace,
    existing_paths: frozenset[str],
    newly_satisfied_goal_ids: tuple[str, ...],
) -> ExplorationProbe:
    paths = _bundle_paths(bundle)
    return ExplorationProbe(
        id=probe_id,
        query=query,
        purpose=purpose,
        source=source,
        goal_ids=goal_ids,
        seed_paths=seed_paths,
        retrieval_outcome=trace.outcome,
        retrieval_termination_reason=trace.termination_reason,
        duration_ms=trace.duration_ms,
        result_count=len(bundle.results),
        evidence_anchor_count=len(bundle.evidence_anchors),
        unique_path_count=len(paths),
        duplicate_path_count=len(paths.intersection(existing_paths)),
        novel_path_count=len(paths.difference(existing_paths)),
        newly_satisfied_goal_ids=newly_satisfied_goal_ids,
        source_counts=trace.source_counts,
        final_selection_count=trace.final_selection_count,
    )


def _failed_probe_record(
    candidate: ProbeCandidate,
    probe_id: str,
    reason: str,
    duration_ms: int,
) -> ExplorationProbe:
    return ExplorationProbe(
        id=probe_id,
        query=candidate.query,
        purpose=_trace_purpose(candidate),
        source=candidate.source,
        goal_ids=candidate.goal_ids,
        seed_paths=candidate.seed_paths,
        retrieval_outcome="failed",
        retrieval_termination_reason=reason,
        duration_ms=duration_ms,
        result_count=0,
        evidence_anchor_count=0,
        unique_path_count=0,
        duplicate_path_count=0,
        novel_path_count=0,
        newly_satisfied_goal_ids=(),
        source_counts=tuple((key, 0) for key in SOURCE_COUNT_KEYS),
        final_selection_count=0,
    )


def _trace_purpose(candidate: ProbeCandidate) -> str:
    required = "required" if candidate.required else "recommended"
    if candidate.purpose not in CONTEXT_GROUPS:
        raise ValueError("probe purpose is outside ContextPack groups")
    return f"find_missing_{required}_{candidate.purpose}"


def _final_evidence(
    pack: ContextPack,
    origins: tuple[EvidenceOrigin, ...],
) -> tuple[tuple[FinalEvidence, ...], int]:
    origin_by_path = {origin.file_path: origin for origin in origins}
    records: list[FinalEvidence] = []
    for item in pack.items:
        origin = origin_by_path.get(item.file_path)
        if origin is None:
            raise ValueError("final ContextPack item has no exploration origin")
        records.append(
            FinalEvidence(
                item_id=item.id,
                file_path=item.file_path,
                source_round=origin.round_index,
                probe_id=origin.probe_id,
                probe_rank=origin.source_rank,
                goal_ids=origin.goal_ids,
                selection_reason=origin.selection_reason,
            )
        )
    preview = tuple(records[:20])
    return preview, len(records) - len(preview)


def _bundle_paths(bundle: QueryBundle) -> frozenset[str]:
    return frozenset(
        item.file_path.as_posix()
        for item in (*bundle.results, *bundle.evidence_anchors)
    )


def _goal_ordered_union(
    frozen: FrozenGoals,
    *groups: tuple[str, ...],
) -> tuple[str, ...]:
    included = {goal_id for group in groups for goal_id in group}
    return tuple(goal.id for goal in frozen.goals if goal.id in included)


def _elapsed_ms(start_ns: int | None, end_ns: int) -> int:
    if start_ns is None:
        return 0
    return max(0, (end_ns - start_ns) // 1_000_000)


__all__ = ["explore_repository"]
