import pytest

from context_search_tool.quality.compare import compare_reports


def _case(
    repo_key: str,
    case_id: str,
    status: str,
    metrics: dict | None = None,
    *,
    gate: str = "required",
    tags: list[str] | None = None,
) -> dict:
    return {
        "repo_key": repo_key,
        "case_id": case_id,
        "gate": gate,
        "tags": tags or [],
        "status": status,
        "metrics": metrics or {},
    }


def _repo(repo_key: str, content_hash: str) -> dict:
    return {
        "repo_key": repo_key,
        "source": {
            "content_hash": content_hash,
        },
    }


def _report(
    cases: list[dict],
    *,
    schema_version: int = 2,
    fixture_sha256: str = "sha256:same",
    profile: str = "ci",
    config_hash: str = "sha256:config",
    embedding: dict | None = None,
    planner: dict | None = None,
    repos: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": schema_version,
        "fixture": {"sha256": fixture_sha256},
        "profile": profile,
        "config": {
            "config_hash": config_hash,
            "embedding": embedding if embedding is not None else {"provider": "hash"},
        },
        "planner": planner if planner is not None else {"enabled": False},
        "repos": repos if repos is not None else [_repo("sample", "sha256:content")],
        "aggregate": {
            "metrics": {
                "overall": {},
                "by_repository": {},
                "by_tag": {},
                "by_profile": {},
                "by_embedding": {},
            }
        },
        "cases": cases,
    }


def _classifications(comparison: dict) -> dict[str, str]:
    return {
        case["case_key"]: case["classification"]
        for case in comparison["cases"]
    }


def test_pass_to_fail_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([_case("sample", "target", "fail")]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["gating_regressions"] == 1


def test_fail_to_pass_is_improved() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "fail")]),
        _report([_case("sample", "target", "pass")]),
    )

    assert _classifications(comparison) == {"sample/target": "improved"}
    assert comparison["aggregate"]["improvements"] == 1


def test_fixture_sha256_mismatch_adds_metadata_warning() -> None:
    comparison = compare_reports(
        _report([], fixture_sha256="sha256:baseline"),
        _report([], fixture_sha256="sha256:candidate"),
    )

    assert "fixture sha256 differs" in comparison["metadata_warnings"]


def test_noise_top5_increase_by_at_least_two_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"noise_top5": 1})]),
        _report([_case("sample", "target", "pass", {"noise_top5": 3})]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}


def test_latency_increase_by_more_than_fifty_percent_adds_case_warning() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"latency_ms": 100})]),
        _report([_case("sample", "target", "pass", {"latency_ms": 151})]),
    )

    assert comparison["cases"][0]["warnings"] == [
        "latency increased by more than 50%"
    ]


def test_skipped_to_skipped_preserves_skipped_classification() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "skipped")]),
        _report([_case("sample", "target", "skipped")]),
    )

    assert _classifications(comparison) == {"sample/target": "skipped"}
    assert comparison["aggregate"]["skipped"] == 1


def test_baseline_missing_is_new_case() -> None:
    comparison = compare_reports(
        _report([]),
        _report([_case("sample", "target", "pass")]),
    )

    assert _classifications(comparison) == {"sample/target": "new_case"}
    assert comparison["aggregate"]["new_case"] == 1


def test_candidate_missing_is_removed_required() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([]),
    )

    assert _classifications(comparison) == {"sample/target": "removed_required"}
    assert comparison["aggregate"]["removed_required"] == 1


def test_pass_to_error_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([_case("sample", "target", "error")]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["gating_regressions"] == 1


def test_hit_at_5_false_to_true_is_improved_without_status_transition() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"hit_at_5": False})]),
        _report([_case("sample", "target", "pass", {"hit_at_5": True})]),
    )

    assert _classifications(comparison) == {"sample/target": "improved"}
    assert comparison["aggregate"]["improvements"] == 1


def test_hit_at_5_true_to_false_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"hit_at_5": True})]),
        _report([_case("sample", "target", "pass", {"hit_at_5": False})]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["gating_regressions"] == 1


def test_mrr_drop_greater_than_point_twenty_five_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"mrr": 0.9})]),
        _report([_case("sample", "target", "pass", {"mrr": 0.64})]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["gating_regressions"] == 1


def test_metadata_warnings_include_report_and_config_differences() -> None:
    comparison = compare_reports(
        _report(
            [],
            schema_version=1,
            profile="ci",
            config_hash="sha256:baseline-config",
            embedding={"provider": "hash"},
            planner={"enabled": False},
            repos=[_repo("sample", "sha256:baseline-content")],
        ),
        _report(
            [],
            schema_version=2,
            profile="smoke",
            config_hash="sha256:candidate-config",
            embedding={"provider": "bge"},
            planner={"enabled": True},
            repos=[_repo("sample", "sha256:candidate-content")],
        ),
    )

    assert comparison["metadata_warnings"] == [
        "report schema_version differs",
        "profile differs",
        "config hash differs",
        "embedding config differs",
        "planner config differs",
        "repo identity differs",
    ]


@pytest.mark.parametrize(
    "baseline_status,candidate_status,classification,gating",
    [
        ("pass", "fail", "regressed", True),
        ("pass", "error", "regressed", True),
        ("pass", "skipped", "regressed", True),
        ("fail", "pass", "improved", False),
        ("fail", "fail", "unchanged_fail", False),
        ("fail", "error", "execution_regressed", True),
        ("fail", "skipped", "coverage_lost_required", True),
        ("error", "pass", "improved", False),
        ("error", "fail", "newly_evaluated_failure", False),
        ("error", "error", "unchanged_error", False),
        ("error", "skipped", "unchanged_unverified", False),
        ("skipped", "pass", "newly_verified", False),
        ("skipped", "fail", "newly_evaluated_failure", False),
        ("skipped", "error", "unchanged_unverified", False),
        ("skipped", "skipped", "skipped", False),
    ],
)
def test_required_status_matrix(
    baseline_status: str,
    candidate_status: str,
    classification: str,
    gating: bool,
) -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", baseline_status)]),
        _report([_case("sample", "target", candidate_status)]),
    )

    assert comparison["cases"][0]["classification"] == classification
    assert comparison["cases"][0]["gating"] is gating


def test_required_removal_and_gate_weakening_are_gating() -> None:
    removed = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([]),
    )
    weakened = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report(
            [_case("sample", "target", "informational", gate="informational")]
        ),
    )

    assert removed["cases"][0]["classification"] == "removed_required"
    assert removed["aggregate"]["gating_regressions"] == 1
    assert weakened["cases"][0]["classification"] == "gate_weakened"
    assert weakened["aggregate"]["gating_regressions"] == 1


def test_non_required_removal_and_gate_strengthening_are_observations() -> None:
    removed = compare_reports(
        _report([_case("sample", "target", "informational", gate="informational")]),
        _report([]),
    )
    strengthened = compare_reports(
        _report([_case("sample", "target", "informational", gate="informational")]),
        _report([_case("sample", "target", "pass", gate="required")]),
    )

    assert removed["cases"][0]["classification"] == "removed_observation"
    assert removed["aggregate"]["gating_regressions"] == 0
    assert strengthened["cases"][0]["classification"] == "gate_strengthened"


def test_different_non_required_gates_are_observational_changes() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "known_gap", gate="known_gap")]),
        _report(
            [_case("sample", "target", "informational", gate="informational")]
        ),
    )

    assert comparison["cases"][0]["classification"] == "gate_changed_observation"
    assert comparison["cases"][0]["gating"] is False


@pytest.mark.parametrize(
    "baseline_metrics,candidate_metrics,classification",
    [
        ({"hit_at_5": True}, {"hit_at_5": False}, "regressed"),
        ({"mrr": 0.9}, {"mrr": 0.64}, "regressed"),
        ({"noise_top5": 1}, {"noise_top5": 3}, "regressed"),
        ({"hit_at_5": False}, {"hit_at_5": True}, "improved"),
        ({"mrr": 0.5}, {"mrr": 0.76}, "improved"),
        ({"noise_top5": 3}, {"noise_top5": 1}, "improved"),
        (
            {"mrr": 0.9, "noise_top5": 3},
            {"mrr": 0.64, "noise_top5": 1},
            "regressed",
        ),
    ],
)
def test_required_protected_metric_thresholds(
    baseline_metrics: dict,
    candidate_metrics: dict,
    classification: str,
) -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", baseline_metrics)]),
        _report([_case("sample", "target", "pass", candidate_metrics)]),
    )

    assert comparison["cases"][0]["classification"] == classification


@pytest.mark.parametrize(
    "baseline_metrics,candidate_metrics",
    [
        ({"mrr": 0.5}, {"mrr": 0.75}),
        ({"noise_top5": 3}, {"noise_top5": 2}),
    ],
)
def test_required_threshold_boundaries_are_not_protected_changes(
    baseline_metrics: dict,
    candidate_metrics: dict,
) -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", baseline_metrics)]),
        _report([_case("sample", "target", "pass", candidate_metrics)]),
    )

    assert comparison["cases"][0]["classification"] == "unchanged_pass"


def test_boolean_numeric_metrics_do_not_trigger_numeric_thresholds() -> None:
    comparison = compare_reports(
        _report(
            [_case("sample", "target", "pass", {"mrr": False, "noise_top5": True})]
        ),
        _report(
            [_case("sample", "target", "pass", {"mrr": True, "noise_top5": False})]
        ),
    )

    case = comparison["cases"][0]
    assert case["classification"] == "unchanged_pass"
    assert case["metric_deltas"] == {
        "mrr": {"baseline": False, "candidate": True, "delta": 1},
        "noise_top5": {"baseline": True, "candidate": False, "delta": -1},
    }


def test_informational_mixed_metrics_use_decline_first_without_gating() -> None:
    comparison = compare_reports(
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "informational",
                    {"precision_at_12": 0.5, "noise_top12": 4},
                    gate="informational",
                )
            ]
        ),
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "informational",
                    {"precision_at_12": 0.7, "noise_top12": 5},
                    gate="informational",
                )
            ]
        ),
    )

    case = comparison["cases"][0]
    assert case["classification"] == "metric_decline"
    assert case["gating"] is False
    assert case["metric_deltas"]["precision_at_12"]["delta"] == pytest.approx(0.2)
    assert comparison["aggregate"]["observed_declines"] == 1


@pytest.mark.parametrize(
    "baseline_status,candidate_status",
    [
        ("informational", "skipped"),
        ("error", "informational"),
        ("known_gap", "error"),
    ],
)
def test_non_required_unavailable_statuses_are_observations(
    baseline_status: str,
    candidate_status: str,
) -> None:
    comparison = compare_reports(
        _report(
            [_case("sample", "target", baseline_status, gate="informational")]
        ),
        _report(
            [_case("sample", "target", candidate_status, gate="informational")]
        ),
    )

    assert comparison["cases"][0]["classification"] == "observation_unavailable"
    assert comparison["cases"][0]["gating"] is False


def test_compare_rejects_duplicate_case_keys_and_unsupported_schema() -> None:
    duplicate = _report(
        [_case("sample", "same", "pass"), _case("sample", "same", "pass")]
    )
    with pytest.raises(ValueError, match="duplicate case key"):
        compare_reports(duplicate, _report([]))
    with pytest.raises(ValueError, match="unsupported report schema"):
        compare_reports(_report([], schema_version=3), _report([]))


@pytest.mark.parametrize("schema_version", [True, 1.0, "2"])
def test_compare_requires_integer_report_schema(schema_version: object) -> None:
    with pytest.raises(ValueError, match="unsupported report schema"):
        compare_reports(_report([], schema_version=schema_version), _report([]))


def test_v1_case_without_gate_defaults_to_required() -> None:
    baseline_case = _case("sample", "target", "pass")
    baseline_case.pop("gate")

    comparison = compare_reports(
        _report([baseline_case], schema_version=1),
        _report([], schema_version=1),
    )

    assert comparison["cases"][0]["classification"] == "removed_required"
    assert comparison["cases"][0]["baseline_gate"] == "required"


@pytest.mark.parametrize(
    "case, message",
    [
        (_case("sample", "bad-status", "surprise"), "unknown status"),
        (
            _case("sample", "bad-gate", "informational", gate="surprise"),
            "unknown gate",
        ),
        (
            _case("sample", "inconsistent", "known_gap", gate="required"),
            "inconsistent required gate/status",
        ),
    ],
)
def test_compare_rejects_invalid_statuses_and_gates_with_case_key(
    case: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=rf"{message}.*sample/{case['case_id']}"):
        compare_reports(_report([case]), _report([]))


def test_compare_rejects_pass_case_without_metric_object() -> None:
    invalid = _case("sample", "target", "pass")
    invalid["metrics"] = None

    with pytest.raises(ValueError, match="pass case missing metrics: sample/target"):
        compare_reports(_report([invalid]), _report([]))


def test_comparison_emits_nested_aggregate_metric_deltas() -> None:
    baseline = _report([])
    candidate = _report([])
    baseline["aggregate"]["metrics"]["overall"] = {
        "mrr": {"count": 2, "mean": 0.5},
        "hit_at_5": {"successes": 1, "total": 2, "rate": 0.5},
    }
    candidate["aggregate"]["metrics"]["overall"] = {
        "mrr": {"count": 2, "mean": 0.75},
        "hit_at_5": {"successes": 2, "total": 2, "rate": 1.0},
    }

    comparison = compare_reports(baseline, candidate)

    assert comparison["metric_deltas"]["overall"]["mrr"]["delta"] == 0.25
    assert comparison["metric_deltas"]["overall"]["hit_at_5"]["delta"] == 0.5


def test_comparison_preserves_latency_aggregate_leaves() -> None:
    baseline = _report([])
    candidate = _report([])
    baseline["aggregate"]["metrics"]["overall"] = {
        "latency_ms": {"count": 2, "mean": 10, "p50": 8, "p95": 12},
    }
    candidate["aggregate"]["metrics"]["overall"] = {
        "latency_ms": {"count": 3, "mean": 12, "p50": 9, "p95": 15},
    }

    comparison = compare_reports(baseline, candidate)

    assert comparison["metric_deltas"]["overall"]["latency_ms"] == {
        "mean": {"baseline": 10.0, "candidate": 12.0, "delta": 2.0},
        "p50": {"baseline": 8.0, "candidate": 9.0, "delta": 1.0},
        "p95": {"baseline": 12.0, "candidate": 15.0, "delta": 3.0},
    }


def test_v2_repo_effective_config_difference_is_reported() -> None:
    baseline = _report([])
    candidate = _report([])
    baseline["repos"][0]["config"] = {"config_hash": "sha256:baseline"}
    candidate["repos"][0]["config"] = {"config_hash": "sha256:candidate"}

    comparison = compare_reports(baseline, candidate)

    assert "repo effective config differs" in comparison["metadata_warnings"]


def test_case_delta_flattens_expected_coverage_ratio() -> None:
    comparison = compare_reports(
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "pass",
                    {"expected_coverage_top5": {"count": 1, "ratio": 0.5}},
                )
            ]
        ),
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "pass",
                    {"expected_coverage_top5": {"count": 2, "ratio": 1.0}},
                )
            ]
        ),
    )

    assert comparison["cases"][0]["metric_deltas"][
        "expected_coverage_top5_ratio"
    ]["delta"] == 0.5
