from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import context_search_tool.quality.runner as quality_runner
import p4_real_exploration_acceptance as acceptance
from context_search_tool.config import ToolConfig
from context_search_tool.models import QueryPlan, RetrievalResult
from context_search_tool.quality.cases import (
    FinalAtLeast,
    Gate,
    Matcher,
    QualityCase,
    adapt_legacy_query_case,
    load_quality_fixture,
)
from context_search_tool.quality.metrics import (
    CaseEvaluation,
    evaluate_exploration,
)
from context_search_tool.quality.aggregate import aggregate_cases
from context_search_tool.quality.compare import compare_reports
from context_search_tool.quality.reports import render_markdown_report
from context_search_tool.retrieval import QueryBundle
from p4_exploration_identity import P4_CATALOG_PATH, load_raw_p4_catalog


EXPLORATION_METRICS = {
    "exploration_goal_coverage_initial",
    "exploration_goal_coverage_final",
    "exploration_goal_gain",
    "novel_path_count",
    "duplicate_path_ratio",
    "executed_probe_count",
    "probe_efficiency",
    "retrieval_call_count",
    "exploration_trace_coverage",
    "final_pack_noise_count",
    "final_pack_noise_ratio",
    "exploration_latency_ms",
}


def _result(path: str) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content=path,
        score=1.0,
        score_parts={},
        reasons=[],
        followup_keywords=[],
    )


def _bundle(*paths: str) -> QueryBundle:
    return QueryBundle(
        query="owner flow",
        expanded_tokens=[],
        results=[_result(path) for path in paths],
        followup_keywords=[],
        planner=QueryPlan(original_query="owner flow"),
    )


def _pack(*paths: str) -> SimpleNamespace:
    return SimpleNamespace(
        items=tuple(SimpleNamespace(file_path=path) for path in paths),
    )


def _base_case(**changes: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": "flow",
        "query": "owner flow",
        "mode": "exploration",
        "gate": "required",
        "initial_absent": ["src/OwnerTest.java"],
        "final_present": ["src/OwnerTest.java"],
        "expected_termination_reason": "satisfied",
        "maximum_retrieval_call_count": 3,
        "minimum_goal_gain": 1,
        "maximum_final_noise_items": 0,
    }
    case.update(changes)
    return case


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown_exploration_field": True},
        {"initial_absent": ["src/A.java", "src/A.java"]},
        {
            "final_at_least": {
                "matchers": ["src/A.java", "src/A.java"],
                "min_matches": 1,
            }
        },
        {
            "final_at_least": {
                "matchers": ["src/A.java"],
                "min_matches": 2,
            }
        },
        {"expected_retrieval_call_count": 0},
        {"expected_retrieval_call_count": 4},
        {"maximum_retrieval_call_count": 0},
        {"maximum_retrieval_call_count": 4},
        {
            "expected_retrieval_call_count": 3,
            "maximum_retrieval_call_count": 2,
        },
        {"minimum_goal_gain": -1},
        {"maximum_final_noise_items": -1},
        {"expected_termination_reason": "invented"},
    ],
)
def test_exploration_case_schema_rejects_invalid_fields(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        adapt_legacy_query_case(_base_case(**changes))


@pytest.mark.parametrize("mode", ["results", "context_pack"])
def test_exploration_fields_are_rejected_on_other_modes(mode: str) -> None:
    with pytest.raises(ValueError, match="only valid for exploration mode"):
        adapt_legacy_query_case(
            {
                "id": "flow",
                "query": "owner flow",
                "mode": mode,
                "initial_absent": ["src/OwnerTest.java"],
            }
        )


def _matcher_payload(matcher: Matcher) -> object:
    if matcher.path is not None:
        return matcher.path
    if matcher.glob is not None:
        return matcher.glob
    return {"contains": matcher.contains}


def _production_catalog_projection() -> dict[str, object]:
    fixture = load_quality_fixture(P4_CATALOG_PATH)
    repos = []
    for repo in fixture.repos:
        repo_payload: dict[str, object] = {"repo_key": repo.repo_key}
        for field in (
            "path_env",
            "repo_dir_name",
            "snapshot_path",
            "source_url",
            "source_commit",
            "checkout_dir",
        ):
            value = getattr(repo, field)
            if value:
                repo_payload[field] = value
        repo_payload["profiles"] = list(repo.profiles)
        if repo.default_config:
            repo_payload["default_config"] = repo.default_config
        cases = []
        for case in repo.queries:
            payload: dict[str, object] = {
                "id": case.case_id,
                "query": case.query,
                "profiles": list(case.profiles),
                "mode": case.mode,
                "tags": list(case.tags),
                "gate": case.gate.value,
            }
            if case.maximum_pack_bytes is not None:
                payload["maximum_pack_bytes"] = case.maximum_pack_bytes
            for field in (
                "initial_absent",
                "final_present",
                "final_forbidden",
                "final_noise_matchers",
            ):
                values = getattr(case, field)
                if values:
                    payload[field] = [_matcher_payload(item) for item in values]
            if case.final_at_least is not None:
                payload["final_at_least"] = {
                    "matchers": [
                        _matcher_payload(item)
                        for item in case.final_at_least.matchers
                    ],
                    "min_matches": case.final_at_least.min_matches,
                }
            for field in (
                "expected_termination_reason",
                "expected_retrieval_call_count",
                "maximum_retrieval_call_count",
                "minimum_goal_gain",
                "maximum_final_noise_items",
            ):
                value = getattr(case, field)
                if value is not None:
                    payload[field] = value
            cases.append(payload)
        repo_payload["queries"] = cases
        repos.append(repo_payload)
    return {
        "schema_version": fixture.schema_version,
        "profile_configs": fixture.profile_configs,
        "repos": repos,
    }


def test_production_p4_fixture_projection_matches_frozen_raw_catalog() -> None:
    assert _production_catalog_projection() == load_raw_p4_catalog()


def _write_fixture(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _canonical_fixture(
    *,
    profile: str = "p4_exploration",
    profile_config: dict[str, object] | None = None,
    remote: bool = False,
) -> dict[str, object]:
    config = profile_config or {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    }
    repo: dict[str, object] = {
        "repo_key": "sample",
        "profiles": [profile],
        "queries": [
            {
                "id": "flow",
                "query": "owner flow",
                "profiles": [profile],
                "mode": "exploration",
            }
        ],
    }
    if remote:
        repo.update(
            {
                "source_url": "https://example.com/sample.git",
                "source_commit": "a" * 40,
                "checkout_dir": "sample",
            }
        )
    else:
        repo["snapshot_path"] = "snapshot"
    return {
        "schema_version": 1,
        "profile_configs": {profile: config},
        "repos": [repo],
    }


@pytest.mark.parametrize(
    "profile_config",
    [
        {
            "embedding": {
                "provider": "hash",
                "model": "wrong",
                "dimensions": 384,
            },
            "query_planner": {"enabled": False},
        },
        {
            "embedding": {
                "provider": "hash",
                "model": "hash-v1",
                "dimensions": 384,
                "base_url": "https://example.com",
            },
            "query_planner": {"enabled": False},
        },
        {
            "embedding": {
                "provider": "hash",
                "model": "hash-v1",
                "dimensions": 384,
            },
            "query_planner": {"enabled": True},
        },
    ],
)
def test_p4_deterministic_profile_is_closed(
    tmp_path: Path,
    profile_config: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _canonical_fixture(profile_config=profile_config),
            )
        )


def test_p4_source_contracts_distinguish_snapshot_and_remote(
    tmp_path: Path,
) -> None:
    deterministic_remote = _canonical_fixture(remote=True)
    with pytest.raises(ValueError, match="snapshot"):
        load_quality_fixture(_write_fixture(tmp_path, deterministic_remote))

    real_snapshot = _canonical_fixture(profile="p4_real_exploration")
    real_snapshot["profile_configs"]["p4_real_exploration"]["retrieval"] = {
        "final_top_k": 12
    }
    with pytest.raises(ValueError, match="remote"):
        load_quality_fixture(_write_fixture(tmp_path, real_snapshot))


def _explored_fixture() -> SimpleNamespace:
    first_probe = SimpleNamespace(
        unique_path_count=3,
        duplicate_path_count=1,
        novel_path_count=2,
        newly_satisfied_goal_ids=("goal-2",),
        duration_ms=7,
    )
    second_probe = SimpleNamespace(
        unique_path_count=2,
        duplicate_path_count=2,
        novel_path_count=0,
        newly_satisfied_goal_ids=(),
        duration_ms=5,
    )
    initial_probe = SimpleNamespace(duration_ms=5)
    trace = SimpleNamespace(
        retained_goal_count=4,
        initial_satisfied_goal_count=1,
        final_satisfied_goal_count=3,
        executed_probe_count=2,
        retrieval_call_count=3,
        final_evidence_count=3,
        final_evidence_omitted_count=2,
        final_evidence=(
            SimpleNamespace(
                source_round=1,
                probe_id="r1p0",
                probe_rank=1,
                selection_reason="added_novel_probe_evidence",
            ),
        ),
        termination_reason="satisfied",
        duration_ms=19,
        rounds=(
            SimpleNamespace(probes=(initial_probe,)),
            SimpleNamespace(probes=(first_probe, second_probe)),
        ),
    )
    return SimpleNamespace(
        initial_bundle=_bundle("src/A.java", "src/B.java"),
        initial_pack=_pack("src/A.java"),
        fused_bundle=_bundle(
            "src/A.java",
            "src/B.java",
            "src/C.java",
            "src/noise/Generated.java",
        ),
        final_pack=_pack(
            "src/C.java",
            "src/D.java",
            "src/noise/Generated.java",
        ),
        trace=trace,
    )


def test_exploration_metrics_and_gates_use_same_run_artifacts() -> None:
    case = QualityCase(
        case_id="flow",
        query="owner flow",
        mode="exploration",
        gate=Gate.REQUIRED,
        initial_absent=(Matcher(path="src/OwnerTest.java"),),
        final_present=(Matcher(path="src/C.java"),),
        final_at_least=FinalAtLeast(
            (Matcher(path="src/C.java"), Matcher(path="src/D.java")),
            2,
        ),
        final_forbidden=(Matcher(path="package-lock.json"),),
        final_noise_matchers=(Matcher(glob="src/noise/**"),),
        expected_termination_reason="satisfied",
        expected_retrieval_call_count=3,
        maximum_retrieval_call_count=3,
        minimum_goal_gain=2,
        maximum_final_noise_items=1,
    )
    evaluation = CaseEvaluation(
        case_id="flow",
        status="pass",
        metrics={"latency_ms": 5},
        failures=[],
        top_results=[],
    )

    result = evaluate_exploration(case, _explored_fixture(), evaluation)
    metrics = {name: result.metrics[name] for name in EXPLORATION_METRICS}

    assert result.status == "pass"
    assert result.failures == []
    assert metrics == {
        "exploration_goal_coverage_initial": 0.25,
        "exploration_goal_coverage_final": 0.75,
        "exploration_goal_gain": 2,
        "novel_path_count": 2,
        "duplicate_path_ratio": 0.6,
        "executed_probe_count": 2,
        "probe_efficiency": 0.5,
        "retrieval_call_count": 3,
        "exploration_trace_coverage": 1.0,
        "final_pack_noise_count": 1,
        "final_pack_noise_ratio": 1 / 3,
        "exploration_latency_ms": 19,
    }


def test_exploration_metrics_use_null_for_zero_denominators() -> None:
    trace = SimpleNamespace(
        retained_goal_count=0,
        initial_satisfied_goal_count=0,
        final_satisfied_goal_count=0,
        executed_probe_count=0,
        retrieval_call_count=1,
        final_evidence_count=0,
        final_evidence_omitted_count=0,
        final_evidence=(),
        termination_reason="initial_empty",
        duration_ms=0,
        rounds=(SimpleNamespace(probes=(SimpleNamespace(duration_ms=0),)),),
    )
    explored = SimpleNamespace(
        initial_bundle=_bundle(),
        initial_pack=_pack(),
        fused_bundle=_bundle(),
        final_pack=_pack(),
        trace=trace,
    )
    evaluation = CaseEvaluation("empty", "pass", {}, [], [])

    result = evaluate_exploration(
        QualityCase("empty", "owner flow", mode="exploration"),
        explored,
        evaluation,
    )

    assert set(result.metrics).issuperset(EXPLORATION_METRICS)
    for name in (
        "exploration_goal_coverage_initial",
        "exploration_goal_coverage_final",
        "duplicate_path_ratio",
        "probe_efficiency",
        "exploration_trace_coverage",
        "final_pack_noise_ratio",
    ):
        assert result.metrics[name] is None


def test_exploration_metric_invariants_fail_closed() -> None:
    explored = _explored_fixture()
    explored.trace.retrieval_call_count = 2
    with pytest.raises(ValueError, match="retrieval_call_count"):
        evaluate_exploration(
            QualityCase("flow", "owner flow", mode="exploration"),
            explored,
            CaseEvaluation("flow", "pass", {}, [], []),
        )


def test_quality_runner_keeps_exploration_import_inside_mode_branch() -> None:
    source = Path(quality_runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert all(
        not (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("context_search_tool.exploration")
        )
        for node in top_level_imports
    )


def test_quality_exploration_runner_calls_explore_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import context_search_tool.exploration as exploration

    explored = _explored_fixture()
    calls: list[tuple[Path, str]] = []

    def fake_explore(repo, query, config, options):
        calls.append((repo, query))
        return explored

    monkeypatch.setattr(exploration, "explore_repository", fake_explore)
    monkeypatch.setattr(
        exploration,
        "resolve_explore_pack_options",
        lambda config, **kwargs: object(),
    )
    sentinel = CaseEvaluation("flow", "pass", {}, [], [])
    monkeypatch.setattr(
        quality_runner,
        "_evaluate_explored_case",
        lambda case, profile, value: sentinel,
    )
    monkeypatch.setattr(
        quality_runner,
        "query_repository",
        lambda *args, **kwargs: pytest.fail("original query must not be re-run"),
    )

    returned_explored, returned_evaluation = quality_runner._run_exploration_case(
        tmp_path,
        QualityCase("flow", "owner flow", mode="exploration"),
        "p4_exploration",
        ToolConfig(),
    )

    assert returned_explored is explored
    assert returned_evaluation is sentinel
    assert calls == [(tmp_path, "owner flow")]


def _exploration_metric_payload(
    *,
    latency: int,
    gain: int = 2,
) -> dict[str, object]:
    return {
        "exploration_goal_coverage_initial": 0.25,
        "exploration_goal_coverage_final": 0.75,
        "exploration_goal_gain": gain,
        "novel_path_count": 3,
        "duplicate_path_ratio": None,
        "executed_probe_count": 1,
        "probe_efficiency": 1.0,
        "retrieval_call_count": 2,
        "exploration_trace_coverage": 1.0,
        "final_pack_noise_count": 0,
        "final_pack_noise_ratio": 0.0,
        "exploration_latency_ms": latency,
        "latency_ms": 5,
    }


def test_aggregate_handles_nullable_exploration_metrics_and_total_latency() -> None:
    cases = [
        {
            "repo_key": "sample",
            "case_id": "one",
            "status": "pass",
            "attempted": True,
            "tags": ["p4"],
            "metrics": _exploration_metric_payload(latency=10),
        },
        {
            "repo_key": "sample",
            "case_id": "two",
            "status": "pass",
            "attempted": True,
            "tags": ["p4"],
            "metrics": {
                **_exploration_metric_payload(latency=30),
                "duplicate_path_ratio": 0.5,
            },
        },
    ]
    repos = [
        {
            "repo_key": "sample",
            "config": {
                "embedding": {"provider": "hash", "model": "hash-v1"}
            },
        }
    ]

    metrics = aggregate_cases(cases, repos, "p4_exploration")["metrics"]["overall"]

    assert metrics["duplicate_path_ratio"] == {"count": 1, "mean": 0.5}
    assert metrics["exploration_latency_ms"] == {
        "count": 2,
        "mean": 20.0,
        "p50": 10,
        "p95": 30,
    }


def _comparison_report(
    *,
    exploration_latency: int | None,
    legacy_latency: int,
    gain: int,
) -> dict[str, object]:
    metrics = _exploration_metric_payload(
        latency=exploration_latency or 0,
        gain=gain,
    )
    if exploration_latency is None:
        metrics.pop("exploration_latency_ms")
    metrics["latency_ms"] = legacy_latency
    return {
        "schema_version": 1,
        "aggregate": {"metrics": {}},
        "cases": [
            {
                "repo_key": "sample",
                "case_id": "flow",
                "status": "pass",
                "metrics": metrics,
            }
        ],
    }


def test_comparison_treats_p4_deltas_as_neutral_and_prefers_total_latency() -> None:
    comparison = compare_reports(
        _comparison_report(exploration_latency=10, legacy_latency=100, gain=2),
        _comparison_report(exploration_latency=16, legacy_latency=50, gain=5),
    )
    case = comparison["cases"][0]

    assert case["classification"] == "unchanged_pass"
    assert case["gating"] is False
    assert case["metric_deltas"]["exploration_goal_gain"]["delta"] == 3
    assert case["warnings"] == ["latency increased by more than 50%"]


def test_comparison_latency_warning_falls_back_for_non_exploration_cases() -> None:
    comparison = compare_reports(
        _comparison_report(exploration_latency=None, legacy_latency=10, gain=2),
        _comparison_report(exploration_latency=None, legacy_latency=16, gain=2),
    )
    assert comparison["cases"][0]["warnings"] == [
        "latency increased by more than 50%"
    ]


def test_markdown_report_shows_bounded_exploration_summary_only() -> None:
    markdown = render_markdown_report(
        {
            "profile": "p4_exploration",
            "aggregate": {
                "selected": 1,
                "attempted": 1,
                "executed": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "known_gaps": 0,
                "informational": 0,
                "errors": 0,
                "metrics": {"overall": {}},
            },
            "cases": [
                {
                    "repo_key": "sample",
                    "case_id": "flow",
                    "status": "pass",
                    "metrics": _exploration_metric_payload(latency=19),
                    "top_results": [{"path": "SECRET_SOURCE_PATH"}],
                    "probes": ["SECRET_PROBE"],
                    "failures": [],
                }
            ],
        }
    )

    assert "## Exploration Cases" in markdown
    assert "sample/flow" in markdown
    assert "calls" in markdown
    assert "goal gain" in markdown
    assert "trace coverage" in markdown
    assert "noise" in markdown
    assert "latency ms" in markdown
    assert "SECRET_SOURCE_PATH" not in markdown
    assert "SECRET_PROBE" not in markdown


def test_acceptance_projection_normalizes_only_trace_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_payload = {
        "schema_version": 2,
        "mode": "exploration",
        "duration_ms": 19,
        "kept": 7,
        "rounds": [
            {
                "duration_ms": 11,
                "kept": "round",
                "probes": [
                    {"duration_ms": 5, "kept": "probe"},
                ],
            }
        ],
    }
    explored = _explored_fixture()
    monkeypatch.setattr(
        acceptance,
        "exploration_trace_payload",
        lambda trace: trace_payload,
    )
    monkeypatch.setattr(
        acceptance,
        "canonical_context_pack_bytes",
        lambda pack: b"initial" if pack is explored.initial_pack else b"final",
    )
    metrics = _exploration_metric_payload(latency=19)
    evaluation = CaseEvaluation("flow", "pass", metrics, [], [])
    case = QualityCase("flow", "owner flow", mode="exploration")

    projection = acceptance.build_projection(
        "sample",
        case,
        explored,
        evaluation,
    )

    assert tuple(projection) == acceptance.PROJECTION_KEYS
    assert tuple(projection["non_timing_metrics"]) == acceptance.NON_TIMING_METRICS
    assert "exploration_latency_ms" not in projection["non_timing_metrics"]
    assert projection["trace"] == {
        "schema_version": 2,
        "mode": "exploration",
        "duration_ms": 0,
        "kept": 7,
        "rounds": [
            {
                "duration_ms": 0,
                "kept": "round",
                "probes": [{"duration_ms": 0, "kept": "probe"}],
            }
        ],
    }
    assert trace_payload["duration_ms"] == 19


def test_acceptance_projection_matches_production_quality_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explored = _explored_fixture()
    case = QualityCase("flow", "owner flow", mode="exploration")
    calls: list[str] = []

    def fake_raw(*args, **kwargs):
        calls.append("raw")
        assert kwargs["latency_ms"] == 5
        return CaseEvaluation("flow", "pass", {"latency_ms": 5}, [], [])

    def fake_context(case, pack, evaluation):
        calls.append("context")
        assert pack is explored.final_pack
        return evaluation

    def fake_exploration(case, value, evaluation):
        calls.append("exploration")
        return CaseEvaluation(
            "flow",
            "pass",
            _exploration_metric_payload(latency=19),
            ["fixture failure"],
            [],
        )

    monkeypatch.setattr(quality_runner, "evaluate_case", fake_raw)
    monkeypatch.setattr(
        quality_runner,
        "_apply_profile_expectations",
        lambda case, profile, bundle, evaluation: evaluation,
    )
    monkeypatch.setattr(quality_runner, "evaluate_context_pack", fake_context)
    monkeypatch.setattr(quality_runner, "evaluate_exploration", fake_exploration)
    evaluation = quality_runner._evaluate_explored_case(
        case,
        "p4_exploration",
        explored,
    )
    monkeypatch.setattr(
        acceptance,
        "exploration_trace_payload",
        lambda trace: {
            "schema_version": 2,
            "mode": "exploration",
            "duration_ms": 19,
            "rounds": [],
        },
    )
    monkeypatch.setattr(
        acceptance,
        "canonical_context_pack_bytes",
        lambda pack: b"pack",
    )

    projection = acceptance.build_projection("sample", case, explored, evaluation)

    assert calls == ["raw", "context", "exploration"]
    assert projection["non_timing_metrics"] == {
        name: evaluation.metrics[name]
        for name in acceptance.NON_TIMING_METRICS
    }
    assert projection["failures"] == evaluation.failures


def _acceptance_candidate() -> dict[str, object]:
    fixture = load_quality_fixture(P4_CATALOG_PATH)
    repo = next(item for item in fixture.repos if item.repo_key == "spring_petclinic")
    case = repo.queries[0]
    return {
        "schema_version": 1,
        "repo_key": repo.repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "initial_result_paths": [
            "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
        ],
        "initial_context_pack_sha256": "0" * 64,
        "final_context_pack_sha256": "1" * 64,
        "trace": {
            "schema_version": 2,
            "mode": "exploration",
            "duration_ms": 0,
            "rounds": [],
        },
        "non_timing_metrics": {
            name: 0 for name in acceptance.NON_TIMING_METRICS
        },
        "failures": [],
    }


def test_acceptance_initialize_refuses_drift_and_overwrite(tmp_path: Path) -> None:
    content = acceptance.canonical_json_bytes(_acceptance_candidate())
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    output = tmp_path / "expected.json"
    first.write_bytes(content)
    second.write_bytes(content)

    acceptance.initialize_projection(P4_CATALOG_PATH, first, second, output)
    acceptance.verify_projection(second, output)
    assert output.read_bytes() == content

    with pytest.raises(ValueError, match="already exists"):
        acceptance.initialize_projection(P4_CATALOG_PATH, first, second, output)

    drifted = tmp_path / "drifted.json"
    drifted.write_bytes(content + b" ")
    with pytest.raises(ValueError, match="differ"):
        acceptance.initialize_projection(
            P4_CATALOG_PATH,
            first,
            drifted,
            tmp_path / "other.json",
        )
