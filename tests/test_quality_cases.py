import json
from dataclasses import replace
from pathlib import Path

import pytest

import context_search_tool.quality as quality
import context_search_tool.quality.cases as quality_cases
from context_search_tool.config import (
    EmbeddingConfig,
    QueryPlannerConfig,
    ToolConfig,
)
from context_search_tool.quality.cases import (
    AtLeastTopKGroup,
    Gate,
    LegacyProvenance,
    Matcher,
    ProfileExpectation,
    TopKMatcher,
    _parse_measurement_matchers,
    adapt_legacy_query_case,
    load_quality_fixture,
    normalize_result_path,
    validate_profile_compatible,
)


_VALID_BGE_EMBEDDING = EmbeddingConfig(
    provider="bge",
    model="bge-m3",
    dimensions=1024,
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


def _load_canonical_case(tmp_path: Path, case_overrides: dict | None = None):
    return load_quality_fixture(
        _write_fixture(
            tmp_path,
            {
                "schema_version": 1,
                "profile_configs": {"ci": {}},
                "repos": [
                    {
                        "repo_key": "sample",
                        "profiles": ["ci"],
                        "queries": [
                            {
                                "id": "case-1",
                                "query": "login",
                                **(case_overrides or {}),
                            }
                        ],
                    }
                ],
            },
        )
    ).repos[0].queries[0]


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
    assert quality.LegacyProvenance is LegacyProvenance
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


def test_context_pack_case_parses_typed_expectations(tmp_path: Path) -> None:
    case = _load_canonical_case(
        tmp_path,
        {
            "mode": "context_pack",
            "expected_context_groups": {
                "entrypoints": [{"path": "src/AppController.java"}],
                "implementations": [
                    {"glob": "src/**/*ServiceImpl.java"},
                    {"contains": "Repository"},
                ],
            },
            "expected_pack_status": "ready",
            "minimum_context_confidence": "medium",
            "expected_need_matches": [
                {
                    "category": "configs_docs",
                    "subject": "postgresql",
                    "required": True,
                    "matched": False,
                }
            ],
            "maximum_pack_bytes": 65536,
            "maximum_truncated_items": 4,
            "forbidden_next_query_patterns": ["/oups", "GET /owners dto"],
        },
    )

    assert case.mode == "context_pack"
    assert case.expected_context_groups == {
        "entrypoints": (Matcher(path="src/AppController.java"),),
        "implementations": (
            Matcher(glob="src/**/*ServiceImpl.java"),
            Matcher(contains="Repository"),
        ),
    }
    assert case.expected_pack_status == "ready"
    assert case.minimum_context_confidence == "medium"
    assert case.expected_need_matches == (
        quality_cases.ExpectedNeedMatch(
            category="configs_docs",
            subject="postgresql",
            required=True,
            matched=False,
        ),
    )
    assert case.maximum_pack_bytes == 65536
    assert case.maximum_truncated_items == 4
    assert case.forbidden_next_query_patterns == (
        "/oups",
        "GET /owners dto",
    )


def test_expected_need_subject_is_nfc_normalized_before_length_validation(
    tmp_path: Path,
) -> None:
    decomposed = "e\u0301" * 64

    case = _load_canonical_case(
        tmp_path,
        {
            "mode": "context_pack",
            "expected_need_matches": [
                {
                    "category": "configs_docs",
                    "subject": decomposed,
                    "required": True,
                    "matched": True,
                }
            ],
        },
    )

    assert case.expected_need_matches[0].subject == "é" * 64
    assert len(case.expected_need_matches[0].subject) == 64


def test_case_without_mode_keeps_results_defaults(tmp_path: Path) -> None:
    case = _load_canonical_case(tmp_path)

    assert case.mode == "results"
    assert case.expected_context_groups == {}
    assert case.expected_pack_status is None
    assert case.minimum_context_confidence is None
    assert case.expected_need_matches == ()
    assert case.maximum_pack_bytes is None
    assert case.maximum_truncated_items is None
    assert case.forbidden_next_query_patterns == ()


@pytest.mark.parametrize("mode", ["raw", "", None, 1])
def test_case_rejects_unknown_quality_mode(tmp_path: Path, mode: object) -> None:
    with pytest.raises(ValueError, match="mode"):
        _load_canonical_case(tmp_path, {"mode": mode})


@pytest.mark.parametrize(
    "context_field",
    [
        {"expected_context_groups": {}},
        {"expected_pack_status": ""},
        {"minimum_context_confidence": ""},
        {"expected_need_matches": []},
        {"maximum_pack_bytes": 1},
        {"maximum_truncated_items": 0},
        {"forbidden_next_query_patterns": []},
    ],
)
def test_results_case_rejects_context_only_fields_even_when_empty(
    tmp_path: Path,
    context_field: dict,
) -> None:
    with pytest.raises(ValueError, match="context_pack"):
        _load_canonical_case(
            tmp_path,
            {"mode": "results", **context_field},
        )


@pytest.mark.parametrize("groups", [None, [], (), "entrypoints", 1])
def test_context_groups_require_an_object(
    tmp_path: Path,
    groups: object,
) -> None:
    with pytest.raises(ValueError, match="expected_context_groups"):
        _load_canonical_case(
            tmp_path,
            {"mode": "context_pack", "expected_context_groups": groups},
        )


def test_context_groups_reject_unknown_group_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="context group"):
        _load_canonical_case(
            tmp_path,
            {
                "mode": "context_pack",
                "expected_context_groups": {"controllers": []},
            },
        )


@pytest.mark.parametrize(
    "matchers",
    [None, {}, "src/App.java", 1, [1], [{"path": "src/App.java", "glob": "src/*"}]],
)
def test_context_group_values_require_valid_matcher_sequences(
    tmp_path: Path,
    matchers: object,
) -> None:
    with pytest.raises(ValueError, match="entrypoints"):
        _load_canonical_case(
            tmp_path,
            {
                "mode": "context_pack",
                "expected_context_groups": {"entrypoints": matchers},
            },
        )


@pytest.mark.parametrize("status", [None, "", "complete", 1])
def test_context_pack_status_rejects_invalid_and_explicit_null_values(
    tmp_path: Path,
    status: object,
) -> None:
    with pytest.raises(ValueError, match="expected_pack_status"):
        _load_canonical_case(
            tmp_path,
            {"mode": "context_pack", "expected_pack_status": status},
        )


@pytest.mark.parametrize("confidence", [None, "", "very_high", 1])
def test_minimum_context_confidence_rejects_invalid_and_explicit_null_values(
    tmp_path: Path,
    confidence: object,
) -> None:
    with pytest.raises(ValueError, match="minimum_context_confidence"):
        _load_canonical_case(
            tmp_path,
            {
                "mode": "context_pack",
                "minimum_context_confidence": confidence,
            },
        )


@pytest.mark.parametrize(
    "need",
    [
        {"category": "controllers", "subject": "x", "required": True, "matched": True},
        {"category": "tests", "subject": "", "required": True, "matched": True},
        {"category": "tests", "subject": "x" * 65, "required": True, "matched": True},
        {"category": "tests", "subject": "x", "required": 1, "matched": True},
        {"category": "tests", "subject": "x", "required": True, "matched": 0},
    ],
)
def test_expected_need_matches_reject_invalid_closed_fields(
    tmp_path: Path,
    need: dict,
) -> None:
    with pytest.raises(ValueError, match="expected_need_matches"):
        _load_canonical_case(
            tmp_path,
            {"mode": "context_pack", "expected_need_matches": [need]},
        )


@pytest.mark.parametrize("value", [None, True, 0, -1])
def test_maximum_pack_bytes_requires_a_positive_integer(
    tmp_path: Path,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="maximum_pack_bytes"):
        _load_canonical_case(
            tmp_path,
            {"mode": "context_pack", "maximum_pack_bytes": value},
        )


@pytest.mark.parametrize("value", [None, True, -1])
def test_maximum_truncated_items_requires_a_non_negative_integer(
    tmp_path: Path,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="maximum_truncated_items"):
        _load_canonical_case(
            tmp_path,
            {"mode": "context_pack", "maximum_truncated_items": value},
        )


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "   ",
        "x" * 161,
        "[",
        "(a+)+$",
        "(a|aa)+$",
        r"(a)\1",
        "(?=a)a",
        r"\s+\s+$",
    ],
)
def test_forbidden_next_query_patterns_are_bounded_valid_regexes(
    tmp_path: Path,
    pattern: str,
) -> None:
    with pytest.raises(ValueError, match="forbidden_next_query_patterns"):
        _load_canonical_case(
            tmp_path,
            {
                "mode": "context_pack",
                "forbidden_next_query_patterns": [pattern],
            },
        )


def test_forbidden_next_query_patterns_accept_documented_safe_subset(
    tmp_path: Path,
) -> None:
    case = _load_canonical_case(
        tmp_path,
        {
            "mode": "context_pack",
            "forbidden_next_query_patterns": [
                "/oups",
                "GET /owners dto",
                r"POSTGRESQL\s+CONFIGURATION",
            ],
        },
    )

    assert case.forbidden_next_query_patterns == (
        "/oups",
        "GET /owners dto",
        r"POSTGRESQL\s+CONFIGURATION",
    )


def test_informational_measurement_fields_parse(tmp_path: Path) -> None:
    fixture = load_quality_fixture(
        _write_fixture(
            tmp_path,
            _minimal_fixture(
                case_overrides={
                    "gate": "informational",
                    "metric_k": 12,
                    "relevance_matchers": [
                        {"contains": "whitelist"},
                        {"contains": "blacklist"},
                    ],
                    "noise_matchers": [{"contains": "region"}],
                }
            ),
        )
    )
    case = fixture.repos[0].queries[0]
    assert case.metric_k == 12
    assert case.relevance_matchers == (
        Matcher(contains="whitelist"), Matcher(contains="blacklist"),
    )
    assert case.noise_matchers == (Matcher(contains="region"),)


@pytest.mark.parametrize("field_name", ["relevance_matchers", "noise_matchers"])
@pytest.mark.parametrize("value", [None, False, 0, "", {}])
def test_measurement_matchers_reject_explicit_malformed_falsy_values(
    tmp_path: Path,
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(case_overrides={field_name: value}),
            )
        )


def test_measurement_matchers_accept_empty_lists_and_missing_defaults(
    tmp_path: Path,
) -> None:
    explicit_empty = load_quality_fixture(
        _write_fixture(
            tmp_path,
            _minimal_fixture(
                case_overrides={
                    "relevance_matchers": [],
                    "noise_matchers": [],
                }
            ),
        )
    ).repos[0].queries[0]
    missing = load_quality_fixture(
        _write_fixture(tmp_path, _minimal_fixture())
    ).repos[0].queries[0]

    assert explicit_empty.relevance_matchers == ()
    assert explicit_empty.noise_matchers == ()
    assert missing.relevance_matchers == ()
    assert missing.noise_matchers == ()


@pytest.mark.parametrize("field_name", ["relevance_matchers", "noise_matchers"])
def test_parse_measurement_matchers_accepts_empty_tuple(field_name: str) -> None:
    assert _parse_measurement_matchers((), field_name) == ()


def test_explicit_null_metric_k_requires_relevance_matchers(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc_info:
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(case_overrides={"metric_k": None}),
            )
        )

    assert str(exc_info.value) == "metric_k requires relevance_matchers"


def test_measurement_matchers_require_contains_selector(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="measurement matcher requires contains"):
        load_quality_fixture(_write_fixture(tmp_path, _minimal_fixture(case_overrides={
            "metric_k": 12,
            "relevance_matchers": [{"path": "src/App.java"}],
        })))
    with pytest.raises(ValueError, match="metric_k requires relevance_matchers"):
        load_quality_fixture(_write_fixture(tmp_path, _minimal_fixture(case_overrides={
            "metric_k": 12,
            "noise_matchers": [{"contains": "region"}],
        })))


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


@pytest.mark.parametrize("min_matches", [-1, 4, True, 1.5, "2"])
def test_at_least_group_rejects_invalid_minimum(
    tmp_path: Path, min_matches: object
) -> None:
    with pytest.raises(ValueError, match="min_matches"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "expected_at_least_top_k": [
                            {
                                "matchers": [
                                    "src/A.java",
                                    "src/B.java",
                                    "src/C.java",
                                ],
                                "top_k": 5,
                                "min_matches": min_matches,
                            }
                        ]
                    }
                ),
            )
        )


def test_at_least_group_rejects_duplicate_matchers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate matcher"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "expected_at_least_top_k": [
                            {
                                "matchers": ["src/A.java", "src/A.java"],
                                "top_k": 5,
                                "min_matches": 1,
                            }
                        ]
                    }
                ),
            )
        )


@pytest.mark.parametrize(
    "matchers",
    [
        pytest.param(
            ["src/A.java", "./src/A.java"],
            id="path-dot-prefix",
        ),
        pytest.param(
            ["src/A.java", r"src\A.java"],
            id="path-backslash",
        ),
        pytest.param(
            [
                {"glob": "src/**/*.java"},
                {"glob": "./src/**/*.java"},
            ],
            id="glob-dot-prefix",
        ),
        pytest.param(
            [
                {"glob": "src/**/*.java"},
                {"glob": r"src\**\*.java"},
            ],
            id="glob-backslash",
        ),
    ],
)
def test_at_least_group_rejects_semantically_duplicate_matchers(
    tmp_path: Path,
    matchers: list[object],
) -> None:
    with pytest.raises(ValueError, match="duplicate matcher"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "expected_at_least_top_k": [
                            {
                                "matchers": matchers,
                                "top_k": 5,
                                "min_matches": 1,
                            }
                        ]
                    }
                ),
            )
        )


@pytest.mark.parametrize(
    "expected_core",
    [
        pytest.param(
            ["src/A.java", "./src/A.java"],
            id="dot-prefix",
        ),
        pytest.param(
            ["src/A.java", r"src\A.java"],
            id="backslash",
        ),
    ],
)
def test_legacy_expected_core_rejects_semantically_duplicate_matchers(
    expected_core: list[str],
) -> None:
    with pytest.raises(ValueError, match="expected_core has duplicate matcher"):
        adapt_legacy_query_case(
            {
                "id": "legacy-duplicate-core",
                "query": "login",
                "expected_core": expected_core,
            }
        )


@pytest.mark.parametrize(
    "raw_value",
    [
        pytest.param(None, id="none"),
        pytest.param(False, id="false"),
        pytest.param(0, id="zero"),
        pytest.param("", id="empty-string"),
        pytest.param({}, id="empty-object"),
    ],
)
def test_at_least_groups_reject_malformed_top_level_value(raw_value: object) -> None:
    with pytest.raises(ValueError, match="expected_at_least_top_k"):
        adapt_legacy_query_case(
            {
                "id": "malformed-at-least-groups",
                "query": "login",
                "expected_at_least_top_k": raw_value,
            }
        )


@pytest.mark.parametrize(
    "case_overrides",
    [
        pytest.param({}, id="missing"),
        pytest.param({"expected_at_least_top_k": []}, id="empty-list"),
        pytest.param({"expected_at_least_top_k": ()}, id="empty-tuple"),
    ],
)
def test_at_least_groups_accept_empty_or_missing_sequence(
    case_overrides: dict,
) -> None:
    case = adapt_legacy_query_case(
        {
            "id": "empty-at-least-groups",
            "query": "login",
            **case_overrides,
        }
    )

    assert case.expected_at_least_top_k == ()


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
        assert_invalid(
            {"expected_core": ["src/App.java"], "expected_top5_min": value}
        )


def test_legacy_expected_top5_min_zero_becomes_zero_minimum_group() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-zero-min",
            "query": "login",
            "expected_core": ["src/AuthController.java"],
            "expected_top5_min": 0,
        }
    )
    assert case.expected_at_least_top_k == (
        AtLeastTopKGroup(
            matchers=(Matcher(path="src/AuthController.java"),),
            top_k=5,
            min_matches=0,
        ),
    )


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


def test_legacy_calibration_maps_n_of_m_required_and_forbidden_paths() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-core",
            "query": "feedback",
            "expected_core": [
                "src/FeedbackController.java",
                "src/FeedbackService.java",
                "src/FeedbackServiceImpl.java",
            ],
            "expected_top5_min": 2,
            "required_top3": ["src/FeedbackController.java"],
            "forbidden_top3": ["src/WxMiniLoginClient.java"],
        }
    )

    assert case.expected_top_k == (
        TopKMatcher(Matcher(path="src/FeedbackController.java"), 3),
    )
    assert case.expected_at_least_top_k == (
        AtLeastTopKGroup(
            matchers=(
                Matcher(path="src/FeedbackController.java"),
                Matcher(path="src/FeedbackService.java"),
                Matcher(path="src/FeedbackServiceImpl.java"),
            ),
            top_k=5,
            min_matches=2,
        ),
    )
    assert case.absent_top_k == (
        TopKMatcher(Matcher(path="src/WxMiniLoginClient.java"), 3),
    )


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


def test_legacy_forbidden_above_max_rank_becomes_absent_window() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-window",
            "query": "fund service",
            "expected_top_k": [
                {"path": "collector/internal/service/fund_service.go", "top_k": 5}
            ],
            "forbidden_above": [
                {
                    "glob": "investment-assistant-backend/**/*.java",
                    "top_k": 5,
                    "max_rank": 2,
                }
            ],
        }
    )

    assert case.absent_top_k == (
        TopKMatcher(Matcher(glob="investment-assistant-backend/**/*.java"), 2),
    )
    assert case.forbidden_above == ()


def test_ci_profile_rejects_model_backed_config() -> None:
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024)
    )

    with pytest.raises(ValueError, match="ci profile"):
        validate_profile_compatible("ci", config)


def test_load_fixture_parses_profile_registry_case_profiles_and_legacy(
    tmp_path: Path,
) -> None:
    fixture_path = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "ci": {
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
                    "query_planner": {"enabled": False},
                },
                "smoke": {
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
                    "query_planner": {"enabled": False},
                },
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {
                            "id": "login",
                            "query": "login",
                            "profiles": ["ci"],
                            "legacy": {
                                "fixture": "generic_baseline_quality",
                                "key": "sample/login",
                            },
                        }
                    ],
                }
            ],
        },
    )

    fixture = load_quality_fixture(fixture_path)

    assert fixture.canonical is True
    assert set(fixture.profile_configs) == {"ci", "smoke"}
    case = fixture.repos[0].queries[0]
    assert case.profiles == ("ci",)
    assert case.legacy == LegacyProvenance(
        fixture="generic_baseline_quality",
        key="sample/login",
    )


def test_case_parses_profile_specific_runtime_expectations(
    tmp_path: Path,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {
            "p1_vector_bge": {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "p1_hybrid_bge": {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {
                    "enabled": True,
                    "provider": "ollama",
                    "model": "qwen3.5:4b-mlx",
                },
            },
        },
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["p1_vector_bge", "p1_hybrid_bge"],
                "queries": [
                    {
                        "id": "cross-language",
                        "query": "数据看板",
                        "profiles": ["p1_vector_bge", "p1_hybrid_bge"],
                        "profile_expectations": {
                            "p1_vector_bge": {
                                "planner_status": "disabled",
                                "variant_retrieval_status": "original_only",
                            },
                            "p1_hybrid_bge": {
                                "planner_status": "ok",
                                "variant_retrieval_status": "hybrid",
                                "top_result_planner_semantic_match": True,
                            },
                        },
                    }
                ],
            }
        ],
    }

    case = load_quality_fixture(_write_fixture(tmp_path, data)).repos[0].queries[0]

    assert case.profile_expectations == {
        "p1_vector_bge": ProfileExpectation(
            planner_status="disabled",
            variant_retrieval_status="original_only",
        ),
        "p1_hybrid_bge": ProfileExpectation(
            planner_status="ok",
            variant_retrieval_status="hybrid",
            top_result_planner_semantic_match=True,
        ),
    }


@pytest.mark.parametrize(
    "expectation,message",
    [
        ({"unknown": True}, "unknown profile expectation field"),
        ({"planner_status": "maybe"}, "invalid planner_status"),
        (
            {"variant_retrieval_status": "fallback"},
            "invalid variant_retrieval_status",
        ),
        (
            {"top_result_planner_semantic_match": 1},
            "top_result_planner_semantic_match must be a bool",
        ),
    ],
)
def test_profile_expectations_reject_unknown_or_invalid_values(
    tmp_path: Path,
    expectation: dict,
    message: str,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {"custom": {}},
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["custom"],
                "queries": [
                    {
                        "id": "case",
                        "query": "query",
                        "profile_expectations": {"custom": expectation},
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match=message):
        load_quality_fixture(_write_fixture(tmp_path, data))


@pytest.mark.parametrize(
    "field,message",
    [
        ("planner_status", "invalid planner_status"),
        ("variant_retrieval_status", "invalid variant_retrieval_status"),
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param([], id="list"),
        pytest.param({}, id="dict"),
        pytest.param(True, id="bool"),
        pytest.param(1, id="number"),
    ],
)
def test_profile_expectations_reject_non_string_status_values(
    tmp_path: Path,
    field: str,
    message: str,
    value: object,
) -> None:
    data = _minimal_fixture(
        repo_overrides={"profiles": ["custom"]},
        case_overrides={
            "profile_expectations": {"custom": {field: value}},
        },
    )
    data["profile_configs"] = {"custom": {}}

    with pytest.raises(ValueError, match=f"^{message}$"):
        load_quality_fixture(_write_fixture(tmp_path, data))


@pytest.mark.parametrize(
    "profile_expectations,message",
    [
        ([], "profile_expectations must be an object"),
        ({"": {}}, "profile expectation name must be a non-empty string"),
        ({"custom": []}, "profile_expectations.custom must be an object"),
    ],
)
def test_profile_expectations_require_object_shapes_and_nonempty_names(
    tmp_path: Path,
    profile_expectations: object,
    message: str,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {"custom": {}},
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["custom"],
                "queries": [
                    {
                        "id": "case",
                        "query": "query",
                        "profile_expectations": profile_expectations,
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match=message):
        load_quality_fixture(_write_fixture(tmp_path, data))


def test_profile_expectation_rejects_unselected_case_profile(
    tmp_path: Path,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {"selected": {}, "unselected": {}},
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["selected", "unselected"],
                "queries": [
                    {
                        "id": "case",
                        "query": "query",
                        "profiles": ["selected"],
                        "profile_expectations": {
                            "unselected": {"planner_status": "disabled"}
                        },
                    }
                ],
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match="profile expectation uses unselected profile",
    ):
        load_quality_fixture(_write_fixture(tmp_path, data))


def test_profile_expectation_uses_repo_profiles_when_case_profiles_are_empty(
    tmp_path: Path,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {"custom": {}},
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["custom"],
                "queries": [
                    {
                        "id": "case",
                        "query": "query",
                        "profile_expectations": {
                            "custom": {"planner_status": "fallback"}
                        },
                    }
                ],
            }
        ],
    }

    case = load_quality_fixture(_write_fixture(tmp_path, data)).repos[0].queries[0]

    assert case.profile_expectations == {
        "custom": ProfileExpectation(planner_status="fallback")
    }


def test_canonical_fixture_allows_registry_defined_profile_name(
    tmp_path: Path,
) -> None:
    data = _minimal_fixture(repo_overrides={"profiles": ["custom"]})
    data["profile_configs"] = {"custom": {}}

    fixture = load_quality_fixture(_write_fixture(tmp_path, data))

    assert fixture.profile_configs == {"custom": {}}


def test_canonical_config_accepts_integer_for_float_field(tmp_path: Path) -> None:
    data = _minimal_fixture()
    data["profile_configs"] = {
        "ci": {"query_planner": {"timeout_seconds": 8}},
    }

    fixture = load_quality_fixture(_write_fixture(tmp_path, data))

    assert fixture.profile_configs["ci"]["query_planner"]["timeout_seconds"] == 8


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda data: data["repos"].append(data["repos"][0].copy()),
            "duplicate repo_key",
        ),
        (
            lambda data: data["repos"][0]["queries"].append(
                data["repos"][0]["queries"][0].copy()
            ),
            "duplicate case id",
        ),
        (
            lambda data: data["repos"][0]["queries"][0].update(
                {"profiles": ["missing"]}
            ),
            "unknown profile",
        ),
        (
            lambda data: data["repos"][0].update(
                {"default_config": {"embedding": {"provider": "bge"}}}
            ),
            "canonical repo default_config",
        ),
        (
            lambda data: data.update({"profile_configs": None}),
            "profile_configs",
        ),
        (
            lambda data: data["profile_configs"]["ci"].update({"retrieval": []}),
            "profile ci.retrieval",
        ),
        (
            lambda data: data["profile_configs"]["ci"]["embedding"].update(
                {"dimensions": "384"}
            ),
            "profile ci.embedding.dimensions",
        ),
        (
            lambda data: data["profile_configs"]["ci"]["embedding"].update(
                {"dimensions": True}
            ),
            "profile ci.embedding.dimensions",
        ),
        (
            lambda data: data["profile_configs"]["ci"]["query_planner"].update(
                {"enabled": 0}
            ),
            "profile ci.query_planner.enabled",
        ),
        (
            lambda data: data["profile_configs"]["ci"]["query_planner"].update(
                {"surprise": True}
            ),
            "unknown config option",
        ),
    ],
)
def test_canonical_fixture_rejects_profile_and_identity_errors(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {
            "ci": {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            }
        },
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["ci"],
                "queries": [{"id": "login", "query": "login"}],
            }
        ],
    }
    mutate(data)

    with pytest.raises(ValueError, match=message):
        load_quality_fixture(_write_fixture(tmp_path, data))


def test_legacy_v1_fixture_derives_profiles_without_registry(tmp_path: Path) -> None:
    fixture = load_quality_fixture(
        _write_fixture(
            tmp_path,
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "profiles": ["ci", "smoke"],
                        "queries": [{"id": "login", "query": "login"}],
                    }
                ],
            },
        )
    )

    assert fixture.profile_configs == {"ci": {}, "smoke": {}}
    assert fixture.canonical is False
    assert fixture.repos[0].queries[0].profiles == ()


@pytest.mark.parametrize(
    "profile,bad_config,message",
    [
        (
            "smoke",
            {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "smoke profile requires hash embeddings",
        ),
        (
            "planner",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "planner profile requires the query planner enabled",
        ),
        (
            "ab_bge",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "ab_bge profile requires BGE M3",
        ),
    ],
)
def test_loader_rejects_invalid_unused_canonical_profile(
    tmp_path: Path,
    profile: str,
    bad_config: dict,
    message: str,
) -> None:
    data = {
        "schema_version": 1,
        "profile_configs": {
            "ci": {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            profile: bad_config,
        },
        "repos": [
            {
                "repo_key": "sample",
                "profiles": ["ci"],
                "queries": [{"id": "login", "query": "login"}],
            }
        ],
    }

    with pytest.raises(ValueError, match=message):
        load_quality_fixture(_write_fixture(tmp_path, data))


@pytest.mark.parametrize(
    "profile,bad_config,message",
    [
        (
            "smoke",
            ToolConfig(embedding=EmbeddingConfig(provider="bge")),
            "smoke profile requires hash embeddings",
        ),
        (
            "ab_hash",
            ToolConfig(query_planner=QueryPlannerConfig(enabled=True)),
            "ab_hash profile requires the query planner disabled",
        ),
        (
            "ci",
            ToolConfig(embedding=EmbeddingConfig(base_url="https://example.test")),
            "ci profile does not allow remote embedding settings",
        ),
        (
            "planner",
            ToolConfig(
                embedding=EmbeddingConfig(provider="bge"),
                query_planner=QueryPlannerConfig(enabled=True),
            ),
            "planner profile requires hash embeddings",
        ),
        (
            "planner",
            ToolConfig(query_planner=QueryPlannerConfig(enabled=False)),
            "planner profile requires the query planner enabled",
        ),
        (
            "planner",
            ToolConfig(
                query_planner=QueryPlannerConfig(enabled=True, provider="remote")
            ),
            "planner profile requires the Ollama planner",
        ),
        (
            "calibration_bge",
            ToolConfig(
                embedding=replace(_VALID_BGE_EMBEDDING, provider="hash")
            ),
            "calibration_bge profile requires BGE M3",
        ),
        (
            "calibration_bge",
            ToolConfig(embedding=replace(_VALID_BGE_EMBEDDING, model="other")),
            "calibration_bge profile requires BGE M3",
        ),
        (
            "calibration_bge",
            ToolConfig(embedding=replace(_VALID_BGE_EMBEDDING, dimensions=384)),
            "calibration_bge profile requires BGE M3",
        ),
        (
            "calibration_bge",
            ToolConfig(
                embedding=_VALID_BGE_EMBEDDING,
                query_planner=QueryPlannerConfig(enabled=True),
            ),
            "calibration_bge profile requires the query planner disabled",
        ),
        (
            "p1_vector_bge",
            ToolConfig(
                embedding=EmbeddingConfig(
                    provider="hash",
                    model="bge-m3",
                    dimensions=1024,
                ),
                query_planner=QueryPlannerConfig(enabled=False),
            ),
            "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
        ),
        (
            "p1_vector_bge",
            ToolConfig(embedding=replace(_VALID_BGE_EMBEDDING, model="other")),
            "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
        ),
        (
            "p1_vector_bge",
            ToolConfig(embedding=replace(_VALID_BGE_EMBEDDING, dimensions=384)),
            "p1_vector_bge profile requires BGE M3 at 1024 dimensions",
        ),
        (
            "p1_vector_bge",
            ToolConfig(
                embedding=_VALID_BGE_EMBEDDING,
                query_planner=QueryPlannerConfig(enabled=True),
            ),
            "p1_vector_bge profile requires the query planner disabled",
        ),
        (
            "p1_hybrid_bge",
            ToolConfig(
                embedding=_VALID_BGE_EMBEDDING,
                query_planner=QueryPlannerConfig(enabled=False),
            ),
            "p1_hybrid_bge profile requires the query planner enabled",
        ),
        (
            "p1_hybrid_bge",
            ToolConfig(
                embedding=_VALID_BGE_EMBEDDING,
                query_planner=QueryPlannerConfig(
                    enabled=True,
                    provider="remote",
                    model="qwen3.5:4b-mlx",
                ),
            ),
            "p1_hybrid_bge profile requires the Ollama planner",
        ),
        (
            "p1_hybrid_bge",
            ToolConfig(
                embedding=_VALID_BGE_EMBEDDING,
                query_planner=QueryPlannerConfig(
                    enabled=True,
                    provider="ollama",
                    model="other",
                ),
            ),
            "p1_hybrid_bge profile requires qwen3.5:4b-mlx",
        ),
    ],
)
def test_canonical_profile_invariants_reject_each_invalid_property(
    profile: str,
    bad_config: ToolConfig,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_profile_compatible(profile, bad_config, canonical=True)


def test_p2_context_pack_profile_accepts_offline_deterministic_config() -> None:
    validate_profile_compatible(
        "p2_context_pack",
        ToolConfig(
            embedding=EmbeddingConfig(
                provider="hash",
                model="hash-v1",
                dimensions=384,
            ),
            query_planner=QueryPlannerConfig(enabled=False),
        ),
        canonical=True,
    )


@pytest.mark.parametrize(
    ("bad_config", "message"),
    [
        (
            ToolConfig(embedding=_VALID_BGE_EMBEDDING),
            "p2_context_pack profile requires hash-v1 embeddings at 384 dimensions",
        ),
        (
            ToolConfig(
                embedding=EmbeddingConfig(
                    provider="openai-compatible",
                    model="remote",
                    dimensions=384,
                )
            ),
            "p2_context_pack profile requires hash-v1 embeddings at 384 dimensions",
        ),
        (
            ToolConfig(embedding=EmbeddingConfig(model="other")),
            "p2_context_pack profile requires hash-v1 embeddings at 384 dimensions",
        ),
        (
            ToolConfig(embedding=EmbeddingConfig(dimensions=768)),
            "p2_context_pack profile requires hash-v1 embeddings at 384 dimensions",
        ),
        (
            ToolConfig(query_planner=QueryPlannerConfig(enabled=True)),
            "p2_context_pack profile requires the query planner disabled",
        ),
        (
            ToolConfig(
                embedding=EmbeddingConfig(base_url="https://example.test/v1")
            ),
            "p2_context_pack profile does not allow remote embedding settings",
        ),
        (
            ToolConfig(embedding=EmbeddingConfig(api_key_env="EMBEDDING_API_KEY")),
            "p2_context_pack profile does not allow remote embedding settings",
        ),
    ],
)
def test_p2_context_pack_profile_rejects_non_deterministic_config(
    bad_config: ToolConfig,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_profile_compatible(
            "p2_context_pack",
            bad_config,
            canonical=True,
        )


def test_unknown_canonical_profile_is_not_treated_as_p2_context_pack() -> None:
    validate_profile_compatible(
        "custom",
        ToolConfig(embedding=_VALID_BGE_EMBEDDING),
        canonical=True,
    )
