# P0 Quality Control Loop Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close roadmap Phase 0 by migrating all retrieval-quality cases into one profile-driven catalog, preserving legacy gates exactly, and making reports and comparisons reliable development gates.

**Architecture:** Extend the existing v1 fixture loader additively with profile configuration, case selection, provenance, N-of-M gates, and informational metrics. Keep retrieval untouched; the quality runner selects and copies repositories, applies an explicit effective config, emits report schema v2, and delegates typed aggregation and comparison to focused quality modules. Migrate legacy fixtures only after parity tests prove all 33 cases retain their meaning.

**Tech Stack:** Python 3.11+, frozen dataclasses, pathlib, JSON, Typer, pytest, existing CST indexer/retrieval/config/query-planner APIs, Conda `base` test environment.

---

## Source Documents

- Approved design: `docs/superpowers/specs/2026-07-11-p0-quality-control-loop-closure-design.md`
- Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
- Existing quality design: `docs/superpowers/specs/2026-07-08-retrieval-quality-scoring-system-design.md`
- Pending planner quality requirements: `docs/superpowers/plans/2026-07-09-repo-aware-query-planner.md`

## Scope Guardrails

- Do not modify `src/context_search_tool/retrieval.py` ranking, candidate generation, score weights, or result selection.
- Do not add ContextPack, RetrievalTrace, multi-round exploration, a new model provider, or automatic branch switching.
- Keep CI hash-based and planner-free.
- Keep BGE, Ollama, and private real repositories outside mandatory CI.
- Never index a source repository in place during a quality run.
- Do not delete a legacy fixture until its parity test passes against the canonical catalog.
- Preserve the two unrelated untracked plan files already present in the main worktree.

## File Structure

Create:

- `src/context_search_tool/quality/aggregate.py` — typed report aggregation and grouping.
- `tests/test_quality_aggregate.py` — counter, rate, mean, percentile, and grouping tests.
- `tests/test_quality_catalog.py` — canonical inventory, legacy parity, profile selection, snapshot, and provenance tests.
- `tests/test_quality_planner.py` — fake and optional real planner diagnostic acceptance.
- `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/DashboardController.java`
- `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/StatisticsService.java`
- `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/ChartService.java`
- `tests/fixtures/real_projects/embedding_ab/src/access/WhitelistValidation.java`
- `tests/fixtures/real_projects/embedding_ab/src/access/BlacklistManager.java`
- `tests/fixtures/real_projects/embedding_ab/src/order/OrderService.java`
- `tests/fixtures/real_projects/embedding_ab/src/noise/RegionService.java`
- `tests/fixtures/real_projects/embedding_ab/src/noise/RoleAnnouncement.java`
- `docs/retrieval-quality.md` — operational quality workflow.

Modify:

- `src/context_search_tool/quality/__init__.py`
- `src/context_search_tool/quality/cases.py`
- `src/context_search_tool/quality/metrics.py`
- `src/context_search_tool/quality/runner.py`
- `src/context_search_tool/quality/compare.py`
- `src/context_search_tool/quality/reports.py`
- `src/context_search_tool/quality/__main__.py`
- `tests/test_quality_cases.py`
- `tests/test_quality_metrics.py`
- `tests/test_quality_runner.py`
- `tests/test_quality_compare.py`
- `tests/test_quality_reports.py`
- `tests/test_quality_cli.py`
- `tests/fixtures/retrieval_quality/queries.json`
- `README.md`
- `.gitignore`
- `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

Delete only after Task 9 parity succeeds:

- `tests/fixtures/generic_baseline_quality/queries.json`
- `tests/fixtures/retrieval_calibration/queries.json`
- `tests/fixtures/ab_comparison/queries.json`
- `tests/test_generic_baseline_quality.py`
- `tests/test_retrieval_calibration.py`
- `tests/test_ab_comparison.py`

Retain `tests/test_generic_baseline_quality.py` until its candidate-pool diagnostic is moved in Task 10.

## Test Command Convention

Use the repository's established interpreter for every command:

```bash
conda run -n base python -m pytest tests/test_quality_cases.py -q
```

Do not substitute bare `python`; the current shell does not provide it.

## Task 1: Add Profile Registry, Case Profiles, And Provenance

**Files:**
- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/__init__.py`
- Modify: `tests/test_quality_cases.py`

- [ ] **Step 1: Write failing profile and provenance tests**

Append these tests to `tests/test_quality_cases.py`:

```python
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
            lambda data: data["profile_configs"]["ci"].update(
                {"retrieval": []}
            ),
            "profile ci.retrieval",
        ),
        (
            lambda data: data["profile_configs"]["ci"]["embedding"].update(
                {"dimensions": "384"}
            ),
            "profile ci.embedding.dimensions",
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
```

Add `LegacyProvenance` to the imports from `context_search_tool.quality.cases`.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py::test_load_fixture_parses_profile_registry_case_profiles_and_legacy \
  tests/test_quality_cases.py::test_canonical_fixture_rejects_profile_and_identity_errors \
  tests/test_quality_cases.py::test_legacy_v1_fixture_derives_profiles_without_registry \
  tests/test_quality_cases.py::test_loader_rejects_invalid_unused_canonical_profile \
  -q
```

Expected: FAIL because `QualityFixture.profile_configs`, `QualityCase.profiles`, and `LegacyProvenance` do not exist.

- [ ] **Step 3: Add the profile and provenance data model**

In `src/context_search_tool/quality/cases.py`, import `fields` and `replace` from `dataclasses`
and `DEFAULT_CONFIG` from `context_search_tool.config`, then add:

```python
@dataclass(frozen=True)
class LegacyProvenance:
    fixture: str
    key: str


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    query: str
    profiles: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    mode: str = "results"
    gate: Gate = Gate.REQUIRED
    expected_top_k: tuple[TopKMatcher, ...] = ()
    expected_any_top_k: tuple[ExpectedAnyGroup, ...] = ()
    preferred_rank: tuple[PreferredRank, ...] = ()
    absent_top_k: tuple[TopKMatcher, ...] = ()
    outranks: tuple[Outranks, ...] = ()
    forbidden_above: tuple[Outranks, ...] = ()
    anchor_expected: tuple[str, ...] = ()
    known_gap_reason: str = ""
    notes: str = ""
    expected_top5_min: int | None = None
    legacy: LegacyProvenance | None = None


@dataclass(frozen=True)
class QualityFixture:
    schema_version: int
    profile_configs: dict[str, dict[str, Any]]
    repos: tuple[QualityRepo, ...]
    path: Path
    canonical: bool
```

Do not remove any other fields until Task 2 replaces `expected_top5_min`.

- [ ] **Step 4: Parse and validate canonical profiles**

Add these helpers and call them from `load_quality_fixture()` after parsing repositories:

```python
def _parse_profile_configs(raw: Any) -> dict[str, dict[str, Any]]:
    raw = _require_dict(raw, "profile_configs")
    parsed: dict[str, dict[str, Any]] = {}
    for name, config in raw.items():
        name = _require_non_empty_str(name, "profile name")
        config = _require_dict(config, f"profile {name}")
        unknown = set(config) - {"index", "retrieval", "embedding", "query_planner"}
        if unknown:
            raise ValueError(f"unknown profile config section: {sorted(unknown)[0]}")
        parsed[name] = {
            section: _validate_config_section(f"profile {name}", section, values)
            for section, values in config.items()
        }
    return parsed


def _validate_config_section(
    owner: str,
    section: str,
    raw: Any,
) -> dict[str, Any]:
    values = dict(_require_dict(raw, f"{owner}.{section}"))
    template = getattr(DEFAULT_CONFIG, section)
    allowed = {item.name for item in fields(template)}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(
            f"unknown config option: {owner}.{section}.{sorted(unknown)[0]}"
        )
    for name, value in values.items():
        default = getattr(template, name)
        label = f"{owner}.{section}.{name}"
        valid = (
            isinstance(value, list)
            and all(isinstance(item, str) for item in value)
            if isinstance(default, list)
            else isinstance(value, str | None)
            if default is None
            else isinstance(value, int | float) and not isinstance(value, bool)
            if isinstance(default, float)
            else type(value) is type(default)
        )
        if not valid:
            raise ValueError(f"{label} has invalid type")
    return values
```

Replace the existing CI-only `validate_profile_compatible()` and add the
profile materializer:

```python
def _canonical_profile_config(overrides: dict[str, Any]) -> ToolConfig:
    result = DEFAULT_CONFIG
    for section in ("index", "retrieval", "embedding", "query_planner"):
        if section in overrides:
            result = replace(
                result,
                **{
                    section: replace(
                        getattr(DEFAULT_CONFIG, section),
                        **overrides[section],
                    )
                },
            )
    return result


def validate_profile_compatible(
    profile: str,
    config: ToolConfig,
    *,
    canonical: bool = False,
) -> None:
    if not canonical:
        if profile != "ci":
            return
        if config.embedding.provider != "hash":
            raise ValueError("ci profile requires hash embeddings")
        if config.query_planner.enabled:
            raise ValueError("ci profile requires the query planner disabled")
        if (
            config.embedding.api_key_env is not None
            or config.embedding.base_url is not None
        ):
            raise ValueError("ci profile does not allow remote embedding settings")
        return
    if profile in {"ci", "smoke", "ab_hash"}:
        if config.embedding.provider != "hash":
            raise ValueError(f"{profile} profile requires hash embeddings")
        if config.query_planner.enabled:
            raise ValueError(f"{profile} profile requires the query planner disabled")
        if profile == "ci" and (
            config.embedding.api_key_env is not None
            or config.embedding.base_url is not None
        ):
            raise ValueError("ci profile does not allow remote embedding settings")
        return
    if profile == "planner":
        if config.embedding.provider != "hash":
            raise ValueError("planner profile requires hash embeddings")
        if not config.query_planner.enabled:
            raise ValueError("planner profile requires the query planner enabled")
        if config.query_planner.provider != "ollama":
            raise ValueError("planner profile requires the Ollama planner")
        return
    if profile in {"calibration_bge", "ab_bge"}:
        if (
            config.embedding.provider != "bge"
            or config.embedding.model != "bge-m3"
            or config.embedding.dimensions != 1024
        ):
            raise ValueError(f"{profile} profile requires BGE M3 at 1024 dimensions")
        if config.query_planner.enabled:
            raise ValueError(f"{profile} profile requires the query planner disabled")
```

In `_parse_repo()`, replace the current loose `default_config` copy with:

```python
raw_default_config = _require_dict(raw.get("default_config", {}), "default_config")
unknown_sections = set(raw_default_config) - {
    "index", "retrieval", "embedding", "query_planner"
}
if unknown_sections:
    raise ValueError(
        f"unknown default_config section: {sorted(unknown_sections)[0]}"
    )
default_config = {
    section: _validate_config_section(
        f"repo {repo_key}.default_config",
        section,
        values,
    )
    for section, values in raw_default_config.items()
}
```

Use this validated `default_config` in the `QualityRepo(...)` return. Then add:

```python
def _validate_fixture_profiles(
    profile_configs: dict[str, dict[str, Any]],
    repos: tuple[QualityRepo, ...],
    canonical: bool,
) -> None:
    if canonical:
        for profile, overrides in profile_configs.items():
            validate_profile_compatible(
                profile,
                _canonical_profile_config(overrides),
                canonical=True,
            )
    repo_keys: set[str] = set()
    for repo in repos:
        if repo.repo_key in repo_keys:
            raise ValueError(f"duplicate repo_key: {repo.repo_key}")
        repo_keys.add(repo.repo_key)
        if canonical and set(repo.default_config) - {"index", "retrieval"}:
            raise ValueError("canonical repo default_config only allows index and retrieval")
        for profile in repo.profiles:
            if profile not in profile_configs:
                raise ValueError(f"unknown profile: {profile}")
        case_ids: set[str] = set()
        for case in repo.queries:
            if case.case_id in case_ids:
                raise ValueError(f"duplicate case id: {repo.repo_key}/{case.case_id}")
            case_ids.add(case.case_id)
            for profile in case.profiles:
                if profile not in repo.profiles or profile not in profile_configs:
                    raise ValueError(f"unknown profile: {profile}")
```

Update `load_quality_fixture()` to use explicit profiles when present and derive empty legacy profiles otherwise:

```python
canonical = "profile_configs" in data
repos = tuple(_parse_repo(raw_repo) for raw_repo in raw_repos)
profile_configs = (
    _parse_profile_configs(data["profile_configs"])
    if canonical
    else {}
)
if not canonical:
    profile_configs = {
        profile: {}
        for repo in repos
        for profile in repo.profiles
    }
_validate_fixture_profiles(profile_configs, repos, canonical)
return QualityFixture(
    schema_version=1,
    profile_configs=profile_configs,
    repos=repos,
    path=path,
    canonical=canonical,
)
```

In `_parse_case()`, parse case profiles and legacy provenance immediately after
`case_id`, `query`, and `gate` are parsed:

```python
raw_legacy = raw.get("legacy")
legacy = None
if raw_legacy is not None:
    raw_legacy = _require_dict(raw_legacy, "legacy")
    legacy = LegacyProvenance(
        fixture=_require_non_empty_str(raw_legacy.get("fixture"), "legacy.fixture"),
        key=_require_non_empty_str(raw_legacy.get("key"), "legacy.key"),
    )

profiles = _require_str_tuple(raw.get("profiles", ()), "profiles")
```

Then add exactly these two keyword arguments to the existing `QualityCase(...)`
return expression; leave every pre-existing keyword argument in place:

```python
profiles=profiles,
legacy=legacy,
```

- [ ] **Step 5: Export the new public type and run the case suite**

Add `LegacyProvenance` to `src/context_search_tool/quality/__init__.py` imports and `__all__`, then run:

```bash
conda run -n base python -m pytest tests/test_quality_cases.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/__init__.py \
  tests/test_quality_cases.py
git commit -m "feat: add quality profile registry"
```

## Task 2: Preserve Calibration N-Of-M And Legacy Rank Windows

**Files:**
- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/__init__.py`
- Modify: `src/context_search_tool/quality/metrics.py`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_metrics.py`

- [ ] **Step 1: Replace the legacy calibration adapter test**

Replace `test_legacy_calibration_expected_core_becomes_relevance_targets` and
`test_legacy_forbidden_above_dict_shorthand_uses_first_expected_target` in
`tests/test_quality_cases.py` with:

```python
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
        TopKMatcher(
            Matcher(glob="investment-assistant-backend/**/*.java"),
            2,
        ),
    )
    assert case.forbidden_above == ()
```

Import `AtLeastTopKGroup` and `TopKMatcher` in that test file.

- [ ] **Step 2: Add N-of-M validation tests**

Append:

```python
@pytest.mark.parametrize("min_matches", [-1, 4, True, 1.5, "2"])
def test_at_least_group_rejects_invalid_minimum(
    tmp_path: Path,
    min_matches: object,
) -> None:
    with pytest.raises(ValueError, match="min_matches"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "expected_at_least_top_k": [
                            {
                                "matchers": ["src/A.java", "src/B.java", "src/C.java"],
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
```

- [ ] **Step 3: Add the failing evaluator parity test**

Append to `tests/test_quality_metrics.py`:

```python
def test_at_least_group_gates_n_of_m_but_counts_each_relevance_target() -> None:
    group = AtLeastTopKGroup(
        matchers=tuple(Matcher(path=f"src/{name}.java") for name in "ABCDE"),
        top_k=5,
        min_matches=2,
    )
    case = QualityCase(
        case_id="two-of-five",
        query="auth",
        expected_at_least_top_k=(group,),
    )

    passes = evaluate_case(
        case,
        [_result("src/A.java"), _result("src/C.java")],
        latency_ms=1,
    )
    fails = evaluate_case(case, [_result("src/A.java")], latency_ms=1)

    assert passes.status == "pass"
    assert passes.failures == []
    assert passes.metrics["recall_at_5"] == pytest.approx(2 / 5)
    assert fails.status == "fail"
    assert fails.failures == [
        "expected_at_least_top_k expected 2 within top 5, found 1"
    ]


def test_zero_minimum_records_relevance_without_failure() -> None:
    case = QualityCase(
        case_id="zero-minimum",
        query="alarm",
        expected_at_least_top_k=(
            AtLeastTopKGroup(
                matchers=(Matcher(path="src/AlarmService.java"),),
                top_k=5,
                min_matches=0,
            ),
        ),
    )

    evaluation = evaluate_case(case, [], latency_ms=1)

    assert evaluation.status == "pass"
    assert evaluation.metrics["recall_at_5"] == 0.0


def test_informational_cross_language_metrics_without_legacy_minimum() -> None:
    case = QualityCase(
        case_id="cross-language-info",
        query="数据看板",
        tags=("cross_language",),
        gate=Gate.INFORMATIONAL,
        expected_top_k=(
            TopKMatcher(Matcher(path="src/Dashboard.java"), 5),
        ),
    )

    evaluation = evaluate_case(
        case,
        [_result("src/Dashboard.java")],
        latency_ms=1,
    )

    assert evaluation.status == "informational"
    assert evaluation.metrics["cross_language_success"] is True


def test_legacy_forbidden_window_matches_absolute_rank_semantics() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-window",
            "query": "fund service",
            "expected_top_k": [{"path": "src/FundService.go", "top_k": 5}],
            "forbidden_above": [
                {"glob": "legacy/**/*.java", "top_k": 5, "max_rank": 2}
            ],
        }
    )

    fails = evaluate_case(
        case,
        [_result("src/FundService.go"), _result("legacy/Old.java")],
        latency_ms=1,
    )
    passes = evaluate_case(
        case,
        [
            _result("src/FundService.go"),
            _result("src/Other.go"),
            _result("legacy/Old.java"),
        ],
        latency_ms=1,
    )

    assert fails.status == "fail"
    assert fails.failures == [
        "absent_top_k present within top 2: legacy/**/*.java"
    ]
    assert passes.status == "pass"


def test_expected_anchor_must_remain_outside_ranked_results() -> None:
    case = QualityCase(
        case_id="anchor-separation",
        query="readme",
        anchor_expected=("README.md",),
    )

    evaluation = evaluate_case(
        case,
        [_result("README.md")],
        latency_ms=1,
        anchor_paths=["README.md"],
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "anchor_expected must remain outside ranked results: README.md"
    ]
```

Import `AtLeastTopKGroup` and `adapt_legacy_query_case` in
`tests/test_quality_metrics.py`. Replace the
pre-existing `test_expected_top5_min_informational_and_cross_language_metrics`
with `test_informational_cross_language_metrics_without_legacy_minimum` above.

- [ ] **Step 4: Run the new tests and verify failure**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py::test_legacy_calibration_maps_n_of_m_required_and_forbidden_paths \
  tests/test_quality_cases.py::test_legacy_forbidden_above_max_rank_becomes_absent_window \
  tests/test_quality_cases.py::test_at_least_group_rejects_invalid_minimum \
  tests/test_quality_cases.py::test_at_least_group_rejects_duplicate_matchers \
  tests/test_quality_metrics.py::test_at_least_group_gates_n_of_m_but_counts_each_relevance_target \
  tests/test_quality_metrics.py::test_zero_minimum_records_relevance_without_failure \
  tests/test_quality_metrics.py::test_informational_cross_language_metrics_without_legacy_minimum \
  tests/test_quality_metrics.py::test_legacy_forbidden_window_matches_absolute_rank_semantics \
  tests/test_quality_metrics.py::test_expected_anchor_must_remain_outside_ranked_results \
  -q
```

Expected: FAIL because N-of-M fields do not exist, legacy `max_rank` still maps
to a relational outrank, and anchor/result separation is not enforced.

- [ ] **Step 5: Implement N-of-M parsing and legacy conversion**

Add to `cases.py`:

```python
@dataclass(frozen=True)
class AtLeastTopKGroup:
    matchers: tuple[Matcher, ...]
    top_k: int
    min_matches: int


def _parse_at_least_groups(raw: Any) -> tuple[AtLeastTopKGroup, ...]:
    if not raw:
        return ()
    groups: list[AtLeastTopKGroup] = []
    for item in _require_sequence(raw, "expected_at_least_top_k"):
        item = _require_dict(item, "expected_at_least_top_k group")
        matchers = tuple(
            Matcher.from_raw(value)
            for value in _require_sequence(item.get("matchers"), "matchers")
        )
        if not matchers:
            raise ValueError("expected_at_least_top_k requires matchers")
        if len(set(matchers)) != len(matchers):
            raise ValueError("expected_at_least_top_k has duplicate matcher")
        minimum = _require_non_negative_int(item.get("min_matches"), "min_matches")
        if minimum > len(matchers):
            raise ValueError("min_matches cannot exceed matcher count")
        groups.append(
            AtLeastTopKGroup(
                matchers=matchers,
                top_k=_require_positive_int(item.get("top_k"), "top_k"),
                min_matches=minimum,
            )
        )
    return tuple(groups)


def _partition_forbidden_above(
    raw: Any,
) -> tuple[tuple[TopKMatcher, ...], tuple[Any, ...]]:
    if not raw:
        return (), ()
    items = tuple(raw) if isinstance(raw, (list, tuple)) else (raw,)
    windows: list[TopKMatcher] = []
    relational: list[Any] = []
    for item in items:
        if (
            isinstance(item, dict)
            and "max_rank" in item
            and not {"source", "noise"}.issubset(item)
        ):
            top_k = _require_positive_int(item.get("top_k", 5), "top_k")
            max_rank = _require_positive_int(item.get("max_rank"), "max_rank")
            if max_rank > top_k:
                raise ValueError("forbidden_above max_rank cannot exceed top_k")
            windows.append(TopKMatcher(Matcher.from_raw(item), max_rank))
        else:
            relational.append(item)
    return tuple(windows), tuple(relational)
```

In `_parse_case()`, stop appending `expected_core` to `expected_top_k`. Instead build:

```python
at_least_groups = _parse_at_least_groups(raw.get("expected_at_least_top_k", ()))
if "expected_core" in raw:
    core_matchers = tuple(
        Matcher.from_raw(item)
        for item in _require_sequence(raw["expected_core"], "expected_core")
    )
    if not core_matchers:
        raise ValueError("expected_core requires at least one matcher")
    if len(set(core_matchers)) != len(core_matchers):
        raise ValueError("expected_core has duplicate matcher")
    minimum = raw.get("expected_top5_min", len(core_matchers))
    minimum = _require_non_negative_int(minimum, "expected_top5_min")
    if minimum > len(core_matchers):
        raise ValueError("expected_top5_min cannot exceed expected_core count")
    at_least_groups += (
        AtLeastTopKGroup(core_matchers, top_k=5, min_matches=minimum),
    )
```

Append legacy `required_top3` paths with:

```python
if "required_top3" in raw:
    expected_top_k += tuple(
        TopKMatcher(Matcher.from_raw(item), 3)
        for item in _require_sequence(raw["required_top3"], "required_top3")
    )
```

Keep the existing `forbidden_top3 -> absent_top_k` block. Add
`expected_at_least_top_k=at_least_groups` to the `QualityCase(...)` return and
remove the `expected_top5_min` field and return argument entirely.

Before the `QualityCase(...)` return, partition legacy absolute rank windows:

```python
forbidden_windows, relational_forbidden = _partition_forbidden_above(
    raw.get("forbidden_above")
)
absent_top_k += forbidden_windows
forbidden_above = _parse_forbidden_above(
    relational_forbidden,
    expected_top_k,
)
```

Pass this `forbidden_above` variable instead of reparsing the raw field. This
keeps explicit `{source, noise, top_k}` and string shorthand relational, while
the two legacy `{matcher, top_k, max_rank}` cases become exact absolute
`absent_top_k` windows.

- [ ] **Step 6: Implement N-of-M evaluation and relevance counting**

In `evaluate_case()`, delete the `expected_top5_count = ...` assignment and the
entire `if case.expected_top5_min is not None: ...` failure block. Preserve the
separate `coverage_top5_count` calculation. Then add before preferred-rank
evaluation:

```python
for group in case.expected_at_least_top_k:
    match_count = sum(
        1
        for matcher in group.matchers
        if _rank_within(_first_rank(normalized, (matcher,)), group.top_k)
    )
    if match_count < group.min_matches:
        failures.append(
            f"expected_at_least_top_k expected {group.min_matches} "
            f"within top {group.top_k}, found {match_count}"
        )
```

Extend `_relevance_targets()` with one independent target per group matcher:

```python
for group in case.expected_at_least_top_k:
    targets.extend(_RelevanceTarget((matcher,)) for matcher in group.matchers)
```

Replace the existing `anchor_paths is not None` block with:

```python
if anchor_paths is not None:
    normalized_anchors = {normalize_result_path(path) for path in anchor_paths}
    ranked_paths = {result.path for result in normalized}
    for expected_anchor in case.anchor_expected:
        expected_path = normalize_result_path(expected_anchor)
        if expected_path not in normalized_anchors:
            failures.append(f"anchor_expected missing: {expected_path}")
        elif expected_path in ranked_paths:
            failures.append(
                "anchor_expected must remain outside ranked results: "
                f"{expected_path}"
            )
```

Export `AtLeastTopKGroup` from `quality/__init__.py`.

- [ ] **Step 7: Run focused and full quality tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/__init__.py \
  src/context_search_tool/quality/metrics.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py
git commit -m "fix: preserve calibration n-of-m gates"
```

## Task 3: Add Informational A/B Measurements

**Files:**
- Modify: `src/context_search_tool/quality/cases.py`
- Modify: `src/context_search_tool/quality/metrics.py`
- Modify: `tests/test_quality_cases.py`
- Modify: `tests/test_quality_metrics.py`

- [ ] **Step 1: Add failing informational schema tests**

Append to `tests/test_quality_cases.py`:

```python
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
        Matcher(contains="whitelist"),
        Matcher(contains="blacklist"),
    )
    assert case.noise_matchers == (Matcher(contains="region"),)


def test_measurement_matchers_require_contains_selector(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="measurement matcher requires contains"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "metric_k": 12,
                        "relevance_matchers": [{"path": "src/App.java"}],
                    }
                ),
            )
        )

    with pytest.raises(ValueError, match="metric_k requires relevance_matchers"):
        load_quality_fixture(
            _write_fixture(
                tmp_path,
                _minimal_fixture(
                    case_overrides={
                        "metric_k": 12,
                        "noise_matchers": [{"contains": "region"}],
                    }
                ),
            )
        )
```

- [ ] **Step 2: Add the exact legacy-formula metric test**

Append to `tests/test_quality_metrics.py`:

```python
def test_informational_metrics_are_casefolded_unique_and_fixed_denominator() -> None:
    case = QualityCase(
        case_id="embedding-ab",
        query="黑白名单管理",
        gate=Gate.INFORMATIONAL,
        metric_k=12,
        relevance_matchers=(
            Matcher(contains="whitelist"),
            Matcher(contains="blacklist"),
        ),
        noise_matchers=(Matcher(contains="region"),),
    )
    results = [
        _result("src/WhitelistManager.java"),
        _result("src/WhitelistManager.java"),
        _result("src/BLACKLISTService.java"),
        _result("src/RegionService.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=4)

    assert evaluation.status == "informational"
    assert evaluation.metrics["precision_at_12"] == pytest.approx(2 / 12)
    assert evaluation.metrics["noise_top12"] == 1
    assert evaluation.metrics["mrr"] == 1.0
    assert evaluation.failures == []
```

- [ ] **Step 3: Run the tests and verify failure**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py::test_informational_measurement_fields_parse \
  tests/test_quality_cases.py::test_measurement_matchers_require_contains_selector \
  tests/test_quality_metrics.py::test_informational_metrics_are_casefolded_unique_and_fixed_denominator \
  -q
```

Expected: FAIL because measurement fields are not modeled.

- [ ] **Step 4: Parse informational measurement fields**

Add these fields to `QualityCase`:

```python
metric_k: int | None = None
relevance_matchers: tuple[Matcher, ...] = ()
noise_matchers: tuple[Matcher, ...] = ()
```

Add and use:

```python
def _parse_measurement_matchers(raw: Any, field_name: str) -> tuple[Matcher, ...]:
    if not raw:
        return ()
    matchers = tuple(
        Matcher.from_raw(item)
        for item in _require_sequence(raw, field_name)
    )
    if any(matcher.contains is None for matcher in matchers):
        raise ValueError(f"{field_name} measurement matcher requires contains")
    return matchers
```

In `_parse_case()`, use:

```python
relevance_matchers = _parse_measurement_matchers(
    raw.get("relevance_matchers", ()),
    "relevance_matchers",
)
noise_matchers = _parse_measurement_matchers(
    raw.get("noise_matchers", ()),
    "noise_matchers",
)
raw_metric_k = raw.get("metric_k")
if (noise_matchers or raw_metric_k is not None) and not relevance_matchers:
    raise ValueError("metric_k requires relevance_matchers")
if relevance_matchers:
    metric_k = _require_positive_int(raw_metric_k, "metric_k")
else:
    metric_k = None
```

Pass all three values to the `QualityCase(...)` return.

- [ ] **Step 5: Implement case-insensitive measurement formulas**

In `metrics.py` add:

```python
def _measurement_matches(matcher: Matcher, path: str) -> bool:
    assert matcher.contains is not None
    return matcher.contains.casefold() in normalize_result_path(path).casefold()


def _measurement_metrics(
    case: QualityCase,
    results: list[NormalizedResult],
) -> dict[str, Any]:
    if case.metric_k is None:
        return {}
    top = results[: case.metric_k]
    relevant = [
        result
        for result in top
        if any(_measurement_matches(matcher, result.path) for matcher in case.relevance_matchers)
    ]
    noise = [
        result
        for result in top
        if any(_measurement_matches(matcher, result.path) for matcher in case.noise_matchers)
    ]
    first_rank = next(
        (
            result.rank
            for result in results
            if any(
                _measurement_matches(matcher, result.path)
                for matcher in case.relevance_matchers
            )
        ),
        None,
    )
    return {
        f"precision_at_{case.metric_k}": len(relevant) / case.metric_k,
        f"noise_top{case.metric_k}": len(noise),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
    }
```

In `_metrics()`, change its existing `return {` to `metrics = {` without
altering any key/value lines. Immediately after that literal's closing brace,
append:

```python
metrics.update(_measurement_metrics(case, normalized))
return metrics
```

The update deliberately overwrites normal-target `mrr` only when `metric_k` is
present. Do not add measurement failures.

- [ ] **Step 6: Run the quality metric suites**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/context_search_tool/quality/cases.py \
  src/context_search_tool/quality/metrics.py \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py
git commit -m "feat: add informational quality metrics"
```

## Task 4: Add Typed Report Aggregation

**Files:**
- Create: `src/context_search_tool/quality/aggregate.py`
- Create: `tests/test_quality_aggregate.py`
- Modify: `src/context_search_tool/quality/__init__.py`

- [ ] **Step 1: Write failing counter and metric-summary tests**

Create `tests/test_quality_aggregate.py`:

```python
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
                "expected_coverage_top5": {"count": 1, "ratio": 0.5},
            },
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
        "count": 2,
        "mean": 20.0,
        "p50": 10,
        "p95": 30,
    }
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
```

- [ ] **Step 2: Run the aggregation tests and verify import failure**

```bash
conda run -n base python -m pytest tests/test_quality_aggregate.py -q
```

Expected: FAIL because `quality.aggregate` does not exist.

- [ ] **Step 3: Implement typed aggregation**

Create `src/context_search_tool/quality/aggregate.py` with these public contracts and helpers:

```python
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Any, Callable


_EXECUTED_STATUSES = {"pass", "fail", "known_gap", "informational"}
_BOOLEAN_METRICS = {
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "hit_at_10",
    "cross_language_success",
    "preferred_rank_pass",
}


def aggregate_cases(
    cases: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    profile: str,
) -> dict[str, Any]:
    statuses = [case.get("status") for case in cases]
    executed = [case for case in cases if case.get("status") in _EXECUTED_STATUSES]
    aggregate: dict[str, Any] = {
        "total": len(cases),
        "selected": len(cases),
        "attempted": sum(bool(case.get("attempted")) for case in cases),
        "executed": len(executed),
        "passed": statuses.count("pass"),
        "failed": statuses.count("fail"),
        "skipped": statuses.count("skipped"),
        "known_gaps": statuses.count("known_gap"),
        "informational": statuses.count("informational"),
        "errors": statuses.count("error"),
    }
    aggregate["metrics"] = _grouped_metrics(executed, repos, profile)
    return aggregate


def _grouped_metrics(
    cases: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    profile: str,
) -> dict[str, Any]:
    repo_embedding = {
        repo["repo_key"]: repo.get("config", {}).get("embedding", {})
        for repo in repos
    }
    by_repository = _group(cases, lambda case: [case["repo_key"]])
    by_tag = _group(cases, lambda case: case.get("tags", []))
    by_profile = {profile: _metric_summary(cases)}
    by_embedding = _group(
        cases,
        lambda case: [
            "{provider}/{model}".format(
                provider=repo_embedding.get(case["repo_key"], {}).get("provider", ""),
                model=repo_embedding.get(case["repo_key"], {}).get("model", ""),
            )
        ],
    )
    return {
        "overall": _metric_summary(cases),
        "by_repository": by_repository,
        "by_tag": by_tag,
        "by_profile": by_profile,
        "by_embedding": by_embedding,
    }


def _group(
    cases: list[dict[str, Any]],
    keys_for_case: Callable[[dict[str, Any]], list[str]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for key in keys_for_case(case):
            if key:
                grouped[key].append(case)
    return {key: _metric_summary(grouped[key]) for key in sorted(grouped)}


def _metric_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[Any]] = defaultdict(list)
    entrypoint_ranks: list[int | None] = []
    for case in cases:
        metrics = case.get("metrics", {})
        for name, value in metrics.items():
            if value is None:
                continue
            if name == "expected_coverage_top5" and isinstance(value, dict):
                ratio = value.get("ratio")
                if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
                    values["expected_coverage_top5_ratio"].append(float(ratio))
                continue
            if name == "entrypoint_rank":
                continue
            values[name].append(value)
        if "entrypoint" in case.get("tags", []):
            rank = metrics.get("entrypoint_rank")
            entrypoint_ranks.append(
                rank if isinstance(rank, int) and not isinstance(rank, bool) else None
            )

    summary: dict[str, Any] = {}
    for name, items in values.items():
        if name in _BOOLEAN_METRICS:
            booleans = [item for item in items if isinstance(item, bool)]
            if booleans:
                successes = sum(booleans)
                summary[name] = {
                    "successes": successes,
                    "total": len(booleans),
                    "rate": successes / len(booleans),
                }
            continue
        numbers = [
            float(item)
            for item in items
            if isinstance(item, (int, float)) and not isinstance(item, bool)
        ]
        if not numbers:
            continue
        if name == "latency_ms":
            ordered = sorted(numbers)
            summary[name] = {
                "count": len(ordered),
                "mean": mean(ordered),
                "p50": _nearest_rank(ordered, 0.50),
                "p95": _nearest_rank(ordered, 0.95),
            }
        else:
            summary[name] = {"count": len(numbers), "mean": mean(numbers)}

    if entrypoint_ranks:
        for name, limit in (("entrypoint_top1", 1), ("entrypoint_top3", 3)):
            successes = sum(
                rank is not None and rank <= limit for rank in entrypoint_ranks
            )
            summary[name] = {
                "successes": successes,
                "total": len(entrypoint_ranks),
                "rate": successes / len(entrypoint_ranks),
            }
    return summary


def _nearest_rank(values: list[float], percentile: float) -> float:
    index = max(0, math.ceil(percentile * len(values)) - 1)
    value = values[index]
    return int(value) if value.is_integer() else value
```

- [ ] **Step 4: Export and verify aggregation**

Export `aggregate_cases` from `quality/__init__.py`, then run:

```bash
conda run -n base python -m pytest tests/test_quality_aggregate.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/context_search_tool/quality/aggregate.py \
  src/context_search_tool/quality/__init__.py \
  tests/test_quality_aggregate.py
git commit -m "feat: aggregate retrieval quality metrics"
```

## Task 5: Apply Profile Configs And Resolve Sources Safely

**Files:**
- Modify: `src/context_search_tool/quality/runner.py`
- Modify: `tests/test_quality_runner.py`

- [ ] **Step 1: Add failing effective-config tests**

Extend `tests/test_quality_runner.py` imports with:

```python
from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    IndexConfig,
    QueryPlannerConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.indexer import IndexSummary
from context_search_tool.manifest import Manifest
from context_search_tool.retrieval import QueryBundle
```

Append:

```python
def test_canonical_profile_rebuilds_from_default_then_repo_then_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(
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
                }
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "default_config": {"retrieval": {"final_top_k": 7}},
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    stale = ToolConfig(
        index=IndexConfig(max_file_bytes=1),
        retrieval=RetrievalConfig(final_top_k=99),
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="remote",
            dimensions=1536,
            base_url="https://example.invalid",
            api_key_env="API_KEY",
        ),
        query_planner=QueryPlannerConfig(
            enabled=True,
            base_url="https://planner.invalid",
            use_system_proxy=True,
            timeout_seconds=99,
        ),
    )
    captured: list[ToolConfig] = []

    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append(config)
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    def fake_query(*args: object, **kwargs: object) -> QueryBundle:
        return QueryBundle(
            query="targetToken",
            expanded_tokens=["targettoken"],
            results=[],
            followup_keywords=[],
        )

    monkeypatch.setattr("context_search_tool.quality.runner.index_repository", fake_index)
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="sha256:test"),
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fake_query,
    )

    run_quality_fixture(fixture, "ci", None, None, config=stale)

    effective = captured[0]
    assert effective.index == DEFAULT_CONFIG.index
    assert effective.embedding == DEFAULT_CONFIG.embedding
    assert effective.query_planner == DEFAULT_CONFIG.query_planner
    assert effective.retrieval.final_top_k == 7


def test_legacy_fixture_keeps_caller_base_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["smoke"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    caller_config = ToolConfig(
        index=IndexConfig(max_file_bytes=1234),
        retrieval=RetrievalConfig(final_top_k=9),
    )
    captured: list[ToolConfig] = []

    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append(config)
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    monkeypatch.setattr("context_search_tool.quality.runner.index_repository", fake_index)
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="sha256:test"),
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        lambda *args, **kwargs: QueryBundle(
            query="targetToken",
            expanded_tokens=["targettoken"],
            results=[],
            followup_keywords=[],
        ),
    )

    run_quality_fixture(fixture, "smoke", None, None, config=caller_config)

    assert captured[0].index.max_file_bytes == 1234
    assert captured[0].retrieval.final_top_k == 9
```

- [ ] **Step 2: Add failing source-resolution order tests**

Append:

```python
def test_non_ci_source_prefers_existing_env_then_smoke_root_then_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_repo = tmp_path / "env-repo"
    smoke_repo = tmp_path / "smoke" / "sample"
    snapshot = tmp_path / "snapshot"
    for repo in (env_repo, smoke_repo, snapshot):
        repo.mkdir(parents=True)

    quality_repo = QualityRepo(
        repo_key="sample",
        path_env="CST_SAMPLE_REPO",
        repo_dir_name="sample",
        snapshot_path=str(snapshot),
        profiles=("smoke",),
        queries=(QualityCase(case_id="q", query="q"),),
    )
    fixture_path = tmp_path / "quality.json"
    monkeypatch.setenv("CST_SAMPLE_REPO", str(env_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_repo.parent))

    assert _resolve_repo_source(quality_repo, fixture_path, "smoke") == ResolvedSource(
        path=env_repo.resolve(),
        source_type="path_env",
        locator="CST_SAMPLE_REPO",
    )

    monkeypatch.setenv("CST_SAMPLE_REPO", str(tmp_path / "missing-env"))
    assert _resolve_repo_source(quality_repo, fixture_path, "smoke") == ResolvedSource(
        path=smoke_repo.resolve(),
        source_type="smoke_root",
        locator="sample",
    )

    smoke_repo.rmdir()
    assert _resolve_repo_source(quality_repo, fixture_path, "smoke") == ResolvedSource(
        path=snapshot.resolve(),
        source_type="snapshot_path",
        locator="snapshot",
    )
```

Import `QualityCase`, `QualityRepo`, `ResolvedSource`, and `_resolve_repo_source` for this focused internal test.

- [ ] **Step 3: Add failing case-profile selection test**

```python
def test_runner_executes_only_cases_selected_by_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "ci": {
                    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                    "query_planner": {"enabled": False},
                },
                "smoke": {
                    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                    "query_planner": {"enabled": False},
                },
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {"id": "ci-only", "query": "targetToken", "profiles": ["ci"]},
                        {"id": "smoke-only", "query": "targetToken", "profiles": ["smoke"]},
                    ],
                }
            ],
        },
    )

    report = run_quality_fixture(fixture, "ci", None, None)

    assert [case["case_id"] for case in report["cases"]] == ["ci-only"]
    with pytest.raises(ValueError, match="unknown quality profile: missing"):
        run_quality_fixture(fixture, "missing", None, None)


@pytest.mark.parametrize(
    "profile,profile_config,provider,planner_enabled",
    [
        (
            "ci",
            {
                "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                "query_planner": {"enabled": False},
            },
            "hash",
            False,
        ),
        (
            "smoke",
            {
                "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                "query_planner": {"enabled": False},
            },
            "hash",
            False,
        ),
        (
            "planner",
            {
                "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                "query_planner": {"enabled": True, "provider": "ollama"},
            },
            "hash",
            True,
        ),
        (
            "calibration_bge",
            {
                "embedding": {"provider": "bge", "model": "bge-m3", "dimensions": 1024},
                "query_planner": {"enabled": False},
            },
            "bge",
            False,
        ),
        (
            "ab_hash",
            {
                "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                "query_planner": {"enabled": False},
            },
            "hash",
            False,
        ),
        (
            "ab_bge",
            {
                "embedding": {"provider": "bge", "model": "bge-m3", "dimensions": 1024},
                "query_planner": {"enabled": False},
            },
            "bge",
            False,
        ),
    ],
)
def test_all_canonical_profiles_wire_without_external_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    profile_config: dict,
    provider: str,
    planner_enabled: bool,
) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {profile: profile_config},
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": [profile],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[ToolConfig] = []

    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append(config)
        assert (repo / "src" / "App.java").is_file()
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    monkeypatch.setattr("context_search_tool.quality.runner.index_repository", fake_index)
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="sha256:test"),
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        lambda *args, **kwargs: QueryBundle(
            query="targetToken",
            expanded_tokens=["targettoken"],
            results=[],
            followup_keywords=[],
        ),
    )

    report = run_quality_fixture(fixture, profile, None, None)

    assert [case["case_id"] for case in report["cases"]] == ["target"]
    assert captured[0].embedding.provider == provider
    assert captured[0].query_planner.enabled is planner_enabled
```

- [ ] **Step 4: Run focused tests and verify failure**

```bash
conda run -n base python -m pytest \
  tests/test_quality_runner.py::test_canonical_profile_rebuilds_from_default_then_repo_then_profile \
  tests/test_quality_runner.py::test_legacy_fixture_keeps_caller_base_config \
  tests/test_quality_runner.py::test_non_ci_source_prefers_existing_env_then_smoke_root_then_snapshot \
  tests/test_quality_runner.py::test_runner_executes_only_cases_selected_by_profile \
  tests/test_quality_runner.py::test_all_canonical_profiles_wire_without_external_dependencies \
  -q
```

Expected: FAIL because profile configs, `ResolvedSource`, and case filtering are not wired.

- [ ] **Step 5: Implement effective configuration**

Replace `_apply_repo_config()` with:

```python
def _apply_config_sections(
    config: ToolConfig,
    overrides: dict[str, Any],
) -> ToolConfig:
    result = config
    for section_name in ("index", "retrieval", "embedding", "query_planner"):
        if section_name in overrides:
            current = getattr(result, section_name)
            result = replace(
                result,
                **{section_name: replace(current, **overrides[section_name])},
            )
    return result


def _effective_config(
    base: ToolConfig,
    repo_overrides: dict[str, Any],
    profile_overrides: dict[str, Any],
) -> ToolConfig:
    result = _apply_config_sections(base, repo_overrides)
    if "index" in profile_overrides:
        result = replace(
            result,
            index=replace(result.index, **profile_overrides["index"]),
        )
    if "retrieval" in profile_overrides:
        result = replace(
            result,
            retrieval=replace(result.retrieval, **profile_overrides["retrieval"]),
        )
    if "embedding" in profile_overrides:
        result = replace(
            result,
            embedding=replace(DEFAULT_CONFIG.embedding, **profile_overrides["embedding"]),
        )
    if "query_planner" in profile_overrides:
        result = replace(
            result,
            query_planner=replace(
                DEFAULT_CONFIG.query_planner,
                **profile_overrides["query_planner"],
            ),
        )
    return result
```

At the start of `run_quality_fixture()`, reject an unknown profile with:

```python
if profile not in fixture.profile_configs:
    raise ValueError(f"unknown quality profile: {profile}")
```

For each repo, use:

```python
profile_overrides = fixture.profile_configs[profile]
base_config = DEFAULT_CONFIG if fixture.canonical else config
repo_config = _effective_config(
    base_config,
    repo.default_config,
    profile_overrides,
)
validate_profile_compatible(profile, repo_config, canonical=fixture.canonical)
```

Use the canonical/legacy-aware `validate_profile_compatible()` introduced in
Task 1; do not redefine it in the runner task.

- [ ] **Step 6: Implement safe source resolution and case selection**

Add:

```python
@dataclass(frozen=True)
class ResolvedSource:
    path: Path
    source_type: str
    locator: str


def _existing_directory(path: Path) -> Path | None:
    resolved = path.expanduser().resolve()
    return resolved if resolved.is_dir() else None


def _safe_snapshot_locator(raw_path: str) -> str:
    path = Path(raw_path)
    return path.as_posix() if not path.is_absolute() else path.name
```

Return `ResolvedSource` from `_resolve_repo_source()` in this order:

```python
if profile == "ci":
    if not repo.snapshot_path:
        raise ValueError(f"ci profile requires snapshot_path for repo {repo.repo_key}")
    snapshot = _existing_directory(_resolve_snapshot_path(fixture_path, repo.snapshot_path))
    if snapshot is None:
        raise ValueError(f"ci snapshot not found for repo {repo.repo_key}")
    return ResolvedSource(
        snapshot,
        "snapshot_path",
        _safe_snapshot_locator(repo.snapshot_path),
    )

if repo.path_env:
    raw = os.environ.get(repo.path_env)
    if raw and (path := _existing_directory(Path(raw))) is not None:
        return ResolvedSource(path, "path_env", repo.path_env)
if repo.repo_dir_name and (root := os.environ.get("CST_SMOKE_REPOS_DIR")):
    if (path := _existing_directory(Path(root) / repo.repo_dir_name)) is not None:
        return ResolvedSource(path, "smoke_root", repo.repo_dir_name)
if repo.snapshot_path:
    if (path := _existing_directory(_resolve_snapshot_path(fixture_path, repo.snapshot_path))) is not None:
        return ResolvedSource(
            path,
            "snapshot_path",
            _safe_snapshot_locator(repo.snapshot_path),
        )
return None
```

Before resolving a repo, select only cases with no case profiles or the active profile:

```python
selected_cases = tuple(
    case for case in repo.queries if not case.profiles or profile in case.profiles
)
if profile not in repo.profiles or not selected_cases:
    continue
```

Replace `_case_records_for_repo()` with:

```python
def _case_records_for_cases(
    repo_key: str,
    selected_cases: tuple[QualityCase, ...],
    status: str,
    reason: str,
) -> list[dict[str, Any]]:
    return [
        _empty_case_record(repo_key, case, status, reason)
        for case in selected_cases
    ]
```

Use this helper for non-CI source skips and repository setup errors. Iterate
`selected_cases` in the query loop. Use `source.path` for copying and querying,
but pass the safe type and locator into report construction.

- [ ] **Step 7: Run the runner and case suites**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_runner.py \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/context_search_tool/quality/runner.py \
  tests/test_quality_runner.py
git commit -m "feat: apply quality profile configurations"
```

## Task 6: Emit Report Schema V2, Counters, And Planner Diagnostics

**Files:**
- Modify: `src/context_search_tool/quality/runner.py`
- Modify: `tests/test_quality_runner.py`
- Modify: `tests/test_quality_aggregate.py`

- [ ] **Step 1: Add failing report-v2 and privacy tests**

Append to `tests/test_quality_runner.py`:

```python
def test_report_v2_records_effective_config_safe_source_and_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    monkeypatch.setenv("CST_SAMPLE_REPO", str(source))
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "planner": {
                    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                    "query_planner": {"enabled": True, "timeout_seconds": 30},
                }
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "path_env": "CST_SAMPLE_REPO",
                    "profiles": ["planner"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    plan = QueryPlan(
        original_query="targetToken",
        rewritten_queries=["target helper"],
        grep_keywords=["helper"],
        symbol_hints=["TargetHelper"],
        status="ok",
        provider="ollama",
        model="qwen3.5:4b-mlx",
        prompt_version="v2",
        prompt_hash="sha256:prompt",
        latency_ms=4,
        repo_profile_hash="sha256:profile",
        discarded_hints=["RestTemplate"],
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        lambda *args, **kwargs: QueryBundle(
            query="targetToken",
            expanded_tokens=["target", "token", "helper"],
            results=[],
            followup_keywords=[],
            planner=plan,
        ),
    )

    report = run_quality_fixture(fixture, "planner", None, None)

    assert report["schema_version"] == 2
    repo = report["repos"][0]
    assert set(repo["config"]) == {
        "config_hash", "index", "retrieval", "embedding", "query_planner"
    }
    assert repo["source"]["type"] == "path_env"
    assert repo["source"]["locator"] == "CST_SAMPLE_REPO"
    assert str(source) not in json.dumps(report)
    assert repo["workspace"] == {"copied": True, "preserved": False}
    assert report["cases"][0]["expanded_tokens"] == ["target", "token", "helper"]
    assert report["cases"][0]["planner"] == {
        "status": "ok",
        "rewritten_queries": ["target helper"],
        "grep_keywords": ["helper"],
        "symbol_hints": ["TargetHelper"],
        "discarded_hints": ["RestTemplate"],
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "prompt_version": "v2",
        "prompt_hash": "sha256:prompt",
        "latency_ms": 4,
        "repo_profile_hash": "sha256:profile",
        "repo_profile_truncated": False,
    }


def test_report_redacts_source_and_workspace_paths_from_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    monkeypatch.setenv("CST_SAMPLE_REPO", str(source))
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "smoke": {
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
                    "path_env": "CST_SAMPLE_REPO",
                    "profiles": ["smoke"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )

    def fail_query(repo: Path, query: str, config: ToolConfig) -> QueryBundle:
        raise RuntimeError(f"source={source} workspace={repo}")

    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fail_query,
    )

    report = run_quality_fixture(
        fixture,
        "smoke",
        None,
        None,
        allow_empty=True,
    )

    rendered = json.dumps(report)
    assert str(source) not in rendered
    assert "/cst-quality-" not in rendered
    assert report["cases"][0]["failures"] == [
        "source=<source> workspace=<workspace>"
    ]
```

Import `json`, `QueryPlan` from `context_search_tool.models`, and `QueryBundle`
from `context_search_tool.retrieval`.

- [ ] **Step 2: Add failing counter outcome tests**

Append the complete dependency-free setup/query outcome test:

```python
def test_runner_counters_distinguish_setup_and_query_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_source = _write_source_repo(tmp_path / "index")
    query_source = _write_source_repo(tmp_path / "query")
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "smoke": {
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
                    "repo_key": "missing",
                    "snapshot_path": str(tmp_path / "missing"),
                    "profiles": ["smoke"],
                    "queries": [{"id": "skipped", "query": "q"}],
                },
                {
                    "repo_key": "index-error",
                    "snapshot_path": str(index_source),
                    "profiles": ["smoke"],
                    "queries": [{"id": "setup", "query": "q"}],
                },
                {
                    "repo_key": "query",
                    "snapshot_path": str(query_source),
                    "profiles": ["smoke"],
                    "queries": [
                        {"id": "passes", "query": "ok"},
                        {"id": "errors", "query": "explode"},
                    ],
                },
            ],
        },
    )

    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        if repo.name == "index-error":
            raise RuntimeError("index exploded")
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    def fake_query(repo: Path, query: str, config: ToolConfig) -> QueryBundle:
        if query == "explode":
            raise RuntimeError("query exploded")
        return QueryBundle(
            query=query,
            expanded_tokens=[query],
            results=[],
            followup_keywords=[],
        )

    monkeypatch.setattr("context_search_tool.quality.runner.index_repository", fake_index)
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="sha256:test"),
    )
    monkeypatch.setattr("context_search_tool.quality.runner.query_repository", fake_query)

    report = run_quality_fixture(fixture, "smoke", None, None)

    aggregate = report["aggregate"]
    assert aggregate["selected"] == 4
    assert aggregate["attempted"] == 2
    assert aggregate["executed"] == 1
    assert aggregate["errors"] == 2
    assert aggregate["skipped"] == 1
    assert aggregate["selected"] == (
        aggregate["executed"] + aggregate["errors"] + aggregate["skipped"]
    )
    assert [(case["status"], case["attempted"]) for case in report["cases"]] == [
        ("skipped", False),
        ("error", False),
        ("pass", True),
        ("error", True),
    ]
    repo_records = {repo["repo_key"]: repo for repo in report["repos"]}
    assert set(repo_records) == {"index-error", "query"}
    assert repo_records["index-error"]["config"]["embedding"]["provider"] == "hash"
    assert repo_records["index-error"]["index"] == {"status": "error"}
```

- [ ] **Step 3: Add failing empty-run and output-parent tests**

```python
def test_runner_rejects_zero_selected_or_executed_without_allow_empty(
    tmp_path: Path,
) -> None:
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "smoke": {
                    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
                    "query_planner": {"enabled": False},
                }
            },
            "repos": [
                {
                    "repo_key": "missing",
                    "repo_dir_name": "missing",
                    "profiles": ["smoke"],
                    "queries": [{"id": "q", "query": "q"}],
                }
            ],
        },
    )
    output = tmp_path / "nested" / "reports" / "quality.json"

    with pytest.raises(ValueError, match="no cases executed"):
        run_quality_fixture(fixture, "smoke", output, None)

    assert output.exists()
    report = run_quality_fixture(fixture, "smoke", output, None, allow_empty=True)
    assert report["aggregate"]["executed"] == 0

    zero_selected = _write_fixture(
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
                    "repo_key": "ci-only",
                    "snapshot_path": str(tmp_path / "unused"),
                    "profiles": ["ci"],
                    "queries": [{"id": "q", "query": "q"}],
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="no cases selected"):
        run_quality_fixture(
            zero_selected,
            "smoke",
            None,
            None,
            allow_empty=True,
        )
```

When this default changes, update the pre-existing
`test_quality_runner_records_skip_for_missing_repo` call to pass
`allow_empty=True`; its purpose is still to inspect the explicit skip record,
not to assert CLI run validity.

- [ ] **Step 4: Run new runner tests and verify failure**

```bash
conda run -n base python -m pytest \
  tests/test_quality_runner.py::test_report_v2_records_effective_config_safe_source_and_planner \
  tests/test_quality_runner.py::test_report_redacts_source_and_workspace_paths_from_errors \
  tests/test_quality_runner.py::test_runner_counters_distinguish_setup_and_query_outcomes \
  tests/test_quality_runner.py::test_runner_rejects_zero_selected_or_executed_without_allow_empty \
  -q
```

Expected: FAIL because reports are schema v1 and lack attempted/planner/safe config data.

- [ ] **Step 5: Add safe planner and case payloads**

Import `QueryPlan` from `context_search_tool.models` and `QueryBundle` alongside
`query_repository` from `context_search_tool.retrieval`. Add:

```python
def _planner_payload(plan: QueryPlan) -> dict[str, Any]:
    return {
        "status": plan.status,
        "rewritten_queries": list(plan.rewritten_queries),
        "grep_keywords": list(plan.grep_keywords),
        "symbol_hints": list(plan.symbol_hints),
        "discarded_hints": list(plan.discarded_hints),
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "latency_ms": plan.latency_ms,
        "repo_profile_hash": plan.repo_profile_hash,
        "repo_profile_truncated": plan.repo_profile_truncated,
    }


def _safe_error(exc: Exception, source: Path, workspace: Path) -> str:
    message = str(exc)
    for path, replacement in (
        (workspace, "<workspace>"),
        (source, "<source>"),
    ):
        message = message.replace(str(path), replacement)
    return message
```

Change `_case_record()` to accept `bundle: QueryBundle` and add these exact safe
fields to its existing payload:

```python
"attempted": True,
"known_gap_reason": case.known_gap_reason,
"expanded_tokens": list(bundle.expanded_tokens),
"planner": _planner_payload(bundle.planner),
**(
    {
        "legacy": {
            "fixture": case.legacy.fixture,
            "key": case.legacy.key,
        }
    }
    if case.legacy is not None
    else {}
),
```

Pass `bundle` from the successful query loop. Change `_empty_case_record()` to
accept `attempted: bool = False` and add:

```python
"attempted": attempted,
"known_gap_reason": case.known_gap_reason,
"expanded_tokens": [],
**(
    {
        "legacy": {
            "fixture": case.legacy.fixture,
            "key": case.legacy.key,
        }
    }
    if case.legacy is not None
    else {}
),
```

Change `_error_case_record()` to call it with `attempted=True`. Pass
`_safe_error(exc, source.path, workspace)` to both repository-setup and query
error records. Repository
copy/index errors and source skips use the default `False`. Do not emit a fake
planner payload for a query that never returned a bundle.

- [ ] **Step 6: Emit effective config and safe source metadata**

Use `asdict(repo_config)` for the four config sections and the existing
`_config_hash(repo_config)`. As soon as a source resolves, append this record so
an index failure still reports the effective configuration:

```python
workspace = temp_root / repo.repo_key
repo_record = {
    "repo_key": repo.repo_key,
    "source": {
        "type": source.source_type,
        "locator": source.locator,
        "git_commit": _git_commit(source.path),
        "content_hash": _content_identity(source.path),
    },
    "workspace": {
        "copied": False,
        "preserved": keep_workspace,
        **({"path": str(workspace)} if keep_workspace else {}),
    },
    "config": {
        "config_hash": _config_hash(repo_config),
        "index": asdict(repo_config.index),
        "retrieval": asdict(repo_config.retrieval),
        "embedding": asdict(repo_config.embedding),
        "query_planner": asdict(repo_config.query_planner),
    },
    "index": {"status": "pending"},
}
repos.append(repo_record)
```

Set report schema output to 2. Keep fixture schema at 1; Task 7 advances
comparison output to schema 2.

Build the top-level backward-compatible config from the selected profile rather
than the caller's possibly stale base config:

```python
selected_config = _effective_config(
    DEFAULT_CONFIG,
    {},
    fixture.profile_configs[profile],
)
```

Pass `selected_config` to `_report()` so top-level `config` and `planner` describe
the selected profile; repository records remain authoritative for each actual
effective configuration.

Use this repository-setup block:

```python
try:
    _copy_source_repo(source.path, workspace)
    repo_record["workspace"]["copied"] = True
    summary = index_repository(workspace, repo_config)
    manifest = load_manifest(workspace)
except Exception as exc:
    repo_record["index"] = {"status": "error"}
    cases.extend(
        _case_records_for_cases(
            repo.repo_key,
            selected_cases,
            "error",
            _safe_error(exc, source.path, workspace),
        )
    )
    continue

repo_record["index"] = {
    "status": "ok",
    "manifest_schema_version": manifest.schema_version,
    "embedding_config_hash": manifest.embedding_config_hash,
    "config_hash": _config_hash(repo_config),
    "files_indexed": summary.files_indexed,
    "chunks_indexed": summary.chunks_indexed,
}
```

Repository setup records get `attempted=False`. Iterate
`selected_cases`—not `repo.queries`—for skips, setup errors, and queries.

- [ ] **Step 7: Integrate typed aggregation and run-count validation**

Import `aggregate_cases` and replace `_aggregate(cases)` with:

```python
"aggregate": aggregate_cases(cases, repos, profile),
```

Create parent directories before writing:

```python
def _ensure_parent(path: Path | None) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
```

Call `_ensure_parent(output_path)` and `_ensure_parent(markdown_path)` before
either write. Both requested artifacts must exist even when the post-write empty
run validation raises.

Add `allow_empty: bool = False` to `run_quality_fixture()`. Write requested reports first, then validate:

```python
aggregate = report["aggregate"]
if aggregate["selected"] == 0:
    raise ValueError("no cases selected for quality profile")
if aggregate["executed"] == 0 and not allow_empty:
    raise ValueError("no cases executed for quality profile")
```

- [ ] **Step 8: Run focused quality tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_aggregate.py \
  tests/test_quality_runner.py \
  tests/test_quality_reports.py \
  -q
```

Expected: PASS after updating existing schema-version and report-shape assertions to v2.

- [ ] **Step 9: Commit Task 6**

```bash
git add src/context_search_tool/quality/runner.py \
  tests/test_quality_runner.py \
  tests/test_quality_aggregate.py \
  tests/test_quality_reports.py
git commit -m "feat: emit quality report schema v2"
```

## Task 7: Rewrite Comparison As A Gate-Aware V2 Contract

**Files:**
- Modify: `src/context_search_tool/quality/compare.py`
- Modify: `tests/test_quality_compare.py`

- [ ] **Step 1: Update test helpers to carry gates and schema v2**

Add `import pytest` at the top of `tests/test_quality_compare.py`.

Change `_case()` in `tests/test_quality_compare.py` to:

```python
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
```

Make `_report()` default to schema v2 and include a minimal `aggregate.metrics` tree:

```python
"aggregate": {
    "metrics": {
        "overall": {},
        "by_repository": {},
        "by_tag": {},
        "by_profile": {},
        "by_embedding": {},
    }
},
```

Update the pre-existing false-to-true Hit@5 test to use `pass -> pass`; the
approved status matrix fixes `fail -> fail` as `unchanged_fail`, and protected
metric thresholds are evaluated only for `pass -> pass`. Update the removed
case expectation from `removed_case` to `removed_required` because v1 cases
default to `gate: required`.

- [ ] **Step 2: Add the complete required gate/status matrix test**

Append:

```python
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
```

- [ ] **Step 3: Add gate-change and removal tests**

```python
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
```

- [ ] **Step 4: Add protected and observational metric tests**

```python
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
```

- [ ] **Step 5: Add report validation and grouped-delta tests**

```python
def test_compare_rejects_duplicate_case_keys_and_unsupported_schema() -> None:
    duplicate = _report(
        [_case("sample", "same", "pass"), _case("sample", "same", "pass")]
    )
    with pytest.raises(ValueError, match="duplicate case key"):
        compare_reports(duplicate, _report([]))
    with pytest.raises(ValueError, match="unsupported report schema"):
        compare_reports(_report([], schema_version=3), _report([]))


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
```

- [ ] **Step 6: Run comparison tests and verify failure**

```bash
conda run -n base python -m pytest tests/test_quality_compare.py -q
```

Expected: FAIL against the current status-only schema-v1 comparison.

- [ ] **Step 7: Implement validation, deltas, and metric directions**

Replace `compare.py` constants with:

```python
_SUPPORTED_SCHEMAS = {1, 2}
_HIGHER_IS_BETTER = {
    "hit_at_1", "hit_at_3", "hit_at_5", "hit_at_10",
    "recall_at_5", "recall_at_10", "mrr",
    "cross_language_success", "preferred_rank_pass",
}
_LOWER_IS_BETTER_PREFIXES = ("noise_top",)
_LOWER_IS_BETTER = {"entrypoint_rank"}
_NEUTRAL = {"latency_ms", "result_count", "top_score"}
_TOLERANCE = 1e-12
```

Treat names beginning `precision_at_` and `expected_coverage_` as higher-is-better. Add:

```python
def _index_cases(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = report.get("schema_version")
    if schema not in _SUPPORTED_SCHEMAS:
        raise ValueError(f"unsupported report schema: {schema}")
    indexed: dict[str, dict[str, Any]] = {}
    for case in report.get("cases", []):
        key = _case_key(case)
        if key in indexed:
            raise ValueError(f"duplicate case key: {key}")
        if case.get("status") == "pass" and not isinstance(case.get("metrics"), dict):
            raise ValueError(f"pass case missing metrics: {key}")
        indexed[key] = case
    return indexed


def _flatten_case_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        name: value for name, value in metrics.items() if not isinstance(value, dict)
    }
    coverage = metrics.get("expected_coverage_top5")
    if isinstance(coverage, dict):
        flattened["expected_coverage_top5_ratio"] = coverage.get("ratio")
    return flattened


def _scalar_metric_deltas(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, float | bool]]:
    baseline = _flatten_case_metrics(baseline)
    candidate = _flatten_case_metrics(candidate)
    deltas: dict[str, dict[str, float | bool]] = {}
    for name in sorted(set(baseline) & set(candidate)):
        before = baseline[name]
        after = candidate[name]
        if isinstance(before, bool) and isinstance(after, bool):
            deltas[name] = {
                "baseline": before,
                "candidate": after,
                "delta": int(after) - int(before),
            }
        elif (
            isinstance(before, (int, float))
            and not isinstance(before, bool)
            and isinstance(after, (int, float))
            and not isinstance(after, bool)
        ):
            deltas[name] = {
                "baseline": before,
                "candidate": after,
                "delta": after - before,
            }
    return deltas
```

Implement metric direction and protected-threshold helpers exactly as follows:

```python
def _direction(name: str, delta: float) -> str:
    if abs(delta) <= _TOLERANCE or name in _NEUTRAL:
        return "tie"
    higher_is_better = (
        name in _HIGHER_IS_BETTER
        or name.startswith("precision_at_")
        or name.startswith("expected_coverage_")
    )
    lower_is_better = (
        name in _LOWER_IS_BETTER
        or name.startswith(_LOWER_IS_BETTER_PREFIXES)
    )
    if higher_is_better:
        return "improvement" if delta > 0 else "decline"
    if lower_is_better:
        return "decline" if delta > 0 else "improvement"
    return "neutral"


def _bool_transition(
    deltas: dict[str, dict[str, Any]],
    name: str,
    before: bool,
    after: bool,
) -> bool:
    item = deltas.get(name, {})
    return item.get("baseline") is before and item.get("candidate") is after


def _numeric_gain(deltas: dict[str, dict[str, Any]], name: str) -> float:
    delta = deltas.get(name, {}).get("delta")
    return max(float(delta), 0.0) if isinstance(delta, int | float) else 0.0


def _numeric_drop(deltas: dict[str, dict[str, Any]], name: str) -> float:
    delta = deltas.get(name, {}).get("delta")
    return max(-float(delta), 0.0) if isinstance(delta, int | float) else 0.0
```

- [ ] **Step 8: Implement classification precedence**

Use this exact order inside `_compare_case()`, passing `case_key` through every
payload call:

```python
if baseline is None:
    return _payload(case_key, "new_case", False, baseline, candidate)
if candidate is None:
    required = baseline.get("gate", "required") == "required"
    return _payload(
        case_key,
        "removed_required" if required else "removed_observation",
        required,
        baseline,
        candidate,
    )

baseline_gate = baseline.get("gate", "required")
candidate_gate = candidate.get("gate", "required")
if baseline_gate == "required" and candidate_gate != "required":
    return _payload(case_key, "gate_weakened", True, baseline, candidate)
if baseline_gate != "required" and candidate_gate == "required":
    return _payload(case_key, "gate_strengthened", False, baseline, candidate)
if baseline_gate != candidate_gate:
    return _payload(case_key, "gate_changed_observation", False, baseline, candidate)

metric_deltas = _scalar_metric_deltas(
    baseline.get("metrics", {}),
    candidate.get("metrics", {}),
)
if baseline_gate == "required":
    classification, gating = _classify_required(
        baseline["status"], candidate["status"], metric_deltas
    )
else:
    classification, gating = _classify_observation(
        baseline["status"], candidate["status"], metric_deltas
    )
return _payload(
    case_key,
    classification,
    gating,
    baseline,
    candidate,
    metric_deltas=metric_deltas,
)
```

Implement the required status matrix and `pass/pass` thresholds without fall-through:

```python
_REQUIRED_STATUS_MATRIX = {
    ("pass", "fail"): ("regressed", True),
    ("pass", "error"): ("regressed", True),
    ("pass", "skipped"): ("regressed", True),
    ("fail", "pass"): ("improved", False),
    ("fail", "fail"): ("unchanged_fail", False),
    ("fail", "error"): ("execution_regressed", True),
    ("fail", "skipped"): ("coverage_lost_required", True),
    ("error", "pass"): ("improved", False),
    ("error", "fail"): ("newly_evaluated_failure", False),
    ("error", "error"): ("unchanged_error", False),
    ("error", "skipped"): ("unchanged_unverified", False),
    ("skipped", "pass"): ("newly_verified", False),
    ("skipped", "fail"): ("newly_evaluated_failure", False),
    ("skipped", "error"): ("unchanged_unverified", False),
    ("skipped", "skipped"): ("skipped", False),
}


def _classify_required(
    baseline_status: str,
    candidate_status: str,
    deltas: dict[str, dict[str, Any]],
) -> tuple[str, bool]:
    if baseline_status == candidate_status == "pass":
        decline = (
            _bool_transition(deltas, "hit_at_5", True, False)
            or _numeric_drop(deltas, "mrr") > 0.25
            or _numeric_gain(deltas, "noise_top5") >= 2
        )
        improvement = (
            _bool_transition(deltas, "hit_at_5", False, True)
            or _numeric_gain(deltas, "mrr") > 0.25
            or _numeric_drop(deltas, "noise_top5") >= 2
        )
        if decline:
            return "regressed", True
        if improvement:
            return "improved", False
        return "unchanged_pass", False
    return _REQUIRED_STATUS_MATRIX[(baseline_status, candidate_status)]
```

Implement non-required classification exactly:

```python
def _classify_observation(
    baseline_status: str,
    candidate_status: str,
    deltas: dict[str, dict[str, Any]],
) -> tuple[str, bool]:
    if baseline_status in {"error", "skipped"} or candidate_status in {
        "error",
        "skipped",
    }:
        return "observation_unavailable", False
    directions = {
        _direction(name, float(item["delta"]))
        for name, item in deltas.items()
    }
    if "decline" in directions:
        return "metric_decline", False
    if "improvement" in directions:
        return "metric_improvement", False
    return "unchanged_observation", False


def _payload(
    case_key: str,
    classification: str,
    gating: bool,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *,
    metric_deltas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_key": case_key,
        "classification": classification,
        "gating": gating,
        "baseline_gate": baseline.get("gate", "required") if baseline else None,
        "candidate_gate": candidate.get("gate", "required") if candidate else None,
        "baseline_status": baseline.get("status") if baseline else None,
        "candidate_status": candidate.get("status") if candidate else None,
        "metric_deltas": metric_deltas or {},
        "warnings": _case_warnings(baseline, candidate),
    }
```

Validate status values against `{"pass", "fail", "known_gap", "informational",
"error", "skipped"}` and gate values against `{"required", "known_gap",
"informational"}` while indexing. A required case may use only `pass`, `fail`,
`error`, or `skipped`; reject a required `known_gap`/`informational` status as an
invalid report. Raise `ValueError` with the case key for an unknown or
inconsistent value instead of reaching a matrix `KeyError`.

- [ ] **Step 9: Emit case and grouped metric deltas**

Use `_payload()` above for case output. Recursively compare matching `mean`,
`rate`, `p50`, and `p95` leaves under `report["aggregate"]["metrics"]`. A metric
with only `mean` or only `rate` collapses to one `{baseline, candidate, delta}`
payload (so `overall.mrr.delta` and `overall.hit_at_5.delta` are direct); latency
retains separate `mean`, `p50`, and `p95` payloads. Preserve the surrounding
`overall`, repository, tag, profile, and embedding grouping tree.

Use this leaf helper from the recursive walker:

```python
def _delta_payload(before: Any, after: Any) -> dict[str, float] | None:
    if (
        isinstance(before, int | float)
        and not isinstance(before, bool)
        and isinstance(after, int | float)
        and not isinstance(after, bool)
    ):
        return {
            "baseline": float(before),
            "candidate": float(after),
            "delta": float(after) - float(before),
        }
    return None


def _aggregate_metric_deltas(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in sorted(set(baseline) & set(candidate)):
        before = baseline[key]
        after = candidate[key]
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        leaves = {
            field: payload
            for field in ("rate", "mean", "p50", "p95")
            if (
                payload := _delta_payload(before.get(field), after.get(field))
            ) is not None
        }
        if set(leaves) in ({"rate"}, {"mean"}):
            output[key] = next(iter(leaves.values()))
            continue
        if leaves:
            output[key] = leaves
            continue
        nested = _aggregate_metric_deltas(before, after)
        if nested:
            output[key] = nested
    return output
```

Call it with the two `report.get("aggregate", {}).get("metrics", {})` trees and
store the result under top-level `metric_deltas`.

Retain existing fixture/profile/top-level warnings and compare v2 repository
effective configuration with:

```python
def _repo_config_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("config", {}).get("config_hash")
        for repo in report.get("repos", [])
    }
```

Append `"repo effective config differs"` when those identities differ. Keep
repository content identity as a separate warning.

Aggregate classifications into:

```python
counts = Counter(case["classification"] for case in cases)
aggregate = {
    "total": len(cases),
    "gating_regressions": sum(case["gating"] for case in cases),
    "improvements": sum(
        counts[name]
        for name in ("improved", "newly_verified", "metric_improvement")
    ),
    "observed_declines": counts["metric_decline"],
    "removed_required": counts["removed_required"],
    **{name: counts[name] for name in sorted(counts)},
}
```

Import `Counter` from `collections`. Emit comparison `schema_version: 2`, the
aggregate above, `metric_deltas`, metadata warnings, and sorted cases. Update
pre-existing aggregate assertions to `gating_regressions`, `improvements`, or
the new exact classification key as appropriate.

- [ ] **Step 10: Run comparison tests**

```bash
conda run -n base python -m pytest tests/test_quality_compare.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit Task 7**

```bash
git add src/context_search_tool/quality/compare.py tests/test_quality_compare.py
git commit -m "feat: make quality comparison gate aware"
```

## Task 8: Update Markdown And CLI Gates

**Files:**
- Modify: `src/context_search_tool/quality/reports.py`
- Modify: `src/context_search_tool/quality/__main__.py`
- Modify: `tests/test_quality_reports.py`
- Modify: `tests/test_quality_cli.py`

- [ ] **Step 1: Add failing Markdown-v2 tests**

Update report fixtures in `tests/test_quality_reports.py` to include `selected`, `attempted`, `executed`, `informational`, and `metrics`. Add:

```python
def test_markdown_report_renders_metrics_and_reason_only_known_gaps() -> None:
    report = {
        "profile": "ci",
        "aggregate": {
            "selected": 2,
            "attempted": 2,
            "executed": 2,
            "passed": 2,
            "failed": 0,
            "skipped": 0,
            "known_gaps": 0,
            "informational": 0,
            "errors": 0,
            "metrics": {
                "overall": {
                    "mrr": {"count": 2, "mean": 0.75},
                    "hit_at_5": {"successes": 2, "total": 2, "rate": 1.0},
                }
            },
        },
        "cases": [
            {
                "repo_key": "sample",
                "case_id": "gap-reason",
                "status": "pass",
                "known_gap_reason": "service chain is incomplete",
                "failures": [],
            }
        ],
    }

    markdown = render_markdown_report(report)

    assert "| executed | 2 |" in markdown
    assert "| mrr.mean | 0.75 |" in markdown
    assert "| hit_at_5.rate | 1.0 |" in markdown
    assert "### sample/gap-reason" in markdown
    assert "service chain is incomplete" in markdown
```

Append the exact comparison-section ordering test:

```python
def test_markdown_comparison_orders_gates_declines_deltas_and_warnings() -> None:
    comparison = {
        "aggregate": {
            "total": 2,
            "gating_regressions": 1,
            "improvements": 0,
            "observed_declines": 1,
            "removed_required": 0,
        },
        "cases": [
            {
                "case_key": "sample/weakened",
                "classification": "gate_weakened",
                "gating": True,
                "baseline_status": "pass",
                "candidate_status": "informational",
                "metric_deltas": {},
                "warnings": [],
            },
            {
                "case_key": "sample/observation",
                "classification": "metric_decline",
                "gating": False,
                "baseline_status": "informational",
                "candidate_status": "informational",
                "metric_deltas": {
                    "noise_top12": {"baseline": 1, "candidate": 2, "delta": 1}
                },
                "warnings": [],
            },
        ],
        "metric_deltas": {
            "overall": {
                "mrr": {"baseline": 0.5, "candidate": 0.4, "delta": -0.1}
            }
        },
        "metadata_warnings": ["fixture sha256 differs"],
    }

    markdown = render_markdown_comparison(comparison)

    headings = [
        "## Gating Regressions",
        "## Observed Declines",
        "## Metric Deltas",
        "## Metadata Warnings",
    ]
    assert all(heading in markdown for heading in headings)
    assert [markdown.index(heading) for heading in headings] == sorted(
        markdown.index(heading) for heading in headings
    )
    assert "### sample/weakened" in markdown
    assert "### sample/observation" in markdown
    assert "overall.mrr" in markdown
```

- [ ] **Step 2: Add failing CLI exit and parent-directory tests**

Append to `tests/test_quality_cli.py`:

```python
def test_compare_cli_fails_on_gating_regression_unless_allowed(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps(_minimal_report([_case("target", "pass")])))
    candidate.write_text(json.dumps(_minimal_report([_case("target", "fail")])))
    output = tmp_path / "nested" / "comparison" / "report.json"
    runner = CliRunner()

    failed = runner.invoke(
        app,
        [
            "quality", "compare",
            "--baseline", str(baseline),
            "--candidate", str(candidate),
            "--output", str(output),
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "quality", "compare",
            "--baseline", str(baseline),
            "--candidate", str(candidate),
            "--output", str(output),
            "--allow-regressions",
        ],
    )

    assert failed.exit_code == 1
    assert output.exists()
    assert allowed.exit_code == 0


def test_feedback_cli_creates_nested_output_parent(tmp_path: Path) -> None:
    log = tmp_path / "mcp_calls.jsonl"
    log.write_text('{"ok": true, "result_count": 1}\n', encoding="utf-8")
    output = tmp_path / "nested" / "feedback" / "summary.json"

    result = CliRunner().invoke(
        app,
        ["quality", "feedback", str(log), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.exists()


def test_run_cli_rejects_all_skipped_unless_allowed(tmp_path: Path) -> None:
    fixture = tmp_path / "all-skipped.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_configs": {
                    "smoke": {
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
                        "repo_key": "missing",
                        "repo_dir_name": "missing",
                        "profiles": ["smoke"],
                        "queries": [{"id": "q", "query": "q"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "nested" / "run" / "report.json"
    runner = CliRunner()

    failed = runner.invoke(
        app,
        ["quality", "run", str(fixture), "--profile", "smoke", "--output", str(output)],
    )
    allowed = runner.invoke(
        app,
        [
            "quality", "run", str(fixture), "--profile", "smoke",
            "--output", str(output), "--allow-empty",
        ],
    )

    assert failed.exit_code == 1
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["aggregate"]["executed"] == 0
    assert allowed.exit_code == 0
```

- [ ] **Step 3: Run focused tests and verify failure**

```bash
conda run -n base python -m pytest \
  tests/test_quality_reports.py \
  tests/test_quality_cli.py \
  -q
```

Expected: FAIL because v2 sections and CLI gates are absent.

- [ ] **Step 4: Render v2 report and comparison Markdown**

Update `_REPORT_SUMMARY_KEYS` to:

```python
(
    "selected", "attempted", "executed", "passed", "failed",
    "skipped", "known_gaps", "informational", "errors",
)
```

Add these two report helpers:

```python
def _flatten_metric_values(
    node: dict[str, Any],
    prefix: str = "",
) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key in sorted(node):
        value = node[key]
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(_flatten_metric_values(value, name))
        elif key in {"mean", "rate", "p50", "p95"}:
            rows.append((name, value))
    return rows


def _known_gap_lines(case: dict[str, Any]) -> list[str]:
    lines = [f"### {_case_key(case)}"]
    reason = case.get("known_gap_reason", "")
    if reason:
        lines.append(f"- {reason}")
    lines.extend(f"- {failure}" for failure in case.get("failures", []))
    if len(lines) == 1:
        lines.append("- No known-gap reason supplied.")
    lines.append("")
    return lines
```

Render rows from
`_flatten_metric_values(report["aggregate"]["metrics"]["overall"])` under a
`## Metrics` table. Select known-gap sections with:

```python
known_gaps = [
    case
    for case in report.get("cases", [])
    if case.get("known_gap_reason") or case.get("status") == "known_gap"
]
```

For comparison Markdown, use these exact section predicates:

```python
gating = [case for case in cases if case.get("gating")]
observed = [case for case in cases if case.get("classification") == "metric_decline"]
```

Render aggregate metric deltas recursively and keep metadata warnings last.

Use this exact delta flattener for both case and aggregate delta payloads:

```python
def _flatten_deltas(
    node: dict[str, Any],
    prefix: str = "",
) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    if set(node) >= {"baseline", "candidate", "delta"}:
        return [(prefix, node)]
    for key in sorted(node):
        value = node[key]
        if isinstance(value, dict):
            name = f"{prefix}.{key}" if prefix else key
            rows.extend(_flatten_deltas(value, name))
    return rows
```

Build comparison output sections in this literal order: summary, Gating
Regressions, Observed Declines, Metric Deltas, Metadata Warnings. For every
delta row, render `name`, baseline, candidate, and signed delta in a Markdown
table. Preserve the existing final newline contract.

- [ ] **Step 5: Implement CLI v2 behavior**

Add to `run`:

```python
allow_empty: bool = typer.Option(False, "--allow-empty")
```

Pass it into `run_quality_fixture()`. Print selected/executed/passed/failed/errors and exit 1 for failed required cases or errors.

Use this exact post-run block:

```python
aggregate = report.get("aggregate", {})
typer.echo(
    "selected={selected} executed={executed} passed={passed} "
    "failed={failed} errors={errors}".format(
        selected=aggregate.get("selected", 0),
        executed=aggregate.get("executed", 0),
        passed=aggregate.get("passed", 0),
        failed=aggregate.get("failed", 0),
        errors=aggregate.get("errors", 0),
    )
)
if aggregate.get("failed", 0) > 0 or aggregate.get("errors", 0) > 0:
    raise typer.Exit(code=1)
```

Add to `compare`:

```python
allow_regressions: bool = typer.Option(False, "--allow-regressions")
```

Add once in `quality/__main__.py`:

```python
def _ensure_parent(path: Path | None) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
```

Before comparison writes, call `_ensure_parent(output)` and
`_ensure_parent(markdown)`. Use this exact post-write behavior:

```python
aggregate = comparison.get("aggregate", {})
typer.echo(
    "gating_regressions={gating} improvements={improvements} "
    "observed_declines={declines}".format(
        gating=aggregate.get("gating_regressions", 0),
        improvements=aggregate.get("improvements", 0),
        declines=aggregate.get("observed_declines", 0),
    )
)
if aggregate.get("gating_regressions", 0) > 0 and not allow_regressions:
    raise typer.Exit(code=1)
```

Call `_ensure_parent(output)` in `feedback()` before `write_text()`.

Update the pre-existing `test_quality_compare_cli_writes_comparison` invocation
to include `--allow-regressions`, assert comparison schema 2, and replace its two
exact case payloads with:

```python
assert comparison["cases"] == [
    {
        "case_key": "sample/recovered",
        "classification": "improved",
        "gating": False,
        "baseline_gate": "required",
        "candidate_gate": "required",
        "baseline_status": "fail",
        "candidate_status": "pass",
        "metric_deltas": {},
        "warnings": [],
    },
    {
        "case_key": "sample/目标",
        "classification": "regressed",
        "gating": True,
        "baseline_gate": "required",
        "candidate_gate": "required",
        "baseline_status": "pass",
        "candidate_status": "fail",
        "metric_deltas": {},
        "warnings": [],
    },
]
assert comparison["aggregate"]["gating_regressions"] == 1
assert comparison["aggregate"]["improvements"] == 1
```

- [ ] **Step 6: Run all quality UI tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_reports.py \
  tests/test_quality_cli.py \
  tests/test_quality_feedback.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 8**

```bash
git add src/context_search_tool/quality/reports.py \
  src/context_search_tool/quality/__main__.py \
  tests/test_quality_reports.py \
  tests/test_quality_cli.py
git commit -m "feat: gate quality CLI regressions"
```

## Task 9: Build The Canonical Catalog And Snapshot Fixtures

**Files:**
- Create: `tests/test_quality_catalog.py`
- Create: `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/DashboardController.java`
- Create: `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/StatisticsService.java`
- Create: `tests/fixtures/real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/ChartService.java`
- Create: `tests/fixtures/real_projects/embedding_ab/src/access/WhitelistValidation.java`
- Create: `tests/fixtures/real_projects/embedding_ab/src/access/BlacklistManager.java`
- Create: `tests/fixtures/real_projects/embedding_ab/src/order/OrderService.java`
- Create: `tests/fixtures/real_projects/embedding_ab/src/noise/RegionService.java`
- Create: `tests/fixtures/real_projects/embedding_ab/src/noise/RoleAnnouncement.java`
- Modify: `tests/fixtures/retrieval_quality/queries.json`
- Keep during this task: all three legacy query JSON files

- [ ] **Step 1: Create deterministic English-only and A/B source snapshots**

Create the dashboard files with exactly this English-only content:

```java
// DashboardController.java
package com.example.dashboard;

public final class DashboardController {
    private final StatisticsService statisticsService;

    public DashboardController(StatisticsService statisticsService) {
        this.statisticsService = statisticsService;
    }

    public String dashboard() {
        return statisticsService.statistics();
    }
}
```

```java
// StatisticsService.java
package com.example.dashboard;

public final class StatisticsService {
    private final ChartService chartService = new ChartService();

    public String statistics() {
        return chartService.chartData();
    }
}
```

```java
// ChartService.java
package com.example.dashboard;

public final class ChartService {
    public String chartData() {
        return "dashboard statistics chart";
    }
}
```

Create the A/B files:

```java
// WhitelistValidation.java
package access;

public final class WhitelistValidation {
    public boolean validateAccess(String subject) {
        return subject != null && !subject.isBlank();
    }
}
```

```java
// BlacklistManager.java
package access;

public final class BlacklistManager {
    public void add(String subject) {}
    public void remove(String subject) {}
    public boolean manage(String subject) { return subject != null; }
}
```

```java
// OrderService.java
package order;

public final class OrderService {
    public void cancel(String orderId) {}
}
```

```java
// RegionService.java
package noise;

public final class RegionService {
    public String region() { return "region"; }
}
```

```java
// RoleAnnouncement.java
package noise;

public final class RoleAnnouncement {
    public String notification() { return "role announcement user notification"; }
}
```

- [ ] **Step 2: Add snapshot-integrity tests**

Create `tests/test_quality_catalog.py` with:

```python
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from context_search_tool.quality.cases import (
    Gate,
    LegacyProvenance,
    QualityCase,
    adapt_legacy_query_case,
    load_quality_fixture,
)


ROOT = Path(__file__).parent
CATALOG_PATH = ROOT / "fixtures" / "retrieval_quality" / "queries.json"
LEGACY_GENERIC = ROOT / "fixtures" / "generic_baseline_quality" / "queries.json"
LEGACY_CALIBRATION = ROOT / "fixtures" / "retrieval_calibration" / "queries.json"
LEGACY_AB = ROOT / "fixtures" / "ab_comparison" / "queries.json"
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _catalog_cases() -> dict[str, QualityCase]:
    fixture = load_quality_fixture(CATALOG_PATH)
    return {
        f"{repo.repo_key}/{case.case_id}": case
        for repo in fixture.repos
        for case in repo.queries
    }


def test_cross_language_dashboard_snapshot_contains_no_cjk() -> None:
    root = ROOT / "fixtures" / "real_projects" / "cross_language_dashboard"
    files = sorted(root.rglob("*.java"))

    assert [path.name for path in files] == [
        "ChartService.java",
        "DashboardController.java",
        "StatisticsService.java",
    ]
    assert all(CJK_RE.search(path.read_text(encoding="utf-8")) is None for path in files)


def test_catalog_profile_registry_and_inventory() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    cases = _catalog_cases()

    assert set(fixture.profile_configs) == {
        "ci", "smoke", "planner", "calibration_bge", "ab_hash", "ab_bge"
    }
    assert len(cases) == 39
    assert "program_tool/qrcode-tool" in cases
    assert "program_tool_snapshot/qrcode-entrypoint" not in cases
    assert cases["cross_language_dashboard/dashboard-cross-language"].tags == (
        "java_spring", "cross_language", "entrypoint"
    )
```

- [ ] **Step 3: Replace the one-case fixture with the profile registry and repository catalog**

Use `apply_patch` to replace `tests/fixtures/retrieval_quality/queries.json`. Add these six exact profile configs:

```json
{
  "ci": {
    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    "query_planner": {"enabled": false}
  },
  "smoke": {
    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    "query_planner": {"enabled": false}
  },
  "planner": {
    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    "query_planner": {
      "enabled": true,
      "provider": "ollama",
      "model": "qwen3.5:4b-mlx",
      "timeout_seconds": 30
    }
  },
  "calibration_bge": {
    "embedding": {"provider": "bge", "model": "bge-m3", "dimensions": 1024},
    "query_planner": {"enabled": false}
  },
  "ab_hash": {
    "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384},
    "query_planner": {"enabled": false}
  },
  "ab_bge": {
    "embedding": {"provider": "bge", "model": "bge-m3", "dimensions": 1024},
    "query_planner": {"enabled": false}
  }
}
```

Add these exact repository definitions and source locators:

| repo key | profiles | path env | repo dir | snapshot |
| --- | --- | --- | --- | --- |
| `imagebed` | `smoke` | `CST_SMOKE_IMAGEBED_REPO` | `imagebed` | none |
| `env_change` | `smoke` | `CST_SMOKE_ENV_CHANGE_REPO` | `env-change` | none |
| `investment_assistant` | `smoke` | `CST_SMOKE_INVESTMENT_ASSISTANT_REPO` | `Investment-Assistant` | none |
| `program_tool` | `ci`, `smoke` | `CST_SMOKE_PROGRAM_TOOL_REPO` | `program-tool` | `tests/fixtures/real_projects/program_tool` |
| `java_spring_mini` | `ci` | none | none | `tests/fixtures/java-spring-mini` |
| `operation_client` | `calibration_bge` | `CST_CALIBRATION_OPERATION_CLIENT_REPO` | `operation-client-api` | none |
| `console_iot` | `calibration_bge` | `CST_CALIBRATION_CONSOLE_IOT_REPO` | `console-iot-api` | none |
| `psf_requests` | `planner` | `CST_PLANNER_REQUESTS_REPO` | `requests` | none |
| `cross_language_dashboard` | `planner` | none | none | `tests/fixtures/real_projects/cross_language_dashboard` |
| `embedding_ab` | `ab_hash`, `ab_bge` | `CST_QUALITY_AB_REPO` | `embedding-ab` | `tests/fixtures/real_projects/embedding_ab` |

- [ ] **Step 4: Migrate all 22 generic cases without changing their assertions**

Copy each query object from `tests/fixtures/generic_baseline_quality/queries.json` into its repository entry. Preserve `id`, `query`, `expected_top_k`, `expected_any_top_k`, `preferred_rank`, `absent_top_k`, `outranks`, and `anchor_expected` exactly. Convert each legacy `forbidden_above` matcher with `max_rank: N` into the same matcher under `absent_top_k` with `top_k: N`; do not retain that item under `forbidden_above`. When present, rename `known_gap` to `known_gap_reason` without changing its string. Add:

```json
"gate": "required",
"legacy": {
  "fixture": "generic_baseline_quality",
  "key": "imagebed/go-upload-handler"
}
```

The JSON above shows the first case. For every case, compute `legacy.key` as
`f"{repo_key}/{raw_case['id']}"`; the parity test below checks all 22 values.

Use this exact tag map, keyed by the unchanged legacy ID:

```python
GENERIC_TAGS = {
    "go-upload-handler": ["generic", "go"],
    "go-auth-middleware": ["generic", "go"],
    "go-storage-implementations": ["generic", "go"],
    "go-delete-handler": ["generic", "go"],
    "go-route-registration": ["generic", "go"],
    "tauri-commands": ["generic", "rust", "typescript"],
    "engine-apply-restore": ["generic", "rust", "typescript"],
    "frontend-invoke": ["generic", "rust", "typescript"],
    "settings-persistence": ["generic", "rust", "typescript"],
    "frontend-auth-store": ["monorepo", "frontend"],
    "collector-handler": ["monorepo", "go"],
    "frontend-sse-composable": ["monorepo", "frontend"],
    "collector-fund-service": ["monorepo", "go"],
    "collector-nav-fetcher": ["monorepo", "go"],
    "collector-scheduler": ["monorepo", "go"],
    "java-ai-sse-controller": ["monorepo", "java_spring"],
    "watermark-remover": ["frontend", "vue", "entrypoint"],
    "mqtt-tool": ["frontend", "vue"],
    "qrcode-tool": ["frontend", "vue", "entrypoint"],
    "json-to-entity": ["frontend", "vue"],
    "app-layout-theme": ["frontend", "vue"],
    "ai-chat": ["frontend", "vue", "entrypoint"],
}
```

For the QR query, use `repo_key: program_tool`, `id: qrcode-tool`, and legacy key `program_tool/qrcode-tool`. Add `role: entrypoint` to its view `preferred_rank`; do not retain `qrcode-entrypoint`.

- [ ] **Step 5: Migrate all eight calibration cases using N-of-M**

Map queries to these IDs in source order:

```python
CALIBRATION_IDS = {
    ("operation_client", "账号密码登录注册"): "operation-client-auth-login-register",
    ("operation_client", "驿站设备列表"): "operation-client-station-device-list",
    ("operation_client", "发布意见反馈 发送短信"): "operation-client-feedback-sms",
    ("console_iot", "设备列表"): "console-iot-equipment-list",
    ("console_iot", "开门控制"): "console-iot-access-control",
    ("console_iot", "IOT设备状态"): "console-iot-device-status",
    ("console_iot", "设备告警"): "console-iot-alarm",
    ("console_iot", "用户登录认证"): "console-iot-user-auth",
}
```

For each source object:

- convert `expected_core` and `expected_top5_min` to one `expected_at_least_top_k` group with `top_k: 5`;
- convert every `required_top3` path to `expected_top_k` with `top_k: 3`;
- convert every `forbidden_top3` path to `absent_top_k` with `top_k: 3`;
- copy `known_gap` to `known_gap_reason` without changing `gate: required`;
- use tags `java_spring`, `chinese_query`;
- set legacy fixture `retrieval_calibration` and compute the key as
  `f"{raw_case['repo_key']}/{case_id}"` using `CALIBRATION_IDS` above.

- [ ] **Step 6: Add three requests cases and the dashboard cross-language case**

Under `psf_requests`, add these exact three cases:

```json
[
  {
    "id": "cookies-between-calls",
    "query": "where does requests keep cookies between multiple calls in a client session",
    "profiles": ["planner"],
    "tags": ["python", "planner", "natural_language"],
    "gate": "required",
    "expected_any_top_k": [
      {
        "matchers": [
          {"path": "src/requests/sessions.py"},
          {"path": "src/requests/cookies.py"}
        ],
        "top_k": 5
      }
    ]
  },
  {
    "id": "retry-proxy-pooling-natural",
    "query": "where are retries proxy connections and connection pools configured for sending requests",
    "profiles": ["planner"],
    "tags": ["python", "planner", "natural_language"],
    "gate": "required",
    "expected_top_k": [
      {"path": "src/requests/adapters.py", "top_k": 5}
    ]
  },
  {
    "id": "stream-response-body-natural",
    "query": "where can response body be streamed in chunks without loading everything",
    "profiles": ["planner"],
    "tags": ["python", "planner", "natural_language"],
    "gate": "required",
    "expected_top_k": [
      {"path": "src/requests/models.py", "top_k": 5}
    ]
  }
]
```

Add:

```json
{
  "id": "dashboard-cross-language",
  "query": "数据看板统计图表功能",
  "profiles": ["planner"],
  "tags": ["java_spring", "cross_language", "entrypoint"],
  "gate": "required",
  "expected_top_k": [
    {"path": "src/main/java/com/example/dashboard/DashboardController.java", "top_k": 5}
  ],
  "expected_any_top_k": [
    {
      "matchers": [
        {"path": "src/main/java/com/example/dashboard/StatisticsService.java"},
        {"path": "src/main/java/com/example/dashboard/ChartService.java"}
      ],
      "top_k": 5
    }
  ],
  "preferred_rank": [
    {
      "path": "src/main/java/com/example/dashboard/DashboardController.java",
      "top_k": 5,
      "max_rank": 3,
      "role": "entrypoint"
    }
  ]
}
```

- [ ] **Step 7: Add Java CI cases and A/B informational cases**

Add two `java_spring_mini` CI cases:

```json
[
  {
    "id": "apply-audit-endpoint",
    "query": "/apply/audit/pageEs INVOLVED_BY_ME",
    "tags": ["java_spring", "exact_identifier", "entrypoint"],
    "gate": "required",
    "expected_top_k": [
      {"path": "src/main/java/com/example/audit/ResourceApplyAuditController.java", "top_k": 3}
    ],
    "preferred_rank": [
      {
        "path": "src/main/java/com/example/audit/ResourceApplyAuditController.java",
        "top_k": 3,
        "max_rank": 3,
        "role": "entrypoint"
      }
    ]
  },
  {
    "id": "workbench-audit-localized-cjk",
    "query": "工作台统计 待我审核",
    "tags": ["java_spring", "localized_cjk", "entrypoint"],
    "gate": "required",
    "expected_top_k": [
      {"path": "src/main/java/com/example/audit/ApplyAuditController.java", "top_k": 3}
    ],
    "preferred_rank": [
      {
        "path": "src/main/java/com/example/audit/ApplyAuditController.java",
        "top_k": 3,
        "max_rank": 3,
        "role": "entrypoint"
      }
    ]
  }
]
```

Convert the three legacy A/B objects in source order into IDs
`embedding-ab-access-validation`, `embedding-ab-whitelist-management`, and
`embedding-ab-order-cancel`. Use both A/B profiles, `gate: informational`,
`metric_k: 12`, case-insensitive `contains` matchers copied from
`expected_relevant` and `expected_noise`, and legacy fixture `ab_comparison`.
Set each key to `f"embedding_ab/{case_id}"`.

- [ ] **Step 8: Add parity tests while legacy files still exist**

Add these helpers and exact parity tests to `tests/test_quality_catalog.py`:

```python
CALIBRATION_IDS = {
    ("operation_client", "账号密码登录注册"): "operation-client-auth-login-register",
    ("operation_client", "驿站设备列表"): "operation-client-station-device-list",
    ("operation_client", "发布意见反馈 发送短信"): "operation-client-feedback-sms",
    ("console_iot", "设备列表"): "console-iot-equipment-list",
    ("console_iot", "开门控制"): "console-iot-access-control",
    ("console_iot", "IOT设备状态"): "console-iot-device-status",
    ("console_iot", "设备告警"): "console-iot-alarm",
    ("console_iot", "用户登录认证"): "console-iot-user-auth",
}

AB_IDS = (
    "embedding-ab-access-validation",
    "embedding-ab-whitelist-management",
    "embedding-ab-order-cancel",
)


def _without_catalog_metadata(case: QualityCase) -> QualityCase:
    return replace(
        case,
        profiles=(),
        tags=(),
        legacy=None,
        preferred_rank=tuple(
            replace(preferred, role="") for preferred in case.preferred_rank
        ),
    )


def test_generic_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_repos = json.loads(LEGACY_GENERIC.read_text(encoding="utf-8"))

    for raw_repo in legacy_repos:
        for raw_case in raw_repo["queries"]:
            key = f"{raw_repo['repo_key']}/{raw_case['id']}"
            assert _without_catalog_metadata(canonical[key]) == adapt_legacy_query_case(
                raw_case
            )


def test_calibration_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_cases = json.loads(LEGACY_CALIBRATION.read_text(encoding="utf-8"))

    for raw_case in legacy_cases:
        case_id = CALIBRATION_IDS[(raw_case["repo_key"], raw_case["query"])]
        key = f"{raw_case['repo_key']}/{case_id}"
        adapted = adapt_legacy_query_case(
            {
                "id": case_id,
                **{name: value for name, value in raw_case.items() if name != "repo_key"},
            }
        )
        assert _without_catalog_metadata(canonical[key]) == adapted


def test_ab_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_cases = json.loads(LEGACY_AB.read_text(encoding="utf-8"))

    for case_id, raw_case in zip(AB_IDS, legacy_cases, strict=True):
        case = canonical[f"embedding_ab/{case_id}"]
        assert case.query == raw_case["query"]
        assert case.gate is Gate.INFORMATIONAL
        assert case.metric_k == 12
        assert [matcher.contains for matcher in case.relevance_matchers] == raw_case[
            "expected_relevant"
        ]
        assert [matcher.contains for matcher in case.noise_matchers] == raw_case[
            "expected_noise"
        ]
        assert case.legacy == LegacyProvenance(
            fixture="ab_comparison",
            key=f"embedding_ab/{case_id}",
        )


def test_legacy_provenance_inventory() -> None:
    provenance = [
        case.legacy
        for case in _catalog_cases().values()
        if case.legacy is not None
    ]
    provenance_counts = {
        fixture: sum(item.fixture == fixture for item in provenance)
        for fixture in {
            "generic_baseline_quality",
            "retrieval_calibration",
            "ab_comparison",
        }
    }

    assert len({(item.fixture, item.key) for item in provenance}) == 33
    assert provenance_counts == {
        "generic_baseline_quality": 22,
        "retrieval_calibration": 8,
        "ab_comparison": 3,
    }
```

- [ ] **Step 9: Run schema, catalog, and CI profile tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_catalog.py \
  -q

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p0-catalog-ci.json \
  --markdown /tmp/cst-p0-catalog-ci.md
```

Expected: tests PASS; CLI exits 0; the report includes `program_tool` and `java_spring_mini` cases.

- [ ] **Step 10: Commit Task 9 without deleting legacy fixtures**

```bash
git add tests/test_quality_catalog.py \
  tests/fixtures/retrieval_quality/queries.json \
  tests/fixtures/real_projects/cross_language_dashboard \
  tests/fixtures/real_projects/embedding_ab
git commit -m "test: consolidate retrieval quality catalog"
```

## Task 10: Remove Legacy Fixture Duplication Safely

**Files:**
- Modify: `tests/test_quality_catalog.py`
- Delete: `tests/test_generic_baseline_quality.py`
- Delete: `tests/test_retrieval_calibration.py`
- Delete: `tests/test_ab_comparison.py`
- Delete: `tests/fixtures/generic_baseline_quality/queries.json`
- Delete: `tests/fixtures/retrieval_calibration/queries.json`
- Delete: `tests/fixtures/ab_comparison/queries.json`

- [ ] **Step 1: Run all parity tests immediately before deletion**

```bash
conda run -n base python -m pytest \
  tests/test_quality_catalog.py::test_generic_legacy_parity \
  tests/test_quality_catalog.py::test_calibration_legacy_parity \
  tests/test_quality_catalog.py::test_ab_legacy_parity \
  tests/test_quality_catalog.py::test_legacy_provenance_inventory \
  -q
```

Expected: 4 passed. Stop and fix the canonical catalog if any parity assertion fails.

- [ ] **Step 2: Replace parity tests with durable canonical inventory tests**

After deleting legacy JSON, remove the three tests that read it. Keep and strengthen `test_legacy_provenance_inventory`:

Remove the now-unused `json`, `replace`, `Gate`, and
`adapt_legacy_query_case` imports, the three `LEGACY_*` path constants,
`CALIBRATION_IDS`, and `_without_catalog_metadata`. Keep `AB_IDS` because the
durable expected-pair set uses it.

```python
EXPECTED_LEGACY_PAIRS = {
    *{
        ("generic_baseline_quality", f"imagebed/{case_id}")
        for case_id in (
            "go-upload-handler", "go-auth-middleware",
            "go-storage-implementations", "go-delete-handler",
            "go-route-registration",
        )
    },
    *{
        ("generic_baseline_quality", f"env_change/{case_id}")
        for case_id in (
            "tauri-commands", "engine-apply-restore",
            "frontend-invoke", "settings-persistence",
        )
    },
    *{
        ("generic_baseline_quality", f"investment_assistant/{case_id}")
        for case_id in (
            "frontend-auth-store", "collector-handler",
            "frontend-sse-composable", "collector-fund-service",
            "collector-nav-fetcher", "collector-scheduler",
            "java-ai-sse-controller",
        )
    },
    *{
        ("generic_baseline_quality", f"program_tool/{case_id}")
        for case_id in (
            "watermark-remover", "mqtt-tool", "qrcode-tool",
            "json-to-entity", "app-layout-theme", "ai-chat",
        )
    },
    *{
        ("retrieval_calibration", f"operation_client/{case_id}")
        for case_id in (
            "operation-client-auth-login-register",
            "operation-client-station-device-list",
            "operation-client-feedback-sms",
        )
    },
    *{
        ("retrieval_calibration", f"console_iot/{case_id}")
        for case_id in (
            "console-iot-equipment-list", "console-iot-access-control",
            "console-iot-device-status", "console-iot-alarm",
            "console-iot-user-auth",
        )
    },
    *{
        ("ab_comparison", f"embedding_ab/{case_id}")
        for case_id in AB_IDS
    },
}


def test_legacy_provenance_inventory() -> None:
    cases = _catalog_cases()
    provenance = [case.legacy for case in cases.values() if case.legacy is not None]
    pairs = {(item.fixture, item.key) for item in provenance}

    assert len(provenance) == 33
    assert len(pairs) == 33
    assert sum(item.fixture == "generic_baseline_quality" for item in provenance) == 22
    assert sum(item.fixture == "retrieval_calibration" for item in provenance) == 8
    assert sum(item.fixture == "ab_comparison" for item in provenance) == 3
    assert pairs == EXPECTED_LEGACY_PAIRS
    assert cases["program_tool/qrcode-tool"].legacy == LegacyProvenance(
        fixture="generic_baseline_quality",
        key="program_tool/qrcode-tool",
)
```

- [ ] **Step 3: Preserve the candidate-pool diagnostic in the canonical suite**

Move the `_candidate_pool_paths_before_rerank()` helper from `tests/test_generic_baseline_quality.py` into `tests/test_quality_catalog.py` with its existing imports. Add:

```python
@pytest.mark.slow
@pytest.mark.integration
def test_investment_assistant_targets_enter_candidate_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_repo = os.environ.get("CST_SMOKE_INVESTMENT_ASSISTANT_REPO")
    smoke_root = os.environ.get("CST_SMOKE_REPOS_DIR")
    source = (
        Path(raw_repo)
        if raw_repo
        else Path(smoke_root) / "Investment-Assistant"
        if smoke_root
        else None
    )
    if source is None or not source.is_dir():
        pytest.skip("investment assistant repo not configured")

    copied = tmp_path / source.name
    shutil.copytree(source, copied, ignore=shutil.ignore_patterns(".git", ".context-search"))
    index_repository(copied, DEFAULT_CONFIG)
    fixture = load_quality_fixture(CATALOG_PATH)
    repo = next(item for item in fixture.repos if item.repo_key == "investment_assistant")

    for case in repo.queries:
        candidates = _candidate_pool_paths_before_rerank(copied, case.query)
        for expected in case.expected_top_k:
            assert any(expected.matcher.matches(path) for path in candidates), case.case_id
```

The legacy anchor-separation assertion is already preserved by
`test_expected_anchor_must_remain_outside_ranked_results` in Task 2; verify that
test remains before deleting the generic harness.

- [ ] **Step 4: Delete legacy harnesses and fixtures**

Use `apply_patch` to delete the three legacy JSON files and three legacy test modules listed in this task. Do not remove `src/context_search_tool/metrics.py` or `tests/test_metrics.py`; they remain a separate public utility surface and are outside this closure.

- [ ] **Step 5: Verify no code references deleted fixtures**

```bash
rg -n "generic_baseline_quality/queries|retrieval_calibration/queries|ab_comparison/queries" \
  src tests README.md
```

Expected: no matches.

- [ ] **Step 6: Run catalog, quality, and full default suites**

```bash
conda run -n base python -m pytest tests/test_quality_catalog.py -q
conda run -n base python -m pytest tests/test_quality_*.py -q
conda run -n base python -m pytest -q
```

Expected: all commands PASS; only the repository's established integration skips remain.

- [ ] **Step 7: Commit Task 10**

```bash
git add tests/test_quality_catalog.py \
  tests/test_generic_baseline_quality.py \
  tests/test_retrieval_calibration.py \
  tests/test_ab_comparison.py \
  tests/fixtures/generic_baseline_quality/queries.json \
  tests/fixtures/retrieval_calibration/queries.json \
  tests/fixtures/ab_comparison/queries.json
git commit -m "test: retire legacy quality fixtures"
```

## Task 11: Add Planner Acceptance And Operational Documentation

**Files:**
- Create: `tests/test_quality_planner.py`
- Create: `docs/retrieval-quality.md`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add dependency-free planner diagnostic tests**

Create `tests/test_quality_planner.py`:

```python
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from context_search_tool.models import QueryPlan
from context_search_tool.quality.cases import load_quality_fixture
from context_search_tool.quality.runner import run_quality_fixture
from context_search_tool.tokenizer import tokenize_query


CATALOG = Path(__file__).parent / "fixtures" / "retrieval_quality" / "queries.json"
FORBIDDEN = {"spring", "resttemplate", "httpsession", "restcontroller"}


def _consumed_values(plan: QueryPlan) -> list[str]:
    return [*plan.rewritten_queries, *plan.grep_keywords, *plan.symbol_hints]


def _consumed_tokens(plan: QueryPlan) -> set[str]:
    return {
        token.casefold()
        for value in _consumed_values(plan)
        for token in tokenize_query(value)
    }


def _compacted_consumed_text(plan: QueryPlan) -> str:
    return re.sub(r"[\W_]+", "", "\n".join(_consumed_values(plan)).casefold())


def assert_supported_non_noop_plan(
    plan: QueryPlan,
    original_query: str,
    expanded_tokens: list[str],
) -> None:
    assert plan.status == "ok"
    assert plan.repo_profile_hash
    consumed = _consumed_tokens(plan)
    assert consumed
    compacted = _compacted_consumed_text(plan)
    assert all(term not in compacted for term in FORBIDDEN)
    original = {token.casefold() for token in tokenize_query(original_query)}
    expanded = {token.casefold() for token in expanded_tokens}
    assert (consumed - original) & expanded


def test_canonical_planner_inventory_contains_requests_and_dashboard() -> None:
    fixture = load_quality_fixture(CATALOG)
    planner_cases = {
        f"{repo.repo_key}/{case.case_id}"
        for repo in fixture.repos
        for case in repo.queries
        if "planner" in (case.profiles or repo.profiles)
    }

    assert planner_cases == {
        "psf_requests/cookies-between-calls",
        "psf_requests/retry-proxy-pooling-natural",
        "psf_requests/stream-response-body-natural",
        "cross_language_dashboard/dashboard-cross-language",
    }


def test_supported_non_noop_plan_contract() -> None:
    plan = QueryPlan(
        original_query="数据看板统计图表功能",
        rewritten_queries=["dashboard statistics chart"],
        status="ok",
        repo_profile_hash="sha256:profile",
    )

    assert_supported_non_noop_plan(
        plan,
        plan.original_query,
        ["数据看板统计图表功能", "dashboard", "statistics", "chart"],
    )


@pytest.mark.parametrize(
    "plan,original_query,expanded_tokens",
    [
        (
            QueryPlan(
                original_query="target",
                rewritten_queries=["target helper"],
                status="fallback",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target", "helper"],
        ),
        (
            QueryPlan(
                original_query="target",
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target"],
        ),
        (
            QueryPlan(
                original_query="target query",
                rewritten_queries=["target query"],
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target query",
            ["target", "query"],
        ),
        (
            QueryPlan(
                original_query="target",
                grep_keywords=["RestTemplate"],
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target", "resttemplate"],
        ),
    ],
    ids=["fallback", "empty-hints", "no-op-hints", "unsupported-consumed"],
)
def test_supported_non_noop_plan_rejects_invalid_diagnostics(
    plan: QueryPlan,
    original_query: str,
    expanded_tokens: list[str],
) -> None:
    with pytest.raises(AssertionError):
        assert_supported_non_noop_plan(plan, original_query, expanded_tokens)
```

- [ ] **Step 2: Add optional real planner integration tests**

In the same file, add one module-scoped real report fixture and two specialized
`slow`/`integration` acceptance tests:

```python
def _plan_from_record(case: dict) -> QueryPlan:
    return QueryPlan(
        original_query=case["query"],
        **{
            key: value
            for key, value in case["planner"].items()
            if key in QueryPlan.__dataclass_fields__ and key != "original_query"
        },
    )


@pytest.fixture(scope="module")
def real_planner_report() -> dict:
    raw_repo = os.environ.get("CST_PLANNER_REQUESTS_REPO")
    if not raw_repo or not Path(raw_repo).is_dir():
        pytest.skip("CST_PLANNER_REQUESTS_REPO is not configured")
    return run_quality_fixture(CATALOG, "planner", None, None)


@pytest.mark.slow
@pytest.mark.integration
def test_real_requests_planner_is_three_of_three_with_supported_hints(
    real_planner_report: dict,
) -> None:
    request_cases = [
        case
        for case in real_planner_report["cases"]
        if case["repo_key"] == "psf_requests"
    ]

    assert {case["case_id"] for case in request_cases} == {
        "cookies-between-calls",
        "retry-proxy-pooling-natural",
        "stream-response-body-natural",
    }
    assert all(case["status"] == "pass" for case in request_cases)
    for case in request_cases:
        planner = _plan_from_record(case)
        assert_supported_non_noop_plan(
            planner,
            case["query"],
            case["expanded_tokens"],
        )


@pytest.mark.slow
@pytest.mark.integration
def test_real_dashboard_planner_supplies_english_bridge(
    real_planner_report: dict,
) -> None:
    case = next(
        case
        for case in real_planner_report["cases"]
        if case["repo_key"] == "cross_language_dashboard"
        and case["case_id"] == "dashboard-cross-language"
    )
    planner = _plan_from_record(case)

    assert case["status"] == "pass"
    assert_supported_non_noop_plan(
        planner,
        case["query"],
        case["expanded_tokens"],
    )
    bridge = {"dashboard", "statistics", "chart"}
    expanded = {token.casefold() for token in case["expanded_tokens"]}
    assert bridge & _consumed_tokens(planner) & expanded
```

These tests intentionally ignore forbidden words in `discarded_hints`; only
consumed fields are rejected. Task 6 already records `expanded_tokens` in each
safe case payload.

- [ ] **Step 3: Run dependency-free planner tests**

```bash
conda run -n base python -m pytest tests/test_quality_planner.py -m "not integration" -q
```

Expected: PASS.

- [ ] **Step 4: Write the operational guide**

Create `docs/retrieval-quality.md` with these sections and commands:

````markdown
# Retrieval Quality Workflow

## Profiles

| profile | dependency | purpose |
| --- | --- | --- |
| `ci` | committed snapshots | deterministic frontend, Java, exact, and noise gates |
| `smoke` | real generic repositories | all 22 generic cases |
| `planner` | Ollama and requests checkout | repo-aware planner and genuine cross-language cases |
| `calibration_bge` | BGE and two Java repositories | all eight Java calibration cases |
| `ab_hash` | committed A/B snapshot | local embedding baseline |
| `ab_bge` | Ollama BGE-M3 | BGE candidate report |

## Fast CI Run

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci --output .quality/ci.json --markdown .quality/ci.md
```

## Real Repository Smoke

```bash
CST_SMOKE_REPOS_DIR=/absolute/path/to/repos \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke --output .quality/smoke.json --markdown .quality/smoke.md
```

## Baseline And Candidate Comparison

Run the same profile from the baseline and candidate worktrees, then:

```bash
cst quality compare --baseline .quality/main.json \
  --candidate .quality/branch.json \
  --output .quality/comparison.json \
  --markdown .quality/comparison.md
```

## Planner, Calibration, And A/B

### External Source Variables

| variable | repository |
| --- | --- |
| `CST_SMOKE_IMAGEBED_REPO` | imagebed |
| `CST_SMOKE_ENV_CHANGE_REPO` | env-change |
| `CST_SMOKE_INVESTMENT_ASSISTANT_REPO` | Investment-Assistant |
| `CST_SMOKE_PROGRAM_TOOL_REPO` | program-tool |
| `CST_CALIBRATION_OPERATION_CLIENT_REPO` | operation-client-api |
| `CST_CALIBRATION_CONSOLE_IOT_REPO` | console-iot-api |
| `CST_PLANNER_REQUESTS_REPO` | psf/requests |
| `CST_QUALITY_AB_REPO` | optional A/B replacement repository |
| `CST_SMOKE_REPOS_DIR` | shared parent fallback for each `repo_dir_name` |

Each value is an absolute directory used only to locate input. Reports record
the variable name, never its value.

### Planner

```bash
CST_PLANNER_REQUESTS_REPO=/absolute/path/to/requests \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile planner --output .quality/planner.json --markdown .quality/planner.md
```

### Calibration BGE

```bash
CST_CALIBRATION_OPERATION_CLIENT_REPO=/absolute/path/to/operation-client-api \
CST_CALIBRATION_CONSOLE_IOT_REPO=/absolute/path/to/console-iot-api \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile calibration_bge \
  --output .quality/calibration-bge.json \
  --markdown .quality/calibration-bge.md
```

### A/B Hash

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ab_hash --output .quality/ab-hash.json
```

### A/B BGE

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ab_bge --output .quality/ab-bge.json
```

## MCP Feedback Privacy

```bash
cst quality feedback .context-search/mcp_calls.jsonl \
  --output .quality/feedback.json
```

Query terms and examples remain excluded unless their explicit flags are used.

## Interpreting Results

Required failures, required removals, execution regressions, coverage loss, and
gate weakening are gating regressions. Known-gap and informational cases remain
non-gating observations; their metric declines are shown separately. A skip
means a source was unavailable. An optional profile that cannot be exercised is
`unverified_dependency`, never passed. Metadata warnings identify input or
configuration differences and do not by themselves fail comparison. Generated
`.quality/` artifacts are local and untracked.
````

- [ ] **Step 5: Link docs and ignore generated reports**

Add this line immediately after `.context-search/` in `.gitignore`:

```gitignore
.quality/
```

In README's `## 开发` section, replace the paragraph and pytest command beginning
`真实项目通用基线 smoke` with:

````markdown
检索质量的标准 CI、真实仓库 smoke、planner、BGE A/B、报告比较和 MCP
反馈流程见 [Retrieval Quality Workflow](docs/retrieval-quality.md)。快速本地门禁：

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci --output .quality/ci.json --markdown .quality/ci.md
```

真实项目 smoke：

```bash
CST_SMOKE_REPOS_DIR=/absolute/path/to/repos \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke --output .quality/smoke.json --markdown .quality/smoke.md
```
````

The approved design already links this implementation plan; do not edit the
design during implementation unless a reviewed scope change is required.

- [ ] **Step 6: Verify planner and documentation tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_planner.py \
  tests/test_quality_cli.py \
  -m "not integration" \
  -q

rg -n "quality run|quality compare|quality feedback|CST_PLANNER_REQUESTS_REPO" \
  docs/retrieval-quality.md README.md
```

Expected: pytest PASS; grep shows the canonical commands and planner environment variable.

- [ ] **Step 7: Commit Task 11**

```bash
git add tests/test_quality_planner.py \
  docs/retrieval-quality.md \
  README.md \
  .gitignore
git commit -m "docs: add retrieval quality workflow"
```

## Task 12: Run Phase 0 Acceptance And Update The Roadmap

**Files:**
- Modify after verification: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
- No source changes unless verification exposes a defect in an earlier task.

- [ ] **Step 1: Run all focused quality tests**

```bash
conda run -n base python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_aggregate.py \
  tests/test_quality_runner.py \
  tests/test_quality_reports.py \
  tests/test_quality_compare.py \
  tests/test_quality_feedback.py \
  tests/test_quality_cli.py \
  tests/test_quality_catalog.py \
  tests/test_quality_planner.py \
  -m "not integration" \
  -q
```

Expected: PASS with no skips in the dependency-free quality set.

- [ ] **Step 2: Run the complete default suite**

```bash
conda run -n base python -m pytest -q
```

Expected: PASS; only established slow/integration cases without dependencies are skipped.

- [ ] **Step 3: Run CI, self-comparison, and A/B hash acceptance**

```bash
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p0-ci.json \
  --markdown /tmp/cst-p0-ci.md

conda run -n base cst quality compare \
  --baseline /tmp/cst-p0-ci.json \
  --candidate /tmp/cst-p0-ci.json \
  --output /tmp/cst-p0-self-compare.json \
  --markdown /tmp/cst-p0-self-compare.md

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ab_hash \
  --output /tmp/cst-p0-ab-hash.json

printf 'verified\n' > /tmp/cst-p0-ci.status
printf 'verified\n' > /tmp/cst-p0-ab-hash.status
```

Expected: all commands exit 0; self-comparison has zero gating regressions and zero deltas; all three A/B cases execute as informational.

- [ ] **Step 4: Run the mandatory external smoke on available real repositories**

Use the repositories already available in this workspace environment:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding \
CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool \
conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile smoke \
  --output /tmp/cst-p0-smoke.json \
  --markdown /tmp/cst-p0-smoke.md

conda run -n base python -c '
import json
report = json.load(open("/tmp/cst-p0-smoke.json", encoding="utf-8"))
external = {
    repo["repo_key"] for repo in report["repos"]
    if repo["source"]["type"] in {"path_env", "smoke_root"}
}
executed = {"pass", "fail", "known_gap", "informational"}
assert external
assert any(
    case["repo_key"] in external and case["status"] in executed
    for case in report["cases"]
)
'

printf 'verified\n' > /tmp/cst-p0-smoke.status
```

Expected: both commands exit 0 and at least one case from an external repository executes.

- [ ] **Step 5: Attempt the optional real planner profile and record status**

```bash
mkdir -p /tmp/cst-quality-real
if ! test -d /tmp/cst-quality-real/requests/.git; then
  git clone --depth 1 -c fetch.fsck.badTimezone=ignore \
    https://github.com/psf/requests.git \
    /tmp/cst-quality-real/requests || true
fi

planner_status=unverified_dependency
if test -d /tmp/cst-quality-real/requests/.git && \
   ollama list 2>/dev/null | rg -q 'qwen3.5:4b-mlx'; then
  set +e
  CST_PLANNER_REQUESTS_REPO=/tmp/cst-quality-real/requests \
  conda run -n base cst quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile planner \
    --output /tmp/cst-p0-planner.json \
    --markdown /tmp/cst-p0-planner.md
  run_status=$?

  CST_PLANNER_REQUESTS_REPO=/tmp/cst-quality-real/requests \
  conda run -n base python -m pytest \
    tests/test_quality_planner.py -m "slow and integration" -q
  diagnostic_status=$?
  set -e

  if test "$run_status" -eq 0 && test "$diagnostic_status" -eq 0; then
    planner_status=verified
  else
    planner_status=failed
  fi
fi
printf '%s\n' "$planner_status" > /tmp/cst-p0-planner.status
```

Expected: status is `verified` only when the report path gates and specialized
planner diagnostics both pass. A missing requests checkout, Ollama service, or
planner model is `unverified_dependency`; an available-but-failing run is
`failed`.

- [ ] **Step 6: Attempt optional BGE profiles and record exact status**

```bash
calibration_status=unverified_dependency
ab_bge_status=unverified_dependency

if ollama list 2>/dev/null | rg -q 'bge-m3'; then
  set +e
  conda run -n base cst quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile calibration_bge \
    --allow-empty \
    --output /tmp/cst-p0-calibration-bge.json \
    --markdown /tmp/cst-p0-calibration-bge.md
  set -e

  calibration_status=$(conda run -n base python -c '
import json
from pathlib import Path
path = Path("/tmp/cst-p0-calibration-bge.json")
if not path.is_file():
    print("failed")
else:
    aggregate = json.loads(path.read_text(encoding="utf-8"))["aggregate"]
    if aggregate["failed"] or aggregate["errors"]:
        print("failed")
    elif aggregate["executed"] == 8 and aggregate["skipped"] == 0:
        print("verified")
    else:
        print("unverified_dependency")
')

  set +e
  conda run -n base cst quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ab_bge \
    --output /tmp/cst-p0-ab-bge.json
  set -e

  ab_bge_status=$(conda run -n base python -c '
import json
from pathlib import Path
path = Path("/tmp/cst-p0-ab-bge.json")
if not path.is_file():
    print("failed")
else:
    aggregate = json.loads(path.read_text(encoding="utf-8"))["aggregate"]
    if aggregate["errors"]:
        print("failed")
    elif aggregate["executed"] == 3 and aggregate["informational"] == 3:
        print("verified")
    else:
        print("failed")
')

  if test "$ab_bge_status" = verified; then
    set +e
    conda run -n base cst quality compare \
      --baseline /tmp/cst-p0-ab-hash.json \
      --candidate /tmp/cst-p0-ab-bge.json \
      --output /tmp/cst-p0-ab-comparison.json \
      --markdown /tmp/cst-p0-ab-comparison.md
    compare_status=$?
    set -e
    if test "$compare_status" -ne 0; then
      ab_bge_status=failed
    fi
  fi
fi

printf '%s\n' "$calibration_status" > /tmp/cst-p0-calibration-bge.status
printf '%s\n' "$ab_bge_status" > /tmp/cst-p0-ab-bge.status
```

Expected: `verified` requires zero failures/errors and the full expected
execution count. Missing BGE, private repositories, or service availability is
`unverified_dependency`; an available run with functional failures is `failed`.

- [ ] **Step 7: Inspect generated reports and working tree**

```bash
conda run -n base python -c '
import json
from pathlib import Path
ci = json.load(open("/tmp/cst-p0-ci.json", encoding="utf-8"))
self_compare = json.load(open("/tmp/cst-p0-self-compare.json", encoding="utf-8"))
ab_hash = json.load(open("/tmp/cst-p0-ab-hash.json", encoding="utf-8"))
def delta_values(node):
    if isinstance(node, dict):
        if "delta" in node:
            yield node["delta"]
        for value in node.values():
            yield from delta_values(value)
assert ci["schema_version"] == 2
assert ci["aggregate"]["selected"] == ci["aggregate"]["executed"]
assert ci["aggregate"]["failed"] == 0
assert ci["aggregate"]["errors"] == 0
assert self_compare["aggregate"]["gating_regressions"] == 0
assert all(value == 0 for value in delta_values(self_compare["metric_deltas"]))
assert ab_hash["aggregate"]["selected"] == 3
assert ab_hash["aggregate"]["executed"] == 3
assert ab_hash["aggregate"]["informational"] == 3
status_files = {
    "ci": "/tmp/cst-p0-ci.status",
    "smoke": "/tmp/cst-p0-smoke.status",
    "planner": "/tmp/cst-p0-planner.status",
    "calibration_bge": "/tmp/cst-p0-calibration-bge.status",
    "ab_hash": "/tmp/cst-p0-ab-hash.status",
    "ab_bge": "/tmp/cst-p0-ab-bge.status",
}
statuses = {
    profile: Path(path).read_text(encoding="utf-8").strip()
    for profile, path in status_files.items()
}
allowed = {"verified", "failed", "unverified_dependency"}
assert set(statuses.values()) <= allowed
assert statuses["ci"] == "verified"
assert statuses["smoke"] == "verified"
assert statuses["ab_hash"] == "verified"
Path("/tmp/cst-p0-profile-status.json").write_text(
    json.dumps(statuses, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print("| profile | status |")
print("| --- | --- |")
for profile, status in statuses.items():
    print(f"| {profile} | {status} |")
'

git status --short
git diff --check
```

Expected: report assertions pass; `.quality/` does not appear; only the roadmap
plus the two pre-existing unrelated untracked plan files may remain. Do not
stage those unrelated files. The printed six-row status table is the only
source for roadmap and final-handoff profile claims.

- [ ] **Step 8: Mark Phase 0 complete only after acceptance passes**

In `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`:

Replace the top-level `Next-stage plan` line with:

```markdown
Next-stage review: Phase 1 Query Understanding acceptance review
```

Immediately below `### Phase 0: Quality Control Loop`, insert this block,
then append the exact six-row table printed by Step 7:

```markdown
Status: Complete (2026-07-11)

Operational guide: `docs/retrieval-quality.md`
Canonical catalog: `tests/fixtures/retrieval_quality/queries.json`
Required verified profiles: `ci`, `smoke`, `ab_hash`

Profile status:
```

For every `unverified_dependency` row, add one bullet naming the missing input:
planner uses the requests checkout/Ollama/planner model; calibration uses BGE
plus `CST_CALIBRATION_OPERATION_CLIENT_REPO` and
`CST_CALIBRATION_CONSOLE_IOT_REPO`; `ab_bge` uses BGE. A `failed` optional
profile remains `failed`; never rewrite it as an unavailable dependency.

Do not claim Phase 1 cross-language completion merely because the planner fixture exists.

- [ ] **Step 9: Run final docs and full verification**

```bash
rg -n "Status: Complete|retrieval-quality.md|unverified_dependency|Next-stage" \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md

conda run -n base python -m pytest -q
git diff --check
```

Expected: roadmap references are present; full suite PASS; diff check produces no output.

- [ ] **Step 10: Commit the verified roadmap status**

```bash
git add roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
git commit -m "docs: mark quality control loop complete"
```

## Final Acceptance Checklist

- [ ] One canonical catalog owns all 33 legacy cases with exact provenance.
- [ ] All eight calibration cases preserve N-of-M, required Top-3, forbidden Top-3, and known-gap semantics.
- [ ] CI covers frontend, Java/Spring, exact identifier, noise, and localized-CJK behavior without claiming translation.
- [ ] The English-only dashboard case measures genuine Chinese-to-English planner behavior.
- [ ] Profile configs control embedding and planner sections without stale fields.
- [ ] All six profiles pass dependency-free copied-fixture wiring tests.
- [ ] Source resolution is safe, copied, fallback-aware, and path-redacted.
- [ ] Report schema v2 includes exact config, counters, planner diagnostics, typed aggregates, and known gaps.
- [ ] Comparisons implement the complete gate/status matrix, deterministic metric direction, deltas, and non-zero required regression gates.
- [ ] Informational and known-gap observations never become accidental hard gates.
- [ ] CLI output parents, empty runs, regression exits, and privacy-preserving feedback are tested.
- [ ] Legacy fixtures are deleted only after parity passes.
- [ ] Focused and full tests pass.
- [ ] Required `ci`, `ab_hash`, and real `smoke` profiles are verified.
- [ ] `planner`, `calibration_bge`, and `ab_bge` each have an honest
  `verified`, `failed`, or `unverified_dependency` status with missing
  dependencies named.
- [ ] README, operational guide, design, and roadmap agree on the Phase 0 workflow and status.

## Execution Handoff

Plan implementation should stop after each task's commit for review. Use one of:

1. **Subagent-Driven (recommended):** dispatch a fresh implementation agent per task and run spec-compliance plus code-quality review after every task.
2. **Inline Execution:** use `superpowers:executing-plans` in batches of at most three tasks, with review checkpoints between batches.

Do not begin implementation until the user selects an execution mode.
