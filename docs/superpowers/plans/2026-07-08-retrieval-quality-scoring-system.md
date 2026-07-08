# Retrieval Quality Scoring System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified retrieval quality scoring system that can run portable retrieval fixtures, calculate stable metrics, emit JSON/Markdown reports, compare baseline/candidate reports, and analyze MCP feedback without changing retrieval ranking behavior.

**Architecture:** Add a new `context_search_tool.quality` package with clear boundaries for fixture cases, metrics/evaluation, runner execution, report writing, comparison, and feedback analysis. The quality runner copies source repositories into temporary workspaces before indexing, calls existing `index_repository()` and `query_repository()`, and records enough metadata to make reports comparable. The existing CLI gains a `cst quality` sub-app that wraps the package without duplicating evaluation logic.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, fnmatch, hashlib, json, tempfile, shutil, time.perf_counter, Typer, pytest, existing CST indexer/retrieval/config APIs.

---

## Source Documents

- Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
- Design spec: `docs/superpowers/specs/2026-07-08-retrieval-quality-scoring-system-design.md`

## Scope

This plan implements the scoring/evaluation system only. It does not change retrieval ranking, embeddings, query planning, ContextPack, RetrievalTrace, or language plugins.

The first implementation includes feedback analysis because the spec lists it in acceptance criteria, but it is deliberately last and isolated. If earlier tasks reveal the core evaluator is larger than expected, finish Tasks 1-7 first and keep Task 8 as a separate follow-up commit.

## File Structure

Create:

- `src/context_search_tool/quality/__init__.py`
  Public exports for quality package types and helpers.
- `src/context_search_tool/quality/cases.py`
  Fixture schema dataclasses, matcher validation, legacy adapter, fixture loading, profile compatibility validation.
- `src/context_search_tool/quality/metrics.py`
  Result normalization, expectation evaluation, metric formulas, case status calculation.
- `src/context_search_tool/quality/runner.py`
  Repo resolution, safe workspace copy, indexing/query execution, report assembly.
- `src/context_search_tool/quality/reports.py`
  JSON serialization helpers and Markdown summary rendering.
- `src/context_search_tool/quality/compare.py`
  Baseline/candidate report comparison and regression classification.
- `src/context_search_tool/quality/feedback.py`
  Privacy-preserving MCP feedback log summary.
- `src/context_search_tool/quality/__main__.py`
  Module entry point for `python -m context_search_tool.quality ...`.
- `tests/fixtures/retrieval_quality/queries.json`
  Small committed v1 fixture with snapshot-backed cases.
- `tests/test_quality_cases.py`
- `tests/test_quality_metrics.py`
- `tests/test_quality_runner.py`
- `tests/test_quality_reports.py`
- `tests/test_quality_compare.py`
- `tests/test_quality_feedback.py`
- `tests/test_quality_cli.py`

Modify:

- `src/context_search_tool/cli.py`
  Add `quality` Typer sub-app.
- `docs/superpowers/specs/2026-07-08-retrieval-quality-scoring-system-design.md`
  Add link to this plan.
- `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
  Add link to this next-stage plan.

Do not modify:

- `src/context_search_tool/retrieval.py`
- `src/context_search_tool/indexer.py`
- existing fixture behavior except for optional migration wiring in a later task

## Task 1: Quality Case Schema And Matchers

**Files:**
- Create: `src/context_search_tool/quality/__init__.py`
- Create: `src/context_search_tool/quality/cases.py`
- Create: `tests/test_quality_cases.py`

- [ ] **Step 1: Write failing matcher validation tests**

Create `tests/test_quality_cases.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    QualityFixture,
    adapt_legacy_query_case,
    load_quality_fixture,
    validate_profile_compatible,
)


def test_matcher_rejects_absolute_and_parent_paths() -> None:
    for value in ("/tmp/App.java", "../App.java", "C:/repo/App.java", r"\\server\\repo\\App.java", ""):
        with pytest.raises(ValueError):
            Matcher(path=value)


def test_glob_rejects_empty_and_parent_traversal() -> None:
    for value in ("", "../**/*.py"):
        with pytest.raises(ValueError):
            Matcher(glob=value)


def test_matcher_path_and_glob_match_repo_relative_posix_paths() -> None:
    assert Matcher(path="src/App.java").matches("src/App.java")
    assert not Matcher(path="src/App.java").matches("src/app.java")
    assert Matcher(glob="src/**/*.java").matches("src/main/App.java")
    assert Matcher(contains="Dashboard").matches("src/dashboard/DashboardController.java")


def test_normalize_result_path_preserves_dot_directories() -> None:
    assert Matcher(path=".github/workflows/ci.yml").matches("./.github/workflows/ci.yml")


def test_matcher_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError):
        Matcher(path="src/App.java", glob="src/*.java")
    with pytest.raises(ValueError):
        Matcher()


def test_load_quality_fixture_parses_v1_schema(tmp_path: Path) -> None:
    fixture_path = tmp_path / "queries.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "snapshot_path": "tests/fixtures/sample",
                        "profiles": ["ci"],
                        "queries": [
                            {
                                "id": "find-app",
                                "query": "find app",
                                "gate": "required",
                                "expected_top_k": [
                                    {"path": "src/App.java", "top_k": 5}
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    fixture = load_quality_fixture(fixture_path)

    assert fixture.schema_version == 1
    assert fixture.repos[0].repo_key == "sample"
    assert fixture.repos[0].queries[0].gate is Gate.REQUIRED


def test_legacy_known_gap_is_reason_not_gate() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "storage",
            "query": "storage save",
            "expected_top_k": [{"glob": "storage/*.go", "top_k": 5}],
            "known_gap": "main.go can be useful but storage file is the gate",
        }
    )

    assert case.gate is Gate.REQUIRED
    assert case.known_gap_reason == "main.go can be useful but storage file is the gate"


def test_legacy_expected_any_top_k_flat_list_becomes_group() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "any",
            "query": "service",
            "expected_any_top_k": [
                {"path": "Service.java", "top_k": 3},
                {"path": "ServiceImpl.java", "top_k": 3},
            ],
        }
    )

    assert len(case.expected_any_top_k) == 1
    assert len(case.expected_any_top_k[0].matchers) == 2
    assert case.expected_any_top_k[0].top_k == 3


def test_legacy_calibration_expected_core_becomes_relevance_targets() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "calibration",
            "query": "open permission",
            "expected_core": ["StationServiceImpl.java", "IOTController.java"],
            "expected_top5_min": 1,
            "forbidden_top3": ["Noise.java"],
        }
    )

    assert [item.matcher.path for item in case.expected_top_k] == [
        "StationServiceImpl.java",
        "IOTController.java",
    ]
    assert case.expected_top5_min == 1
    assert [item.matcher.path for item in case.absent_top_k] == ["Noise.java"]
    assert case.absent_top_k[0].top_k == 3


def test_legacy_forbidden_above_shape_becomes_target_and_noise() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "scope",
            "query": "collector fund",
            "expected_top_k": [{"path": "collector/internal/service/fund_service.go", "top_k": 5}],
            "forbidden_above": [
                {"glob": "investment-assistant-backend/**/*.java", "top_k": 5, "max_rank": 2}
            ],
        }
    )

    assert len(case.forbidden_above) == 1
    item = case.forbidden_above[0]
    assert item.source.path == "collector/internal/service/fund_service.go"
    assert item.noise.glob == "investment-assistant-backend/**/*.java"


def test_ci_profile_rejects_model_backed_config() -> None:
    config = ToolConfig(embedding=EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024))

    with pytest.raises(ValueError, match="ci profile"):
        validate_profile_compatible("ci", config)
```

- [ ] **Step 2: Run tests to verify imports fail**

Run:

```bash
python -m pytest tests/test_quality_cases.py -q
```

Expected: FAIL because `context_search_tool.quality.cases` does not exist.

- [ ] **Step 3: Create the quality package exports**

Create `src/context_search_tool/quality/__init__.py`:

```python
from __future__ import annotations

from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    QualityCase,
    QualityFixture,
    QualityRepo,
    load_quality_fixture,
)

__all__ = [
    "Gate",
    "Matcher",
    "QualityCase",
    "QualityFixture",
    "QualityRepo",
    "load_quality_fixture",
]
```

- [ ] **Step 4: Implement schema, matcher validation, fixture loading, and legacy adapter**

Create `src/context_search_tool/quality/cases.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import json
from pathlib import PurePosixPath, Path
from typing import Any

from context_search_tool.config import ToolConfig


class Gate(str, Enum):
    REQUIRED = "required"
    KNOWN_GAP = "known_gap"
    INFORMATIONAL = "informational"


@dataclass(frozen=True)
class Matcher:
    path: str | None = None
    glob: str | None = None
    contains: str | None = None

    def __post_init__(self) -> None:
        selectors = [self.path, self.glob, self.contains]
        if sum(value is not None for value in selectors) != 1:
            raise ValueError("matcher must define exactly one of path, glob, or contains")
        if self.path is not None:
            _validate_relative_posix(self.path, "path")
        if self.glob is not None:
            _validate_relative_posix(self.glob, "glob")
        if self.contains is not None and not self.contains:
            raise ValueError("contains matcher must not be empty")

    @staticmethod
    def from_raw(raw: object) -> Matcher:
        if isinstance(raw, str):
            return Matcher(glob=raw) if _looks_like_glob(raw) else Matcher(path=raw)
        if not isinstance(raw, dict):
            raise ValueError("matcher must be a dict or string")
        allowed = {"path", "glob", "contains"}
        unknown = set(raw) - allowed - {"top_k", "max_rank", "role"}
        if unknown:
            raise ValueError(f"unknown matcher fields: {sorted(unknown)}")
        return Matcher(
            path=_optional_str(raw.get("path")),
            glob=_optional_str(raw.get("glob")),
            contains=_optional_str(raw.get("contains")),
        )

    def matches(self, result_path: str) -> bool:
        normalized = normalize_result_path(result_path)
        if self.path is not None:
            return normalized == self.path
        if self.glob is not None:
            return fnmatch.fnmatchcase(normalized, self.glob)
        assert self.contains is not None
        return self.contains in normalized


@dataclass(frozen=True)
class TopKMatcher:
    matcher: Matcher
    top_k: int


@dataclass(frozen=True)
class ExpectedAnyGroup:
    matchers: tuple[Matcher, ...]
    top_k: int


@dataclass(frozen=True)
class PreferredRank:
    matcher: Matcher
    top_k: int
    max_rank: int
    role: str = ""


@dataclass(frozen=True)
class Outranks:
    source: Matcher
    noise: Matcher
    top_k: int


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    query: str
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


@dataclass(frozen=True)
class QualityRepo:
    repo_key: str
    path_env: str = ""
    repo_dir_name: str = ""
    snapshot_path: str = ""
    profiles: tuple[str, ...] = ("ci",)
    queries: tuple[QualityCase, ...] = ()
    default_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityFixture:
    schema_version: int
    repos: tuple[QualityRepo, ...]
    path: Path


def load_quality_fixture(path: Path) -> QualityFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("quality fixture schema_version must be 1")
    repos = tuple(_parse_repo(raw) for raw in data.get("repos", []))
    if not repos:
        raise ValueError("quality fixture must contain at least one repo")
    return QualityFixture(schema_version=1, repos=repos, path=path)


def adapt_legacy_query_case(raw: dict[str, Any]) -> QualityCase:
    return _parse_case(raw)


def validate_profile_compatible(profile: str, config: ToolConfig) -> None:
    if profile == "ci":
        if config.embedding.provider != "hash":
            raise ValueError("ci profile requires hash embedding")
        if config.query_planner.enabled:
            raise ValueError("ci profile requires query planner disabled")
        if config.embedding.api_key_env or config.embedding.base_url:
            raise ValueError("ci profile rejects remote embedding configuration")


def _parse_repo(raw: dict[str, Any]) -> QualityRepo:
    repo_key = _required_str(raw, "repo_key")
    queries = tuple(_parse_case(item) for item in raw.get("queries", []))
    if not queries:
        raise ValueError(f"repo {repo_key} must define at least one query")
    return QualityRepo(
        repo_key=repo_key,
        path_env=_optional_str(raw.get("path_env")) or "",
        repo_dir_name=_optional_str(raw.get("repo_dir_name")) or "",
        snapshot_path=_optional_str(raw.get("snapshot_path")) or "",
        profiles=tuple(raw.get("profiles", ["ci"])),
        queries=queries,
        default_config=dict(raw.get("default_config", {})),
    )


def _parse_case(raw: dict[str, Any]) -> QualityCase:
    case_id = _required_str(raw, "id")
    query = _required_str(raw, "query")
    gate = Gate(raw.get("gate", Gate.REQUIRED.value))
    legacy_known_gap = raw.get("known_gap")
    known_gap_reason = _optional_str(raw.get("known_gap_reason")) or ""
    if isinstance(legacy_known_gap, str) and legacy_known_gap:
        known_gap_reason = legacy_known_gap
    expected_top_k = list(_parse_top_k(item) for item in raw.get("expected_top_k", []))
    for legacy_path in raw.get("expected_core", []):
        expected_top_k.append(TopKMatcher(Matcher.from_raw({"path": legacy_path}), 5))
    absent_top_k = list(_parse_top_k(item) for item in raw.get("absent_top_k", []))
    for legacy_path in raw.get("forbidden_top3", []):
        absent_top_k.append(TopKMatcher(Matcher.from_raw({"path": legacy_path}), 3))
    return QualityCase(
        case_id=case_id,
        query=query,
        tags=tuple(raw.get("tags", [])),
        mode=raw.get("mode", "results"),
        gate=gate,
        expected_top_k=tuple(expected_top_k),
        expected_any_top_k=tuple(_parse_expected_any(raw.get("expected_any_top_k", []))),
        preferred_rank=tuple(_parse_preferred(item) for item in raw.get("preferred_rank", [])),
        absent_top_k=tuple(absent_top_k),
        outranks=tuple(_parse_outranks(item) for item in raw.get("outranks", [])),
        forbidden_above=tuple(_parse_forbidden_above(item, expected_top_k) for item in raw.get("forbidden_above", [])),
        anchor_expected=tuple(raw.get("anchor_expected", [])),
        known_gap_reason=known_gap_reason,
        notes=_optional_str(raw.get("notes")) or "",
        expected_top5_min=raw.get("expected_top5_min"),
    )


def _parse_top_k(raw: dict[str, Any]) -> TopKMatcher:
    return TopKMatcher(matcher=Matcher.from_raw(raw), top_k=_positive_int(raw, "top_k"))


def _parse_expected_any(raw_items: list[dict[str, Any]]) -> list[ExpectedAnyGroup]:
    if not raw_items:
        return []
    if all("matchers" not in item for item in raw_items):
        top_k = max(_positive_int(item, "top_k") for item in raw_items)
        return [ExpectedAnyGroup(tuple(Matcher.from_raw(item) for item in raw_items), top_k)]
    groups: list[ExpectedAnyGroup] = []
    for item in raw_items:
        matchers = tuple(Matcher.from_raw(raw) for raw in item.get("matchers", []))
        if not matchers:
            raise ValueError("expected_any_top_k group must include matchers")
        groups.append(ExpectedAnyGroup(matchers=matchers, top_k=_positive_int(item, "top_k")))
    return groups


def _parse_preferred(raw: dict[str, Any]) -> PreferredRank:
    return PreferredRank(
        matcher=Matcher.from_raw(raw),
        top_k=_positive_int(raw, "top_k"),
        max_rank=_positive_int(raw, "max_rank"),
        role=_optional_str(raw.get("role")) or "",
    )


def _parse_outranks(raw: dict[str, Any]) -> Outranks:
    return Outranks(
        source=Matcher.from_raw(raw["source"]),
        noise=Matcher.from_raw(raw["noise"]),
        top_k=_positive_int(raw, "top_k"),
    )


def _parse_forbidden_above(raw: dict[str, Any], expected_top_k: list[TopKMatcher]) -> Outranks:
    if "source" in raw and "noise" in raw:
        return _parse_outranks(raw)
    if not expected_top_k:
        raise ValueError("forbidden_above shorthand requires expected_top_k")
    return Outranks(
        source=expected_top_k[0].matcher,
        noise=Matcher.from_raw(raw),
        top_k=_positive_int(raw, "top_k"),
    )


def normalize_result_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def _validate_relative_posix(value: str, field: str) -> None:
    if not value:
        raise ValueError(f"{field} must not be empty")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise ValueError(f"{field} must be repo-relative")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        raise ValueError(f"{field} must not be a Windows absolute path")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ValueError(f"{field} must not contain parent traversal")


def _looks_like_glob(value: str) -> bool:
    return any(char in value for char in "*?[")


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected string")
    return value


def _positive_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
python -m pytest tests/test_quality_cases.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/context_search_tool/quality/__init__.py src/context_search_tool/quality/cases.py tests/test_quality_cases.py
git commit -m "feat: add retrieval quality fixture schema"
```

## Task 2: Metric Evaluation

**Files:**
- Create: `src/context_search_tool/quality/metrics.py`
- Create: `tests/test_quality_metrics.py`

- [ ] **Step 1: Write failing metric tests**

Create `tests/test_quality_metrics.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from context_search_tool.models import RetrievalResult
from context_search_tool.quality.cases import (
    ExpectedAnyGroup,
    Gate,
    Matcher,
    PreferredRank,
    QualityCase,
    TopKMatcher,
)
from context_search_tool.quality.metrics import evaluate_case, normalize_results


def _result(path: str, score: float = 1.0) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content="",
        score=score,
        score_parts={"lexical": score},
        reasons=["test"],
        followup_keywords=[],
    )


def test_normalize_results_deduplicates_paths() -> None:
    normalized = normalize_results([
        _result("src/App.java", 2.0),
        _result("src/App.java", 1.0),
        _result("src/Service.java", 0.5),
    ])

    assert [item.path for item in normalized] == ["src/App.java", "src/Service.java"]
    assert normalized[0].rank == 1
    assert normalized[1].rank == 2


def test_evaluate_case_calculates_hit_recall_and_mrr() -> None:
    case = QualityCase(
        case_id="flow",
        query="flow",
        expected_top_k=(
            TopKMatcher(Matcher(path="Controller.java"), 5),
            TopKMatcher(Matcher(path="Service.java"), 5),
        ),
    )

    evaluation = evaluate_case(case, [_result("Other.java"), _result("Service.java")], latency_ms=12)

    assert evaluation.status == "fail"
    assert evaluation.metrics["hit_at_1"] is False
    assert evaluation.metrics["hit_at_3"] is True
    assert evaluation.metrics["recall_at_5"] == pytest.approx(0.5)
    assert evaluation.metrics["mrr"] == pytest.approx(0.5)
    assert evaluation.metrics["latency_ms"] == 12


def test_expected_any_group_counts_as_one_relevance_target() -> None:
    case = QualityCase(
        case_id="any",
        query="service",
        expected_any_top_k=(
            ExpectedAnyGroup(
                matchers=(Matcher(path="Service.java"), Matcher(path="ServiceImpl.java")),
                top_k=5,
            ),
        ),
    )

    evaluation = evaluate_case(case, [_result("ServiceImpl.java")], latency_ms=1)

    assert evaluation.status == "pass"
    assert evaluation.metrics["recall_at_5"] == pytest.approx(1.0)


def test_known_gap_status_does_not_fail_gate() -> None:
    case = QualityCase(
        case_id="gap",
        query="gap",
        gate=Gate.KNOWN_GAP,
        expected_top_k=(TopKMatcher(Matcher(path="Missing.java"), 5),),
    )

    evaluation = evaluate_case(case, [_result("Other.java")], latency_ms=1)

    assert evaluation.status == "known_gap"
    assert evaluation.failures


def test_preferred_entrypoint_rank_and_noise_count() -> None:
    case = QualityCase(
        case_id="entry",
        query="entry",
        expected_top_k=(TopKMatcher(Matcher(path="View.vue"), 5),),
        preferred_rank=(PreferredRank(Matcher(path="View.vue"), top_k=5, max_rank=1, role="entrypoint"),),
        absent_top_k=(TopKMatcher(Matcher(path="package-lock.json"), 5),),
    )

    evaluation = evaluate_case(
        case,
        [_result("package-lock.json"), _result("View.vue")],
        latency_ms=1,
    )

    assert evaluation.status == "fail"
    assert evaluation.metrics["entrypoint_rank"] == 2
    assert evaluation.metrics["noise_top5"] == 1
    assert evaluation.metrics["preferred_rank_pass"] is False
```

- [ ] **Step 2: Run tests to verify metrics module is missing**

Run:

```bash
python -m pytest tests/test_quality_metrics.py -q
```

Expected: FAIL because `context_search_tool.quality.metrics` does not exist.

- [ ] **Step 3: Implement normalized results and case evaluation**

Create `src/context_search_tool/quality/metrics.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_search_tool.models import RetrievalResult
from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    Outranks,
    QualityCase,
    normalize_result_path,
)


@dataclass(frozen=True)
class NormalizedResult:
    rank: int
    path: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    status: str
    metrics: dict[str, Any]
    failures: list[str] = field(default_factory=list)
    top_results: list[dict[str, Any]] = field(default_factory=list)


def normalize_results(results: list[RetrievalResult]) -> list[NormalizedResult]:
    seen: set[str] = set()
    normalized: list[NormalizedResult] = []
    for result in results:
        path = normalize_result_path(result.file_path.as_posix())
        if path in seen:
            continue
        seen.add(path)
        normalized.append(
            NormalizedResult(
                rank=len(normalized) + 1,
                path=path,
                score=result.score,
                score_parts=dict(result.score_parts),
                reasons=list(result.reasons),
            )
        )
    return normalized


def evaluate_case(
    case: QualityCase,
    results: list[RetrievalResult],
    latency_ms: int,
    top_result_limit: int = 10,
) -> CaseEvaluation:
    normalized = normalize_results(results)
    relevance_targets = _relevance_targets(case)
    satisfied_by_k = {
        k: sum(1 for target in relevance_targets if _first_rank(target, normalized, k) is not None)
        for k in (1, 3, 5, 10)
    }
    first_rank = _first_relevance_rank(relevance_targets, normalized)
    failures = _assert_failures(case, normalized)
    status = _status_for(case, failures)
    metrics = {
        "hit_at_1": satisfied_by_k[1] > 0 if relevance_targets else None,
        "hit_at_3": satisfied_by_k[3] > 0 if relevance_targets else None,
        "hit_at_5": satisfied_by_k[5] > 0 if relevance_targets else None,
        "hit_at_10": satisfied_by_k[10] > 0 if relevance_targets else None,
        "recall_at_5": _ratio_or_none(satisfied_by_k[5], len(relevance_targets)),
        "recall_at_10": _ratio_or_none(satisfied_by_k[10], len(relevance_targets)),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
        "expected_coverage_top5": {
            "count": satisfied_by_k[5],
            "ratio": _ratio_or_none(satisfied_by_k[5], len(relevance_targets)),
        },
        "preferred_rank_pass": not any(message.startswith("preferred_rank") for message in failures),
        "noise_top5": _noise_count(case, normalized, 5),
        "noise_top10": _noise_count(case, normalized, 10),
        "entrypoint_rank": _entrypoint_rank(case, normalized),
        "cross_language_success": satisfied_by_k[5] > 0 if "cross_language" in case.tags else None,
        "latency_ms": latency_ms,
        "result_count": len(normalized),
        "top_score": normalized[0].score if normalized else None,
    }
    return CaseEvaluation(
        case_id=case.case_id,
        status=status,
        metrics=metrics,
        failures=failures,
        top_results=[_top_result_payload(item) for item in normalized[:top_result_limit]],
    )


def _relevance_targets(case: QualityCase) -> list[Matcher | tuple[Matcher, ...]]:
    targets: list[Matcher | tuple[Matcher, ...]] = []
    targets.extend(item.matcher for item in case.expected_top_k)
    targets.extend(group.matchers for group in case.expected_any_top_k)
    return targets


def _first_relevance_rank(
    targets: list[Matcher | tuple[Matcher, ...]],
    results: list[NormalizedResult],
) -> int | None:
    ranks = [
        rank
        for target in targets
        if (rank := _first_rank(target, results, len(results))) is not None
    ]
    return min(ranks) if ranks else None


def _first_rank(
    target: Matcher | tuple[Matcher, ...],
    results: list[NormalizedResult],
    top_k: int,
) -> int | None:
    matchers = target if isinstance(target, tuple) else (target,)
    for result in results[:top_k]:
        if any(matcher.matches(result.path) for matcher in matchers):
            return result.rank
    return None


def _assert_failures(case: QualityCase, results: list[NormalizedResult]) -> list[str]:
    failures: list[str] = []
    for item in case.expected_top_k:
        if _first_rank(item.matcher, results, item.top_k) is None:
            failures.append(f"expected_top_k missing within top {item.top_k}: {item.matcher}")
    for group in case.expected_any_top_k:
        if _first_rank(group.matchers, results, group.top_k) is None:
            failures.append(f"expected_any_top_k missing within top {group.top_k}: {group.matchers}")
    if case.expected_top5_min is not None:
        matched_top5 = sum(
            1
            for item in case.expected_top_k
            if _first_rank(item.matcher, results, 5) is not None
        )
        if matched_top5 < case.expected_top5_min:
            failures.append(f"expected_top5_min failed: matched={matched_top5} required={case.expected_top5_min}")
    for item in case.preferred_rank:
        rank = _first_rank(item.matcher, results, item.top_k)
        if rank is None or rank > item.max_rank:
            failures.append(f"preferred_rank failed: {item.matcher} rank={rank} max={item.max_rank}")
    for item in case.absent_top_k:
        rank = _first_rank(item.matcher, results, item.top_k)
        if rank is not None:
            failures.append(f"absent_top_k present at rank {rank}: {item.matcher}")
    for item in case.outranks:
        failures.extend(_outrank_failures("outranks", item, results))
    for item in case.forbidden_above:
        failures.extend(_outrank_failures("forbidden_above", item, results))
    return failures


def _outrank_failures(kind: str, item: Outranks, results: list[NormalizedResult]) -> list[str]:
    source_rank = _first_rank(item.source, results, item.top_k)
    noise_rank = _first_rank(item.noise, results, item.top_k)
    if noise_rank is None:
        return []
    if source_rank is None or source_rank > noise_rank:
        return [f"{kind} failed: source={source_rank} noise={noise_rank} top_k={item.top_k}"]
    return []


def _status_for(case: QualityCase, failures: list[str]) -> str:
    if case.gate is Gate.KNOWN_GAP:
        return "known_gap"
    if case.gate is Gate.INFORMATIONAL:
        return "informational"
    return "fail" if failures else "pass"


def _ratio_or_none(value: int, total: int) -> float | None:
    return None if total == 0 else value / total


def _noise_count(case: QualityCase, results: list[NormalizedResult], top_k: int) -> int:
    noise_matchers = [item.matcher for item in case.absent_top_k if item.top_k <= top_k]
    return sum(
        1
        for result in results[:top_k]
        if any(matcher.matches(result.path) for matcher in noise_matchers)
    )


def _entrypoint_rank(case: QualityCase, results: list[NormalizedResult]) -> int | None:
    ranks = [
        rank
        for item in case.preferred_rank
        if item.role == "entrypoint"
        if (rank := _first_rank(item.matcher, results, item.top_k)) is not None
    ]
    return min(ranks) if ranks else None


def _top_result_payload(result: NormalizedResult) -> dict[str, Any]:
    return {
        "rank": result.rank,
        "path": result.path,
        "score": result.score,
        "score_parts": result.score_parts,
        "reasons": result.reasons,
    }
```

- [ ] **Step 4: Run metric tests**

Run:

```bash
python -m pytest tests/test_quality_metrics.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/context_search_tool/quality/metrics.py tests/test_quality_metrics.py
git commit -m "feat: add retrieval quality metrics"
```

## Task 3: Runner With Safe Workspace Copy

**Files:**
- Create: `src/context_search_tool/quality/runner.py`
- Create: `tests/test_quality_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_quality_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_search_tool.quality.runner import run_quality_fixture


def _snapshot(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_quality_runner_copies_repo_without_mutating_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "App.java").write_text("class App { String targetToken; }\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (source / ".context-search").mkdir()
    (source / ".context-search" / "old.txt").write_text("old\n", encoding="utf-8")
    (source / ".gitignore").write_text("existing\n", encoding="utf-8")
    before = _snapshot(source)

    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "snapshot_path": str(source),
                        "profiles": ["ci"],
                        "queries": [
                            {
                                "id": "target",
                                "query": "targetToken",
                                "expected_top_k": [{"path": "src/App.java", "top_k": 5}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_quality_fixture(fixture, profile="ci", output_path=None, markdown_path=None, keep_workspace=True)

    assert report["aggregate"]["total"] == 1
    assert report["aggregate"]["passed"] == 1
    assert report["fixture"]["fixture_case_count"] == 1
    assert report["fixture"]["run_case_count"] == 1
    assert report["config"]["embedding"]["provider"] == "hash"
    assert _snapshot(source) == before
    repo_record = report["repos"][0]
    assert repo_record["workspace"]["copied"] is True
    assert repo_record["index"]["embedding_config_hash"]
    assert repo_record["index"]["config_hash"].startswith("sha256:")
    assert Path(repo_record["workspace"]["path"]).exists()
    assert not (Path(repo_record["workspace"]["path"]) / ".git").exists()


def test_quality_runner_records_skip_for_missing_repo(tmp_path: Path) -> None:
    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "missing",
                        "snapshot_path": str(tmp_path / "missing"),
                        "profiles": ["smoke"],
                        "queries": [{"id": "q", "query": "anything"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_quality_fixture(fixture, profile="smoke", output_path=None, markdown_path=None)

    assert report["aggregate"]["skipped"] == 1
    assert report["cases"][0]["status"] == "skipped"


def test_ci_profile_rejects_env_only_repo_even_when_env_is_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (external / "App.java").write_text("class App {}\n", encoding="utf-8")
    monkeypatch.setenv("CST_SMOKE_EXTERNAL_REPO", str(external))
    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "external",
                        "path_env": "CST_SMOKE_EXTERNAL_REPO",
                        "profiles": ["ci"],
                        "queries": [{"id": "q", "query": "App"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ci profile requires snapshot_path"):
        run_quality_fixture(fixture, profile="ci", output_path=None, markdown_path=None)


def test_quality_runner_records_query_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "App.java").write_text("class App { String targetToken; }\n", encoding="utf-8")
    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "snapshot_path": str(source),
                        "profiles": ["ci"],
                        "queries": [{"id": "target", "query": "targetToken"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_query(*args, **kwargs):
        raise RuntimeError("query exploded")

    monkeypatch.setattr("context_search_tool.quality.runner.query_repository", fail_query)

    report = run_quality_fixture(fixture, profile="ci", output_path=None, markdown_path=None)

    assert report["aggregate"]["errors"] == 1
    assert report["cases"][0]["status"] == "error"
    assert report["cases"][0]["failures"] == ["query exploded"]
```

- [ ] **Step 2: Run runner tests to verify module is missing**

Run:

```bash
python -m pytest tests/test_quality_runner.py -q
```

Expected: FAIL because `context_search_tool.quality.runner` does not exist.

- [ ] **Step 3: Implement runner**

Create `src/context_search_tool/quality/runner.py`:

```python
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.manifest import load_manifest
from context_search_tool.quality.cases import QualityFixture, QualityRepo, load_quality_fixture, validate_profile_compatible
from context_search_tool.quality.metrics import evaluate_case
from context_search_tool.retrieval import query_repository


EXCLUDE_DIRS = {".git", ".context-search", ".venv", "node_modules", "dist", "build", "target", "__pycache__"}


def run_quality_fixture(
    fixture_path: Path,
    profile: str,
    output_path: Path | None,
    markdown_path: Path | None,
    keep_workspace: bool = False,
    config: ToolConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    fixture = load_quality_fixture(fixture_path)
    validate_profile_compatible(profile, config)
    started = int(time.time())
    cases: list[dict[str, Any]] = []
    repos: list[dict[str, Any]] = []
    temp_root = Path(tempfile.mkdtemp(prefix="cst-quality-"))
    try:
        for repo_spec in fixture.repos:
            if profile not in repo_spec.profiles:
                continue
            repo_config = _config_for_repo(config, repo_spec)
            validate_profile_compatible(profile, repo_config)
            source = _resolve_repo(repo_spec, fixture, profile)
            if source is None or not source.exists():
                cases.extend(_skipped_cases(repo_spec, "repo not found"))
                continue
            workspace = temp_root / repo_spec.repo_key
            _copy_repo(source, workspace)
            try:
                summary = index_repository(workspace, repo_config)
            except Exception as exc:
                cases.extend(_error_cases(repo_spec, str(exc)))
                continue
            repo_record = _repo_record(repo_spec, source, workspace, summary, repo_config)
            repos.append(repo_record)
            for case in repo_spec.queries:
                t0 = time.perf_counter()
                try:
                    bundle = query_repository(workspace, case.query, repo_config)
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    evaluation = evaluate_case(case, bundle.results, latency_ms=latency_ms)
                    cases.append(_case_record(repo_spec.repo_key, case, evaluation))
                except Exception as exc:
                    cases.append(_error_case(repo_spec.repo_key, case, str(exc)))
        report = _report_payload(fixture, profile, config, started, repos, cases)
        if output_path is not None:
            output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if markdown_path is not None:
            from context_search_tool.quality.reports import render_markdown_report

            markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
        return report
    finally:
        if not keep_workspace:
            shutil.rmtree(temp_root, ignore_errors=True)


def _resolve_repo(repo: QualityRepo, fixture: QualityFixture, profile: str) -> Path | None:
    if profile == "ci":
        if not repo.snapshot_path:
            raise ValueError(f"ci profile requires snapshot_path for repo {repo.repo_key}")
        return _resolve_snapshot_path(fixture.path, repo.snapshot_path)
    if repo.snapshot_path:
        return _resolve_snapshot_path(fixture.path, repo.snapshot_path)
    if repo.path_env and os.environ.get(repo.path_env):
        return Path(os.environ[repo.path_env])
    if repo.repo_dir_name and os.environ.get("CST_SMOKE_REPOS_DIR"):
        return Path(os.environ["CST_SMOKE_REPOS_DIR"]) / repo.repo_dir_name
    return None


def _resolve_snapshot_path(fixture_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidate = fixture_path.parent / path
    return candidate if candidate.exists() else Path.cwd() / path


def _config_for_repo(base_config: ToolConfig, repo: QualityRepo) -> ToolConfig:
    config = base_config
    raw = repo.default_config
    if not raw:
        return config
    if "embedding" in raw:
        config = replace(config, embedding=replace(config.embedding, **raw["embedding"]))
    if "query_planner" in raw:
        config = replace(config, query_planner=replace(config.query_planner, **raw["query_planner"]))
    if "retrieval" in raw:
        config = replace(config, retrieval=replace(config.retrieval, **raw["retrieval"]))
    if "index" in raw:
        config = replace(config, index=replace(config.index, **raw["index"]))
    return config


def _copy_repo(source: Path, workspace: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in EXCLUDE_DIRS}

    shutil.copytree(source, workspace, ignore=ignore)


def _repo_record(repo: QualityRepo, source: Path, workspace: Path, summary: Any, config: ToolConfig) -> dict[str, Any]:
    manifest = load_manifest(workspace)
    return {
        "repo_key": repo.repo_key,
        "source": {
            "type": "snapshot_path" if repo.snapshot_path else "external",
            "path": str(source),
            "git_commit": _git_commit(source),
            "content_hash": _content_identity(source),
        },
        "workspace": {"path": str(workspace), "copied": True},
        "index": {
            "manifest_schema_version": manifest.schema_version,
            "embedding_config_hash": manifest.embedding_config_hash,
            "config_hash": _config_hash(config),
            "files_indexed": summary.files_indexed,
            "chunks_indexed": summary.chunks_indexed,
        },
    }


def _case_record(repo_key: str, case: Any, evaluation: Any) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "status": evaluation.status,
        "metrics": evaluation.metrics,
        "top_results": evaluation.top_results,
        "failures": evaluation.failures,
    }


def _skipped_cases(repo: QualityRepo, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "repo_key": repo.repo_key,
            "case_id": case.case_id,
            "query": case.query,
            "tags": list(case.tags),
            "gate": case.gate.value,
            "status": "skipped",
            "metrics": {},
            "top_results": [],
            "failures": [reason],
        }
        for case in repo.queries
    ]


def _error_cases(repo: QualityRepo, reason: str) -> list[dict[str, Any]]:
    return [_error_case(repo.repo_key, case, reason) for case in repo.queries]


def _error_case(repo_key: str, case: Any, reason: str) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "status": "error",
        "metrics": {},
        "top_results": [],
        "failures": [reason],
    }


def _report_payload(
    fixture: QualityFixture,
    profile: str,
    config: ToolConfig,
    generated_at: int,
    repos: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "command_args": [],
        "tool": {"name": "context-search-tool", "git_commit": _git_commit(Path.cwd()), "version": "0.1.0"},
        "fixture": {
            "path": str(fixture.path),
            "sha256": _file_sha256(fixture.path),
            "schema_version": fixture.schema_version,
            "fixture_case_count": sum(len(repo.queries) for repo in fixture.repos),
            "run_case_count": len(cases),
        },
        "profile": profile,
        "config": {"config_hash": _config_hash(config), "embedding": asdict(config.embedding)},
        "planner": {"enabled": config.query_planner.enabled},
        "aggregate": _aggregate(cases),
        "repos": repos,
        "cases": cases,
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [case["status"] for case in cases]
    return {
        "total": len(cases),
        "passed": statuses.count("pass"),
        "failed": statuses.count("fail"),
        "skipped": statuses.count("skipped"),
        "known_gaps": statuses.count("known_gap"),
        "errors": statuses.count("error"),
    }


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _config_hash(config: ToolConfig) -> str:
    payload = json.dumps(asdict(config), sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_identity(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file() and ".git" not in item.parts and ".context-search" not in item.parts:
            relative = item.relative_to(path).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(str(item.stat().st_size).encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def _git_commit(path: Path) -> str | None:
    head = path / ".git" / "HEAD"
    if not head.exists():
        return None
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref: "):
        ref_path = path / ".git" / text[5:]
        return ref_path.read_text(encoding="utf-8").strip() if ref_path.exists() else None
    return text
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
python -m pytest tests/test_quality_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/context_search_tool/quality/runner.py tests/test_quality_runner.py
git commit -m "feat: add retrieval quality runner"
```

## Task 4: Reports And Comparison

**Files:**
- Create: `src/context_search_tool/quality/reports.py`
- Create: `src/context_search_tool/quality/compare.py`
- Create: `tests/test_quality_reports.py`
- Create: `tests/test_quality_compare.py`

- [ ] **Step 1: Write failing report and comparison tests**

Create `tests/test_quality_reports.py`:

```python
from __future__ import annotations

from context_search_tool.quality.reports import render_markdown_comparison, render_markdown_report


def test_render_markdown_report_puts_failures_first() -> None:
    report = {
        "profile": "ci",
        "aggregate": {"total": 2, "passed": 1, "failed": 1, "skipped": 0, "known_gaps": 0, "errors": 0},
        "cases": [
            {"repo_key": "r", "case_id": "pass", "status": "pass", "metrics": {}, "failures": []},
            {"repo_key": "r", "case_id": "fail", "status": "fail", "metrics": {"mrr": 0.0}, "failures": ["missing target"]},
        ],
    }

    markdown = render_markdown_report(report)

    assert "# Retrieval Quality Report" in markdown
    assert "## Failures" in markdown
    assert "`r/fail`" in markdown
    assert "missing target" in markdown


def test_render_markdown_comparison_highlights_regressions() -> None:
    comparison = {
        "aggregate": {"regressed": 1, "improved": 0, "total": 1},
        "metadata_warnings": ["fixture sha256 differs"],
        "cases": [{"case_key": "repo/case", "classification": "regressed"}],
    }

    markdown = render_markdown_comparison(comparison)

    assert "# Retrieval Quality Comparison" in markdown
    assert "fixture sha256 differs" in markdown
    assert "`repo/case`" in markdown
```

Create `tests/test_quality_compare.py`:

```python
from __future__ import annotations

from context_search_tool.quality.compare import compare_reports


def _report(
    status: str,
    mrr: float,
    fixture_hash: str = "sha256:a",
    hit_at_5: bool | None = None,
    noise_top5: int = 0,
    latency_ms: int = 10,
) -> dict:
    return {
        "schema_version": 1,
        "fixture": {"sha256": fixture_hash, "schema_version": 1},
        "profile": "ci",
        "config": {"config_hash": "sha256:c", "embedding": {"provider": "hash", "model": "hash-v1", "dimensions": 384}},
        "planner": {"enabled": False},
        "repos": [{"repo_key": "repo", "source": {"content_hash": "sha256:r"}}],
        "cases": [
            {
                "repo_key": "repo",
                "case_id": "case",
                "status": status,
                "metrics": {
                    "mrr": mrr,
                    "hit_at_5": status == "pass" if hit_at_5 is None else hit_at_5,
                    "noise_top5": noise_top5,
                    "latency_ms": latency_ms,
                },
            }
        ],
    }


def test_compare_reports_classifies_pass_to_fail_as_regression() -> None:
    comparison = compare_reports(_report("pass", 1.0), _report("fail", 0.0))

    assert comparison["aggregate"]["regressed"] == 1
    assert comparison["cases"][0]["classification"] == "regressed"


def test_compare_reports_warns_on_fixture_hash_mismatch() -> None:
    comparison = compare_reports(_report("pass", 1.0, "sha256:a"), _report("pass", 1.0, "sha256:b"))

    assert "fixture sha256 differs" in comparison["metadata_warnings"]


def test_compare_reports_classifies_metric_improvement() -> None:
    comparison = compare_reports(_report("fail", 0.0, hit_at_5=False), _report("pass", 1.0, hit_at_5=True))

    assert comparison["aggregate"]["improved"] == 1


def test_compare_reports_classifies_noise_regression_and_latency_warning() -> None:
    comparison = compare_reports(
        _report("pass", 1.0, noise_top5=0, latency_ms=10),
        _report("pass", 1.0, noise_top5=2, latency_ms=30),
    )

    assert comparison["aggregate"]["regressed"] == 1
    assert comparison["cases"][0]["classification"] == "regressed"
    assert "latency increased by more than 50%" in comparison["cases"][0]["warnings"]


def test_compare_reports_preserves_skipped_classification() -> None:
    comparison = compare_reports(_report("skipped", 0.0, hit_at_5=None), _report("skipped", 0.0, hit_at_5=None))

    assert comparison["cases"][0]["classification"] == "skipped"
```

- [ ] **Step 2: Run tests to verify modules are missing**

Run:

```bash
python -m pytest tests/test_quality_reports.py tests/test_quality_compare.py -q
```

Expected: FAIL because report and compare modules do not exist.

- [ ] **Step 3: Implement Markdown report rendering**

Create `src/context_search_tool/quality/reports.py`:

```python
from __future__ import annotations

from typing import Any


def render_markdown_report(report: dict[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    lines = [
        "# Retrieval Quality Report",
        "",
        f"Profile: `{report.get('profile', '')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in ("total", "passed", "failed", "skipped", "known_gaps", "errors"):
        lines.append(f"| {key} | {aggregate.get(key, 0)} |")
    failures = [case for case in report.get("cases", []) if case.get("status") in {"fail", "error"}]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("No failures.")
    for case in failures:
        lines.append(f"- `{case.get('repo_key')}/{case.get('case_id')}` status=`{case.get('status')}`")
        for failure in case.get("failures", []):
            lines.append(f"  - {failure}")
    known_gaps = [case for case in report.get("cases", []) if case.get("status") == "known_gap"]
    lines.extend(["", "## Known Gaps", ""])
    if not known_gaps:
        lines.append("No known gaps.")
    for case in known_gaps:
        lines.append(f"- `{case.get('repo_key')}/{case.get('case_id')}`")
    return "\n".join(lines) + "\n"


def render_markdown_comparison(comparison: dict[str, Any]) -> str:
    aggregate = comparison.get("aggregate", {})
    lines = [
        "# Retrieval Quality Comparison",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in ("total", "improved", "regressed", "new_case", "removed_case"):
        lines.append(f"| {key} | {aggregate.get(key, 0)} |")
    warnings = comparison.get("metadata_warnings", [])
    lines.extend(["", "## Metadata Warnings", ""])
    if not warnings:
        lines.append("No metadata warnings.")
    for warning in warnings:
        lines.append(f"- {warning}")
    regressions = [case for case in comparison.get("cases", []) if case.get("classification") == "regressed"]
    lines.extend(["", "## Regressions", ""])
    if not regressions:
        lines.append("No regressions.")
    for case in regressions:
        lines.append(f"- `{case.get('case_key')}`")
        for warning in case.get("warnings", []):
            lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Implement report comparison**

Create `src/context_search_tool/quality/compare.py`:

```python
from __future__ import annotations

from typing import Any


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    warnings = _metadata_warnings(baseline, candidate)
    baseline_cases = {_case_key(case): case for case in baseline.get("cases", [])}
    candidate_cases = {_case_key(case): case for case in candidate.get("cases", [])}
    all_keys = sorted(set(baseline_cases) | set(candidate_cases))
    cases = []
    for key in all_keys:
        base = baseline_cases.get(key)
        cand = candidate_cases.get(key)
        classification = _classification(base, cand)
        cases.append(
            {
                "case_key": key,
                "classification": classification,
                "baseline_status": None if base is None else base.get("status"),
                "candidate_status": None if cand is None else cand.get("status"),
                "warnings": _case_warnings(base, cand),
            }
        )
    return {
        "schema_version": 1,
        "metadata_warnings": warnings,
        "aggregate": _aggregate(cases),
        "cases": cases,
    }


def _case_key(case: dict[str, Any]) -> str:
    return f"{case.get('repo_key')}/{case.get('case_id')}"


def _classification(base: dict[str, Any] | None, cand: dict[str, Any] | None) -> str:
    if base is None:
        return "new_case"
    if cand is None:
        return "removed_case"
    base_status = base.get("status")
    cand_status = cand.get("status")
    if base_status == "skipped" and cand_status == "skipped":
        return "skipped"
    if base_status == "pass" and cand_status == "fail":
        return "regressed"
    if base_status == "fail" and cand_status == "pass":
        return "improved"
    base_metrics = base.get("metrics", {})
    cand_metrics = cand.get("metrics", {})
    if base_metrics.get("hit_at_5") is False and cand_metrics.get("hit_at_5") is True:
        return "improved"
    if base_metrics.get("hit_at_5") is True and cand_metrics.get("hit_at_5") is False:
        return "regressed"
    if _mrr_drop(base_metrics, cand_metrics) > 0.25:
        return "regressed"
    if cand_metrics.get("noise_top5", 0) - base_metrics.get("noise_top5", 0) >= 2:
        return "regressed"
    return "unchanged_pass" if cand_status == "pass" else "unchanged_fail"


def _mrr_drop(base_metrics: dict[str, Any], cand_metrics: dict[str, Any]) -> float:
    return float(base_metrics.get("mrr") or 0.0) - float(cand_metrics.get("mrr") or 0.0)


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "improved": sum(1 for case in cases if case["classification"] == "improved"),
        "regressed": sum(1 for case in cases if case["classification"] == "regressed"),
        "new_case": sum(1 for case in cases if case["classification"] == "new_case"),
        "removed_case": sum(1 for case in cases if case["classification"] == "removed_case"),
        "skipped": sum(1 for case in cases if case["classification"] == "skipped"),
        "total": len(cases),
    }


def _metadata_warnings(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if baseline.get("schema_version") != candidate.get("schema_version"):
        warnings.append("report schema_version differs")
    if baseline.get("fixture", {}).get("sha256") != candidate.get("fixture", {}).get("sha256"):
        warnings.append("fixture sha256 differs")
    if baseline.get("profile") != candidate.get("profile"):
        warnings.append("profile differs")
    if baseline.get("config", {}).get("config_hash") != candidate.get("config", {}).get("config_hash"):
        warnings.append("config hash differs")
    if baseline.get("config", {}).get("embedding") != candidate.get("config", {}).get("embedding"):
        warnings.append("embedding config differs")
    if baseline.get("planner") != candidate.get("planner"):
        warnings.append("planner config differs")
    if _repo_identity(baseline) != _repo_identity(candidate):
        warnings.append("repo identity differs")
    return warnings


def _repo_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key"): repo.get("source", {}).get("content_hash")
        for repo in report.get("repos", [])
    }


def _case_warnings(base: dict[str, Any] | None, cand: dict[str, Any] | None) -> list[str]:
    if base is None or cand is None:
        return []
    base_latency = (base.get("metrics") or {}).get("latency_ms")
    cand_latency = (cand.get("metrics") or {}).get("latency_ms")
    if isinstance(base_latency, (int, float)) and base_latency > 0 and isinstance(cand_latency, (int, float)):
        if cand_latency > base_latency * 1.5:
            return ["latency increased by more than 50%"]
    return []
```

- [ ] **Step 5: Run report and compare tests**

Run:

```bash
python -m pytest tests/test_quality_reports.py tests/test_quality_compare.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/context_search_tool/quality/reports.py src/context_search_tool/quality/compare.py tests/test_quality_reports.py tests/test_quality_compare.py
git commit -m "feat: add retrieval quality reports and comparison"
```

## Task 5: CLI Surface

**Files:**
- Create: `src/context_search_tool/quality/__main__.py`
- Modify: `src/context_search_tool/cli.py`
- Create: `tests/test_quality_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_quality_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app


def test_quality_run_cli_writes_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App { String targetToken; }\n", encoding="utf-8")
    fixture = tmp_path / "queries.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "snapshot_path": str(repo),
                        "profiles": ["ci"],
                        "queries": [
                            {
                                "id": "target",
                                "query": "targetToken",
                                "expected_top_k": [{"path": "App.java", "top_k": 5}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "quality.json"

    result = CliRunner().invoke(app, ["quality", "run", str(fixture), "--profile", "ci", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["aggregate"]["passed"] == 1


def test_quality_compare_cli_writes_comparison(tmp_path: Path) -> None:
    report = {
        "schema_version": 1,
        "fixture": {"sha256": "sha256:a", "schema_version": 1},
        "profile": "ci",
        "config": {"config_hash": "sha256:c"},
        "repos": [],
        "cases": [],
    }
    baseline = tmp_path / "base.json"
    candidate = tmp_path / "head.json"
    output = tmp_path / "comparison.json"
    baseline.write_text(json.dumps(report), encoding="utf-8")
    candidate.write_text(json.dumps(report), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["quality", "compare", "--baseline", str(baseline), "--candidate", str(candidate), "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
```

- [ ] **Step 2: Run CLI tests to verify command is missing**

Run:

```bash
python -m pytest tests/test_quality_cli.py -q
```

Expected: FAIL because `quality` command is not registered.

- [ ] **Step 3: Implement quality module CLI**

Create `src/context_search_tool/quality/__main__.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import typer

from context_search_tool.quality.compare import compare_reports
from context_search_tool.quality.runner import run_quality_fixture

quality_app = typer.Typer(help="Retrieval quality evaluation tools", no_args_is_help=True)


@quality_app.command("run")
def run(
    fixture: Path,
    profile: str = typer.Option("ci", "--profile"),
    output: Path = typer.Option(..., "--output"),
    markdown: Path | None = typer.Option(None, "--markdown"),
) -> None:
    report = run_quality_fixture(fixture, profile=profile, output_path=output, markdown_path=markdown)
    typer.echo(
        f"Quality run complete: total={report['aggregate']['total']} "
        f"passed={report['aggregate']['passed']} failed={report['aggregate']['failed']}"
    )


@quality_app.command("compare")
def compare(
    baseline: Path = typer.Option(..., "--baseline"),
    candidate: Path = typer.Option(..., "--candidate"),
    output: Path = typer.Option(..., "--output"),
    markdown: Path | None = typer.Option(None, "--markdown"),
) -> None:
    comparison = compare_reports(
        json.loads(baseline.read_text(encoding="utf-8")),
        json.loads(candidate.read_text(encoding="utf-8")),
    )
    output.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    if markdown is not None:
        from context_search_tool.quality.reports import render_markdown_comparison

        markdown.write_text(render_markdown_comparison(comparison), encoding="utf-8")
    typer.echo(
        f"Quality comparison complete: regressed={comparison['aggregate']['regressed']} "
        f"improved={comparison['aggregate']['improved']}"
    )


if __name__ == "__main__":
    quality_app()
```

- [ ] **Step 4: Register sub-app in main CLI**

Modify `src/context_search_tool/cli.py` after `app = typer.Typer(...)`:

```python
from context_search_tool.quality.__main__ import quality_app

app.add_typer(quality_app, name="quality")
```

Keep import placement compatible with lint-free module import. If circular imports appear, move the import below `app = typer.Typer(...)`.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
python -m pytest tests/test_quality_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/context_search_tool/quality/__main__.py src/context_search_tool/cli.py tests/test_quality_cli.py
git commit -m "feat: add retrieval quality CLI"
```

## Task 6: Feedback Log Summary

**Files:**
- Create: `src/context_search_tool/quality/feedback.py`
- Modify: `src/context_search_tool/quality/__main__.py`
- Create: `tests/test_quality_feedback.py`

- [ ] **Step 1: Write failing feedback tests**

Create `tests/test_quality_feedback.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from context_search_tool.quality.feedback import summarize_feedback_log


def test_feedback_summary_redacts_queries_by_default(tmp_path: Path) -> None:
    log = tmp_path / "mcp_calls.jsonl"
    log.write_text(
        json.dumps({"ok": True, "query": "secret customer endpoint", "result_count": 2, "top_score": 3.0}) + "\n"
        + json.dumps({"ok": False, "query": "another secret", "error_code": "boom", "result_count": 0}) + "\n",
        encoding="utf-8",
    )

    summary = summarize_feedback_log(log)

    assert summary["total_calls"] == 2
    assert summary["ok_calls"] == 1
    assert summary["error_calls"] == 1
    assert "queries" not in summary
    assert "query_terms" not in summary


def test_feedback_summary_can_include_terms_when_explicit(tmp_path: Path) -> None:
    log = tmp_path / "mcp_calls.jsonl"
    log.write_text(json.dumps({"ok": True, "query": "alpha alpha beta", "result_count": 1}) + "\n", encoding="utf-8")

    summary = summarize_feedback_log(log, include_query_terms=True)

    assert summary["query_terms"]["alpha"] == 2
    assert summary["query_terms"]["beta"] == 1
```

- [ ] **Step 2: Run feedback tests to verify module is missing**

Run:

```bash
python -m pytest tests/test_quality_feedback.py -q
```

Expected: FAIL because `context_search_tool.quality.feedback` does not exist.

- [ ] **Step 3: Implement feedback summary**

Create `src/context_search_tool/quality/feedback.py`:

```python
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


def summarize_feedback_log(
    path: Path,
    include_query_terms: bool = False,
    include_query_examples: bool = False,
    max_examples: int = 10,
) -> dict[str, Any]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    result: dict[str, Any] = {
        "total_calls": len(events),
        "ok_calls": sum(1 for event in events if event.get("ok") is True),
        "error_calls": sum(1 for event in events if event.get("ok") is not True),
        "empty_result_calls": sum(1 for event in events if event.get("result_count") == 0),
        "planner_status": dict(Counter(_planner_status(event) for event in events if _planner_status(event))),
        "embedding": dict(Counter(_embedding_key(event) for event in events if _embedding_key(event))),
    }
    top_scores = [event.get("top_score") for event in events if isinstance(event.get("top_score"), (int, float))]
    if top_scores:
        result["top_score"] = {"min": min(top_scores), "max": max(top_scores), "avg": sum(top_scores) / len(top_scores)}
    if include_query_terms:
        terms: Counter[str] = Counter()
        for event in events:
            terms.update(_query_terms(str(event.get("query", ""))))
        result["query_terms"] = dict(terms.most_common(25))
    if include_query_examples:
        result["queries"] = [event.get("query", "") for event in events[:max_examples]]
    return result


def _planner_status(event: dict[str, Any]) -> str:
    planner = event.get("planner")
    if not isinstance(planner, dict):
        return ""
    return str(planner.get("status") or "")


def _embedding_key(event: dict[str, Any]) -> str:
    embedding = event.get("embedding")
    if not isinstance(embedding, dict):
        return ""
    provider = embedding.get("provider")
    model = embedding.get("model")
    if not provider and not model:
        return ""
    return f"{provider or ''}/{model or ''}"


def _query_terms(query: str) -> list[str]:
    return [part.lower() for part in query.replace("/", " ").replace("_", " ").split() if part]
```

- [ ] **Step 4: Add CLI feedback command**

Modify `src/context_search_tool/quality/__main__.py`:

```python
@quality_app.command("feedback")
def feedback(
    log_path: Path,
    output: Path = typer.Option(..., "--output"),
    include_query_terms: bool = typer.Option(False, "--include-query-terms"),
    include_query_examples: bool = typer.Option(False, "--include-query-examples"),
) -> None:
    from context_search_tool.quality.feedback import summarize_feedback_log

    summary = summarize_feedback_log(
        log_path,
        include_query_terms=include_query_terms,
        include_query_examples=include_query_examples,
    )
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Feedback summary complete: total={summary['total_calls']}")
```

- [ ] **Step 5: Run feedback tests**

Run:

```bash
python -m pytest tests/test_quality_feedback.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add src/context_search_tool/quality/feedback.py src/context_search_tool/quality/__main__.py tests/test_quality_feedback.py
git commit -m "feat: add retrieval quality feedback summary"
```

## Task 7: Committed Fixture And Existing Suite Migration

**Files:**
- Create: `tests/fixtures/retrieval_quality/queries.json`
- Modify: `tests/test_generic_baseline_quality.py`

- [ ] **Step 1: Add a small v1 quality fixture**

Create `tests/fixtures/retrieval_quality/queries.json`:

```json
{
  "schema_version": 1,
  "repos": [
    {
      "repo_key": "program_tool_snapshot",
      "snapshot_path": "tests/fixtures/real_projects/program_tool",
      "profiles": ["ci", "smoke"],
      "queries": [
        {
          "id": "qrcode-entrypoint",
          "query": "QRCode generate scan camera decode paste image qrcode-reader",
          "tags": ["frontend", "entrypoint"],
          "gate": "required",
          "expected_top_k": [
            {"path": "src/views/qrcode/QRCodeTool.vue", "top_k": 5}
          ],
          "expected_any_top_k": [
            {
              "matchers": [
                {"path": "src/utils/qrcodeUtils.ts"},
                {"path": "src/types/qrcode-reader.d.ts"}
              ],
              "top_k": 5
            }
          ],
          "absent_top_k": [
            {"path": "package-lock.json", "top_k": 5}
          ]
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Add a shared-helper smoke test or migrate one existing helper**

In `tests/test_generic_baseline_quality.py`, import `Matcher` and use it in one focused helper test without changing existing real-project gates:

```python
from context_search_tool.quality.cases import Matcher


def test_quality_matcher_supports_existing_glob_expectations() -> None:
    matcher = Matcher.from_raw("storage/*.go")

    assert matcher.matches("storage/local.go")
    assert not matcher.matches("handler/upload.go")
```

- [ ] **Step 3: Run fixture and migration tests**

Run:

```bash
python -m pytest tests/test_quality_cases.py tests/test_quality_runner.py tests/test_generic_baseline_quality.py -q
```

Expected: PASS or existing slow/integration tests skipped according to current pytest markers and local repo availability. If unmarked real-project tests run slowly, use:

```bash
python -m pytest tests/test_quality_cases.py tests/test_quality_runner.py tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 4: Run quality CLI against committed fixture**

Run:

```bash
python -m context_search_tool.quality run tests/fixtures/retrieval_quality/queries.json --profile ci --output /tmp/cst-quality.json
python -m context_search_tool.quality compare --baseline /tmp/cst-quality.json --candidate /tmp/cst-quality.json --output /tmp/cst-quality-compare.json
```

Expected: both commands exit 0. `/tmp/cst-quality.json` contains `"profile": "ci"` and at least one case. `/tmp/cst-quality-compare.json` contains `"regressed": 0`.

- [ ] **Step 5: Commit Task 7**

```bash
git add tests/fixtures/retrieval_quality/queries.json tests/test_generic_baseline_quality.py
git commit -m "test: add retrieval quality fixture"
```

## Task 8: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused quality test suite**

Run:

```bash
python -m pytest \
  tests/test_quality_cases.py \
  tests/test_quality_metrics.py \
  tests/test_quality_runner.py \
  tests/test_quality_reports.py \
  tests/test_quality_compare.py \
  tests/test_quality_feedback.py \
  tests/test_quality_cli.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run existing default test suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS with the repository's existing skipped tests unchanged.

- [ ] **Step 3: Run CLI smoke**

Run:

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json --profile ci --output /tmp/cst-quality.json --markdown /tmp/cst-quality.md
cst quality compare --baseline /tmp/cst-quality.json --candidate /tmp/cst-quality.json --output /tmp/cst-quality-compare.json
```

Expected: both commands exit 0. The Markdown file starts with `# Retrieval Quality Report`. The comparison JSON has no regressions.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only quality package, quality tests, fixture, and CLI changes are present.

- [ ] **Step 5: Commit final cleanup if needed**

If verification required small fixes, commit them:

```bash
git add src/context_search_tool/quality src/context_search_tool/cli.py tests/test_quality_*.py tests/fixtures/retrieval_quality/queries.json tests/test_generic_baseline_quality.py
git commit -m "test: verify retrieval quality scoring system"
```

If no files changed after verification, do not create an empty commit.

## Self-Review Checklist

- [ ] The plan implements the spec's core evaluator, runner, reports, compare, profile checks, safe copy behavior, and feedback privacy defaults.
- [ ] The plan does not modify retrieval ranking.
- [ ] Every task includes tests before implementation.
- [ ] Every task includes exact verification commands.
- [ ] Existing quality tests remain in place during migration.
- [ ] CI profile rejects model/network/planner dependencies.
- [ ] Runner indexes copied workspaces, not source repositories.
- [ ] JSON report includes fixture/config/repo metadata needed for comparison.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-retrieval-quality-scoring-system.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, with checkpoints after each batch.
