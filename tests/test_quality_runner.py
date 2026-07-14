import json
import ntpath
import os
import shutil
import stat
import subprocess
import sys
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote

import pytest

import context_search_tool.quality.runner as quality_runner
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
from context_search_tool.models import (
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    SemanticMatch,
)
from context_search_tool.quality.cases import (
    Gate,
    ProfileExpectation,
    QualityCase,
    QualityRepo,
)
from context_search_tool.quality.metrics import CaseEvaluation
from context_search_tool.quality.runner import (
    ResolvedSource,
    _content_identity,
    _copy_source_repo,
    _effective_config,
    _git_commit,
    _resolve_repo_source,
    run_quality_fixture,
)
from context_search_tool.retrieval import QueryBundle


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    fixture_path = tmp_path / "quality.json"
    fixture_path.write_text(json.dumps(data), encoding="utf-8")
    return fixture_path


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_source_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src" / "App.java").write_text(
        """
        package sample;

        class App {
            String targetToken() {
                return "targetToken";
            }
        }
        """,
        encoding="utf-8",
    )
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("abc123\n", encoding="utf-8")
    (source / ".context-search").mkdir()
    (source / ".context-search" / "old.txt").write_text("old index\n", encoding="utf-8")
    (source / ".gitignore").write_text(".context-search/\n", encoding="utf-8")
    return source


def _patch_runner_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    captured: list[tuple[Path, ToolConfig]],
) -> None:
    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append((repo, config))
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    def fake_query(
        repo: Path,
        query: str,
        config: ToolConfig,
    ) -> QueryBundle:
        return QueryBundle(
            query=query,
            expanded_tokens=[],
            results=[],
            followup_keywords=[],
        )

    monkeypatch.setattr(
        "context_search_tool.quality.runner.index_repository",
        fake_index,
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="test-hash"),
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fake_query,
    )


def _write_successful_ci_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    source = _write_source_repo(tmp_path / "fixture-source")
    fixture = _write_fixture(
        tmp_path,
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
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    return fixture


def _passing_evaluation() -> CaseEvaluation:
    return CaseEvaluation(
        case_id="case",
        status="pass",
        metrics={},
        failures=[],
        top_results=[],
    )


def _runtime_result(
    path: str,
    semantic_matches: list[SemanticMatch] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content="class App {}",
        score=1.0,
        score_parts={},
        reasons=[],
        followup_keywords=[],
        semantic_matches=list(semantic_matches or []),
    )


def _profile_case(
    expectation: ProfileExpectation,
    gate: Gate = Gate.REQUIRED,
) -> QualityCase:
    return QualityCase(
        case_id="case",
        query="query",
        gate=gate,
        profile_expectations={"selected": expectation},
    )


def _runtime_bundle(
    results: list[RetrievalResult] | None = None,
    *,
    planner_status: str = "disabled",
    variant_retrieval_status: str = "original_only",
) -> QueryBundle:
    return QueryBundle(
        query="query",
        expanded_tokens=[],
        results=list(results or []),
        followup_keywords=[],
        planner=QueryPlan("query", status=planner_status),
        variant_retrieval_status=variant_retrieval_status,
    )


def test_profile_expectations_fail_case_when_hybrid_did_not_execute() -> None:
    case = QualityCase(
        case_id="case",
        query="query",
        gate=Gate.REQUIRED,
        profile_expectations={
            "p1_hybrid_bge": ProfileExpectation(
                planner_status="ok",
                variant_retrieval_status="hybrid",
                top_result_planner_semantic_match=True,
            )
        },
    )
    bundle = QueryBundle(
        query="query",
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
        planner=QueryPlan("query", status="fallback"),
        query_variants=[QueryVariant("original", "query", "original")],
        variant_retrieval_status="original_only",
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "p1_hybrid_bge",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "planner_status expected ok, got fallback",
        "variant_retrieval_status expected hybrid, got original_only",
        "top_result_planner_semantic_match expected true, got false",
    ]


def test_profile_expectations_pass_with_actual_planner_semantic_top_result() -> None:
    case = QualityCase(
        case_id="case",
        query="query",
        gate=Gate.REQUIRED,
        profile_expectations={
            "p1_hybrid_bge": ProfileExpectation(
                planner_status="ok",
                variant_retrieval_status="hybrid",
                top_result_planner_semantic_match=True,
            )
        },
    )
    bundle = QueryBundle(
        query="query",
        expanded_tokens=[],
        results=[
            RetrievalResult(
                file_path=Path("App.java"),
                start_line=1,
                end_line=1,
                content="class App {}",
                score=1.0,
                score_parts={},
                reasons=[],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.9)],
            )
        ],
        followup_keywords=[],
        planner=QueryPlan("query", status="ok"),
        query_variants=[
            QueryVariant("original", "query", "original"),
            QueryVariant("planner:0", "app", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "p1_hybrid_bge",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "pass"
    assert evaluation.failures == []


@pytest.mark.parametrize(
    ("semantic_matches", "expected_status", "expected_failures"),
    [
        (
            [SemanticMatch("planner:0", 0.9)],
            "fail",
            [
                "top_result_planner_semantic_match expected false, got true"
            ],
        ),
        ([], "pass", []),
    ],
    ids=["actual-true-fails", "actual-false-passes"],
)
def test_profile_expectations_treat_false_top_match_as_meaningful(
    semantic_matches: list[SemanticMatch],
    expected_status: str,
    expected_failures: list[str],
) -> None:
    case = _profile_case(
        ProfileExpectation(top_result_planner_semantic_match=False)
    )
    bundle = _runtime_bundle(
        [_runtime_result("App.java", semantic_matches)]
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "selected",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == expected_status
    assert evaluation.failures == expected_failures


def test_profile_expectations_require_planner_match_in_top_result() -> None:
    case = _profile_case(
        ProfileExpectation(top_result_planner_semantic_match=True)
    )
    bundle = _runtime_bundle(
        [
            _runtime_result(
                "First.java",
                [SemanticMatch("original", 0.9)],
            ),
            _runtime_result(
                "Second.java",
                [SemanticMatch("planner:0", 0.8)],
            ),
        ]
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "selected",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "top_result_planner_semantic_match expected true, got false"
    ]


def test_profile_expectations_preserve_existing_required_failures() -> None:
    case = _profile_case(
        ProfileExpectation(
            planner_status="ok",
            variant_retrieval_status="hybrid",
            top_result_planner_semantic_match=True,
        )
    )
    bundle = _runtime_bundle(
        [
            _runtime_result(
                "App.java",
                [SemanticMatch("planner:0", 0.9)],
            )
        ],
        planner_status="ok",
        variant_retrieval_status="hybrid",
    )
    existing = CaseEvaluation(
        case_id="case",
        status="fail",
        metrics={},
        failures=["existing relevance failure"],
        top_results=[],
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "selected",
        bundle,
        existing,
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == ["existing relevance failure"]


@pytest.mark.parametrize(
    "profile_expectations",
    [
        {},
        {"other": ProfileExpectation(planner_status="ok")},
    ],
    ids=["absent", "wrong-profile"],
)
def test_profile_expectations_without_selected_profile_are_noop(
    profile_expectations: dict[str, ProfileExpectation],
) -> None:
    case = QualityCase(
        case_id="case",
        query="query",
        profile_expectations=profile_expectations,
    )
    evaluation = _passing_evaluation()

    actual = quality_runner._apply_profile_expectations(
        case,
        "selected",
        QueryBundle("query", [], [], []),
        evaluation,
    )

    assert actual is evaluation


@pytest.mark.parametrize(
    ("gate", "status"),
    [
        (Gate.KNOWN_GAP, "known_gap"),
        (Gate.INFORMATIONAL, "informational"),
    ],
)
def test_profile_expectations_preserve_non_required_status(
    gate: Gate,
    status: str,
) -> None:
    case = _profile_case(
        ProfileExpectation(planner_status="ok"),
        gate,
    )
    evaluation = CaseEvaluation(
        case_id="case",
        status=status,
        metrics={},
        failures=[],
        top_results=[],
    )

    actual = quality_runner._apply_profile_expectations(
        case,
        "selected",
        _runtime_bundle(planner_status="fallback"),
        evaluation,
    )

    assert actual.status == status
    assert actual.failures == ["planner_status expected ok, got fallback"]


def test_profile_expectations_ignore_unspecified_fields() -> None:
    case = _profile_case(ProfileExpectation())
    bundle = _runtime_bundle(
        [
            _runtime_result(
                "App.java",
                [SemanticMatch("planner:0", 0.9)],
            )
        ],
        planner_status="fallback",
        variant_retrieval_status="original_only",
    )

    evaluation = quality_runner._apply_profile_expectations(
        case,
        "selected",
        bundle,
        _passing_evaluation(),
    )

    assert evaluation.status == "pass"
    assert evaluation.failures == []


def test_case_record_serializes_executed_variant_provenance() -> None:
    record = quality_runner._case_record(
        "repo",
        QualityCase(case_id="case", query="query"),
        _passing_evaluation(),
        QueryBundle(
            query="query",
            expanded_tokens=[],
            results=[],
            followup_keywords=[],
            query_variants=[
                QueryVariant("original", "query", "original"),
                QueryVariant("planner:0", "app", "planner"),
            ],
            variant_retrieval_status="hybrid",
        ),
    )

    assert record["query_variants"] == [
        {"variant_id": "original", "text": "query", "source": "original"},
        {"variant_id": "planner:0", "text": "app", "source": "planner"},
    ]
    assert record["variant_retrieval_status"] == "hybrid"


def test_nonexecuted_case_records_omit_executed_variant_provenance() -> None:
    case = QualityCase(case_id="case", query="query")
    records = [
        quality_runner._empty_case_record(
            "repo",
            case,
            "skipped",
            "repo not found",
        ),
        quality_runner._error_case_record("repo", case, "query failed"),
    ]

    assert [record["status"] for record in records] == ["skipped", "error"]
    for record in records:
        assert "query_variants" not in record
        assert "variant_retrieval_status" not in record


def test_run_quality_fixture_applies_parsed_profile_expectations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path / "fixture-source")
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {"smoke": {}},
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["smoke"],
                    "queries": [
                        {
                            "id": "runtime-gate",
                            "query": "query",
                            "profile_expectations": {
                                "smoke": {
                                    "planner_status": "ok",
                                    "variant_retrieval_status": "hybrid",
                                    "top_result_planner_semantic_match": True,
                                }
                            },
                        }
                    ],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    monkeypatch.setattr(
        quality_runner,
        "query_repository",
        lambda repo, query, config: QueryBundle(
            query=query,
            expanded_tokens=[],
            results=[
                _runtime_result(
                    "src/App.java",
                    [SemanticMatch("original", 0.9)],
                )
            ],
            followup_keywords=[],
            planner=QueryPlan(query, status="fallback"),
            query_variants=[QueryVariant("original", query, "original")],
            variant_retrieval_status="original_only",
        ),
    )

    report = run_quality_fixture(fixture, "smoke", None, None)

    record = report["cases"][0]
    assert record["gate"] == "required"
    assert record["status"] == "fail"
    assert record["failures"] == [
        "planner_status expected ok, got fallback",
        "variant_retrieval_status expected hybrid, got original_only",
        "top_result_planner_semantic_match expected true, got false",
    ]


def test_quality_runner_copies_repo_without_mutating_source(tmp_path: Path) -> None:
    source = _write_source_repo(tmp_path)
    before = _snapshot_files(source)
    fixture = _write_fixture(
        tmp_path,
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
        },
    )

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    assert report["aggregate"]["total"] == 1
    assert report["aggregate"]["passed"] == 1
    assert report["fixture"]["fixture_case_count"] == 1
    assert report["fixture"]["run_case_count"] == 1
    assert report["config"]["embedding"]["provider"] == "hash"
    assert _snapshot_files(source) == before

    repo_record = report["repos"][0]
    assert repo_record["workspace"]["copied"] is True
    assert repo_record["workspace"]["preserved"] is True
    assert repo_record["index"]["embedding_config_hash"]
    assert repo_record["index"]["config_hash"].startswith("sha256:")

    workspace = Path(repo_record["workspace"]["path"])
    assert workspace.exists()
    assert not (workspace / ".git").exists()
    assert not (workspace / ".context-search" / "old.txt").exists()


def test_quality_runner_records_git_commit_from_worktree_gitdir_file(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main"
    source = tmp_path / "source"
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    (main / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(main),
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=quality@example.test",
            "commit",
            "-q",
            "-m",
            "initial",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", str(source)],
        check=True,
    )
    expected = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert _git_commit(source) == expected


def test_git_commit_rejects_symlinked_dot_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "external.git"
    external.mkdir()
    (external / "HEAD").write_text(f"{'a' * 40}\n", encoding="utf-8")
    (repo / ".git").symlink_to(external, target_is_directory=True)

    assert _git_commit(repo) is None


def test_git_commit_rejects_refs_directory_symlink_outside_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    gitdir.mkdir(parents=True)
    external_refs = tmp_path / "external-refs"
    (external_refs / "heads").mkdir(parents=True)
    (external_refs / "heads" / "main").write_text(
        f"{'d' * 40}\n",
        encoding="utf-8",
    )
    (gitdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (gitdir / "refs").symlink_to(external_refs, target_is_directory=True)

    assert _git_commit(repo) is None


@pytest.mark.parametrize("gitdir_kind", ["absolute", "traversal"])
def test_git_commit_rejects_unowned_gitdir_indirection(
    tmp_path: Path,
    gitdir_kind: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "external.git"
    external.mkdir()
    (external / "HEAD").write_text(f"{'b' * 40}\n", encoding="utf-8")
    raw_gitdir = str(external) if gitdir_kind == "absolute" else "../external.git"
    (repo / ".git").write_text(f"gitdir: {raw_gitdir}\n", encoding="utf-8")

    assert _git_commit(repo) is None


@pytest.mark.parametrize("commondir_kind", ["absolute", "traversal"])
def test_git_commit_rejects_commondir_outside_linked_worktree_metadata(
    tmp_path: Path,
    commondir_kind: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    common_gitdir = tmp_path / "common.git"
    gitdir = common_gitdir / "worktrees" / "repo"
    gitdir.mkdir(parents=True)
    external = tmp_path / "external.git"
    external.mkdir()
    oid = "c" * 40
    ref = "refs/heads/main"
    (external / "packed-refs").write_text(f"{oid} {ref}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text(f"ref: {ref}\n", encoding="utf-8")
    (gitdir / "gitdir").write_text(str(repo / ".git") + "\n", encoding="utf-8")
    raw_commondir = (
        str(external)
        if commondir_kind == "absolute"
        else "../../../external.git"
    )
    (gitdir / "commondir").write_text(raw_commondir + "\n", encoding="utf-8")
    (repo / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert _git_commit(repo) is None


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        pytest.param("<absolute>", id="absolute"),
        pytest.param("refs/heads/../../sentinel", id="traversal"),
        pytest.param(r"refs\heads\main", id="backslash"),
        pytest.param("refs/heads/bad\x01name", id="control"),
        pytest.param("refs/heads/bad:name", id="invalid-component"),
    ],
)
def test_git_commit_rejects_unsafe_symbolic_ref_paths(
    tmp_path: Path,
    unsafe_ref: str,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    gitdir.mkdir(parents=True)
    oid = "a" * 40

    if unsafe_ref == "<absolute>":
        sentinel = tmp_path / "sentinel"
        ref = str(sentinel)
    elif unsafe_ref == "refs/heads/../../sentinel":
        (gitdir / "refs" / "heads").mkdir(parents=True)
        sentinel = gitdir / "sentinel"
        ref = unsafe_ref
    else:
        sentinel = gitdir / unsafe_ref
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        ref = unsafe_ref
    sentinel.write_text(f"{oid}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text(f"ref: {ref}\n", encoding="utf-8")

    assert _git_commit(repo) is None


@pytest.mark.parametrize(
    "storage",
    [
        pytest.param("detached", id="detached-head"),
        pytest.param("loose", id="loose-ref"),
        pytest.param("packed", id="packed-ref"),
    ],
)
def test_git_commit_rejects_non_object_id_contents(
    tmp_path: Path,
    storage: str,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    gitdir.mkdir(parents=True)
    if storage == "detached":
        (gitdir / "HEAD").write_text("private metadata\n", encoding="utf-8")
    else:
        ref = "refs/heads/main"
        (gitdir / "HEAD").write_text(f"ref: {ref}\n", encoding="utf-8")
        if storage == "loose":
            ref_path = gitdir / ref
            ref_path.parent.mkdir(parents=True)
            ref_path.write_text("private metadata\n", encoding="utf-8")
        else:
            (gitdir / "packed-refs").write_text(
                f"private-metadata {ref}\n",
                encoding="utf-8",
            )

    assert _git_commit(repo) is None


def test_git_commit_indirection_never_returns_raw_head_contents(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    gitdir = tmp_path / "external.git"
    gitdir.mkdir()
    (gitdir / "HEAD").write_text("private metadata\n", encoding="utf-8")
    (repo / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert _git_commit(repo) is None


def test_git_commit_rejects_malformed_gitdir_indirection(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: bad\x00path\n", encoding="utf-8")

    assert _git_commit(repo) is None


@pytest.mark.parametrize("oid", ["a" * 40, "b" * 64], ids=["sha1", "sha256"])
@pytest.mark.parametrize(
    "storage",
    [
        pytest.param("detached", id="detached-head"),
        pytest.param("loose", id="loose-ref"),
        pytest.param("packed", id="packed-ref"),
    ],
)
def test_git_commit_accepts_valid_object_ids(
    tmp_path: Path,
    storage: str,
    oid: str,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    gitdir.mkdir(parents=True)
    if storage == "detached":
        (gitdir / "HEAD").write_text(f"{oid}\n", encoding="utf-8")
    else:
        ref = "refs/heads/main"
        (gitdir / "HEAD").write_text(f"ref: {ref}\n", encoding="utf-8")
        if storage == "loose":
            ref_path = gitdir / ref
            ref_path.parent.mkdir(parents=True)
            ref_path.write_text(f"{oid}\n", encoding="utf-8")
        else:
            (gitdir / "packed-refs").write_text(
                f"{oid} {ref}\n",
                encoding="utf-8",
            )

    assert _git_commit(repo) == oid


@pytest.mark.skipif(
    not quality_runner._DESCRIPTOR_GIT_READ_SUPPORTED,
    reason="requires descriptor-relative no-follow reads",
)
@pytest.mark.parametrize(
    "swap_directory",
    [False, True],
    ids=["ref-file", "ref-directory"],
)
def test_git_commit_does_not_retraverse_ref_swapped_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_directory: bool,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    ref_dir = gitdir / "refs" / "race-guard-heads"
    ref_path = ref_dir / "race-guard-ref"
    ref_dir.mkdir(parents=True)
    original_oid = "a" * 40
    external_oid = "b" * 40
    external_dir = tmp_path / "external-refs"
    external_dir.mkdir()
    external_ref = external_dir / ref_path.name
    ref_path.write_text(f"{original_oid}\n", encoding="utf-8")
    external_ref.write_text(f"{external_oid}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text(
        "ref: refs/race-guard-heads/race-guard-ref\n",
        encoding="utf-8",
    )
    swap_path = ref_dir if swap_directory else ref_path
    moved_path = (
        gitdir / "original-ref-directory"
        if swap_directory
        else ref_dir / "original-ref"
    )
    external_target = external_dir if swap_directory else external_ref
    original_open = os.open
    swapped = False

    def racing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if (
            dir_fd is not None
            and os.fspath(path) == swap_path.name
            and not swapped
        ):
            swap_path.rename(moved_path)
            swap_path.symlink_to(
                external_target,
                target_is_directory=swap_directory,
            )
            swapped = True
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(quality_runner.os, "open", racing_open)

    commit = _git_commit(repo)
    assert swapped
    assert commit is None
    assert commit != external_oid


@pytest.mark.skipif(
    not quality_runner._DESCRIPTOR_GIT_READ_SUPPORTED,
    reason="requires descriptor-relative no-follow reads",
)
def test_git_commit_fails_closed_when_dot_git_boundary_is_exchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git"
    gitdir.mkdir(parents=True)
    original_oid = "a" * 40
    external_oid = "b" * 40
    (gitdir / "HEAD").write_text(f"{original_oid}\n", encoding="utf-8")
    external_gitdir = tmp_path / "external.git"
    external_gitdir.mkdir()
    (external_gitdir / "HEAD").write_text(
        f"{external_oid}\n",
        encoding="utf-8",
    )
    moved_gitdir = repo / ".git-original"
    original_resolve = Path.resolve
    original_open = os.open
    swapped = False

    def exchange_gitdir() -> None:
        nonlocal swapped
        gitdir.rename(moved_gitdir)
        external_gitdir.rename(gitdir)
        swapped = True

    def racing_resolve(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> Path:
        if path == gitdir and not swapped:
            exchange_gitdir()
        return original_resolve(path, *args, **kwargs)

    def racing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd is not None and os.fspath(path) == ".git" and not swapped:
            exchange_gitdir()
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(Path, "resolve", racing_resolve)
    monkeypatch.setattr(quality_runner.os, "open", racing_open)

    commit = _git_commit(repo)

    assert swapped
    assert commit is None
    assert commit != external_oid


def test_quality_runner_records_skip_for_missing_repo(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
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
        },
    )

    report = run_quality_fixture(
        fixture,
        profile="smoke",
        output_path=None,
        markdown_path=None,
        allow_empty=True,
    )

    assert report["aggregate"]["skipped"] == 1
    assert report["cases"][0]["status"] == "skipped"
    assert report["cases"][0]["failures"] == ["repo not found"]


def test_ci_profile_rejects_env_only_repo_even_when_env_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (external / "App.java").write_text("class App {}\n", encoding="utf-8")
    monkeypatch.setenv("CST_SMOKE_EXTERNAL_REPO", str(external))
    fixture = _write_fixture(
        tmp_path,
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
        },
    )

    with pytest.raises(ValueError, match="ci profile requires snapshot_path"):
        run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
        )


def test_quality_runner_records_query_errors(
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
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )

    def fail_query(*args: object, **kwargs: object) -> object:
        raise RuntimeError("query exploded")

    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fail_query,
    )

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        allow_empty=True,
    )

    assert report["aggregate"]["errors"] == 1
    assert report["cases"][0]["status"] == "error"
    assert report["cases"][0]["failures"] == ["query exploded"]


def test_quality_runner_contains_copy_errors_and_continues_later_repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_source = _write_source_repo(tmp_path / "first-source")
    second_source = _write_source_repo(tmp_path / "second-source")
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "first",
                    "snapshot_path": str(first_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first-case", "query": "first"}],
                },
                {
                    "repo_key": "second",
                    "snapshot_path": str(second_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second-case", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    original_copy = _copy_source_repo

    def copy_with_first_failure(source: Path, workspace: Path) -> None:
        if workspace.name == "first":
            workspace.mkdir()
            (workspace / "partial.txt").write_text("partial\n", encoding="utf-8")
            raise PermissionError("copy denied")
        original_copy(source, workspace)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "_copy_source_repo", copy_with_first_failure)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        assert [(case["case_id"], case["status"]) for case in report["cases"]] == [
            ("first-case", "error"),
            ("second-case", "pass"),
        ]
        assert report["cases"][0]["failures"] == ["copy denied"]
        assert [repo["repo_key"] for repo in report["repos"]] == [
            "first",
            "second",
        ]
        first_repo = report["repos"][0]
        assert first_repo["source"]["git_commit"] is None
        assert first_repo["source"]["content_hash"] is None
        assert first_repo["workspace"] == {"copied": False, "preserved": False}
        assert first_repo["index"] == {"status": "error"}
        assert [workspace.name for workspace, _config in captured] == ["second"]
        assert not (temp_root / "first").exists()
        assert (temp_root / "second").is_dir()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_quality_runner_retains_copied_provenance_when_index_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path).resolve()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    git_commit = "1234567890abcdef1234567890abcdef12345678"
    expected_content_hash = _content_identity(source)
    copied_workspaces: list[Path] = []

    def fail_index(repo: Path, config: ToolConfig) -> IndexSummary:
        copied_workspaces.append(repo)
        raise RuntimeError("index exploded")

    monkeypatch.setattr(quality_runner, "_git_commit", lambda path: git_commit)
    monkeypatch.setattr(quality_runner, "index_repository", fail_index)

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        allow_empty=True,
    )

    repo = report["repos"][0]
    assert repo["source"]["git_commit"] == git_commit
    assert repo["source"]["content_hash"].startswith("sha256:")
    assert repo["source"]["content_hash"] == expected_content_hash
    assert repo["workspace"] == {"copied": True, "preserved": False}
    assert repo["index"] == {"status": "error"}
    assert report["cases"][0]["status"] == "error"
    assert report["cases"][0]["attempted"] is False
    assert copied_workspaces and not copied_workspaces[0].exists()


def test_quality_runner_does_not_advertise_cleaned_failed_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path).resolve()
    temp_root = (tmp_path / "temp-root").resolve()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    copied_workspaces: list[Path] = []

    def fail_index(repo: Path, config: ToolConfig) -> IndexSummary:
        copied_workspaces.append(repo)
        raise RuntimeError("index exploded")

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "index_repository", fail_index)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
            allow_empty=True,
        )

        repo = report["repos"][0]
        assert repo["workspace"] == {"copied": True, "preserved": False}
        assert "path" not in repo["workspace"]
        assert copied_workspaces and not copied_workspaces[0].exists()
        assert str(copied_workspaces[0]) not in json.dumps(repo)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.parametrize(
    ("failure_stage", "reason"),
    [
        pytest.param("git_commit", "git metadata denied", id="git-commit"),
        pytest.param("content_identity", "identity denied", id="content-identity"),
    ],
)
def test_quality_runner_contains_provenance_setup_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    reason: str,
) -> None:
    first_source = _write_source_repo(tmp_path / "first-source").resolve()
    second_source = _write_source_repo(tmp_path / "second-source").resolve()
    temp_root = (tmp_path / "temp-root").resolve()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "first",
                    "snapshot_path": str(first_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first-case", "query": "first"}],
                },
                {
                    "repo_key": "second",
                    "snapshot_path": str(second_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second-case", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    if failure_stage == "git_commit":
        original_git_commit = quality_runner._git_commit

        def git_commit_with_first_failure(path: Path) -> str | None:
            if path == first_source:
                raise PermissionError(reason)
            return original_git_commit(path)

        monkeypatch.setattr(
            quality_runner,
            "_git_commit",
            git_commit_with_first_failure,
        )
    else:
        original_content_identity = _content_identity

        def content_identity_with_first_failure(path: Path) -> str:
            if path == first_source or path == temp_root / "first":
                raise PermissionError(reason)
            return original_content_identity(path)

        monkeypatch.setattr(
            quality_runner,
            "_content_identity",
            content_identity_with_first_failure,
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        assert [(case["case_id"], case["status"]) for case in report["cases"]] == [
            ("first-case", "error"),
            ("second-case", "pass"),
        ]
        assert report["cases"][0]["failures"] == [reason]
        assert [repo["repo_key"] for repo in report["repos"]] == [
            "first",
            "second",
        ]
        assert report["repos"][0]["index"] == {"status": "error"}
        assert [workspace.name for workspace, _config in captured] == ["second"]
        assert not (temp_root / "first").exists()
        assert (temp_root / "second").is_dir()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_canonical_profile_rebuilds_from_default_then_repo_then_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "source.txt").write_text("source\n", encoding="utf-8")
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
                    "snapshot_path": "snapshot",
                    "profiles": ["ci"],
                    "default_config": {"retrieval": {"final_top_k": 7}},
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    stale_config = ToolConfig(
        index=IndexConfig(max_file_bytes=1),
        retrieval=RetrievalConfig(final_top_k=99),
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="remote-embedding",
            dimensions=1536,
            base_url="https://embedding.example.test/v1",
            api_key_env="REMOTE_EMBEDDING_API_KEY",
        ),
        query_planner=QueryPlannerConfig(
            enabled=True,
            provider="openai-compatible",
            model="remote-planner",
            base_url="https://planner.example.test/v1",
            use_system_proxy=True,
            timeout_seconds=99,
        ),
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        config=stale_config,
    )

    effective = captured[0][1]
    assert effective.index == DEFAULT_CONFIG.index
    assert effective.embedding == DEFAULT_CONFIG.embedding
    assert effective.query_planner == DEFAULT_CONFIG.query_planner
    assert effective.retrieval.final_top_k == 7


def test_legacy_fixture_keeps_caller_base_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": ["smoke"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    caller_config = ToolConfig(
        index=IndexConfig(
            include=["*.java"],
            exclude=["vendor/**"],
            max_file_bytes=1234,
            max_full_file_bytes=987,
        ),
        retrieval=RetrievalConfig(
            semantic_top_k=17,
            lexical_top_k=19,
            final_top_k=9,
            context_before_lines=3,
            context_after_lines=4,
        ),
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="legacy-embedding",
            dimensions=768,
            base_url="https://embedding.example.test/v1",
            api_key_env="LEGACY_EMBEDDING_KEY",
        ),
        query_planner=QueryPlannerConfig(
            enabled=True,
            provider="openai-compatible",
            model="legacy-planner",
            base_url="https://planner.example.test/v1",
            use_system_proxy=True,
            timeout_seconds=21,
            max_rewritten_queries=2,
            max_keywords=7,
            max_symbol_hints=5,
        ),
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    report = run_quality_fixture(
        fixture,
        profile="smoke",
        output_path=None,
        markdown_path=None,
        config=caller_config,
    )

    effective = captured[0][1]
    repo_config = report["repos"][0]["config"]
    assert effective == caller_config
    assert report["config"]["config_hash"] == repo_config["config_hash"]
    assert report["config"]["embedding"] == repo_config["embedding"]
    assert report["planner"] == repo_config["query_planner"]


def test_non_ci_source_prefers_existing_env_then_smoke_root_then_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_repo = tmp_path / "env-repo"
    env_repo.mkdir()
    smoke_root = tmp_path / "smoke"
    smoke_repo = smoke_root / "sample"
    smoke_repo.mkdir(parents=True)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    fixture_path = tmp_path / "quality.json"
    repo = QualityRepo(
        repo_key="sample",
        path_env="CST_SAMPLE_REPO",
        repo_dir_name="sample",
        snapshot_path="snapshot",
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SAMPLE_REPO", str(env_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        env_repo.resolve(),
        "path_env",
        "CST_SAMPLE_REPO",
    )

    monkeypatch.setenv("CST_SAMPLE_REPO", str(tmp_path / "missing-env"))
    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        smoke_repo.resolve(),
        "smoke_root",
        "sample",
    )

    smoke_repo.rmdir()
    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        snapshot.resolve(),
        "snapshot_path",
        "snapshot",
    )


@pytest.mark.parametrize("profile", ["p1_vector_bge", "p1_hybrid_bge"])
def test_phase_one_source_uses_committed_snapshot_despite_external_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)
    env_repo = tmp_path / "env-repo"
    env_repo.mkdir()
    smoke_root = tmp_path / "smoke"
    (smoke_root / "embedding-ab").mkdir(parents=True)
    snapshot_path = "tests/fixtures/real_projects/embedding_ab"
    repo = QualityRepo(
        repo_key="embedding_ab",
        path_env="CST_QUALITY_AB_REPO",
        repo_dir_name="embedding-ab",
        snapshot_path=snapshot_path,
        profiles=(profile,),
    )
    monkeypatch.setenv("CST_QUALITY_AB_REPO", str(env_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(
        repo,
        project_root / "tests/fixtures/retrieval_quality/queries.json",
        profile,
    ) == ResolvedSource(
        (project_root / snapshot_path).resolve(),
        "snapshot_path",
        snapshot_path,
    )


@pytest.mark.parametrize("profile", ["ab_hash", "ab_bge"])
def test_ab_source_keeps_path_env_precedence_with_committed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)
    env_repo = tmp_path / "env-repo"
    env_repo.mkdir()
    smoke_root = tmp_path / "smoke"
    (smoke_root / "embedding-ab").mkdir(parents=True)
    snapshot_path = "tests/fixtures/real_projects/embedding_ab"
    repo = QualityRepo(
        repo_key="embedding_ab",
        path_env="CST_QUALITY_AB_REPO",
        repo_dir_name="embedding-ab",
        snapshot_path=snapshot_path,
        profiles=(profile,),
    )
    monkeypatch.setenv("CST_QUALITY_AB_REPO", str(env_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(
        repo,
        project_root / "tests/fixtures/retrieval_quality/queries.json",
        profile,
    ) == ResolvedSource(
        env_repo.resolve(),
        "path_env",
        "CST_QUALITY_AB_REPO",
    )


@pytest.mark.parametrize(
    "profile",
    ["ci", "p1_vector_bge", "p1_hybrid_bge"],
)
def test_snapshot_only_profile_requires_snapshot_path_with_profile_name(
    tmp_path: Path,
    profile: str,
) -> None:
    repo = QualityRepo(repo_key="sample", profiles=(profile,))

    with pytest.raises(ValueError) as exc_info:
        _resolve_repo_source(repo, tmp_path / "quality.json", profile)

    assert str(exc_info.value) == (
        f"{profile} profile requires snapshot_path for repo sample"
    )


@pytest.mark.parametrize(
    "profile",
    ["ci", "p1_vector_bge", "p1_hybrid_bge"],
)
def test_snapshot_only_profile_reports_missing_snapshot_with_profile_name(
    tmp_path: Path,
    profile: str,
) -> None:
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(tmp_path / "missing"),
        profiles=(profile,),
    )

    with pytest.raises(ValueError) as exc_info:
        _resolve_repo_source(repo, tmp_path / "quality.json", profile)

    assert str(exc_info.value) == f"{profile} snapshot not found for repo sample"


def test_runner_executes_only_cases_selected_by_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
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
                    "snapshot_path": "snapshot",
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {
                            "id": "ci-only",
                            "query": "ci query",
                            "profiles": ["ci"],
                        },
                        {
                            "id": "smoke-only",
                            "query": "smoke query",
                            "profiles": ["smoke"],
                        },
                    ],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert [case["case_id"] for case in report["cases"]] == ["ci-only"]
    with pytest.raises(ValueError, match="^unknown quality profile: missing$"):
        run_quality_fixture(
            fixture,
            profile="missing",
            output_path=None,
            markdown_path=None,
        )


@pytest.mark.parametrize(
    ("profile", "profile_config", "provider", "model", "dimensions", "planner"),
    [
        pytest.param(
            "ci",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="ci",
        ),
        pytest.param(
            "smoke",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="smoke",
        ),
        pytest.param(
            "planner",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": True, "provider": "ollama"},
            },
            "hash",
            "hash-v1",
            384,
            True,
            id="planner",
        ),
        pytest.param(
            "calibration_bge",
            {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "bge",
            "bge-m3",
            1024,
            False,
            id="calibration-bge",
        ),
        pytest.param(
            "ab_hash",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="ab-hash",
        ),
        pytest.param(
            "ab_bge",
            {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "bge",
            "bge-m3",
            1024,
            False,
            id="ab-bge",
        ),
    ],
)
def test_all_canonical_profiles_wire_without_external_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    profile_config: dict,
    provider: str,
    model: str,
    dimensions: int,
    planner: bool,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "source.txt").write_text("source\n", encoding="utf-8")
    case_id = f"{profile}-case"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {profile: profile_config},
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": [profile],
                    "queries": [
                        {
                            "id": case_id,
                            "query": "target",
                            "profiles": [profile],
                        }
                    ],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    report = run_quality_fixture(
        fixture,
        profile=profile,
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    workspace, effective = captured[0]
    try:
        assert [case["case_id"] for case in report["cases"]] == [case_id]
        assert effective.embedding.provider == provider
        assert effective.embedding.model == model
        assert effective.embedding.dimensions == dimensions
        assert effective.query_planner.enabled is planner
        assert (workspace / "source.txt").is_file()
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)


@pytest.mark.parametrize(
    "unsafe_repo_key",
    [
        pytest.param("<absolute>", id="absolute"),
        pytest.param("..", id="parent"),
        pytest.param("../escape", id="parent-child"),
        pytest.param("a/b", id="forward-slash"),
        pytest.param(r"a\b", id="backslash"),
        pytest.param("./alias", id="dot-alias"),
        pytest.param("C:repo", id="windows-drive-relative"),
        pytest.param("repo:name", id="colon"),
        pytest.param("repo?name", id="question-mark"),
        pytest.param("repo*name", id="asterisk"),
        pytest.param('repo"name', id="double-quote"),
        pytest.param("repo<name", id="less-than"),
        pytest.param("repo>name", id="greater-than"),
        pytest.param("repo|name", id="pipe"),
        pytest.param("repo\x00name", id="nul-control"),
        pytest.param("repo\x01name", id="control"),
        pytest.param("repo\x1fname", id="unit-separator-control"),
        pytest.param("CON", id="windows-reserved"),
        pytest.param("con.txt", id="windows-reserved-extension"),
        pytest.param("COM¹", id="windows-reserved-com-superscript"),
        pytest.param("LPT².txt", id="windows-reserved-lpt-superscript-extension"),
        pytest.param("CON .txt", id="windows-reserved-space-before-extension"),
        pytest.param("CONIN$", id="windows-reserved-console-input"),
        pytest.param("CONOUT$", id="windows-reserved-console-output"),
        pytest.param("repo.", id="trailing-dot"),
        pytest.param("repo ", id="trailing-space"),
    ],
)
def test_quality_runner_rejects_unsafe_repo_keys_without_leaking_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_repo_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    absolute_escape = tmp_path / "absolute-escape"
    parent_escape = tmp_path / "escape"
    repo_key = (
        str(absolute_escape) if unsafe_repo_key == "<absolute>" else unsafe_repo_key
    )
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": repo_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.tempfile.mkdtemp",
        fake_mkdtemp,
    )

    try:
        with pytest.raises(ValueError, match=r"repo_key.*safe.*component"):
            run_quality_fixture(
                fixture,
                profile="ci",
                output_path=None,
                markdown_path=None,
            )
        assert not temp_root.exists()
        assert not absolute_escape.exists()
        assert not parent_escape.exists()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        shutil.rmtree(absolute_escape, ignore_errors=True)
        shutil.rmtree(parent_escape, ignore_errors=True)


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        pytest.param("repo", "REPO", id="casefold"),
        pytest.param("caf\u00e9", "cafe\u0301", id="unicode-nfc"),
    ],
)
def test_quality_runner_rejects_duplicate_workspace_repo_key_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_key: str,
    second_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": first_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first", "query": "first"}],
                },
                {
                    "repo_key": second_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    with pytest.raises(ValueError, match=r"duplicate workspace repo_key"):
        run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
        )

    assert [workspace.name for workspace, _config in captured] == [first_key]
    assert not temp_root.exists()


@pytest.mark.parametrize(
    "repo_key",
    ["sample_repo", "sample-repo", "仓库", "COM⁴", "LPT⁵.txt"],
)
def test_quality_runner_keeps_safe_repo_keys_inside_temp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": repo_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.tempfile.mkdtemp",
        fake_mkdtemp,
    )

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        workspace = captured[0][0]
        assert workspace == (temp_root / repo_key).resolve()
        assert workspace.parent == temp_root.resolve()
        assert report["repos"][0]["workspace"]["path"] == str(workspace)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.parametrize(
    "value",
    ["COM¹", "LPT².txt", "CON .txt", "CONIN$", "CONOUT$"],
)
def test_safe_path_component_fallback_rejects_windows_reserved_names(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.delattr(ntpath, "isreserved", raising=False)

    with pytest.raises(ValueError, match=r"repo_key.*safe.*component"):
        quality_runner._safe_path_component(value, "repo_key")


@pytest.mark.parametrize("value", ["COM⁴", "LPT⁵.txt", "CON文档"])
def test_safe_path_component_fallback_keeps_non_reserved_unicode_names(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.delattr(ntpath, "isreserved", raising=False)

    assert quality_runner._safe_path_component(value, "repo_key") == value


@pytest.mark.parametrize(
    "unsafe_repo_dir_name",
    [
        pytest.param("<absolute>", id="absolute"),
        pytest.param("..", id="parent"),
        pytest.param("../external", id="parent-child"),
        pytest.param("a/b", id="forward-slash"),
        pytest.param(r"a\b", id="backslash"),
        pytest.param("C:repo", id="windows-drive-relative"),
        pytest.param("repo:name", id="colon"),
        pytest.param("repo?name", id="question-mark"),
        pytest.param("repo*name", id="asterisk"),
        pytest.param('repo"name', id="double-quote"),
        pytest.param("repo<name", id="less-than"),
        pytest.param("repo>name", id="greater-than"),
        pytest.param("repo|name", id="pipe"),
        pytest.param("repo\x00name", id="nul-control"),
        pytest.param("repo\x01name", id="control"),
        pytest.param("repo\x1fname", id="unit-separator-control"),
        pytest.param("AUX", id="windows-reserved"),
        pytest.param("lpt9.log", id="windows-reserved-extension"),
        pytest.param("COM¹", id="windows-reserved-com-superscript"),
        pytest.param("LPT².txt", id="windows-reserved-lpt-superscript-extension"),
        pytest.param("CON .txt", id="windows-reserved-space-before-extension"),
        pytest.param("CONIN$", id="windows-reserved-console-input"),
        pytest.param("CONOUT$", id="windows-reserved-console-output"),
        pytest.param("repo.", id="trailing-dot"),
        pytest.param("repo ", id="trailing-space"),
    ],
)
def test_smoke_source_rejects_unsafe_repo_dir_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_repo_dir_name: str,
) -> None:
    smoke_root = tmp_path / "smoke"
    smoke_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (smoke_root / "a" / "b").mkdir(parents=True)
    (smoke_root / r"a\b").mkdir()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    repo_dir_name = (
        str(external)
        if unsafe_repo_dir_name == "<absolute>"
        else unsafe_repo_dir_name
    )
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name=repo_dir_name,
        snapshot_path=str(snapshot),
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    with pytest.raises(ValueError, match=r"repo_dir_name.*safe.*component"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "smoke")


def test_smoke_source_rejects_child_symlink_escaping_resolved_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_root = tmp_path / "smoke"
    smoke_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (smoke_root / "sample").symlink_to(external, target_is_directory=True)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name="sample",
        snapshot_path=str(snapshot),
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    with pytest.raises(ValueError, match=r"repo_dir_name.*escape"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "smoke")


@pytest.mark.parametrize("repo_dir_name", ["safe_repo-仓库", "COM⁴", "LPT⁵.txt"])
def test_smoke_source_keeps_safe_child_and_component_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_dir_name: str,
) -> None:
    smoke_root = tmp_path / "smoke"
    source = smoke_root / repo_dir_name
    source.mkdir(parents=True)
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name=repo_dir_name,
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(
        repo,
        tmp_path / "quality.json",
        "smoke",
    ) == ResolvedSource(
        source.resolve(),
        "smoke_root",
        repo_dir_name,
    )


@pytest.mark.parametrize(
    "snapshot_path",
    [
        pytest.param("../private", id="parent"),
        pytest.param("snapshots/../../private", id="nested-parent"),
        pytest.param(r"..\private", id="backslash-parent"),
        pytest.param(r"snapshots\..\private", id="nested-backslash-parent"),
        pytest.param(r"\private", id="rooted-backslash"),
        pytest.param(r"C:\private", id="windows-drive"),
    ],
)
def test_snapshot_source_rejects_unsafe_relative_paths(
    tmp_path: Path,
    snapshot_path: str,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (tmp_path / "private").mkdir()
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=snapshot_path,
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*safe relative"):
        _resolve_repo_source(repo, fixture_dir / "quality.json", "ci")


@pytest.mark.parametrize(
    ("snapshot_path", "locator"),
    [
        pytest.param("snapshots/nested", "snapshots/nested", id="posix"),
        pytest.param(r"snapshots\nested", "snapshots/nested", id="backslash"),
        pytest.param("./snapshots/nested", "snapshots/nested", id="dot"),
    ],
)
def test_snapshot_source_normalizes_safe_nested_relative_paths(
    tmp_path: Path,
    snapshot_path: str,
    locator: str,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    source = fixture_dir / "snapshots" / "nested"
    source.mkdir(parents=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=snapshot_path,
        profiles=("ci",),
    )

    assert _resolve_repo_source(
        repo,
        fixture_dir / "quality.json",
        "ci",
    ) == ResolvedSource(
        source.resolve(),
        "snapshot_path",
        locator,
    )


def test_snapshot_source_allows_absolute_directory_with_redacted_locator(
    tmp_path: Path,
) -> None:
    source = tmp_path / "absolute-source"
    source.mkdir()
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(source),
        profiles=("ci",),
    )

    assert _resolve_repo_source(
        repo,
        tmp_path / "quality.json",
        "ci",
    ) == ResolvedSource(
        source.resolve(),
        "snapshot_path",
        "absolute-source",
    )


def test_snapshot_source_normalizes_absolute_directory_before_redacting_locator(
    tmp_path: Path,
) -> None:
    source = tmp_path / "absolute-source"
    child = source / "child"
    child.mkdir(parents=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(child / ".."),
        profiles=("ci",),
    )

    assert _resolve_repo_source(
        repo,
        tmp_path / "quality.json",
        "ci",
    ) == ResolvedSource(
        source.resolve(),
        "snapshot_path",
        source.resolve().name,
    )


def test_snapshot_source_rejects_filesystem_root_without_safe_locator(
    tmp_path: Path,
) -> None:
    root = Path(tmp_path.anchor)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(root),
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*named directory"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "ci")


def test_snapshot_source_rejects_relative_symlink_escape(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (fixture_dir / "snapshot").symlink_to(external, target_is_directory=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path="snapshot",
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*escape"):
        _resolve_repo_source(repo, fixture_dir / "quality.json", "ci")


def test_snapshot_source_rejects_absolute_top_level_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    snapshot_link = tmp_path / "snapshot-link"
    snapshot_link.symlink_to(source, target_is_directory=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(snapshot_link),
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*symlink"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "ci")


@pytest.mark.parametrize("profile", ["ci", "smoke"])
def test_snapshot_source_swap_never_recanonicalizes_to_external_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    snapshot = fixture_dir / "snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    moved_snapshot = fixture_dir / "snapshot-original"
    external = tmp_path / "external"
    external.mkdir()
    secret = b"external-secret-token"
    (external / "secret.txt").write_bytes(secret)
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        fixture_dir,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": [profile],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    original_resolve_snapshot = quality_runner._resolve_snapshot_path
    original_resolve_source = quality_runner._resolve_repo_source
    original_copy = quality_runner._copy_source_repo
    resolved_sources: list[ResolvedSource | None] = []
    copied_sources: list[Path] = []
    swapped = False

    def resolve_then_swap(fixture_path: Path, raw_path: str) -> Path:
        nonlocal swapped
        resolved = original_resolve_snapshot(fixture_path, raw_path)
        if not swapped:
            resolved.rename(moved_snapshot)
            resolved.symlink_to(external, target_is_directory=True)
            swapped = True
        return resolved

    def capture_resolved_source(
        repo: QualityRepo,
        fixture_path: Path,
        selected_profile: str,
    ) -> ResolvedSource | None:
        source = original_resolve_source(repo, fixture_path, selected_profile)
        resolved_sources.append(source)
        return source

    def capture_copy_source(source: Path, workspace: Path) -> None:
        copied_sources.append(source)
        original_copy(source, workspace)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "_resolve_snapshot_path", resolve_then_swap)
    monkeypatch.setattr(quality_runner, "_resolve_repo_source", capture_resolved_source)
    monkeypatch.setattr(quality_runner, "_copy_source_repo", capture_copy_source)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    report: dict[str, object] | None = None
    try:
        if profile == "ci":
            with pytest.raises(ValueError, match=r"ci snapshot not found"):
                run_quality_fixture(
                    fixture,
                    profile=profile,
                    output_path=None,
                    markdown_path=None,
                    keep_workspace=True,
                )
        else:
            report = run_quality_fixture(
                fixture,
                profile=profile,
                output_path=None,
                markdown_path=None,
                keep_workspace=True,
                allow_empty=True,
            )
            assert report["aggregate"]["skipped"] == 1
            assert report["cases"][0]["status"] == "skipped"

        assert swapped
        assert all(
            source is None or source.path != external.resolve()
            for source in resolved_sources
        )
        assert copied_sources == []
        copied_contents = [
            path.read_bytes()
            for path in temp_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        ]
        assert secret not in copied_contents
        assert report is None or secret.decode() not in json.dumps(report)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_copy_source_repo_fails_closed_without_descriptor_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(quality_runner, "_descriptor_copy_supported", lambda: False)

    with pytest.raises(
        RuntimeError,
        match=r"secure repository copy is not supported on this platform",
    ):
        _copy_source_repo(source, workspace)

    assert not workspace.exists()


def test_copy_source_repo_removes_new_workspace_after_mid_copy_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not quality_runner._descriptor_copy_supported():
        pytest.skip("descriptor-based no-follow copy is not supported")

    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    workspace = tmp_path / "workspace"

    def fail_mid_copy(source_file: object, destination_file: object) -> None:
        destination_file.write(b"partial")
        raise PermissionError("copy interrupted")

    monkeypatch.setattr(quality_runner.shutil, "copyfileobj", fail_mid_copy)

    with pytest.raises(PermissionError, match="copy interrupted"):
        _copy_source_repo(source, workspace)

    assert not workspace.exists()


def test_copy_source_repo_preserves_preexisting_workspace_when_copy_refuses(
    tmp_path: Path,
) -> None:
    if not quality_runner._descriptor_copy_supported():
        pytest.skip("descriptor-based no-follow copy is not supported")

    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    marker = workspace / "caller-owned.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _copy_source_repo(source, workspace)

    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_quality_runner_records_unsupported_secure_copy_for_each_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_source = _write_source_repo(tmp_path / "first-source")
    second_source = _write_source_repo(tmp_path / "second-source")
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {"ci": {}, "smoke": {}},
            "repos": [
                {
                    "repo_key": "first",
                    "snapshot_path": str(first_source),
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {
                            "id": "first-selected",
                            "query": "first",
                            "profiles": ["ci"],
                        },
                        {
                            "id": "first-unselected",
                            "query": "first",
                            "profiles": ["smoke"],
                        },
                    ],
                },
                {
                    "repo_key": "second",
                    "snapshot_path": str(second_source),
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {
                            "id": "second-selected",
                            "query": "second",
                            "profiles": ["ci"],
                        },
                        {
                            "id": "second-unselected",
                            "query": "second",
                            "profiles": ["smoke"],
                        },
                    ],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "_descriptor_copy_supported", lambda: False)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
            allow_empty=True,
        )

        assert [repo["repo_key"] for repo in report["repos"]] == [
            "first",
            "second",
        ]
        assert [repo["index"] for repo in report["repos"]] == [
            {"status": "error"},
            {"status": "error"},
        ]
        assert [
            (case["repo_key"], case["case_id"], case["status"])
            for case in report["cases"]
        ] == [
            ("first", "first-selected", "error"),
            ("second", "second-selected", "error"),
        ]
        assert [case["failures"] for case in report["cases"]] == [
            ["secure repository copy is not supported on this platform"],
            ["secure repository copy is not supported on this platform"],
        ]
        assert captured == []
        assert not (temp_root / "first").exists()
        assert not (temp_root / "second").exists()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_copy_source_repo_ignores_nested_file_and_directory_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    external_file = tmp_path / "external.txt"
    external_file.write_text("private\n", encoding="utf-8")
    external_dir = tmp_path / "external-dir"
    external_dir.mkdir()
    (external_dir / "private.txt").write_text("private\n", encoding="utf-8")
    contained_file = source / "contained.txt"
    contained_file.write_text("contained\n", encoding="utf-8")
    contained_dir = source / "contained-dir"
    contained_dir.mkdir()
    (contained_dir / "value.txt").write_text("contained\n", encoding="utf-8")
    (nested / "file-link.txt").symlink_to(external_file)
    (nested / "dir-link").symlink_to(external_dir, target_is_directory=True)
    (nested / "contained-file-link.txt").symlink_to(contained_file)
    (nested / "contained-dir-link").symlink_to(
        contained_dir,
        target_is_directory=True,
    )
    workspace = tmp_path / "workspace"

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").read_text(encoding="utf-8") == "normal\n"
    assert not (workspace / "nested" / "file-link.txt").exists()
    assert not (workspace / "nested" / "file-link.txt").is_symlink()
    assert not (workspace / "nested" / "dir-link").exists()
    assert not (workspace / "nested" / "dir-link").is_symlink()
    assert (workspace / "contained.txt").is_file()
    assert (workspace / "contained-dir" / "value.txt").is_file()
    assert not (workspace / "nested" / "contained-file-link.txt").exists()
    assert not (workspace / "nested" / "contained-file-link.txt").is_symlink()
    assert not (workspace / "nested" / "contained-dir-link").exists()
    assert not (workspace / "nested" / "contained-dir-link").is_symlink()


def test_copy_source_repo_omits_junction_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    junction = source / "junction"
    junction.mkdir(parents=True)
    (junction / "private.txt").write_text("private\n", encoding="utf-8")
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    original_is_junction = getattr(Path, "is_junction", None)

    def fake_is_junction(path: Path) -> bool:
        if path.name == "junction":
            return True
        return original_is_junction(path) if original_is_junction else False

    monkeypatch.setattr(Path, "is_junction", fake_is_junction, raising=False)

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").is_file()
    assert not (workspace / "junction").exists()


def test_copy_source_repo_omits_non_regular_files(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is not supported on this platform")

    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    os.mkfifo(source / "named-pipe")
    workspace = tmp_path / "workspace"

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").is_file()
    assert not (workspace / "named-pipe").exists()


def test_copy_source_repo_does_not_follow_directory_swapped_to_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not (
        os.name == "posix"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
    ):
        pytest.skip("descriptor-based no-follow copy is not supported")

    source = tmp_path / "source"
    swappable = source / "swappable"
    swappable.mkdir(parents=True)
    (swappable / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    secret = "external-secret-token"
    (external / "secret.txt").write_text(secret, encoding="utf-8")
    workspace = tmp_path / "workspace"
    moved = source / "swappable-original"
    original_open = os.open
    swapped = False

    def racing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if dir_fd is not None and os.fspath(path) == "swappable" and not swapped:
            swappable.rename(moved)
            swappable.symlink_to(external, target_is_directory=True)
            swapped = True
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(quality_runner.os, "open", racing_open)

    try:
        _copy_source_repo(source, workspace)
    except OSError:
        pass

    assert swapped
    copied_contents = [
        path.read_text(encoding="utf-8")
        for path in workspace.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    assert secret not in copied_contents


def test_quality_runner_hashes_the_copied_workspace_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    source_file = source / "src" / "App.java"
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def index_then_change_source(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append((repo, config))
        source_file.write_text("changed-after-copy\n", encoding="utf-8")
        external.write_text("external-v2\n", encoding="utf-8")
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    monkeypatch.setattr(quality_runner, "index_repository", index_then_change_source)

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    workspace = captured[0][0]
    try:
        content_hash = report["repos"][0]["source"]["content_hash"]
        assert content_hash == _content_identity(workspace)
        assert content_hash != _content_identity(source)
        assert not (workspace / "external-link.txt").exists()
        assert not (workspace / "external-link.txt").is_symlink()
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)


def test_quality_runner_content_hash_ignores_external_symlink_target_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    first_report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )
    external.write_text("external-v2\n", encoding="utf-8")
    second_report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert (
        first_report["repos"][0]["source"]["content_hash"]
        == second_report["repos"][0]["source"]["content_hash"]
    )


def test_content_identity_skips_symlink_files_but_hashes_normal_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    normal = source / "normal.txt"
    normal.write_text("normal-v1\n", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)

    original_identity = _content_identity(source)
    external.write_text("external-v2\n", encoding="utf-8")
    after_external_change = _content_identity(source)

    assert after_external_change == original_identity

    normal.write_text("normal-v2\n", encoding="utf-8")
    assert _content_identity(source) != after_external_change


def test_effective_config_copies_base_and_default_index_lists() -> None:
    original_default_include = list(DEFAULT_CONFIG.index.include)
    original_default_exclude = list(DEFAULT_CONFIG.index.exclude)
    custom_base = ToolConfig(
        index=IndexConfig(include=["base-include"], exclude=["base-exclude"])
    )

    try:
        custom_first = _effective_config(custom_base, {}, {})
        custom_second = _effective_config(custom_base, {}, {})
        default_first = _effective_config(DEFAULT_CONFIG, {}, {})
        default_second = _effective_config(DEFAULT_CONFIG, {}, {})

        custom_first.index.include.append("mutated-include")
        custom_first.index.exclude.append("mutated-exclude")
        default_first.index.include.append("mutated-default-include")
        default_first.index.exclude.append("mutated-default-exclude")

        assert custom_base.index.include == ["base-include"]
        assert custom_base.index.exclude == ["base-exclude"]
        assert custom_second.index.include == ["base-include"]
        assert custom_second.index.exclude == ["base-exclude"]
        assert DEFAULT_CONFIG.index.include == original_default_include
        assert DEFAULT_CONFIG.index.exclude == original_default_exclude
        assert default_second.index.include == original_default_include
        assert default_second.index.exclude == original_default_exclude
    finally:
        DEFAULT_CONFIG.index.include[:] = original_default_include
        DEFAULT_CONFIG.index.exclude[:] = original_default_exclude


def test_effective_config_copies_repo_and_profile_override_lists() -> None:
    repo_include = ["repo-include"]
    profile_exclude = ["profile-exclude"]
    repo_overrides = {"index": {"include": repo_include}}
    profile_overrides = {"index": {"exclude": profile_exclude}}

    first = _effective_config(DEFAULT_CONFIG, repo_overrides, profile_overrides)
    second = _effective_config(DEFAULT_CONFIG, repo_overrides, profile_overrides)
    first.index.include.append("mutated-include")
    first.index.exclude.append("mutated-exclude")

    assert repo_include == ["repo-include"]
    assert profile_exclude == ["profile-exclude"]
    assert second.index.include == ["repo-include"]
    assert second.index.exclude == ["profile-exclude"]


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
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
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
        "config_hash",
        "index",
        "retrieval",
        "embedding",
        "query_planner",
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
    source = _write_source_repo(tmp_path / "source root with spaces").resolve()
    temp_root = (tmp_path / "temporary root with spaces").resolve()
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
        raise RuntimeError(
            " ".join(
                [
                    f"source={source}",
                    f"workspace={repo}",
                    f"source_uri={source.as_uri()}",
                    f"source_encoded={quote(source.as_posix(), safe='/')}",
                    f"source_encoded_all={quote(source.as_posix(), safe='')}",
                    f"source_case={str(source).swapcase()}",
                    f"workspace_uri={repo.as_uri()}",
                    f"workspace_encoded={quote(repo.as_posix(), safe='/')}",
                    f"workspace_encoded_all={quote(repo.as_posix(), safe='')}",
                    f"workspace_case={str(repo).swapcase()}",
                    "diagnostic=keep-me",
                ]
            )
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fail_query,
    )
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    report = run_quality_fixture(
        fixture,
        "smoke",
        None,
        None,
        allow_empty=True,
    )

    rendered = json.dumps(report)
    workspace = temp_root / "sample"
    sensitive_variants = {
        str(source),
        source.as_uri(),
        quote(source.as_posix(), safe="/"),
        quote(source.as_posix(), safe=""),
        str(source).swapcase(),
        str(workspace),
        workspace.as_uri(),
        quote(workspace.as_posix(), safe="/"),
        quote(workspace.as_posix(), safe=""),
        str(workspace).swapcase(),
    }
    assert all(variant not in rendered for variant in sensitive_variants)
    assert report["cases"][0]["failures"] == [
        "source=<source> workspace=<workspace> "
        "source_uri=<source> source_encoded=<source> "
        "source_encoded_all=<source> source_case=<source> "
        "workspace_uri=<workspace> workspace_encoded=<workspace> "
        "workspace_encoded_all=<workspace> workspace_case=<workspace> "
        "diagnostic=keep-me"
    ]


def test_report_redacts_normalized_and_full_casefold_paths_from_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path / "Straße-café-source").resolve()
    temp_root = (tmp_path / "Straße-café-workspace").resolve()
    workspace = temp_root / "sample"
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
    source_nfd = unicodedata.normalize("NFD", source.as_posix())
    workspace_nfd = unicodedata.normalize("NFD", workspace.as_posix())
    source_upper = source_nfd.upper()
    workspace_upper = workspace_nfd.upper()
    source_upper_nfc = unicodedata.normalize("NFC", source.as_posix()).upper()
    workspace_upper_nfc = unicodedata.normalize("NFC", workspace.as_posix()).upper()
    source_upper_nfc_encoded = quote(source_upper_nfc, safe="/")
    workspace_upper_nfc_encoded = quote(workspace_upper_nfc, safe="/")
    source_upper_nfc_mixed = source_upper_nfc_encoded.replace(
        "STRASSE", "%53TRASSE", 1
    )
    workspace_upper_nfc_mixed = workspace_upper_nfc_encoded.replace(
        "STRASSE", "%53TRASSE", 1
    )
    assert source_nfd != source.as_posix()
    assert workspace_nfd != workspace.as_posix()
    assert "STRASSE-CAFE" in source_upper
    assert "STRASSE-CAFE" in workspace_upper
    assert "%C3%89" in source_upper_nfc_encoded
    assert "%C3%89" in workspace_upper_nfc_encoded

    def fail_query(repo: Path, query: str, config: ToolConfig) -> QueryBundle:
        assert repo == workspace
        raise RuntimeError(
            " ".join(
                [
                    f"source={source_nfd}",
                    f"source_uri={Path(source_nfd).as_uri()}",
                    f"source_encoded={quote(source_nfd, safe='/')}",
                    f"source_encoded_all={quote(source_nfd, safe='')}",
                    f"source_casefold={source_upper}",
                    f"source_casefold_uri={Path(source_upper).as_uri()}",
                    f"source_casefold_encoded={quote(source_upper, safe='/')}",
                    f"source_nfc_upper_uri={Path(source_upper_nfc).as_uri()}",
                    f"source_nfc_upper_encoded={source_upper_nfc_encoded}",
                    f"source_nfc_upper_encoded_all={quote(source_upper_nfc, safe='')}",
                    f"source_nfc_upper_mixed={source_upper_nfc_mixed}",
                    f"workspace={workspace_nfd}",
                    f"workspace_uri={Path(workspace_nfd).as_uri()}",
                    f"workspace_encoded={quote(workspace_nfd, safe='/')}",
                    f"workspace_encoded_all={quote(workspace_nfd, safe='')}",
                    f"workspace_casefold={workspace_upper}",
                    f"workspace_casefold_uri={Path(workspace_upper).as_uri()}",
                    f"workspace_casefold_encoded={quote(workspace_upper, safe='/')}",
                    f"workspace_nfc_upper_uri={Path(workspace_upper_nfc).as_uri()}",
                    f"workspace_nfc_upper_encoded={workspace_upper_nfc_encoded}",
                    f"workspace_nfc_upper_encoded_all={quote(workspace_upper_nfc, safe='')}",
                    f"workspace_nfc_upper_mixed={workspace_upper_nfc_mixed}",
                    "diagnostic=keep-me",
                ]
            )
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fail_query,
    )
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    report = run_quality_fixture(
        fixture,
        "smoke",
        None,
        None,
        allow_empty=True,
    )

    rendered = json.dumps(report, ensure_ascii=False)
    sensitive_variants = {
        source_nfd,
        Path(source_nfd).as_uri(),
        quote(source_nfd, safe="/"),
        quote(source_nfd, safe=""),
        source_upper,
        Path(source_upper).as_uri(),
        quote(source_upper, safe="/"),
        Path(source_upper_nfc).as_uri(),
        source_upper_nfc_encoded,
        quote(source_upper_nfc, safe=""),
        source_upper_nfc_mixed,
        workspace_nfd,
        Path(workspace_nfd).as_uri(),
        quote(workspace_nfd, safe="/"),
        quote(workspace_nfd, safe=""),
        workspace_upper,
        Path(workspace_upper).as_uri(),
        quote(workspace_upper, safe="/"),
        Path(workspace_upper_nfc).as_uri(),
        workspace_upper_nfc_encoded,
        quote(workspace_upper_nfc, safe=""),
        workspace_upper_nfc_mixed,
    }
    assert all(variant not in rendered for variant in sensitive_variants)
    assert report["cases"][0]["failures"] == [
        "source=<source> source_uri=<source> source_encoded=<source> "
        "source_encoded_all=<source> source_casefold=<source> "
        "source_casefold_uri=<source> source_casefold_encoded=<source> "
        "source_nfc_upper_uri=<source> source_nfc_upper_encoded=<source> "
        "source_nfc_upper_encoded_all=<source> "
        "source_nfc_upper_mixed=<source> "
        "workspace=<workspace> "
        "workspace_uri=<workspace> workspace_encoded=<workspace> "
        "workspace_encoded_all=<workspace> workspace_casefold=<workspace> "
        "workspace_casefold_uri=<workspace> "
        "workspace_casefold_encoded=<workspace> "
        "workspace_nfc_upper_uri=<workspace> "
        "workspace_nfc_upper_encoded=<workspace> "
        "workspace_nfc_upper_encoded_all=<workspace> "
        "workspace_nfc_upper_mixed=<workspace> diagnostic=keep-me"
    ]


@pytest.mark.parametrize("canonical", [False, True], ids=["legacy", "canonical"])
@pytest.mark.parametrize("failure_stage", ["setup", "query"])
def test_report_redacts_configured_embedding_api_key_from_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical: bool,
    failure_stage: str,
) -> None:
    source = _write_source_repo(tmp_path / "source")
    secret = "quality-secret-token-not-for-reports-a\u0301"
    monkeypatch.setenv("QUALITY_SECRET", secret)
    fixture_data: dict = {
        "schema_version": 1,
        "repos": [
            {
                "repo_key": "sample",
                "snapshot_path": str(source),
                "profiles": ["smoke"],
                "queries": [{"id": "target", "query": "targetToken"}],
            }
        ],
    }
    if canonical:
        fixture_data["profile_configs"] = {
            "smoke": {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                    "api_key_env": "QUALITY_SECRET",
                },
                "query_planner": {"enabled": False},
            }
        }
        config = DEFAULT_CONFIG
    else:
        config = ToolConfig(
            embedding=EmbeddingConfig(api_key_env="QUALITY_SECRET"),
        )
    fixture = _write_fixture(tmp_path, fixture_data)
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fail_setup(repo: Path, effective: ToolConfig) -> IndexSummary:
        raise RuntimeError(f"embedding rejected api-key={secret}\u0327")

    def fail_query(repo: Path, query: str, effective: ToolConfig) -> QueryBundle:
        raise RuntimeError(f"query rejected api-key={secret}\u0327")

    if failure_stage == "setup":
        monkeypatch.setattr(quality_runner, "index_repository", fail_setup)
    else:
        monkeypatch.setattr(quality_runner, "query_repository", fail_query)

    output = tmp_path / "reports" / "quality.json"
    markdown = tmp_path / "reports" / "quality.md"
    report = run_quality_fixture(
        fixture,
        "smoke",
        output,
        markdown,
        config=config,
        allow_empty=True,
    )

    serialized = "\n".join(
        [
            json.dumps(report, ensure_ascii=False),
            output.read_text(encoding="utf-8"),
            markdown.read_text(encoding="utf-8"),
        ]
    )
    assert secret not in serialized
    assert "<api-key>" in serialized


def test_report_redacts_temporary_root_variants_from_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path / "source")
    temp_root = (tmp_path / "cst-quality-root with spaces-a\u0301").resolve()
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
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    root_variants = {
        str(temp_root),
        temp_root.as_uri(),
        quote(temp_root.as_posix(), safe="/"),
        quote(temp_root.as_posix(), safe=""),
    }

    def fail_query(repo: Path, query: str, config: ToolConfig) -> QueryBundle:
        raise RuntimeError(
            " ".join(
                f"temp_root_{index}={value}\u0327"
                for index, value in enumerate(sorted(root_variants))
            )
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "query_repository", fail_query)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)
    output = tmp_path / "reports" / "quality.json"
    markdown = tmp_path / "reports" / "quality.md"

    report = run_quality_fixture(
        fixture,
        "smoke",
        output,
        markdown,
        allow_empty=True,
    )

    serialized = "\n".join(
        [
            json.dumps(report, ensure_ascii=False),
            output.read_text(encoding="utf-8"),
            markdown.read_text(encoding="utf-8"),
        ]
    )
    assert all(variant not in serialized for variant in root_variants)
    assert str(temp_root) not in serialized
    assert "/cst-quality-" not in serialized
    assert "<workspace>" in serialized


@pytest.mark.parametrize(
    ("sensitive_kind", "placeholder"),
    [("source", "<source>"), ("workspace", "<workspace>")],
)
def test_safe_error_redacts_path_with_trailing_combining_mark(
    tmp_path: Path,
    sensitive_kind: str,
    placeholder: str,
) -> None:
    source = (tmp_path / "source").resolve()
    workspace = (tmp_path / "workspace").resolve()
    sensitive = source if sensitive_kind == "source" else workspace
    message = f"{sensitive}\u0301"

    redacted = quality_runner._safe_error(
        RuntimeError(message),
        source,
        workspace,
    )

    assert str(sensitive) not in redacted
    assert redacted == placeholder


@pytest.mark.parametrize(
    "variant_kind",
    ["raw", "uri", "percent_slashes", "percent_all"],
)
def test_safe_error_redacts_literal_source_before_combining_mark_reordering(
    tmp_path: Path,
    variant_kind: str,
) -> None:
    source = (tmp_path / "source-a\u0301").resolve()
    workspace = (tmp_path / "workspace-root" / "sample").resolve()
    variants = {
        "raw": source.as_posix(),
        "uri": source.as_uri(),
        "percent_slashes": quote(source.as_posix(), safe="/"),
        "percent_all": quote(source.as_posix(), safe=""),
    }
    sensitive = variants[variant_kind]

    redacted = quality_runner._safe_error(
        RuntimeError(f"{sensitive}\u0327"),
        source,
        workspace,
    )

    assert sensitive not in redacted
    assert redacted == "<source>"


def test_safe_error_redacts_reordered_combining_path_spellings(
    tmp_path: Path,
) -> None:
    raw_component = "a\u0315\u0300"
    source = (tmp_path / f"source-{raw_component}").resolve()
    workspace = (tmp_path / f"workspace-{raw_component}").resolve()
    source.mkdir()
    workspace.mkdir()

    def path_spellings(path: Path) -> list[str]:
        raw = path.as_posix()
        reordered = unicodedata.normalize("NFD", raw)
        composed = unicodedata.normalize("NFC", raw)
        assert raw != reordered
        return [
            raw,
            reordered,
            composed,
            Path(raw).as_uri(),
            Path(reordered).as_uri(),
            Path(composed).as_uri(),
            quote(raw, safe="/"),
            quote(reordered, safe="/"),
            quote(composed, safe="/"),
            quote(raw, safe=""),
            quote(reordered, safe=""),
            quote(composed, safe=""),
        ]

    source_spellings = path_spellings(source)
    workspace_spellings = path_spellings(workspace)
    sensitive_spellings = source_spellings + workspace_spellings
    message = " ".join(
        [
            *(
                f"source_{index}={value}"
                for index, value in enumerate(source_spellings)
            ),
            *(
                f"workspace_{index}={value}"
                for index, value in enumerate(workspace_spellings)
            ),
            "diagnostic=keep-me",
        ]
    )
    redacted = quality_runner._safe_error(RuntimeError(message), source, workspace)

    assert all(spelling not in redacted for spelling in sensitive_spellings)
    assert str(tmp_path.resolve()) not in redacted
    assert redacted == " ".join(
        [
            *(f"source_{index}=<source>" for index in range(12)),
            *(f"workspace_{index}=<workspace>" for index in range(12)),
            "diagnostic=keep-me",
        ]
    )


@pytest.mark.parametrize(
    ("sensitive_kind", "placeholder"),
    [
        ("source", "<source>"),
        ("workspace", "<workspace>"),
        ("temp_root", "<workspace>"),
    ],
)
@pytest.mark.parametrize(
    "variant_kind",
    ["raw", "uri", "percent_slashes", "percent_all"],
)
def test_safe_error_redacts_extra_lower_class_mark_in_final_path_cluster(
    tmp_path: Path,
    sensitive_kind: str,
    placeholder: str,
    variant_kind: str,
) -> None:
    sensitive_cluster = "a\u0301"
    message_cluster = "a\u0327\u0301"
    source = (tmp_path / f"source-{sensitive_cluster}").resolve()
    temp_root = (tmp_path / f"temp-{sensitive_cluster}").resolve()
    workspace = (temp_root / f"workspace-{sensitive_cluster}").resolve()
    sensitive_path = {
        "source": source,
        "workspace": workspace,
        "temp_root": temp_root,
    }[sensitive_kind]
    raw_message = sensitive_path.as_posix().removesuffix(sensitive_cluster)
    raw_message += message_cluster
    variants = {
        "raw": raw_message,
        "uri": Path(raw_message).as_uri(),
        "percent_slashes": quote(raw_message, safe="/"),
        "percent_all": quote(raw_message, safe=""),
    }

    redacted = quality_runner._safe_error(
        RuntimeError(variants[variant_kind]),
        source,
        workspace,
    )

    assert redacted == placeholder


@pytest.mark.parametrize("variant_kind", ["raw", "percent"])
def test_safe_error_redacts_extra_lower_class_mark_in_api_secret_cluster(
    tmp_path: Path,
    variant_kind: str,
) -> None:
    secret = "api-secret-a\u0301"
    message_secret = "api-secret-a\u0327\u0301"
    variants = {
        "raw": message_secret,
        "percent": quote(message_secret, safe=""),
    }

    redacted = quality_runner._safe_error(
        RuntimeError(variants[variant_kind]),
        (tmp_path / "source").resolve(),
        (tmp_path / "workspace").resolve(),
        secret,
    )

    assert redacted == "<api-key>"


def test_quality_report_redacts_extra_final_cluster_marks_from_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_cluster = "a\u0301"
    message_cluster = "a\u0327\u0301"
    source = _write_source_repo(tmp_path / "fixture")
    marked_source = source.with_name(f"source-{sensitive_cluster}")
    source.rename(marked_source)
    source = marked_source.resolve()
    temp_root = (tmp_path / f"temp-root-{sensitive_cluster}").resolve()
    repo_key = f"sample-{sensitive_cluster}"
    workspace = temp_root / repo_key
    secret = f"api-secret-{sensitive_cluster}"
    monkeypatch.setenv("QUALITY_SECRET", secret)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": repo_key,
                    "snapshot_path": str(source),
                    "profiles": ["smoke"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def add_lower_class_mark(value: str) -> str:
        return value.removesuffix(sensitive_cluster) + message_cluster

    source_message = add_lower_class_mark(source.as_posix())
    workspace_message = add_lower_class_mark(workspace.as_posix())
    temp_root_message = add_lower_class_mark(temp_root.as_posix())
    secret_message = add_lower_class_mark(secret)
    leaked_values = {
        "source_raw": source_message,
        "source_uri": Path(source_message).as_uri(),
        "source_percent": quote(source_message, safe=""),
        "workspace_raw": workspace_message,
        "workspace_uri": Path(workspace_message).as_uri(),
        "workspace_percent": quote(workspace_message, safe=""),
        "temp_root_raw": temp_root_message,
        "temp_root_uri": Path(temp_root_message).as_uri(),
        "temp_root_percent": quote(temp_root_message, safe=""),
        "api_raw": secret_message,
        "api_percent": quote(secret_message, safe=""),
    }

    def fail_query(repo: Path, query: str, config: ToolConfig) -> QueryBundle:
        assert repo == workspace
        raise RuntimeError(
            " ".join(f"{key}={value}" for key, value in leaked_values.items())
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "query_repository", fail_query)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)
    output = tmp_path / "reports" / "quality.json"
    markdown = tmp_path / "reports" / "quality.md"
    config = ToolConfig(
        embedding=EmbeddingConfig(api_key_env="QUALITY_SECRET"),
    )

    report = run_quality_fixture(
        fixture,
        "smoke",
        output,
        markdown,
        config=config,
        allow_empty=True,
    )

    serialized = "\n".join(
        [
            json.dumps(report, ensure_ascii=False),
            output.read_text(encoding="utf-8"),
            markdown.read_text(encoding="utf-8"),
        ]
    )
    assert all(value not in serialized for value in leaked_values.values())
    assert report["cases"][0]["failures"] == [
        "source_raw=<source> source_uri=<source> source_percent=<source> "
        "workspace_raw=<workspace> workspace_uri=<workspace> "
        "workspace_percent=<workspace> temp_root_raw=<workspace> "
        "temp_root_uri=<workspace> temp_root_percent=<workspace> "
        "api_raw=<api-key> api_percent=<api-key>"
    ]


def test_safe_error_does_not_rescan_inserted_placeholders(tmp_path: Path) -> None:
    source = (tmp_path / "source").resolve()
    workspace = (tmp_path / "workspace").resolve()

    redacted = quality_runner._safe_error(
        RuntimeError(f"{source} source"),
        source,
        workspace,
        "source",
    )

    assert redacted == "<source> <api-key>"
    assert "<<" not in redacted


def test_quality_runner_does_not_publish_when_setup_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    temp_root = (tmp_path / "temp-root").resolve()
    workspace = temp_root / "sample"
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    original_rmtree = shutil.rmtree

    def fail_index(repo: Path, config: ToolConfig) -> IndexSummary:
        raise RuntimeError("index exploded")

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    def leave_workspace(path: str | Path, *args: object, **kwargs: object) -> None:
        if Path(path) == workspace:
            return
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(quality_runner, "index_repository", fail_index)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(quality_runner.shutil, "rmtree", leave_workspace)

    try:
        with pytest.raises(OSError, match="repository workspace"):
            run_quality_fixture(
                fixture,
                profile="ci",
                output_path=output,
                markdown_path=markdown,
                keep_workspace=True,
                allow_empty=True,
            )

        assert output.read_text(encoding="utf-8") == "old-json\n"
        assert not markdown.exists()
        assert workspace.exists()
    finally:
        original_rmtree(temp_root, ignore_errors=True)


def test_quality_runner_cleans_temp_root_before_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    temp_root = (tmp_path / "temp-root").resolve()
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_rmtree = shutil.rmtree

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    def leave_temp_root(path: str | Path, *args: object, **kwargs: object) -> None:
        if Path(path) == temp_root:
            return
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(quality_runner.shutil, "rmtree", leave_temp_root)

    try:
        with pytest.raises(OSError, match="temporary workspace"):
            run_quality_fixture(fixture, "ci", output, markdown)

        assert output.read_text(encoding="utf-8") == "old-json\n"
        assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
        assert temp_root.exists()
    finally:
        original_rmtree(temp_root, ignore_errors=True)


def test_quality_runner_renders_all_artifacts_before_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")

    def fail_markdown(report: dict) -> str:
        raise RuntimeError("markdown rendering failed")

    monkeypatch.setattr(
        "context_search_tool.quality.reports.render_markdown_report",
        fail_markdown,
    )

    with pytest.raises(RuntimeError, match="markdown rendering failed"):
        run_quality_fixture(fixture, "ci", output, markdown)

    assert output.read_text(encoding="utf-8") == "old-json\n"
    assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
    assert {path.name for path in reports.iterdir()} == {
        "quality.json",
        "quality.md",
    }


def test_quality_runner_temp_write_failure_preserves_existing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_fdopen = os.fdopen

    def fail_staged_write(
        descriptor: int,
        mode: str = "r",
        *args: object,
        **kwargs: object,
    ) -> object:
        if mode == "wb":
            raise OSError("temporary write failed")
        return original_fdopen(descriptor, mode, *args, **kwargs)

    monkeypatch.setattr(quality_runner.os, "fdopen", fail_staged_write)

    with pytest.raises(OSError, match="temporary write failed"):
        run_quality_fixture(fixture, "ci", output, markdown)

    assert output.read_text(encoding="utf-8") == "old-json\n"
    assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
    assert {path.name for path in reports.iterdir()} == {
        "quality.json",
        "quality.md",
    }


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX symlinks")
def test_stage_sibling_file_never_writes_through_swapped_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "quality.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("private\n", encoding="utf-8")
    original_mkstemp = quality_runner.tempfile.mkstemp
    temporary_path: Path | None = None

    def swap_staging_name_to_symlink(*args: object, **kwargs: object) -> tuple[int, str]:
        nonlocal temporary_path
        descriptor, name = original_mkstemp(*args, **kwargs)
        temporary_path = Path(name)
        temporary_path.unlink()
        temporary_path.symlink_to(victim)
        return descriptor, name

    monkeypatch.setattr(
        quality_runner.tempfile,
        "mkstemp",
        swap_staging_name_to_symlink,
    )

    with pytest.raises(OSError, match="staging path"):
        quality_runner._stage_sibling_file(destination, "published\n", "stage")

    assert victim.read_text(encoding="utf-8") == "private\n"
    assert temporary_path is not None
    assert not temporary_path.exists()
    assert not temporary_path.is_symlink()


@pytest.mark.parametrize(
    "destination_kind",
    [
        pytest.param("symlink", id="symlink"),
        pytest.param("fifo", id="fifo"),
        pytest.param("device", id="device"),
        pytest.param("hardlink", id="hardlink"),
    ],
)
def test_quality_runner_rejects_unsafe_existing_artifact_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destination_kind: str,
) -> None:
    if destination_kind == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is not supported on this platform")
    if destination_kind == "device" and os.name != "posix":
        pytest.skip("device-node assertion requires POSIX")

    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    victim = reports / "victim.txt"
    victim.write_text("private\n", encoding="utf-8")

    if destination_kind == "symlink":
        output.symlink_to(victim.name)
    elif destination_kind == "fifo":
        os.mkfifo(output)
    elif destination_kind == "device":
        output = Path("/dev/null")
    else:
        os.link(victim, output)

    original_link = os.readlink(output) if output.is_symlink() else None
    original_inode = output.lstat().st_ino
    rendered = False
    staged = False

    def record_render(report: dict) -> str:
        nonlocal rendered
        rendered = True
        return "markdown\n"

    def record_stage(destination: Path, content: str | bytes, kind: str) -> Path:
        nonlocal staged
        staged = True
        raise AssertionError("unsafe destination reached artifact staging")

    monkeypatch.setattr(
        "context_search_tool.quality.reports.render_markdown_report",
        record_render,
    )
    monkeypatch.setattr(quality_runner, "_stage_sibling_file", record_stage)

    with pytest.raises(ValueError, match="artifact destination"):
        quality_runner._render_artifacts({}, output, markdown)
    with pytest.raises(ValueError, match="artifact destination"):
        quality_runner._publish_artifacts(
            [(output, "json\n"), (markdown, "markdown\n")]
        )

    assert rendered is False
    assert staged is False
    assert output.lstat().st_ino == original_inode
    if destination_kind == "symlink":
        assert output.is_symlink()
        assert os.readlink(output) == original_link
    elif destination_kind == "fifo":
        assert stat.S_ISFIFO(output.lstat().st_mode)
    elif destination_kind == "hardlink":
        assert output.stat().st_ino == victim.stat().st_ino
    assert victim.read_text(encoding="utf-8") == "private\n"
    assert not any(path.name.startswith(".") for path in reports.iterdir())


def test_artifact_backup_opens_existing_file_no_follow_and_nonblocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "quality.json"
    output.write_text("old-json\n", encoding="utf-8")
    original_open = os.open
    backup_flags: list[int] = []

    def tracking_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == output:
            backup_flags.append(flags)
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(quality_runner.os, "open", tracking_open)

    quality_runner._publish_artifacts([(output, "new-json\n")])

    assert backup_flags
    assert all(flags & os.O_NOFOLLOW for flags in backup_flags)
    assert all(flags & os.O_NONBLOCK for flags in backup_flags)
    assert output.read_text(encoding="utf-8") == "new-json\n"


@pytest.mark.parametrize(
    "output_exists",
    [
        pytest.param(True, id="restore-existing"),
        pytest.param(False, id="remove-new"),
    ],
)
def test_quality_runner_second_replace_failure_rolls_back_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_exists: bool,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    if output_exists:
        output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_replace = os.replace
    replace_count = 0

    def fail_second_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("second replace failed")
        original_replace(source, destination)

    monkeypatch.setattr(quality_runner.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="second replace failed"):
        run_quality_fixture(fixture, "ci", output, markdown)

    assert replace_count >= (3 if output_exists else 2)
    if output_exists:
        assert output.read_text(encoding="utf-8") == "old-json\n"
    else:
        assert not output.exists()
    assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
    assert {path.name for path in reports.iterdir()} == (
        {"quality.json", "quality.md"} if output_exists else {"quality.md"}
    )


def test_quality_runner_keyboard_interrupt_rolls_back_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "quality.json"
    markdown = tmp_path / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_replace = os.replace
    replace_count = 0

    def interrupt_second_replace(
        source: str | Path,
        destination: str | Path,
    ) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise KeyboardInterrupt("second replace interrupted")
        original_replace(source, destination)

    monkeypatch.setattr(quality_runner.os, "replace", interrupt_second_replace)

    with pytest.raises(KeyboardInterrupt, match="second replace interrupted"):
        quality_runner._publish_artifacts(
            [(output, "new-json\n"), (markdown, "new-markdown\n")]
        )

    assert output.read_text(encoding="utf-8") == "old-json\n"
    assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
    assert {path.name for path in tmp_path.iterdir()} == {
        "quality.json",
        "quality.md",
    }


def test_quality_runner_atomically_replaces_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    markdown = reports / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")

    report = run_quality_fixture(fixture, "ci", output, markdown)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert markdown.read_text(encoding="utf-8").startswith(
        "# Retrieval Quality Report\n"
    )
    assert {path.name for path in reports.iterdir()} == {
        "quality.json",
        "quality.md",
    }


@pytest.mark.parametrize(
    "alias_kind",
    [
        pytest.param("same", id="same-path"),
        pytest.param("normalized", id="normalized-path"),
        pytest.param("symlink", id="symlink-alias"),
        pytest.param("hardlink", id="hardlink-alias"),
    ],
)
def test_quality_runner_rejects_aliasing_artifact_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alias_kind: str,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / "quality.json"
    output.write_text("old-artifact\n", encoding="utf-8")

    if alias_kind == "same":
        markdown = output
    elif alias_kind == "normalized":
        (reports / "nested").mkdir()
        markdown = reports / "nested" / ".." / "quality.json"
    elif alias_kind == "symlink":
        markdown = reports / "quality.md"
        markdown.symlink_to(output.name)
    else:
        markdown = reports / "quality.md"
        os.link(output, markdown)

    original_inode = output.stat().st_ino
    original_link = os.readlink(markdown) if markdown.is_symlink() else None

    with pytest.raises(ValueError, match="artifact destinations must be distinct"):
        run_quality_fixture(fixture, "ci", output, markdown)

    assert output.read_text(encoding="utf-8") == "old-artifact\n"
    if alias_kind == "symlink":
        assert markdown.is_symlink()
        assert os.readlink(markdown) == original_link
    elif alias_kind == "hardlink":
        assert markdown.stat().st_ino == original_inode
        assert markdown.read_text(encoding="utf-8") == "old-artifact\n"
    assert not any(path.name.startswith(".") for path in reports.rglob("*"))


@pytest.mark.parametrize(
    ("output_name", "markdown_name"),
    [
        pytest.param("Report.JSON", "report.json", id="casefold"),
        pytest.param(
            unicodedata.normalize("NFC", "café.json"),
            unicodedata.normalize("NFD", "café.json"),
            id="unicode-normalization",
        ),
    ],
)
def test_quality_runner_rejects_portable_artifact_aliases_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_name: str,
    markdown_name: str,
) -> None:
    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    rendered = False

    def record_markdown_render(report: dict) -> str:
        nonlocal rendered
        rendered = True
        return "markdown\n"

    monkeypatch.setattr(
        "context_search_tool.quality.reports.render_markdown_report",
        record_markdown_render,
    )

    with pytest.raises(ValueError, match="artifact destinations must be distinct"):
        run_quality_fixture(
            fixture,
            "ci",
            reports / output_name,
            reports / markdown_name,
        )

    assert rendered is False
    assert list(reports.iterdir()) == []


@pytest.mark.parametrize(
    ("output_name", "markdown_name"),
    [
        pytest.param("Report.JSON", "report.json", id="casefold"),
        pytest.param(
            unicodedata.normalize("NFC", "café.json"),
            unicodedata.normalize("NFD", "café.json"),
            id="unicode-normalization",
        ),
    ],
)
def test_quality_runner_rejects_nonexistent_aliases_on_insensitive_filesystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_name: str,
    markdown_name: str,
) -> None:
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    first_probe = probe_dir / output_name
    second_probe = probe_dir / markdown_name
    first_probe.write_text("probe\n", encoding="utf-8")
    aliases_on_filesystem = second_probe.exists() and os.path.samefile(
        first_probe,
        second_probe,
    )
    first_probe.unlink()
    if not aliases_on_filesystem:
        pytest.skip("filesystem distinguishes these spellings")

    fixture = _write_successful_ci_fixture(tmp_path, monkeypatch)
    reports = tmp_path / "reports"
    reports.mkdir()
    output = reports / output_name
    markdown = reports / markdown_name
    assert not output.exists()
    assert not markdown.exists()

    with pytest.raises(ValueError, match="artifact destinations must be distinct"):
        run_quality_fixture(fixture, "ci", output, markdown)

    assert list(reports.iterdir()) == []


def test_artifact_rollback_does_not_overwrite_concurrent_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "quality.json"
    markdown = tmp_path / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_replace = os.replace
    rollback_replace_reached = threading.Event()
    successful_writer_attempted = threading.Event()
    successful_writer_done = threading.Event()
    failures: list[BaseException] = []

    def controlled_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            threading.current_thread().name == "failing-writer"
            and destination_path == markdown
            and ".stage-" in source_path.name
        ):
            raise OSError("second replace failed")
        if (
            threading.current_thread().name == "failing-writer"
            and destination_path == output
            and ".backup-" in source_path.name
        ):
            rollback_replace_reached.set()
            if not successful_writer_attempted.wait(timeout=5):
                raise AssertionError("concurrent writer did not attempt publication")
        original_replace(source, destination)

    monkeypatch.setattr(quality_runner.os, "replace", controlled_replace)

    def publish_failing() -> None:
        try:
            quality_runner._publish_artifacts(
                [(output, "failing-json\n"), (markdown, "failing-markdown\n")]
            )
        except BaseException as exc:
            failures.append(exc)

    def publish_successful() -> None:
        if not rollback_replace_reached.wait(timeout=5):
            failures.append(AssertionError("rollback replacement was not reached"))
            return
        successful_writer_attempted.set()
        quality_runner._publish_artifacts(
            [(output, "new-json\n"), (markdown, "new-markdown\n")]
        )
        successful_writer_done.set()

    failing_thread = threading.Thread(target=publish_failing, name="failing-writer")
    successful_thread = threading.Thread(
        target=publish_successful,
        name="successful-writer",
    )
    successful_thread.start()
    failing_thread.start()
    failing_thread.join(timeout=5)
    successful_thread.join(timeout=5)

    assert not failing_thread.is_alive()
    assert not successful_thread.is_alive()
    assert rollback_replace_reached.is_set()
    assert successful_writer_attempted.is_set()
    assert successful_writer_done.is_set()
    assert len(failures) == 1
    assert isinstance(failures[0], OSError)
    assert "second replace failed" in str(failures[0])
    assert output.read_text(encoding="utf-8") == "new-json\n"
    assert markdown.read_text(encoding="utf-8") == "new-markdown\n"


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX advisory locks")
def test_artifact_publication_lock_coordinates_processes(tmp_path: Path) -> None:
    output = tmp_path / "quality.json"
    output.write_text("old-json\n", encoding="utf-8")
    script = """
import sys
from pathlib import Path
from context_search_tool.quality.runner import _publish_artifacts

print("ready", flush=True)
_publish_artifacts([(Path(sys.argv[1]), "new-json\\n")])
print("done", flush=True)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    with quality_runner._artifact_publication_lock():
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(output)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        assert process.stdout is not None
        assert process.stdout.readline() == "ready\n"
        assert process.poll() is None
        assert output.read_text(encoding="utf-8") == "old-json\n"

    stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert stdout == "done\n"
    assert output.read_text(encoding="utf-8") == "new-json\n"


@pytest.mark.skipif(
    os.name != "posix" or quality_runner.fcntl is None,
    reason="requires POSIX advisory locks",
)
def test_artifact_publication_lock_is_independent_of_process_tmpdir(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality.json"
    output.write_text("old-json\n", encoding="utf-8")
    child_tmp = tmp_path / "child-tmp"
    child_tmp.mkdir()
    script = """
import fcntl
import sys
from pathlib import Path
import context_search_tool.quality.runner as runner

real_flock = runner.fcntl.flock

def nonblocking_flock(descriptor, operation):
    return real_flock(descriptor, operation | fcntl.LOCK_NB)

runner.fcntl.flock = nonblocking_flock
try:
    runner._publish_artifacts([(Path(sys.argv[1]), "new-json\\n")])
except BlockingIOError:
    print("blocked")
else:
    print("acquired")
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    environment["TMPDIR"] = str(child_tmp)

    with quality_runner._artifact_publication_lock():
        result = subprocess.run(
            [sys.executable, "-c", script, str(output)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )

        assert result.stdout == "blocked\n"
        assert output.read_text(encoding="utf-8") == "old-json\n"


@pytest.mark.skipif(
    os.name != "posix" or quality_runner.fcntl is None,
    reason="requires POSIX advisory locks",
)
def test_artifact_publication_lock_rejects_unexpected_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fstat = os.fstat

    class WrongOwnerStatus:
        def __init__(self, descriptor: int) -> None:
            status = original_fstat(descriptor)
            self.st_mode = status.st_mode
            self.st_nlink = status.st_nlink
            self.st_uid = status.st_uid + 1

    monkeypatch.setattr(
        quality_runner.os,
        "fstat",
        lambda descriptor: WrongOwnerStatus(descriptor),
    )

    with pytest.raises(OSError, match="unexpected owner"):
        with quality_runner._artifact_publication_lock():
            raise AssertionError("untrusted lock owner was accepted")


@pytest.mark.skipif(
    os.name != "posix" or quality_runner.fcntl is None,
    reason="requires POSIX advisory locks",
)
def test_artifact_publication_lock_enforces_private_permissions() -> None:
    lock_path = quality_runner._ARTIFACT_PUBLICATION_LOCK_PATH
    lock_path.touch(mode=0o600, exist_ok=True)
    lock_path.chmod(0o644)
    try:
        with quality_runner._artifact_publication_lock():
            assert lock_path.stat().st_mode & 0o777 == 0o600
    finally:
        lock_path.chmod(0o600)


@pytest.mark.skipif(
    os.name != "posix" or quality_runner.fcntl is None,
    reason="requires POSIX advisory locks",
)
def test_artifact_publication_lock_rejects_hardlink_before_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("private\n", encoding="utf-8")
    victim.chmod(0o640)
    lock_path = tmp_path / "publication.lock"
    os.link(victim, lock_path)
    original_mode = stat.S_IMODE(victim.stat().st_mode)
    monkeypatch.setattr(
        quality_runner,
        "_ARTIFACT_PUBLICATION_LOCK_PATH",
        lock_path,
    )

    with pytest.raises(OSError, match="single-link regular file"):
        with quality_runner._artifact_publication_lock():
            raise AssertionError("hardlinked publication lock was accepted")

    assert victim.read_text(encoding="utf-8") == "private\n"
    assert stat.S_IMODE(victim.stat().st_mode) == original_mode
    assert lock_path.stat().st_ino == victim.stat().st_ino


def test_artifact_rollback_does_not_overwrite_noncooperative_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "quality.json"
    markdown = tmp_path / "quality.md"
    output.write_text("old-json\n", encoding="utf-8")
    markdown.write_text("old-markdown\n", encoding="utf-8")
    original_replace = os.replace

    def overwrite_then_fail(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == markdown and ".stage-" in source_path.name:
            output.write_text("external-json\n", encoding="utf-8")
            raise OSError("second replace failed")
        original_replace(source, destination)

    monkeypatch.setattr(quality_runner.os, "replace", overwrite_then_fail)

    with pytest.raises(OSError, match="second replace failed") as error:
        quality_runner._publish_artifacts(
            [(output, "new-json\n"), (markdown, "new-markdown\n")]
        )

    assert any(
        "rollback skipped" in note
        for note in getattr(error.value, "__notes__", [])
    )
    assert output.read_text(encoding="utf-8") == "external-json\n"
    assert markdown.read_text(encoding="utf-8") == "old-markdown\n"
    assert {path.name for path in tmp_path.iterdir()} == {
        "quality.json",
        "quality.md",
    }


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


def test_runner_rejects_zero_selected_or_executed_without_allow_empty(
    tmp_path: Path,
) -> None:
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
                    "repo_dir_name": "missing",
                    "profiles": ["smoke"],
                    "queries": [{"id": "q", "query": "q"}],
                }
            ],
        },
    )
    output = tmp_path / "nested" / "reports" / "quality.json"
    markdown = tmp_path / "nested" / "reports" / "quality.md"

    with pytest.raises(ValueError, match="no cases executed"):
        run_quality_fixture(fixture, "smoke", output, markdown)

    assert output.exists()
    assert markdown.exists()
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
