import json
from pathlib import Path

import pytest

import context_search_tool.quality as quality
from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    adapt_legacy_query_case,
    load_quality_fixture,
    normalize_result_path,
    validate_profile_compatible,
)


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    fixture_path = tmp_path / "quality.json"
    fixture_path.write_text(json.dumps(data), encoding="utf-8")
    return fixture_path


def _minimal_fixture(
    repo_overrides: dict | None = None,
    case_overrides: dict | None = None,
) -> dict:
    query = {"id": "case-1", "query": "login"}
    if case_overrides:
        query.update(case_overrides)
    repo = {"repo_key": "sample", "queries": [query]}
    if repo_overrides:
        repo.update(repo_overrides)
    return {"schema_version": 1, "repos": [repo]}


def test_matcher_rejects_absolute_and_parent_paths() -> None:
    invalid_paths = [
        "/tmp/App.java",
        "../App.java",
        "C:/repo/App.java",
        "\\\\server\\repo\\App.java",
        "",
    ]

    for invalid_path in invalid_paths:
        with pytest.raises(ValueError):
            Matcher(path=invalid_path)


def test_matcher_rejects_non_string_selectors() -> None:
    for kwargs in [{"path": 1}, {"glob": 1}, {"contains": 1}]:
        with pytest.raises(ValueError):
            Matcher(**kwargs)


def test_glob_rejects_empty_and_parent_traversal() -> None:
    for invalid_glob in ["", "../**/*.py"]:
        with pytest.raises(ValueError):
            Matcher(glob=invalid_glob)


def test_matcher_path_and_glob_match_repo_relative_posix_paths() -> None:
    assert Matcher(path="src/main/App.java").matches("src/main/App.java")
    assert not Matcher(path="src/main/App.java").matches("src/main/app.java")
    assert Matcher(glob="src/**/*.java").matches("src/main/App.java")
    assert Matcher(contains="Dashboard").matches(
        "src/dashboard/DashboardController.java"
    )


def test_normalize_result_path_preserves_dot_directories() -> None:
    matcher = Matcher(path=".github/workflows/ci.yml")

    assert (
        normalize_result_path(".\\.github\\workflows\\ci.yml")
        == ".github/workflows/ci.yml"
    )
    assert matcher.matches("./.github/workflows/ci.yml")


def test_matcher_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError):
        Matcher(path="src/App.java", glob="src/*.java")

    with pytest.raises(ValueError):
        Matcher()


def test_matcher_from_raw_detects_globs_and_rejects_unknown_fields() -> None:
    assert Matcher.from_raw("src/App.java") == Matcher(path="src/App.java")
    assert Matcher.from_raw("src/**/*.java") == Matcher(glob="src/**/*.java")

    with pytest.raises(ValueError):
        Matcher.from_raw({"path": "src/App.java", "unexpected": True})


def test_quality_package_exports_public_helpers() -> None:
    assert quality.adapt_legacy_query_case is adapt_legacy_query_case
    assert quality.normalize_result_path is normalize_result_path
    assert quality.validate_profile_compatible is validate_profile_compatible


def test_load_quality_fixture_parses_v1_schema(tmp_path: Path) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshots/sample.tar.gz",
                    "profiles": ["ci"],
                    "queries": [
                        {
                            "id": "sample-login",
                            "query": "login flow",
                            "anchor_expected": ["class App", "renderLogin"],
                            "expected_top_k": [{"path": "src/App.java", "top_k": 5}],
                        }
                    ],
                }
            ],
        },
    )

    fixture = load_quality_fixture(fixture_path)

    assert fixture.schema_version == 1
    assert fixture.path == fixture_path
    assert fixture.repos[0].repo_key == "sample"
    assert fixture.repos[0].snapshot_path == "snapshots/sample.tar.gz"
    assert fixture.repos[0].profiles == ("ci",)
    assert fixture.repos[0].queries[0].gate is Gate.REQUIRED
    assert fixture.repos[0].queries[0].expected_top_k[0].matcher == Matcher(
        path="src/App.java"
    )
    assert fixture.repos[0].queries[0].expected_top_k[0].top_k == 5
    assert fixture.repos[0].queries[0].anchor_expected == (
        "class App",
        "renderLogin",
    )


def test_load_quality_fixture_rejects_invalid_container_shapes(tmp_path: Path) -> None:
    invalid_fixtures = [
        {"schema_version": 2, "repos": [{"repo_key": "sample", "queries": []}]},
        {"schema_version": 1, "repos": []},
        {"schema_version": 1, "repos": [{"repo_key": "sample", "queries": []}]},
    ]

    for index, data in enumerate(invalid_fixtures):
        fixture_path = tmp_path / f"invalid-{index}.json"
        fixture_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError):
            load_quality_fixture(fixture_path)


def test_load_quality_fixture_rejects_non_string_fixture_fields(tmp_path: Path) -> None:
    invalid_fixtures = [
        _minimal_fixture(repo_overrides={"repo_key": 123}),
        _minimal_fixture(repo_overrides={"path_env": 123}),
        _minimal_fixture(repo_overrides={"repo_dir_name": 123}),
        _minimal_fixture(repo_overrides={"snapshot_path": 123}),
        _minimal_fixture(repo_overrides={"profiles": ["ci", 123]}),
        _minimal_fixture(case_overrides={"tags": ["ci", 123]}),
        _minimal_fixture(case_overrides={"mode": 123}),
        _minimal_fixture(case_overrides={"gate": 123}),
        _minimal_fixture(case_overrides={"known_gap_reason": 123}),
        _minimal_fixture(case_overrides={"known_gap": 123}),
        _minimal_fixture(case_overrides={"notes": 123}),
        _minimal_fixture(case_overrides={"anchor_expected": ["anchor", 123]}),
        _minimal_fixture(case_overrides={"expected_top_k": [{"path": 123}]}),
        _minimal_fixture(case_overrides={"expected_top_k": [{"glob": 123}]}),
        _minimal_fixture(case_overrides={"expected_top_k": [{"contains": 123}]}),
    ]

    for index, data in enumerate(invalid_fixtures):
        fixture_path = tmp_path / f"invalid-types-{index}.json"
        fixture_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError):
            load_quality_fixture(fixture_path)


def test_load_quality_fixture_rejects_malformed_container_shapes(tmp_path: Path) -> None:
    invalid_fixtures = [
        {"schema_version": 1, "repos": ["bad"]},
        _minimal_fixture(repo_overrides={"queries": ["bad"]}),
        _minimal_fixture(
            repo_overrides={
                "default_config": ["not", "a", "dict"],
            }
        ),
        _minimal_fixture(
            case_overrides={
                "expected_top_k": {"path": "src/App.py", "top_k": 5},
            }
        ),
        _minimal_fixture(case_overrides={"expected_any_top_k": 123}),
        _minimal_fixture(
            case_overrides={
                "preferred_rank": {"path": "src/App.py", "top_k": 5},
            }
        ),
        _minimal_fixture(
            case_overrides={
                "absent_top_k": {"path": "src/App.py", "top_k": 5},
            }
        ),
        _minimal_fixture(
            case_overrides={
                "outranks": {
                    "source": "src/App.py",
                    "noise": "src/Noise.py",
                    "top_k": 5,
                },
            }
        ),
        _minimal_fixture(
            case_overrides={
                "expected_top_k": [{"path": "src/App.py", "top_k": 5}],
                "forbidden_above": 123,
            }
        ),
        _minimal_fixture(case_overrides={"expected_core": "src/App.py"}),
        _minimal_fixture(case_overrides={"forbidden_top3": "src/Noise.py"}),
    ]

    for index, data in enumerate(invalid_fixtures):
        fixture_path = tmp_path / f"invalid-containers-{index}.json"
        fixture_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError):
            load_quality_fixture(fixture_path)


def test_load_quality_fixture_rejects_empty_expected_any_groups(tmp_path: Path) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        _minimal_fixture(
            case_overrides={
                "expected_any_top_k": [{"matchers": [], "top_k": 5}],
            }
        ),
    )

    with pytest.raises(ValueError):
        load_quality_fixture(fixture_path)


def test_rank_fields_require_positive_int() -> None:
    invalid_values = [0, -1, True, 1.5, "3"]

    def assert_invalid(case_overrides: dict) -> None:
        with pytest.raises(ValueError):
            adapt_legacy_query_case(
                {"id": "bad-rank", "query": "login", **case_overrides}
            )

    for value in invalid_values:
        assert_invalid({"expected_top_k": [{"path": "src/App.java", "top_k": value}]})
        assert_invalid(
            {
                "expected_any_top_k": [
                    {"matchers": ["src/App.java"], "top_k": value}
                ]
            }
        )
        assert_invalid({"preferred_rank": [{"path": "src/App.java", "top_k": value}]})
        assert_invalid(
            {"preferred_rank": [{"path": "src/App.java", "max_rank": value}]}
        )
        assert_invalid({"absent_top_k": [{"path": "src/App.java", "top_k": value}]})
        assert_invalid(
            {
                "outranks": [
                    {
                        "source": "src/App.java",
                        "noise": "src/Noise.java",
                        "top_k": value,
                    }
                ]
            }
        )
        assert_invalid(
            {
                "forbidden_above": {
                    "source": "src/App.java",
                    "noise": "src/Noise.java",
                    "top_k": value,
                }
            }
        )
    for value in [-1, True, 1.5, "3"]:
        assert_invalid({"expected_top5_min": value})


def test_expected_top5_min_accepts_zero() -> None:
    case = adapt_legacy_query_case(
        {"id": "legacy-zero-min", "query": "login", "expected_top5_min": 0}
    )

    assert case.expected_top5_min == 0


def test_legacy_known_gap_is_reason_not_gate() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-gap",
            "query": "login",
            "expected_core": ["src/AuthController.java"],
            "known_gap": "No alias coverage yet.",
        }
    )

    assert case.gate is Gate.REQUIRED
    assert case.known_gap_reason == "No alias coverage yet."


def test_legacy_expected_any_top_k_flat_list_becomes_group() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-any",
            "query": "dashboard",
            "expected_any_top_k": [
                {"path": "src/DashboardController.java", "top_k": 3},
                {"path": "src/DashboardService.java", "top_k": 5},
            ],
        }
    )

    assert len(case.expected_any_top_k) == 1
    group = case.expected_any_top_k[0]
    assert group.top_k == 5
    assert group.matchers == (
        Matcher(path="src/DashboardController.java"),
        Matcher(path="src/DashboardService.java"),
    )


def test_legacy_calibration_expected_core_becomes_relevance_targets() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-core",
            "query": "feedback",
            "expected_core": [
                "src/FeedbackController.java",
                "src/FeedbackService.java",
            ],
            "forbidden_top3": ["src/WxMiniLoginClient.java"],
        }
    )

    assert [item.top_k for item in case.expected_top_k] == [5, 5]
    assert [item.matcher for item in case.expected_top_k] == [
        Matcher(path="src/FeedbackController.java"),
        Matcher(path="src/FeedbackService.java"),
    ]
    assert case.absent_top_k[0].top_k == 3
    assert case.absent_top_k[0].matcher == Matcher(path="src/WxMiniLoginClient.java")


def test_legacy_forbidden_above_shape_becomes_target_and_noise() -> None:
    shorthand = adapt_legacy_query_case(
        {
            "id": "legacy-outranks",
            "query": "open door",
            "expected_top_k": [{"path": "src/AccessControlService.java", "top_k": 5}],
            "forbidden_above": "src/NoiseHandler.java",
        }
    )

    assert shorthand.outranks == ()
    assert shorthand.forbidden_above[0].source == Matcher(
        path="src/AccessControlService.java"
    )
    assert shorthand.forbidden_above[0].noise == Matcher(path="src/NoiseHandler.java")
    assert shorthand.forbidden_above[0].top_k == 5

    explicit = adapt_legacy_query_case(
        {
            "id": "legacy-explicit-outranks",
            "query": "open door",
            "forbidden_above": {
                "source": "src/AccessControlService.java",
                "noise": "src/NoiseHandler.java",
                "top_k": 3,
            },
        }
    )

    assert explicit.forbidden_above[0].source == Matcher(
        path="src/AccessControlService.java"
    )
    assert explicit.forbidden_above[0].noise == Matcher(path="src/NoiseHandler.java")
    assert explicit.forbidden_above[0].top_k == 3


def test_legacy_forbidden_above_dict_shorthand_uses_first_expected_target() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-dict-shorthand",
            "query": "open door",
            "expected_top_k": [
                {"path": "src/AccessControlService.java", "top_k": 7}
            ],
            "forbidden_above": {
                "glob": "src/generated/**/*.java",
                "top_k": 5,
                "max_rank": 2,
            },
        }
    )

    assert case.forbidden_above[0].source == Matcher(
        path="src/AccessControlService.java"
    )
    assert case.forbidden_above[0].noise == Matcher(glob="src/generated/**/*.java")
    assert case.forbidden_above[0].top_k == 5


def test_ci_profile_rejects_model_backed_config() -> None:
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024)
    )

    with pytest.raises(ValueError, match="ci profile"):
        validate_profile_compatible("ci", config)
