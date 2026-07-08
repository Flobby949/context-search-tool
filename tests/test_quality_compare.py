from context_search_tool.quality.compare import compare_reports


def _case(
    repo_key: str,
    case_id: str,
    status: str,
    metrics: dict | None = None,
) -> dict:
    return {
        "repo_key": repo_key,
        "case_id": case_id,
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
    schema_version: int = 1,
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
    assert comparison["aggregate"]["regressed"] == 1


def test_fail_to_pass_is_improved() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "fail")]),
        _report([_case("sample", "target", "pass")]),
    )

    assert _classifications(comparison) == {"sample/target": "improved"}
    assert comparison["aggregate"]["improved"] == 1


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


def test_candidate_missing_is_removed_case() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([]),
    )

    assert _classifications(comparison) == {"sample/target": "removed_case"}
    assert comparison["aggregate"]["removed_case"] == 1


def test_pass_to_error_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass")]),
        _report([_case("sample", "target", "error")]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["regressed"] == 1


def test_hit_at_5_false_to_true_is_improved_without_status_transition() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "fail", {"hit_at_5": False})]),
        _report([_case("sample", "target", "fail", {"hit_at_5": True})]),
    )

    assert _classifications(comparison) == {"sample/target": "improved"}
    assert comparison["aggregate"]["improved"] == 1


def test_hit_at_5_true_to_false_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"hit_at_5": True})]),
        _report([_case("sample", "target", "pass", {"hit_at_5": False})]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["regressed"] == 1


def test_mrr_drop_greater_than_point_twenty_five_is_regressed() -> None:
    comparison = compare_reports(
        _report([_case("sample", "target", "pass", {"mrr": 0.9})]),
        _report([_case("sample", "target", "pass", {"mrr": 0.64})]),
    )

    assert _classifications(comparison) == {"sample/target": "regressed"}
    assert comparison["aggregate"]["regressed"] == 1


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
