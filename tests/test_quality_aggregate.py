import json

import pytest

from context_search_tool.quality.aggregate import aggregate_cases


def _case(
    repo_key: str,
    case_id: str,
    status: str,
    *,
    attempted: bool,
    tags: list[str] | None = None,
    metrics: dict | None = None,
) -> dict:
    return {
        "repo_key": repo_key,
        "case_id": case_id,
        "status": status,
        "attempted": attempted,
        "tags": tags or [],
        "metrics": metrics or {},
    }


def _repo(repo_key: str, provider: str = "hash", model: str = "hash-v1") -> dict:
    return {
        "repo_key": repo_key,
        "config": {"embedding": {"provider": provider, "model": model}},
    }


def test_aggregate_counts_selected_attempted_executed_error_and_skipped() -> None:
    cases = [
        _case("a", "pass", "pass", attempted=True),
        _case("a", "query-error", "error", attempted=True),
        _case("b", "index-error", "error", attempted=False),
        _case("c", "missing", "skipped", attempted=False),
        _case("a", "info", "informational", attempted=True),
    ]

    aggregate = aggregate_cases(cases, [_repo("a"), _repo("b"), _repo("c")], "ci")

    assert aggregate["selected"] == 5
    assert aggregate["attempted"] == 3
    assert aggregate["executed"] == 2
    assert aggregate["errors"] == 2
    assert aggregate["skipped"] == 1
    assert aggregate["informational"] == 1
    attempted_errors = sum(
        case["attempted"] for case in cases if case["status"] == "error"
    )
    assert aggregate["attempted"] == aggregate["executed"] + attempted_errors
    assert aggregate["selected"] == (
        aggregate["executed"] + aggregate["errors"] + aggregate["skipped"]
    )


def test_typed_metric_summary_rates_means_and_latency_percentiles() -> None:
    cases = [
        _case(
            "a",
            "one",
            "pass",
            attempted=True,
            tags=["frontend", "entrypoint"],
            metrics={
                "hit_at_5": True,
                "cross_language_success": None,
                "entrypoint_rank": 1,
                "mrr": 1.0,
                "latency_ms": 10,
                "noise_top5_measurement": 1,
                "expected_coverage_top5": {"count": 2, "ratio": 1.0},
            },
        ),
        _case(
            "a",
            "two",
            "pass",
            attempted=True,
            tags=["frontend", "entrypoint"],
            metrics={
                "hit_at_5": False,
                "cross_language_success": True,
                "entrypoint_rank": 3,
                "mrr": 0.5,
                "latency_ms": 30,
                "noise_top5_measurement": 3,
                "expected_coverage_top5": {"count": 1, "ratio": 0.5},
            },
        ),
        _case(
            "a",
            "three",
            "pass",
            attempted=True,
            metrics={"latency_ms": 20},
        ),
    ]

    aggregate = aggregate_cases(cases, [_repo("a")], "ci")
    metrics = aggregate["metrics"]["overall"]

    assert metrics["hit_at_5"] == {"successes": 1, "total": 2, "rate": 0.5}
    assert metrics["cross_language_success"] == {
        "successes": 1,
        "total": 1,
        "rate": 1.0,
    }
    assert metrics["entrypoint_top1"] == {
        "successes": 1,
        "total": 2,
        "rate": 0.5,
    }
    assert metrics["entrypoint_top3"]["rate"] == 1.0
    assert metrics["mrr"] == {"count": 2, "mean": 0.75}
    assert metrics["latency_ms"] == {
        "count": 3,
        "mean": 20.0,
        "p50": 20,
        "p95": 30,
    }
    assert metrics["noise_top5_measurement"] == {"count": 2, "mean": 2.0}
    assert metrics["expected_coverage_top5_ratio"] == {
        "count": 2,
        "mean": 0.75,
    }


def test_aggregate_groups_by_repo_tag_profile_and_embedding() -> None:
    cases = [
        _case(
            "frontend",
            "view",
            "pass",
            attempted=True,
            tags=["frontend"],
            metrics={"mrr": 1.0},
        ),
        _case(
            "backend",
            "controller",
            "pass",
            attempted=True,
            tags=["java_spring"],
            metrics={"mrr": 0.5},
        ),
    ]

    aggregate = aggregate_cases(
        cases,
        [_repo("frontend"), _repo("backend", "bge", "bge-m3")],
        "smoke",
    )

    groups = aggregate["metrics"]
    assert groups["by_repository"]["frontend"]["mrr"]["mean"] == 1.0
    assert groups["by_tag"]["java_spring"]["mrr"]["mean"] == 0.5
    assert groups["by_profile"]["smoke"]["mrr"]["mean"] == 0.75
    assert groups["by_embedding"]["bge/bge-m3"]["mrr"]["mean"] == 0.5


def test_numeric_aggregation_excludes_booleans() -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "one",
                "pass",
                attempted=True,
                metrics={"custom_numeric": True},
            )
        ],
        [_repo("a")],
        "ci",
    )

    assert "custom_numeric" not in aggregate["metrics"]["overall"]


def test_missing_declared_entrypoint_stays_in_rate_denominator() -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "missing-entrypoint",
                "fail",
                attempted=True,
                tags=["entrypoint"],
                metrics={"entrypoint_rank": None},
            )
        ],
        [_repo("a")],
        "ci",
    )

    assert aggregate["metrics"]["overall"]["entrypoint_top1"] == {
        "successes": 0,
        "total": 1,
        "rate": 0.0,
    }
    assert aggregate["metrics"]["overall"]["entrypoint_top3"] == {
        "successes": 0,
        "total": 1,
        "rate": 0.0,
    }


@pytest.mark.parametrize("rank", [0, -1])
def test_non_positive_entrypoint_rank_stays_in_rate_denominator(rank: int) -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "invalid-entrypoint",
                "fail",
                attempted=True,
                tags=["entrypoint"],
                metrics={"entrypoint_rank": rank},
            )
        ],
        [_repo("a")],
        "ci",
    )

    assert aggregate["metrics"]["overall"]["entrypoint_top1"] == {
        "successes": 0,
        "total": 1,
        "rate": 0.0,
    }
    assert aggregate["metrics"]["overall"]["entrypoint_top3"] == {
        "successes": 0,
        "total": 1,
        "rate": 0.0,
    }


def test_empty_profile_is_not_grouped() -> None:
    aggregate = aggregate_cases(
        [_case("a", "one", "pass", attempted=True, metrics={"mrr": 1.0})],
        [_repo("a")],
        "",
    )

    assert aggregate["metrics"]["by_profile"] == {}


def test_incomplete_embedding_config_is_not_grouped() -> None:
    cases = [
        _case("missing-both", "one", "pass", attempted=True, metrics={"mrr": 1.0}),
        _case(
            "missing-provider",
            "two",
            "pass",
            attempted=True,
            metrics={"mrr": 1.0},
        ),
        _case("missing-model", "three", "pass", attempted=True, metrics={"mrr": 1.0}),
    ]
    repos = [
        {"repo_key": "missing-both", "config": {"embedding": {}}},
        {
            "repo_key": "missing-provider",
            "config": {"embedding": {"model": "model"}},
        },
        {
            "repo_key": "missing-model",
            "config": {"embedding": {"provider": "hash"}},
        },
    ]

    aggregate = aggregate_cases(cases, repos, "ci")

    assert aggregate["metrics"]["by_embedding"] == {}


def test_duplicate_tag_contributes_case_once_to_group_metrics() -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "duplicate-tag",
                "pass",
                attempted=True,
                tags=["dup", "dup"],
                metrics={"hit_at_5": True, "latency_ms": 10},
            )
        ],
        [_repo("a")],
        "ci",
    )

    metrics = aggregate["metrics"]["by_tag"]["dup"]
    assert metrics["hit_at_5"] == {"successes": 1, "total": 1, "rate": 1.0}
    assert metrics["latency_ms"] == {
        "count": 1,
        "mean": 10.0,
        "p50": 10,
        "p95": 10,
    }


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="status"):
        aggregate_cases(
            [_case("a", "bad-status", "unknown", attempted=True)],
            [_repo("a")],
            "ci",
        )


@pytest.mark.parametrize("attempted", [1, 0, "false", None])
def test_attempted_must_be_an_exact_bool(attempted: object) -> None:
    case = _case("a", "bad-attempted", "pass", attempted=True)
    case["attempted"] = attempted

    with pytest.raises(ValueError, match="attempted"):
        aggregate_cases([case], [_repo("a")], "ci")


def test_all_six_statuses_are_accepted() -> None:
    statuses = ["pass", "fail", "known_gap", "informational", "skipped", "error"]
    cases = [
        _case("a", status, status, attempted=status != "skipped")
        for status in statuses
    ]

    aggregate = aggregate_cases(cases, [_repo("a")], "ci")

    assert aggregate["total"] == 6
    assert aggregate["executed"] == 4


@pytest.mark.parametrize(
    "status", ["pass", "fail", "known_gap", "informational"]
)
def test_executed_status_requires_attempted_true(status: str) -> None:
    with pytest.raises(ValueError, match="attempted.*status"):
        aggregate_cases(
            [_case("a", "not-attempted", status, attempted=False)],
            [_repo("a")],
            "ci",
        )


def test_skipped_status_requires_attempted_false() -> None:
    with pytest.raises(ValueError, match="attempted.*status"):
        aggregate_cases(
            [_case("a", "attempted-skip", "skipped", attempted=True)],
            [_repo("a")],
            "ci",
        )


@pytest.mark.parametrize("attempted", [False, True])
def test_error_status_accepts_both_attempted_values(attempted: bool) -> None:
    aggregate = aggregate_cases(
        [_case("a", "error", "error", attempted=attempted)],
        [_repo("a")],
        "ci",
    )

    assert aggregate["selected"] == 1
    assert aggregate["attempted"] == int(attempted)
    assert aggregate["executed"] == 0
    assert aggregate["errors"] == 1


@pytest.mark.parametrize(
    "metric_name",
    ["expected_coverage_top5_ratio", "entrypoint_top1", "entrypoint_top3"],
)
def test_reserved_derived_metric_name_is_rejected(metric_name: str) -> None:
    with pytest.raises(ValueError, match=rf"reserved metric.*{metric_name}"):
        aggregate_cases(
            [
                _case(
                    "a",
                    "reserved-metric",
                    "pass",
                    attempted=True,
                    metrics={metric_name: 1},
                )
            ],
            [_repo("a")],
            "ci",
        )


def test_dynamic_and_source_metric_names_remain_accepted() -> None:
    aggregate = aggregate_cases(
        [
            _case(
                "a",
                "valid-metrics",
                "pass",
                attempted=True,
                tags=["entrypoint"],
                metrics={
                    "precision_at_37": 0.25,
                    "noise_top37": 2,
                    "expected_coverage_top5": {"ratio": 0.75},
                    "entrypoint_rank": 3,
                },
            )
        ],
        [_repo("a")],
        "ci",
    )

    metrics = aggregate["metrics"]["overall"]
    assert metrics["precision_at_37"] == {"count": 1, "mean": 0.25}
    assert metrics["noise_top37"] == {"count": 1, "mean": 2.0}
    assert metrics["expected_coverage_top5_ratio"] == {"count": 1, "mean": 0.75}
    assert metrics["entrypoint_top1"] == {
        "successes": 0,
        "total": 1,
        "rate": 0.0,
    }
    assert metrics["entrypoint_top3"] == {
        "successes": 1,
        "total": 1,
        "rate": 1.0,
    }


def test_non_finite_numeric_metrics_are_excluded_from_summaries() -> None:
    cases = [
        _case(
            "a",
            "non-finite",
            "pass",
            attempted=True,
            metrics={
                "latency_ms": float("nan"),
                "expected_coverage_top5": {"ratio": float("inf")},
                "custom_metric": float("-inf"),
            },
        ),
        _case(
            "a",
            "finite",
            "pass",
            attempted=True,
            metrics={
                "latency_ms": 20,
                "expected_coverage_top5": {"ratio": 0.5},
                "custom_metric": 2,
            },
        ),
    ]

    aggregate = aggregate_cases(cases, [_repo("a")], "ci")
    metrics = aggregate["metrics"]["overall"]

    assert metrics["latency_ms"] == {
        "count": 1,
        "mean": 20.0,
        "p50": 20,
        "p95": 20,
    }
    assert metrics["expected_coverage_top5_ratio"] == {"count": 1, "mean": 0.5}
    assert metrics["custom_metric"] == {"count": 1, "mean": 2.0}
    assert json.loads(json.dumps(aggregate, allow_nan=False)) == aggregate


def test_duplicate_repo_key_is_rejected_even_when_config_is_incomplete() -> None:
    repos = [
        {"repo_key": "a", "config": {"embedding": {}}},
        _repo("a"),
    ]

    with pytest.raises(ValueError, match="repo_key"):
        aggregate_cases(
            [_case("a", "duplicate-repo", "pass", attempted=True)],
            repos,
            "ci",
        )


def test_metric_order_is_independent_of_case_order() -> None:
    cases = [
        _case(
            "a",
            "zeta-first",
            "pass",
            attempted=True,
            tags=["entrypoint"],
            metrics={"zeta": 1, "entrypoint_rank": 1},
        ),
        _case(
            "a",
            "alpha-second",
            "pass",
            attempted=True,
            tags=["entrypoint"],
            metrics={"alpha": 3, "entrypoint_rank": 3},
        ),
    ]

    forward = aggregate_cases(cases, [_repo("a")], "ci")["metrics"]
    reverse = aggregate_cases(list(reversed(cases)), [_repo("a")], "ci")["metrics"]

    assert list(forward["overall"]) == [
        "alpha",
        "zeta",
        "entrypoint_top1",
        "entrypoint_top3",
    ]
    assert json.dumps(forward) == json.dumps(reverse)
