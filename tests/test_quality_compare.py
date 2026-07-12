from pathlib import Path

import pytest

from context_search_tool.quality.compare import compare_reports
from context_search_tool.quality.runner import run_quality_fixture


CATALOG_PATH = (
    Path(__file__).parent / "fixtures" / "retrieval_quality" / "queries.json"
)


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
        "config": {"config_hash": "sha256:config"},
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


@pytest.mark.parametrize(
    "baseline_mrr,candidate_mrr",
    [(0.54, 0.29), (0.29, 0.54)],
)
def test_required_mrr_exact_mathematical_boundary_is_unchanged(
    baseline_mrr: float,
    candidate_mrr: float,
) -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"mrr": baseline_mrr})]),
        _report([_case("sample", "target", "pass", {"mrr": candidate_mrr})]),
    )

    assert comparison["cases"][0]["classification"] == "unchanged_pass"


@pytest.mark.parametrize(
    "baseline_mrr,candidate_mrr,classification",
    [
        (0.54, 0.289999999998, "regressed"),
        (0.29, 0.540000000002, "improved"),
    ],
)
def test_required_mrr_change_beyond_tolerance_crosses_threshold(
    baseline_mrr: float,
    candidate_mrr: float,
    classification: str,
) -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"mrr": baseline_mrr})]),
        _report([_case("sample", "target", "pass", {"mrr": candidate_mrr})]),
    )

    assert comparison["cases"][0]["classification"] == classification


@pytest.mark.parametrize(
    "baseline_noise,candidate_noise,classification",
    [
        (0.01, 2.01, "regressed"),
        (2.01, 0.01, "improved"),
        (0.01, 2.009999999998, "unchanged_pass"),
        (2.009999999998, 0.01, "unchanged_pass"),
    ],
)
def test_schema_v1_noise_threshold_is_float_stable(
    baseline_noise: float,
    candidate_noise: float,
    classification: str,
) -> None:
    comparison = compare_reports(
        _report(
            [_case("sample", "target", "pass", {"noise_top5": baseline_noise})],
            schema_version=1,
        ),
        _report(
            [_case("sample", "target", "pass", {"noise_top5": candidate_noise})],
            schema_version=1,
        ),
    )

    assert comparison["cases"][0]["classification"] == classification


@pytest.mark.parametrize(
    "metric_name,value",
    [
        ("hit_at_5", 1),
        ("mrr", False),
        ("mrr", "0.5"),
        ("mrr", float("nan")),
        ("mrr", float("inf")),
        ("mrr", -0.1),
        ("mrr", 1.1),
        ("noise_top5", True),
        ("noise_top5", float("nan")),
        ("noise_top5", float("inf")),
        ("noise_top5", -1),
        ("latency_ms", -1),
    ],
)
def test_compare_rejects_invalid_known_case_metrics_with_case_key(
    metric_name: str,
    value: object,
) -> None:
    invalid = _report(
        [_case("sample", "target", "pass", {metric_name: value})]
    )

    with pytest.raises(
        ValueError,
        match=rf"sample/target.*{metric_name}",
    ):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize("value", ["value", [], {"nested": 1}, object()])
def test_compare_rejects_non_scalar_custom_case_metrics(value: object) -> None:
    invalid = _report(
        [_case("sample", "target", "pass", {"custom_metric": value})]
    )

    with pytest.raises(
        ValueError,
        match=r"sample/target.*custom_metric",
    ):
        compare_reports(invalid, _report([]))


def test_compare_accepts_supported_nullable_and_custom_scalar_metrics() -> None:
    comparison = compare_reports(
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "pass",
                    {
                        "hit_at_5": None,
                        "mrr": None,
                        "noise_top5": 0,
                        "custom_bool": True,
                        "custom_number": -2.5,
                        "custom_missing": None,
                    },
                )
            ]
        ),
        _report(
            [
                _case(
                    "sample",
                    "target",
                    "pass",
                    {
                        "hit_at_5": None,
                        "mrr": None,
                        "noise_top5": 1,
                        "custom_bool": False,
                        "custom_number": -1.5,
                        "custom_missing": None,
                    },
                )
            ]
        ),
    )

    assert comparison["cases"][0]["metric_deltas"]["custom_number"]["delta"] == 1


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


@pytest.mark.parametrize("report", [None, [], "report"])
def test_compare_requires_report_objects(report: object) -> None:
    with pytest.raises(ValueError, match="report must be an object"):
        compare_reports(report, _report([]))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("cases", None, "report cases must be a list"),
        ("fixture", [], "report fixture must be an object"),
        ("config", [], "report config must be an object"),
        ("planner", [], "report planner must be an object"),
        ("repos", {}, "report repos must be a list"),
        ("aggregate", [], "report aggregate must be an object"),
    ],
)
def test_compare_rejects_malformed_top_level_containers(
    field: str,
    value: object,
    message: str,
) -> None:
    invalid = _report([])
    invalid[field] = value

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize(
    "case,message",
    [
        (None, "report case must be an object"),
        (
            {"repo_key": "", "case_id": "target", "status": "pass", "metrics": {}},
            "repo_key must be a non-empty string",
        ),
        (
            {"repo_key": "sample", "case_id": "", "status": "pass", "metrics": {}},
            "case_id must be a non-empty string",
        ),
        (
            {
                "repo_key": "sample",
                "case_id": "target",
                "status": "fail",
                "gate": "required",
                "metrics": [],
            },
            "metrics must be an object",
        ),
        (
            {
                "repo_key": "sample",
                "case_id": "target",
                "status": "fail",
                "gate": "required",
            },
            "metrics must be an object",
        ),
    ],
)
def test_compare_rejects_malformed_case_containers(
    case: object,
    message: str,
) -> None:
    invalid = _report([])
    invalid["cases"] = [case]

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize(
    "repos,message",
    [
        ([None], "report repo must be an object"),
        ([{"repo_key": "sample", "source": []}], "repo source must be an object"),
        ([{"repo_key": "sample", "config": []}], "repo config must be an object"),
    ],
)
def test_compare_rejects_malformed_repo_metadata(
    repos: list[object],
    message: str,
) -> None:
    invalid = _report([])
    invalid["repos"] = repos

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


def test_compare_rejects_malformed_aggregate_metrics_container() -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"] = []

    with pytest.raises(ValueError, match="aggregate metrics must be an object"):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize("missing", ["aggregate", "metrics"])
def test_v2_requires_aggregate_metrics_container(missing: str) -> None:
    invalid = _report([])
    if missing == "aggregate":
        invalid.pop("aggregate")
    else:
        invalid["aggregate"].pop("metrics")

    with pytest.raises(ValueError, match="aggregate.*must be an object"):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize(
    "grouping",
    [
        "overall",
        "by_repository",
        "by_tag",
        "by_profile",
        "by_embedding",
    ],
)
def test_v2_requires_every_aggregate_metric_grouping(grouping: str) -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"].pop(grouping)

    with pytest.raises(ValueError, match="aggregate metrics.*exactly"):
        compare_reports(invalid, _report([]))


def test_v2_rejects_extra_aggregate_metric_grouping() -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"]["extra"] = {}

    with pytest.raises(ValueError, match="aggregate metrics.*exactly"):
        compare_reports(invalid, _report([]))


def test_v1_defaults_missing_aggregate_metrics_to_empty() -> None:
    missing_aggregate = _report([], schema_version=1)
    missing_aggregate.pop("aggregate")
    missing_metrics = _report([], schema_version=1)
    missing_metrics["aggregate"].pop("metrics")

    assert compare_reports(missing_aggregate, missing_aggregate)[
        "metric_deltas"
    ] == {}
    assert compare_reports(missing_metrics, missing_metrics)["metric_deltas"] == {}


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


def test_compare_rejects_ambiguous_formatted_case_keys() -> None:
    with pytest.raises(ValueError, match=r"ambiguous case key: a/b/c"):
        compare_reports(
            _report([_case("a", "b/c", "pass")]),
            _report([_case("a/b", "c", "pass")]),
        )


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


def test_v1_comparison_keeps_single_latency_mean_nested() -> None:
    baseline = _report([], schema_version=1)
    candidate = _report([], schema_version=1)
    baseline["aggregate"]["metrics"]["overall"] = {
        "latency_ms": {"count": 1, "mean": 10},
    }
    candidate["aggregate"]["metrics"]["overall"] = {
        "latency_ms": {"count": 1, "mean": 12},
    }

    comparison = compare_reports(baseline, candidate)

    assert comparison["metric_deltas"]["overall"]["latency_ms"] == {
        "mean": {"baseline": 10.0, "candidate": 12.0, "delta": 2.0},
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_compare_rejects_non_finite_aggregate_metric_leaves(value: float) -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"]["overall"] = {
        "mrr": {"count": 1, "mean": value},
    }

    with pytest.raises(ValueError, match=r"aggregate metrics.*mrr.*mean"):
        compare_reports(invalid, _report([]))


def test_v2_repo_effective_config_difference_is_reported() -> None:
    baseline = _report([])
    candidate = _report([])
    baseline["repos"][0]["config"] = {"config_hash": "sha256:baseline"}
    candidate["repos"][0]["config"] = {"config_hash": "sha256:candidate"}

    comparison = compare_reports(baseline, candidate)

    assert "repo effective config differs" in comparison["metadata_warnings"]


def test_v1_reports_without_repo_config_hashes_do_not_warn_about_config() -> None:
    baseline_repo = _repo("baseline", "sha256:baseline")
    candidate_repo = _repo("candidate", "sha256:candidate")
    baseline_repo.pop("config")
    candidate_repo.pop("config")
    baseline = _report(
        [],
        schema_version=1,
        repos=[baseline_repo],
    )
    candidate = _report(
        [],
        schema_version=1,
        repos=[candidate_repo],
    )

    comparison = compare_reports(baseline, candidate)

    assert "repo effective config differs" not in comparison["metadata_warnings"]
    assert "repo identity differs" in comparison["metadata_warnings"]


def test_v1_reports_with_repo_config_hashes_still_compare_them() -> None:
    baseline = _report([], schema_version=1)
    candidate = _report([], schema_version=1)
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


@pytest.mark.parametrize(
    "metric_name,summary",
    [
        ("hit_at_5", {"successes": 1, "total": 1}),
        (
            "entrypoint_top1",
            {"successes": 1, "total": 1, "rate": 1.0, "count": 1},
        ),
        ("mrr", {"mean": 0.5}),
        ("mrr", {"count": 1, "mean": 0.5, "rate": 0.5}),
        ("latency_ms", {"count": 1, "mean": 1.0, "p50": 1}),
    ],
)
def test_v2_aggregate_summaries_require_exact_shapes(
    metric_name: str,
    summary: dict,
) -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"]["overall"] = {metric_name: summary}

    with pytest.raises(ValueError, match=rf"aggregate metrics.*{metric_name}"):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize(
    "metric_name,summary,message",
    [
        (
            "mrr",
            {"count": 1.5, "mean": 0.5},
            "count must be a positive integer",
        ),
        (
            "mrr",
            {"count": True, "mean": 0.5},
            "count must be a positive integer",
        ),
        (
            "mrr",
            {"count": 0, "mean": 0.5},
            "count must be a positive integer",
        ),
        (
            "hit_at_5",
            {"successes": True, "total": 1, "rate": 1.0},
            "successes must be a nonnegative integer",
        ),
        (
            "hit_at_5",
            {"successes": 1, "total": 0, "rate": 1.0},
            "total must be a positive integer",
        ),
        (
            "hit_at_5",
            {"successes": 2, "total": 1, "rate": 1.0},
            "successes cannot exceed total",
        ),
        (
            "hit_at_5",
            {"successes": 1, "total": 2, "rate": 1.0},
            "rate is inconsistent",
        ),
        (
            "hit_at_5",
            {"successes": 1, "total": 1, "rate": float("nan")},
            "rate must be a finite number",
        ),
        (
            "latency_ms",
            {"count": 1, "mean": -1, "p50": 0, "p95": 0},
            "mean must be nonnegative",
        ),
    ],
)
def test_v2_aggregate_summaries_validate_counts_rates_and_bounds(
    metric_name: str,
    summary: dict,
    message: str,
) -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"]["overall"] = {metric_name: summary}

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("p50", True),
        ("p50", 0.5),
        ("p95", False),
        ("p95", 1.5),
    ],
)
def test_v2_latency_percentiles_require_nonnegative_integers(
    field: str,
    value: object,
) -> None:
    invalid = _report([])
    summary = {"count": 1, "mean": 1.0, "p50": 1, "p95": 1}
    summary[field] = value
    invalid["aggregate"]["metrics"]["overall"] = {"latency_ms": summary}

    with pytest.raises(
        ValueError,
        match=rf"latency_ms\.{field} must be a nonnegative integer",
    ):
        compare_reports(invalid, _report([]))


def test_v2_latency_p50_cannot_exceed_p95() -> None:
    invalid = _report([])
    invalid["aggregate"]["metrics"]["overall"] = {
        "latency_ms": {"count": 2, "mean": 2.0, "p50": 3, "p95": 2},
    }

    with pytest.raises(ValueError, match="latency_ms.p50 cannot exceed p95"):
        compare_reports(invalid, _report([]))


def test_v2_aggregate_accepts_empty_groupings_and_v1_keeps_legacy_summaries() -> None:
    v2 = _report([])
    v2["aggregate"]["metrics"] = {
        "overall": {},
        "by_repository": {},
        "by_tag": {},
        "by_profile": {},
        "by_embedding": {},
    }
    legacy = _report([], schema_version=1)
    legacy["aggregate"]["metrics"]["overall"] = {
        "mrr": {"mean": 0.5},
    }

    assert compare_reports(v2, v2)["metric_deltas"] == {}
    assert compare_reports(legacy, legacy)["metric_deltas"]["overall"]["mrr"] == {
        "baseline": 0.5,
        "candidate": 0.5,
        "delta": 0.0,
    }


@pytest.mark.parametrize(
    "metrics,message",
    [
        (
            {"expected_coverage_top5": {"ratio": 0.5}},
            "expected_coverage_top5 must contain exactly count and ratio",
        ),
        (
            {"expected_coverage_top5": {"count": 1, "ratio": 0.5, "extra": 0}},
            "expected_coverage_top5 must contain exactly count and ratio",
        ),
        (
            {"expected_coverage_top5": {"count": 1.5, "ratio": 0.5}},
            "expected_coverage_top5.count must be a nonnegative integer",
        ),
        (
            {"entrypoint_rank": 0},
            "entrypoint_rank must be a positive integer or null",
        ),
        (
            {"entrypoint_rank": 1.5},
            "entrypoint_rank must be a positive integer or null",
        ),
        (
            {"latency_ms": 1.5},
            "latency_ms must be a nonnegative integer",
        ),
        (
            {"result_count": True},
            "result_count must be a nonnegative integer",
        ),
        (
            {"noise_top12_measurement": -1},
            "noise_top12_measurement must be a nonnegative integer",
        ),
    ],
)
def test_v2_case_metrics_enforce_runner_integer_contracts(
    metrics: dict,
    message: str,
) -> None:
    invalid = _report([_case("sample", "target", "pass", metrics)])

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


def test_v2_case_metrics_allow_runner_nullable_values() -> None:
    metrics = {
        "hit_at_5": None,
        "recall_at_5": None,
        "mrr": None,
        "expected_coverage_top5": {"count": 0, "ratio": None},
        "preferred_rank_pass": True,
        "noise_top5": 0,
        "entrypoint_rank": None,
        "cross_language_success": None,
        "latency_ms": 0,
        "result_count": 0,
        "top_score": None,
    }

    comparison = compare_reports(
        _report([_case("sample", "target", "pass", metrics)]),
        _report([_case("sample", "target", "pass", metrics)]),
    )

    assert comparison["cases"][0]["classification"] == "unchanged_pass"


@pytest.mark.parametrize(
    "repo,message",
    [
        (
            {"repo_key": "sample", "source": {}},
            "repo config must be an object",
        ),
        (
            {"repo_key": "sample", "source": {}, "config": {}},
            "repo config_hash must be a non-empty string",
        ),
        (
            {"repo_key": "sample", "source": {}, "config": {"config_hash": None}},
            "repo config_hash must be a non-empty string",
        ),
        (
            {"repo_key": "sample", "source": {}, "config": {"config_hash": ""}},
            "repo config_hash must be a non-empty string",
        ),
        (
            {
                "repo_key": "sample",
                "source": {},
                "config": {"config_hash": "   "},
            },
            "repo config_hash must be a non-empty string",
        ),
    ],
)
def test_v2_repos_require_non_empty_effective_config_hash(
    repo: dict,
    message: str,
) -> None:
    invalid = _report([], repos=[repo])

    with pytest.raises(ValueError, match=message):
        compare_reports(invalid, _report([]))


def test_v1_repo_metadata_remains_permissive_without_effective_config() -> None:
    legacy = _report(
        [],
        schema_version=1,
        repos=[{"repo_key": "sample", "source": {}}],
    )

    comparison = compare_reports(legacy, legacy)

    assert "repo effective config differs" not in comparison["metadata_warnings"]


def test_compare_accepts_real_schema_v2_runner_report() -> None:
    report = run_quality_fixture(CATALOG_PATH, "ci", None, None)
    latency = report["aggregate"]["metrics"]["overall"]["latency_ms"]

    comparison = compare_reports(report, report)

    assert type(latency["p50"]) is int
    assert type(latency["p95"]) is int
    assert comparison["schema_version"] == 2
    assert comparison["aggregate"]["gating_regressions"] == 0
    assert all(
        case["classification"] == "unchanged_pass"
        for case in comparison["cases"]
    )
