import sqlite3
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.models import DocumentChunk
from context_search_tool.paths import index_dir_for
from context_search_tool.project_scope import (
    PROJECT_SCOPE_METADATA_VERSION,
    PROJECT_SCOPE_METADATA_VERSION_KEY,
    ProjectUnit,
    detect_project_units,
    infer_query_scope,
    project_metadata,
    project_scope_rerank_adjustment,
    project_scope_score_parts,
    project_units_from_chunk_metadata,
    unit_for_path,
)
from context_search_tool.sqlite_store import SQLiteStore


def test_marker_detection_finds_root_and_child_units_with_deepest_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"dependencies":{"vite":"latest"}}\n')
    (repo / "frontend").mkdir()
    (repo / "frontend" / "package.json").write_text(
        '{"dependencies":{"vue":"latest","@vitejs/plugin-vue":"latest"}}\n'
    )
    (repo / "frontend" / "src").mkdir()
    (repo / "frontend" / "src" / "auth.store.ts").write_text("export {}\n")
    (repo / "collector").mkdir()
    (repo / "collector" / "go.mod").write_text("module collector\n")
    (repo / "backend").mkdir()
    (repo / "backend" / "pom.xml").write_text("<project />\n")

    units = detect_project_units(
        repo,
        [
            Path("frontend/src/auth.store.ts"),
            Path("collector/internal/api/handler/collect_handler.go"),
            Path("backend/src/main/java/JwtAuthenticationFilter.java"),
        ],
    )

    by_root = {project_metadata(unit)["project_root"]: unit for unit in units}
    assert set(by_root) == {"", "frontend", "collector", "backend"}
    assert by_root[""].name == repo.name
    assert by_root["frontend"].kind == "frontend"
    assert by_root["frontend"].languages == ("typescript", "vue")
    assert by_root["collector"].kind == "go"
    assert by_root["backend"].kind == "java"
    assert unit_for_path(Path("frontend/src/auth.store.ts"), units) == by_root["frontend"]


def test_marker_discovery_finds_unscanned_go_mod(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "collector").mkdir()
    (repo / "collector" / "go.mod").write_text("module collector\n")

    units = detect_project_units(
        repo,
        [Path("collector/internal/api/handler/collect_handler.go")],
    )

    assert any(unit.root == Path("collector") and unit.kind == "go" for unit in units)


def test_marker_only_in_relative_paths_discovers_unit_when_file_absent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    units = detect_project_units(repo, [Path("collector/go.mod")])

    assert ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 0.9) in units


def test_marker_discovery_skips_ignored_and_symlinked_directories(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "node_modules" / "lib").mkdir(parents=True)
    (repo / "node_modules" / "lib" / "package.json").write_text('{"dependencies":{"vite":"latest"}}\n')
    real_external = tmp_path / "external"
    real_external.mkdir()
    (real_external / "go.mod").write_text("module external\n")
    (repo / "linked").symlink_to(real_external, target_is_directory=True)

    units = detect_project_units(repo, [])

    assert units == (
        ProjectUnit(Path(""), repo.name, "unknown", (), (), 0.0),
    )


def test_relative_path_markers_skip_ignored_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    units = detect_project_units(
        repo,
        [
            Path("node_modules/lib/package.json"),
            Path("target/generated/pom.xml"),
            Path("build/package.json"),
        ],
    )

    assert units == (
        ProjectUnit(Path(""), repo.name, "unknown", (), (), 0.0),
    )


def test_root_package_json_does_not_inherit_nested_frontend_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name":"root"}\n')
    (repo / "frontend" / "src").mkdir(parents=True)
    (repo / "frontend" / "src" / "App.vue").write_text("<template />\n")

    units = detect_project_units(repo, [Path("frontend/src/App.vue")])
    by_root = {project_metadata(unit)["project_root"]: unit for unit in units}

    assert by_root[""].kind == "node"
    assert by_root[""].languages == ()


def test_no_marker_falls_back_to_root_unknown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    units = detect_project_units(repo, [Path("src/main.py")])

    assert units == (
        ProjectUnit(
            root=Path(""),
            name=repo.name,
            kind="unknown",
            languages=(),
            markers=(),
            confidence=0.0,
        ),
    )


def test_project_metadata_is_json_compatible() -> None:
    unit = ProjectUnit(
        root=Path("frontend"),
        name="frontend",
        kind="frontend",
        languages=("typescript", "vue"),
        markers=("package.json",),
        confidence=0.9,
    )
    root_unit = ProjectUnit(
        root=Path(""),
        name="repo",
        kind="unknown",
        languages=(),
        markers=(),
        confidence=0.0,
    )

    assert project_metadata(unit) == {
        PROJECT_SCOPE_METADATA_VERSION_KEY: PROJECT_SCOPE_METADATA_VERSION,
        "project_root": "frontend",
        "project_name": "frontend",
        "project_kind": "frontend",
        "project_languages": ["typescript", "vue"],
        "project_markers": ["package.json"],
    }
    assert project_metadata(root_unit)["project_root"] == ""


def test_indexer_writes_project_metadata_to_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "frontend" / "src").mkdir(parents=True)
    (repo / "frontend" / "package.json").write_text(
        '{"dependencies":{"vite":"latest","vue":"latest","@vitejs/plugin-vue":"latest"}}\n',
        encoding="utf-8",
    )
    (repo / "frontend" / "src" / "main.ts").write_text(
        "import App from './App.vue'\n",
        encoding="utf-8",
    )
    (repo / "frontend" / "src" / "App.vue").write_text(
        "<script setup lang=\"ts\">const title = 'Dashboard'</script>\n",
        encoding="utf-8",
    )

    index_repository(repo, DEFAULT_CONFIG)

    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    source_file = store.source_file_for_path(Path("frontend/src/App.vue"))
    assert source_file is not None
    assert source_file.metadata["project_root"] == "frontend"
    assert source_file.metadata["project_kind"] == "frontend"
    assert source_file.metadata["project_languages"] == ["typescript", "vue"]
    assert (
        source_file.metadata[PROJECT_SCOPE_METADATA_VERSION_KEY]
        == PROJECT_SCOPE_METADATA_VERSION
    )

    chunks = store.chunks_for_file(Path("frontend/src/App.vue"), limit=10)
    assert chunks
    assert chunks[0].metadata["project_root"] == "frontend"
    assert chunks[0].metadata["project_kind"] == "frontend"
    assert chunks[0].metadata["project_languages"] == ["typescript", "vue"]
    assert (
        chunks[0].metadata[PROJECT_SCOPE_METADATA_VERSION_KEY]
        == PROJECT_SCOPE_METADATA_VERSION
    )
    assert store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY) == str(
        PROJECT_SCOPE_METADATA_VERSION
    )


def test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_stale(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "collector" / "internal" / "scheduler").mkdir(parents=True)
    (repo / "collector" / "go.mod").write_text("module collector\n", encoding="utf-8")
    (repo / "collector" / "internal" / "scheduler" / "scheduler.go").write_text(
        "package scheduler\n\nfunc Run() {}\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    store.set_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY, "0")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_skipped == 0
    assert summary.files_indexed == 1
    chunks = store.chunks_for_file(
        Path("collector/internal/scheduler/scheduler.go"),
        limit=10,
    )
    assert chunks
    assert chunks[0].metadata["project_root"] == "collector"
    assert chunks[0].metadata["project_kind"] == "go"
    assert (
        chunks[0].metadata[PROJECT_SCOPE_METADATA_VERSION_KEY]
        == PROJECT_SCOPE_METADATA_VERSION
    )
    assert store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY) == str(
        PROJECT_SCOPE_METADATA_VERSION
    )


def test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_absent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "backend" / "src" / "main" / "java" / "com" / "example").mkdir(
        parents=True
    )
    (repo / "backend" / "build.gradle").write_text(
        "plugins { id 'java' }\n",
        encoding="utf-8",
    )
    java_path = Path("backend/src/main/java/com/example/AuthController.java")
    (repo / java_path).write_text(
        "package com.example;\n\nclass AuthController {}\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    with sqlite3.connect(index_dir_for(repo) / "index.sqlite") as connection:
        connection.execute(
            "DELETE FROM index_metadata WHERE key = ?",
            (PROJECT_SCOPE_METADATA_VERSION_KEY,),
        )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_skipped == 0
    assert summary.files_indexed == 1
    chunks = store.chunks_for_file(java_path, limit=10)
    assert chunks
    assert chunks[0].metadata["project_root"] == "backend"
    assert chunks[0].metadata["project_kind"] == "java"
    assert (
        chunks[0].metadata[PROJECT_SCOPE_METADATA_VERSION_KEY]
        == PROJECT_SCOPE_METADATA_VERSION
    )
    assert store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY) == str(
        PROJECT_SCOPE_METADATA_VERSION
    )


def test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_invalid(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "collector" / "internal" / "scheduler").mkdir(parents=True)
    (repo / "collector" / "go.mod").write_text("module collector\n", encoding="utf-8")
    scheduler_path = Path("collector/internal/scheduler/scheduler.go")
    (repo / scheduler_path).write_text(
        "package scheduler\n\nfunc Run() {}\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    store.set_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY, "not-an-int")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_skipped == 0
    assert summary.files_indexed == 1
    chunks = store.chunks_for_file(scheduler_path, limit=10)
    assert chunks
    assert chunks[0].metadata["project_root"] == "collector"
    assert chunks[0].metadata["project_kind"] == "go"
    assert (
        chunks[0].metadata[PROJECT_SCOPE_METADATA_VERSION_KEY]
        == PROJECT_SCOPE_METADATA_VERSION
    )
    assert store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY) == str(
        PROJECT_SCOPE_METADATA_VERSION
    )


def test_infer_query_scope_ignores_shared_business_words() -> None:
    units = (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), (), 0.9),
    )

    scope = infer_query_scope(
        "auth portfolio fund service",
        ["auth", "portfolio", "fund", "service"],
        units,
    )

    assert scope.project_names == ()
    assert scope.kinds == ()
    assert scope.languages == ()
    assert scope.path_prefixes == ()
    assert scope.file_hints == ()
    assert scope.confidence == 0.0


def test_infer_query_scope_uses_kind_literal_with_non_kind_project_name() -> None:
    units = (
        ProjectUnit(
            Path("webapp"),
            "webapp",
            "frontend",
            ("typescript", "vue"),
            ("package.json",),
            0.9,
        ),
    )

    scope = infer_query_scope("frontend auth flow", ["frontend", "auth", "flow"], units)

    assert scope.project_names == ()
    assert scope.kinds == ("frontend",)
    assert scope.languages == ("typescript", "vue")
    assert scope.confidence > 0.0


def test_infer_query_scope_uses_path_filename_language_marker_extension_and_layout_hints() -> None:
    units = (
        ProjectUnit(
            Path("frontend"),
            "frontend",
            "frontend",
            ("typescript", "vue"),
            ("package.json",),
            0.9,
        ),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 0.9),
        ProjectUnit(Path("backend"), "backend", "java", ("java",), ("pom.xml",), 0.9),
    )

    scope = infer_query_scope(
        (
            "frontend/src auth.store.ts .vue package.json vue pinia vite EventSource "
            "collector/internal collect_handler.go .go go.mod gin go "
            "backend JwtAuthenticationFilter.java .java pom.xml maven spring java"
        ),
        [],
        units,
    )

    assert scope.path_prefixes == ("frontend/src", "collector/internal")
    assert scope.project_names == ("backend", "collector", "frontend")
    assert scope.kinds == ("frontend", "go", "java")
    assert scope.languages == ("go", "java", "typescript", "vue")
    assert {"auth.store.ts", "collect_handler.go", "jwtauthenticationfilter.java"} <= set(
        scope.file_hints
    )
    assert {"package.json", "go.mod", "pom.xml"} <= set(scope.file_hints)
    assert scope.confidence >= 0.6


def test_project_scope_score_parts_returns_empty_for_single_project_repo() -> None:
    chunk = _chunk("frontend/src/auth.store.ts", project_name="frontend")
    scope = infer_query_scope("frontend auth.store.ts", [], ())

    assert project_scope_score_parts(chunk, scope, project_unit_count=1) == {}


def test_project_scope_score_parts_boosts_matching_frontend_and_penalizes_backend() -> None:
    scope = infer_query_scope(
        "frontend/src auth.store.ts vue",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
        ),
    )
    frontend_chunk = _chunk(
        "frontend/src/auth.store.ts",
        project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
        project_root="frontend",
        project_name="frontend",
        project_kind="frontend",
        project_languages=["typescript", "vue"],
    )
    backend_chunk = _chunk(
        "backend/src/main/java/JwtAuthenticationFilter.java",
        project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
        project_root="backend",
        project_name="backend",
        project_kind="java",
        project_languages=["java"],
    )

    frontend_parts = project_scope_score_parts(frontend_chunk, scope, project_unit_count=2)
    backend_parts = project_scope_score_parts(backend_chunk, scope, project_unit_count=2)

    assert frontend_parts == {
        "project_scope_boost": 0.10,
        "project_kind_boost": 0.06,
        "project_language_boost": 0.04,
        "project_path_hint_boost": 0.08,
    }
    assert project_scope_rerank_adjustment(frontend_parts) == 0.28
    assert backend_parts == {"project_scope_mismatch_penalty": -0.06}


def test_pom_xml_and_evidence_anchor_paths_do_not_get_mismatch_penalty() -> None:
    scope = infer_query_scope(
        "frontend/src auth.store.ts vue",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
        ),
    )

    assert project_scope_score_parts(
        _chunk(
            "backend/pom.xml",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="backend",
            project_name="backend",
            project_kind="java",
        ),
        scope,
        project_unit_count=2,
    ) == {}
    assert project_scope_score_parts(
        _chunk(
            "docs/risks.md",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="",
            project_name="repo",
            project_kind="unknown",
        ),
        scope,
        project_unit_count=2,
    ) == {}


def test_missing_and_stale_metadata_are_neutral_for_score_parts() -> None:
    scope = infer_query_scope(
        "frontend auth.store.ts vue",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
        ),
    )

    assert project_scope_score_parts(
        _chunk("backend/src/auth.store.ts"),
        scope,
        project_unit_count=2,
    ) == {}
    assert project_scope_score_parts(
        _chunk(
            "frontend/src/auth.store.ts",
            project_scope_metadata_version=0,
            project_root="frontend",
            project_name="frontend",
            project_kind="frontend",
            project_languages=["typescript", "vue"],
        ),
        scope,
        project_unit_count=2,
    ) == {}


def test_duplicate_filename_does_not_boost_conflicting_project() -> None:
    scope = infer_query_scope(
        "frontend auth.store.ts vue",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
        ),
    )

    parts = project_scope_score_parts(
        _chunk(
            "backend/src/auth.store.ts",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="backend",
            project_name="backend",
            project_kind="java",
            project_languages=["java"],
        ),
        scope,
        project_unit_count=2,
    )

    assert "project_path_hint_boost" not in parts
    assert parts == {"project_scope_mismatch_penalty": -0.06}


def test_filename_only_query_can_boost_matching_file_without_conflict() -> None:
    scope = infer_query_scope(
        "auth.store.ts",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("admin"), "admin", "frontend", ("typescript", "vue"), (), 0.9),
        ),
    )

    assert project_scope_score_parts(
        _chunk(
            "admin/src/auth.store.ts",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="admin",
            project_name="admin",
            project_kind="frontend",
            project_languages=["typescript", "vue"],
        ),
        scope,
        project_unit_count=2,
    ) == {
        "project_language_boost": 0.04,
        "project_path_hint_boost": 0.08,
    }


def test_low_confidence_and_mixed_scope_do_not_trigger_mismatch_penalty() -> None:
    low_confidence_scope = infer_query_scope(
        "auth.store.ts",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
        ),
    )
    mixed_scope = infer_query_scope(
        "frontend backend auth.store.ts vue spring",
        [],
        (
            ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), (), 0.9),
            ProjectUnit(Path("backend"), "backend", "java", ("java",), (), 0.9),
            ProjectUnit(Path("collector"), "collector", "go", ("go",), (), 0.9),
        ),
    )

    assert project_scope_score_parts(
        _chunk(
            "backend/src/Auth.java",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="backend",
            project_name="backend",
            project_kind="java",
            project_languages=["java"],
        ),
        low_confidence_scope,
        project_unit_count=2,
    ) == {}
    assert project_scope_score_parts(
        _chunk(
            "collector/internal/auth.go",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="collector",
            project_name="collector",
            project_kind="go",
            project_languages=["go"],
        ),
        mixed_scope,
        project_unit_count=3,
    ) == {}


def test_project_units_from_chunk_metadata_dedupes_units() -> None:
    chunks = [
        _chunk(
            "frontend/src/auth.store.ts",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="frontend",
            project_name="frontend",
            project_kind="frontend",
            project_languages=["typescript", "vue"],
            project_markers=["package.json"],
        ),
        _chunk(
            "frontend/src/main.ts",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="frontend",
            project_name="frontend",
            project_kind="frontend",
            project_languages=["typescript", "vue"],
            project_markers=["package.json"],
        ),
        _chunk(
            "collector/internal/api/handler/collect_handler.go",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="collector",
            project_name="collector",
            project_kind="go",
            project_languages=["go"],
            project_markers=["go.mod"],
        ),
    ]

    units = project_units_from_chunk_metadata(chunks)

    assert units == (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), ("package.json",), 1.0),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 1.0),
    )


def test_project_units_from_chunk_metadata_ignores_missing_and_stale_metadata() -> None:
    chunks = [
        _chunk(
            "frontend/src/auth.store.ts",
            project_root="frontend",
            project_name="frontend",
            project_kind="frontend",
            project_languages=["typescript", "vue"],
            project_markers=["package.json"],
        ),
        _chunk(
            "backend/src/Auth.java",
            project_scope_metadata_version=0,
            project_root="backend",
            project_name="backend",
            project_kind="java",
            project_languages=["java"],
            project_markers=["pom.xml"],
        ),
        _chunk(
            "collector/internal/auth.go",
            project_scope_metadata_version=PROJECT_SCOPE_METADATA_VERSION,
            project_root="collector",
            project_name="collector",
            project_kind="go",
            project_languages=["go"],
            project_markers=["go.mod"],
        ),
    ]

    assert project_units_from_chunk_metadata(chunks) == (
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 1.0),
    )


def _chunk(path: str, **metadata: object) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=path,
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content="",
        chunk_type="generic",
        metadata=metadata,
    )
