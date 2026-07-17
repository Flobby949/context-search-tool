from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest
import requests

from context_search_tool import exploration
from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.context_pack import (
    ContextPackError,
    ContextPackOptions,
    ReadinessConfidence,
    build_context_pack,
)
from context_search_tool.exploration.models import (
    ExploredContext,
    ExplorationError,
    ExplorationGoal,
    FusedEvidenceState,
    FrozenGoals,
    ProbeCandidate,
)
from context_search_tool.models import (
    EvidenceAnchor,
    DocumentChunk,
    QueryPlan,
    RetrievalResult,
)
from context_search_tool.query_planner import DisabledQueryPlanner
from context_search_tool.retrieval import QueryBundle, TracedQueryBundle
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    ExplorationTrace,
    RetrievalTrace,
    TraceLimits,
    TraceQuery,
    TraceRank,
    TraceSelection,
    TraceStage,
    exploration_trace_payload,
)


def _result(
    path: str,
    content: str,
    *,
    protected: bool = False,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=1.0,
        score_parts={"evidence_priority": 0 if protected else 2},
        reasons=["fixture"],
        followup_keywords=[],
    )


def _anchor(path: str, content: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=Path(path),
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        content=content,
        score=0.5,
        score_parts={"anchor": 1.0},
        reasons=["fixture anchor"],
        anchor_kind="readme",
    )


def _bundle(
    *results: RetrievalResult,
    query: str = "owner flow",
    anchors: tuple[EvidenceAnchor, ...] = (),
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=["owner"],
        results=list(results),
        followup_keywords=[],
        planner=QueryPlan(original_query=query),
        evidence_anchors=list(anchors),
    )


def _source_counts(**values: int) -> tuple[tuple[str, int], ...]:
    return tuple((key, values.get(key, 0)) for key in SOURCE_COUNT_KEYS)


def _selection(
    rank: int,
    path: str,
    *,
    kind: str = "result",
) -> TraceSelection:
    return TraceSelection(
        rank=rank,
        selection_kind=kind,
        selection_reason=(
            "selected_within_result_limit"
            if kind == "result"
            else "selected_within_anchor_limit"
        ),
        file_path=path,
        start_line=1,
        end_line=1,
        score=1.0,
        origin_chunk_ids=(f"chunk-{rank}",),
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
        reasons=("fixture",),
    )


def _traced(
    bundle: QueryBundle,
    *,
    outcome: str = "complete",
    reason: str = "completed",
    omitted: int = 0,
    duration_ms: int = 4,
) -> TracedQueryBundle:
    paths: list[tuple[str, str]] = []
    for result in bundle.results:
        paths.append((result.file_path.as_posix(), "result"))
    for anchor in bundle.evidence_anchors:
        paths.append((anchor.file_path.as_posix(), "evidence_anchor"))
    total = len(paths)
    preview_count = max(0, total - omitted)
    selections = tuple(
        _selection(rank, path, kind=kind)
        for rank, (path, kind) in enumerate(paths[:preview_count], start=1)
    )
    trace = RetrievalTrace(
        schema_version=1,
        outcome=outcome,
        termination_reason=reason,
        duration_ms=duration_ms,
        limits=TraceLimits(),
        query=TraceQuery(1, 1, "original_only"),
        source_counts=_source_counts(lexical=total),
        stages=(
            (
                TraceStage(
                    "final_selection",
                    total,
                    total,
                    total,
                    duration_ms,
                ),
            )
            if outcome == "complete"
            else ()
        ),
        final_selection_count=total,
        final_selection_omitted_count=omitted,
        final_selections=selections,
    )
    return TracedQueryBundle(bundle, trace)


def _goal(
    goal_id: str,
    category: str,
    subject: str = "owner",
    *,
    required: bool = True,
) -> ExplorationGoal:
    return ExplorationGoal(
        id=goal_id,
        kind="need",
        category=category,
        accepted_roles=(),
        subject_terms=(subject,),
        required=required,
        provenance="context_need",
        initially_satisfied=False,
    )


def _frozen(*goals: ExplorationGoal) -> FrozenGoals:
    return FrozenGoals(len(goals), len(goals), tuple(goals), 0)


def _candidate(
    query: str,
    goal: ExplorationGoal,
    *,
    source_rank: int = 1,
) -> ProbeCandidate:
    return ProbeCandidate(
        query=query,
        source="indexed_symbol",
        purpose=goal.category,
        goal_ids=(goal.id,),
        seed_paths=("src/OwnerController.java",),
        required=goal.required,
        goal_order=source_rank - 1,
        source_rank=source_rank,
    )


def _config(*, final_top_k: int = 12) -> ToolConfig:
    return ToolConfig(retrieval=RetrievalConfig(final_top_k=final_top_k))


def _options(
    config: ToolConfig,
    *,
    max_items: int | None = None,
) -> ContextPackOptions:
    options = exploration.resolve_explore_pack_options(
        config,
        context_lines=None,
    )
    return options if max_items is None else replace(options, max_items=max_items)


def _install_calls(
    monkeypatch: pytest.MonkeyPatch,
    values: tuple[TracedQueryBundle | BaseException, ...],
):
    from context_search_tool.exploration import runner

    pending: Iterator[TracedQueryBundle | BaseException] = iter(values)
    calls: list[dict[str, object]] = []
    active = 0

    def fake_trace_repository(
        repo: Path,
        query: str,
        config: ToolConfig,
        context_lines: int | None = None,
        full_file: bool = False,
        planner=None,
        *,
        clock_ns=None,
    ) -> TracedQueryBundle:
        nonlocal active
        active += 1
        assert active == 1
        calls.append(
            {
                "repo": repo,
                "query": query,
                "config": config,
                "context_lines": context_lines,
                "full_file": full_file,
                "planner": planner,
                "clock_ns": clock_ns,
            }
        )
        try:
            value = next(pending)
            if isinstance(value, BaseException):
                raise value
            return value
        finally:
            active -= 1

    monkeypatch.setattr(runner, "trace_repository", fake_trace_repository)
    return calls


def _run(
    tmp_path: Path,
    config: ToolConfig,
    *,
    pack_options: ContextPackOptions | None = None,
    clock_ns=None,
) -> ExploredContext:
    return exploration.explore_repository(
        tmp_path,
        "owner flow",
        config,
        pack_options or _options(config),
        clock_ns=clock_ns or (lambda: 0),
    )


def test_public_runner_uses_v5_probe_planner() -> None:
    from context_search_tool.exploration import probes, runner

    assert runner.plan_probes is probes._plan_probes_v5


@pytest.mark.parametrize(
    (
        "initial",
        "frozen",
        "max_items",
        "exact",
        "expected_outcome",
        "expected_reason",
        "planning_expected",
    ),
    [
        (
            _traced(_bundle(), outcome="empty", reason="missing_index"),
            _frozen(),
            None,
            False,
            "empty",
            "initial_missing_index",
            False,
        ),
        (
            _traced(_bundle(), outcome="empty", reason="no_candidates"),
            _frozen(),
            None,
            False,
            "empty",
            "initial_empty",
            False,
        ),
        (
            _traced(_bundle(), outcome="partial", reason="store_read_error"),
            _frozen(),
            None,
            False,
            "partial",
            "initial_retrieval_incomplete",
            False,
        ),
        (
            _traced(_bundle(_result("src/OwnerController.java", "owner"))),
            _frozen(),
            0,
            True,
            "complete",
            "context_budget_zero",
            False,
        ),
        (
            _traced(
                _bundle(
                    _result(
                        "src/OwnerController.java",
                        "owner controller",
                        protected=True,
                    )
                )
            ),
            _frozen(_goal("goal-test", "tests", required=False)),
            None,
            True,
            "complete",
            "exact_satisfied",
            False,
        ),
        (
            _traced(_bundle(_result("src/OwnerController.java", "owner"))),
            _frozen(),
            None,
            False,
            "complete",
            "initial_satisfied",
            False,
        ),
        (
            _traced(_bundle(_result("src/OwnerController.java", "owner"))),
            _frozen(_goal("goal-test", "tests")),
            None,
            False,
            "complete",
            "no_grounded_probe",
            True,
        ),
        (
            _traced(
                _bundle(_result("src/OwnerController.java", "owner")),
                omitted=1,
            ),
            _frozen(_goal("goal-test", "tests")),
            None,
            False,
            "complete",
            "no_grounded_probe",
            False,
        ),
    ],
)
def test_initial_stop_precedence_and_call_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial: TracedQueryBundle,
    frozen: FrozenGoals,
    max_items: int | None,
    exact: bool,
    expected_outcome: str,
    expected_reason: str,
    planning_expected: bool,
) -> None:
    from context_search_tool.exploration import runner

    config = _config()
    calls = _install_calls(monkeypatch, (initial,))
    planning: list[str] = []
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: exact)

    def plan(*args, **kwargs):
        planning.append("planned")
        return ()

    monkeypatch.setattr(runner, "plan_probes", plan)

    result = _run(
        tmp_path,
        config,
        pack_options=_options(config, max_items=max_items),
    )

    assert result.trace.outcome == expected_outcome
    assert result.trace.termination_reason == expected_reason
    assert result.trace.retrieval_call_count == 1
    assert result.trace.executed_probe_count == 0
    assert len(calls) == 1
    assert bool(planning) is planning_expected


@pytest.mark.parametrize(
    ("followup", "probe_outcome", "probe_reason"),
    [
        (
            _traced(_bundle(), outcome="partial", reason="store_read_error"),
            "partial",
            "store_read_error",
        ),
        (
            _traced(_bundle(), outcome="empty", reason="missing_index"),
            "empty",
            "missing_index",
        ),
        (ValueError("QUERY_SECRET"), "failed", "query_error"),
        (requests.HTTPError("PROVIDER_SECRET"), "failed", "provider_error"),
    ],
)
def test_followup_failures_return_best_initial_context_without_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    followup: TracedQueryBundle | BaseException,
    probe_outcome: str,
    probe_reason: str,
) -> None:
    from context_search_tool.exploration import runner

    goal = _goal("goal-test", "tests")
    frozen = _frozen(goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    calls = _install_calls(monkeypatch, (_traced(initial_bundle), followup))
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (_candidate("OwnerTest test", goal),),
    )

    result = _run(tmp_path, _config())

    probe = result.trace.rounds[1].probes[0]
    assert (result.trace.outcome, result.trace.termination_reason) == (
        "partial",
        "followup_query_failed",
    )
    assert (probe.retrieval_outcome, probe.retrieval_termination_reason) == (
        probe_outcome,
        probe_reason,
    )
    assert [item.file_path for item in result.final_pack.items] == [
        item.file_path for item in result.initial_pack.items
    ]
    assert "SECRET" not in repr(exploration_trace_payload(result.trace))
    assert len(calls) == 2


def test_followup_selection_omission_discards_probe_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    goal = _goal("goal-test", "tests")
    frozen = _frozen(goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    follow_bundle = _bundle(_result("tests/test_owner.py", "owner test"))
    _install_calls(
        monkeypatch,
        (_traced(initial_bundle), _traced(follow_bundle, omitted=1)),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (_candidate("OwnerTest test", goal),),
    )

    result = _run(tmp_path, _config())

    assert result.trace.termination_reason == "followup_query_failed"
    assert result.trace.rounds[1].probes[0].retrieval_outcome == "complete"
    assert len(result.fused_bundle.results) == 1
    assert all(item.file_path != "tests/test_owner.py" for item in result.final_pack.items)


def test_successful_probe_satisfies_goal_disables_planner_and_preserves_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    goal = _goal("goal-test", "tests")
    frozen = _frozen(goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    follow_bundle = _bundle(_result("tests/test_owner.py", "owner test"))
    calls = _install_calls(
        monkeypatch,
        (_traced(initial_bundle), _traced(follow_bundle)),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (_candidate("OwnerTest test", goal),),
    )
    config = _config(final_top_k=1)

    result = _run(tmp_path, config)

    assert (result.trace.outcome, result.trace.termination_reason) == (
        "complete",
        "satisfied",
    )
    assert len(calls) == 2
    assert calls[1]["config"].retrieval.final_top_k == 6
    assert calls[1]["config"].query_planner.enabled is False
    assert isinstance(calls[1]["planner"], DisabledQueryPlanner)
    assert result.trace.limits.effective_initial_top_k == 1
    assert result.final_pack.budget.max_items == config.context.max_items
    assert result.initial_bundle is not result.fused_bundle
    assert result.initial_bundle.results is not result.fused_bundle.results
    assert result.initial_bundle.results[0].score_parts is not (
        result.fused_bundle.results[0].score_parts
    )
    assert result.initial_pack is not result.final_pack
    assert result.initial_pack.groups is not result.final_pack.groups


def test_followup_satisfaction_requires_and_accepts_all_required_goals() -> None:
    from context_search_tool.exploration import runner

    required = _goal("goal-test", "tests")
    recommended = _goal(
        "goal-implementation",
        "implementations",
        required=False,
    )
    pack = build_context_pack(
        _bundle(_result("src/OwnerController.java", "owner controller")),
        _options(_config()),
    )
    medium_pack = replace(
        pack,
        confidence=ReadinessConfidence(
            "medium",
            ("recommended implementations are missing",),
        ),
    )

    assert runner._satisfied(
        _frozen(required, recommended),
        FusedEvidenceState(_bundle(), (), (required.id,)),
        medium_pack,
    )
    assert not runner._satisfied(
        _frozen(recommended),
        FusedEvidenceState(_bundle(), (), ()),
        medium_pack,
    )


def test_empty_no_candidates_and_zero_novel_path_stop_as_no_marginal_gain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    goal = _goal("goal-test", "tests", subject="never")
    frozen = _frozen(goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    _install_calls(
        monkeypatch,
        (
            _traced(initial_bundle),
            _traced(_bundle(), outcome="empty", reason="no_candidates"),
        ),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (_candidate("MissingTest test", goal),),
    )

    result = _run(tmp_path, _config())

    assert result.trace.termination_reason == "no_marginal_gain"
    probe = result.trace.rounds[1].probes[0]
    assert probe.unique_path_count == 0
    assert probe.novel_path_count == 0


def test_duplicate_ratio_exactly_point_eight_stops_without_double_counting_anchors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    goal = _goal("goal-test", "tests", subject="never")
    frozen = _frozen(goal)
    initial_results = tuple(
        _result(f"src/Initial{index}.java", f"initial {index}")
        for index in range(4)
    )
    initial_bundle = _bundle(*initial_results)
    follow_results = tuple(
        _result(item.file_path.as_posix(), item.content) for item in initial_results
    ) + (_result("src/Novel.java", "novel"),)
    follow_bundle = _bundle(
        *follow_results,
        anchors=(_anchor("src/Initial0.java", "duplicate anchor"),),
    )
    _install_calls(
        monkeypatch,
        (_traced(initial_bundle), _traced(follow_bundle)),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (_candidate("MissingTest test", goal),),
    )

    result = _run(tmp_path, _config())

    probe = result.trace.rounds[1].probes[0]
    assert result.trace.termination_reason == "no_marginal_gain"
    assert (probe.unique_path_count, probe.duplicate_path_count, probe.novel_path_count) == (
        5,
        4,
        1,
    )


def test_stale_candidate_is_skipped_and_next_candidate_executes_sequentially(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    test_goal = _goal("goal-test", "tests")
    config_goal = _goal("goal-config", "configs_docs")
    frozen = _frozen(test_goal, config_goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    test_bundle = _bundle(_result("tests/test_owner.py", "owner test"))
    config_bundle = _bundle(
        _result("src/main/resources/application-owner.yml", "owner: true")
    )
    calls = _install_calls(
        monkeypatch,
        (_traced(initial_bundle), _traced(test_bundle), _traced(config_bundle)),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (
            _candidate("OwnerTest test", test_goal, source_rank=1),
            _candidate("owner tests", test_goal, source_rank=2),
            _candidate("owner config", config_goal, source_rank=3),
        ),
    )

    result = _run(tmp_path, _config())

    assert result.trace.termination_reason == "satisfied"
    assert result.trace.executed_probe_count == 2
    assert result.trace.stale_skipped_probe_count == 1
    assert result.trace.unexecuted_probe_count == 0
    assert [probe.id for probe in result.trace.rounds[1].probes] == [
        "r1p0",
        "r1p1",
    ]
    assert [call["query"] for call in calls] == [
        "owner flow",
        "OwnerTest test",
        "owner config",
    ]


def test_two_probe_limit_stops_with_unexecuted_text_absent_from_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    test_goal = _goal("goal-test", "tests")
    config_goal = _goal("goal-config", "configs_docs")
    type_goal = _goal("goal-type", "related_types")
    frozen = _frozen(test_goal, config_goal, type_goal)
    initial_bundle = _bundle(_result("src/OwnerController.java", "owner"))
    test_bundle = _bundle(_result("tests/test_owner.py", "owner test"))
    config_bundle = _bundle(
        _result("src/main/resources/application-owner.yml", "owner: true")
    )
    calls = _install_calls(
        monkeypatch,
        (_traced(initial_bundle), _traced(test_bundle), _traced(config_bundle)),
    )
    monkeypatch.setattr(runner, "freeze_goals", lambda *args: frozen)
    monkeypatch.setattr(runner, "exact_satisfied", lambda *args: False)
    monkeypatch.setattr(
        runner,
        "plan_probes",
        lambda *args, **kwargs: (
            _candidate("OwnerTest test", test_goal, source_rank=1),
            _candidate("owner config", config_goal, source_rank=2),
            _candidate("UNEXECUTED_SECRET", type_goal, source_rank=3),
        ),
    )

    result = _run(tmp_path, _config())

    assert result.trace.termination_reason == "probe_budget_exhausted"
    assert result.trace.executed_probe_count == 2
    assert result.trace.unexecuted_probe_count == 1
    assert len(calls) == 3
    assert "UNEXECUTED_SECRET" not in repr(exploration_trace_payload(result.trace))


@pytest.mark.parametrize(
    ("config", "pack_change", "context_lines", "full_file", "error_type"),
    [
        (
            replace(_config(), retrieval=replace(_config().retrieval, final_top_k=0)),
            {},
            None,
            False,
            ValueError,
        ),
        (_config(), {"max_items": True}, None, False, ContextPackError),
        (_config(), {"max_items": 13}, None, False, ContextPackError),
        (_config(), {"max_excerpt_bytes": 9000}, None, False, ContextPackError),
        (_config(), {}, -1, False, ContextPackError),
        (_config(), {}, None, 1, ContextPackError),
    ],
)
def test_library_preflight_rejects_invalid_values_before_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ToolConfig,
    pack_change: dict[str, object],
    context_lines: int | None,
    full_file: object,
    error_type: type[Exception],
) -> None:
    from context_search_tool.exploration import runner

    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "trace_repository",
        lambda *args, **kwargs: calls.append("called"),
    )
    options = replace(_options(_config()), **pack_change)

    with pytest.raises(error_type):
        exploration.explore_repository(
            tmp_path,
            "owner flow",
            config,
            options,
            context_lines=context_lines,
            full_file=full_file,  # type: ignore[arg-type]
        )

    assert calls == []


def test_unexpected_assembly_failure_is_stable_but_keyboard_interrupt_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.exploration import runner

    initial = _traced(_bundle(_result("src/OwnerController.java", "owner")))
    _install_calls(monkeypatch, (initial,))
    monkeypatch.setattr(
        runner,
        "freeze_goals",
        lambda *args: (_ for _ in ()).throw(RuntimeError("INTERNAL_SECRET")),
    )

    with pytest.raises(ExplorationError) as caught:
        _run(tmp_path, _config())
    assert str(caught.value) == "Controlled exploration failed"
    assert caught.value.code == "explore_failed"

    _install_calls(monkeypatch, (initial,))
    monkeypatch.setattr(
        runner,
        "freeze_goals",
        lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, _config())


def test_public_surface_and_signature_are_exact() -> None:
    assert exploration.__all__ == (
        "ExploredContext",
        "explore_repository",
        "resolve_explore_pack_options",
    )
    assert exploration.ExploredContext is ExploredContext
    assert str(inspect.signature(exploration.explore_repository)) == (
        "(repo: 'Path', query: 'str', config: 'ToolConfig', "
        "pack_options: 'ContextPackOptions', context_lines: 'int | None' = None, "
        "full_file: 'bool' = False, planner: 'QueryPlanner | None' = None, *, "
        "clock_ns=None) -> 'ExploredContext'"
    )
    assert not hasattr(QueryBundle, "trace")
    assert not hasattr(RetrievalResult, "exploration")
    assert not hasattr(DocumentChunk, "exploration")
    assert ExplorationTrace is not RetrievalTrace
