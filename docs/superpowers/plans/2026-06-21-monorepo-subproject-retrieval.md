# Monorepo Subproject Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve root-indexed monorepo retrieval by detecting generic subproject boundaries, annotating chunks with project metadata, and using project scope as a conservative rerank signal.

**Architecture:** Add a small language-neutral `project_scope.py` module for project-unit detection, query-scope inference, and score-part calculation. Indexing writes project metadata onto each `DocumentChunk.metadata` and versions that metadata so old unchanged indexes are rewritten. Retrieval consumes project scope parts in `rerank_score` only, leaving `_combined_score` unchanged for this milestone and preserving existing Java/Spring rerank behavior.

**Tech Stack:** Python 3.11+, pytest, existing scanner/indexer/retrieval pipeline, SQLite metadata, existing hash embedding defaults, optional real-repo smoke through `CST_SMOKE_INVESTMENT_ASSISTANT_REPO`.

---

## 1. Problem Statement

The generic baseline quality work reduced generated, template, lockfile, docs, and config noise. It did not fix root-indexed monorepos where a frontend, collector, and backend all share vocabulary such as `auth`, `fund`, `portfolio`, `position`, and `sse`.

Observed shape on `/Users/flobby/vibe_coding/Investment-Assistant`:

- Indexing `frontend`, `collector`, and `investment-assistant-backend` separately already produces acceptable rankings.
- Indexing the monorepo root lets strong Java backend files outrank Vue and Go files for frontend/collector queries.
- Query tokens like `frontend` or `collector` alone are not enough; path/layout/suffix/project-marker context must become ranking context.

This plan implements the first milestone from `docs/superpowers/specs/2026-06-20-monorepo-subproject-retrieval-design.md`.

## 2. Scope

### In Scope

- Detect project units from generic markers: `package.json`, `go.mod`, `pom.xml`, `build.gradle`, `settings.gradle`, `Cargo.toml`, and `pyproject.toml`.
- Discover marker files directly from the repository filesystem, because some markers such as `go.mod` are not normal indexed source files.
- Attach `project_root`, `project_name`, `project_kind`, `project_languages`, and `project_markers` to each chunk.
- Version project-scope metadata with `project_scope_metadata_version = "1"` and rewrite unchanged chunks when the version is absent or stale.
- Infer query scope from path prefixes, filenames, project names, framework/tool terms, file extensions, and layout hints.
- Use project score parts as a rerank-only adjustment: `project_scope_boost`, `project_kind_boost`, `project_language_boost`, `project_path_hint_boost`, and `project_scope_mismatch_penalty`.
- Add unit tests, synthetic monorepo ranking tests, and optional real-project smoke coverage for `Investment-Assistant`.
- Preserve existing Java/Spring path graph boosts, generic noise demotion, formatter payload shape, MCP payload shape, and CLI arguments.

### Out Of Scope

- No Vue plugin.
- No Go or Gin plugin.
- No repo-specific alias map.
- No LLM query planner dependency.
- No strict filtering by subproject.
- No separate physical index per subproject.
- No SQLite table migration.
- No `cst stats` project-unit reporting in this milestone.
- No config flag for project scope scoring.

## 3. Files And Responsibilities

- Create: `src/context_search_tool/project_scope.py`
  - Project-unit marker discovery, project-unit detection, metadata conversion, query-scope inference, score-part calculation, and rerank adjustment helper.
- Modify: `src/context_search_tool/indexer.py`
  - Detect units once per index, pass the selected unit into chunk preparation, write chunk metadata, and version project metadata.
- Modify: `src/context_search_tool/retrieval.py`
  - Infer query scope from candidate chunk metadata, merge project score parts, add project rerank adjustment, and add project reasons.
- Create: `tests/test_project_scope.py`
  - Unit tests for detection, metadata, query inference, score parts, and index metadata rewrite.
- Modify: `tests/test_retrieval_pipeline.py`
  - Synthetic monorepo fixture, candidate-pool diagnostics, ranking assertions, and Java regression guard.
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
  - Optional `Investment-Assistant` real smoke queries.
- Modify: `tests/test_generic_baseline_quality.py`
  - Allow the `investment_assistant` fixture key and keep shape validation strict.
- Modify: `README.md`
  - Short user-facing note for monorepo root indexing and separate subproject indexing as a valid workaround.

## 4. Implementation Tasks

### Task 1: Add Project Scope Core Module

**Files:**
- Create: `src/context_search_tool/project_scope.py`
- Create: `tests/test_project_scope.py`

- [ ] **Step 1: Write unit tests for project-unit detection**

Create `tests/test_project_scope.py` with these imports and tests:

```python
from pathlib import Path
import sqlite3

from context_search_tool.models import DocumentChunk
from context_search_tool.project_scope import (
    ProjectUnit,
    QueryScope,
    detect_project_units,
    infer_query_scope,
    project_metadata,
    project_scope_rerank_adjustment,
    project_scope_score_parts,
    project_units_from_chunk_metadata,
    unit_for_path,
)


def _touch(repo: Path, relative: str, content: str = "") -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_project_units_finds_deepest_generic_markers(tmp_path: Path) -> None:
    _touch(tmp_path, "package.json", '{"workspaces":["frontend"]}')
    _touch(tmp_path, "frontend/package.json", '{"dependencies":{"vue":"latest","vite":"latest"}}')
    _touch(tmp_path, "frontend/src/main.ts", "createApp(App)")
    _touch(tmp_path, "frontend/src/App.vue", "<template />")
    _touch(tmp_path, "collector/go.mod", "module collector")
    _touch(tmp_path, "collector/internal/api/handler/collect_handler.go", "package handler")
    _touch(tmp_path, "backend/pom.xml", "<project />")
    _touch(tmp_path, "backend/src/main/java/com/example/AuthController.java", "class AuthController {}")

    units = detect_project_units(tmp_path, [path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file()])

    assert [(unit.root.as_posix(), unit.kind) for unit in units] == [
        (".", "node"),
        ("backend", "java"),
        ("collector", "go"),
        ("frontend", "frontend"),
    ]
    assert unit_for_path(Path("collector/internal/api/handler/collect_handler.go"), units).root == Path("collector")
    assert unit_for_path(Path("frontend/src/App.vue"), units).root == Path("frontend")


def test_detect_project_units_discovers_marker_files_outside_scanned_paths(tmp_path: Path) -> None:
    _touch(tmp_path, "collector/go.mod", "module collector")
    _touch(tmp_path, "collector/internal/api/handler/collect_handler.go", "package handler")

    units = detect_project_units(
        tmp_path,
        [Path("collector/internal/api/handler/collect_handler.go")],
    )

    unit = unit_for_path(Path("collector/internal/api/handler/collect_handler.go"), units)
    assert unit.root == Path("collector")
    assert unit.kind == "go"


def test_detect_project_units_falls_back_to_unknown_root(tmp_path: Path) -> None:
    _touch(tmp_path, "notes/readme.txt", "plain notes")

    units = detect_project_units(tmp_path, [Path("notes/readme.txt")])

    assert units == (
        ProjectUnit(
            root=Path("."),
            name=".",
            kind="unknown",
            languages=(),
            markers=(),
            confidence=0.0,
        ),
    )
```

- [ ] **Step 2: Write unit tests for metadata and query inference**

Append these tests to `tests/test_project_scope.py`:

```python
def test_project_metadata_is_json_compatible() -> None:
    unit = ProjectUnit(
        root=Path("frontend"),
        name="frontend",
        kind="frontend",
        languages=("typescript", "vue"),
        markers=("package.json", "src/App.vue"),
        confidence=0.95,
    )

    assert project_metadata(unit) == {
        "project_root": "frontend",
        "project_name": "frontend",
        "project_kind": "frontend",
        "project_languages": ["typescript", "vue"],
        "project_markers": ["package.json", "src/App.vue"],
    }


def test_infer_query_scope_ignores_shared_business_words() -> None:
    units = (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), ("package.json",), 0.95),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 0.95),
        ProjectUnit(Path("backend"), "backend", "java", ("java",), ("pom.xml",), 0.95),
    )

    scope = infer_query_scope("auth portfolio fund service", ["auth", "portfolio", "fund", "service"], units)

    assert scope == QueryScope()


def test_infer_query_scope_uses_path_filename_language_and_layout_hints() -> None:
    units = (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), ("package.json",), 0.95),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 0.95),
        ProjectUnit(Path("backend"), "backend", "java", ("java",), ("pom.xml",), 0.95),
    )

    frontend_scope = infer_query_scope(
        "frontend/src auth.store.ts useAuthStore Pinia",
        ["frontend", "src", "auth", "store", "ts", "useauthstore", "pinia"],
        units,
    )
    collector_scope = infer_query_scope(
        "collector collect_handler.go gin internal handler",
        ["collector", "collect", "handler", "go", "gin", "internal"],
        units,
    )

    assert frontend_scope.project_names == ("frontend",)
    assert "frontend" in frontend_scope.kinds
    assert "typescript" in frontend_scope.languages
    assert "auth.store.ts" in frontend_scope.file_hints
    assert frontend_scope.confidence >= 0.8
    assert collector_scope.project_names == ("collector",)
    assert collector_scope.kinds == ("go",)
    assert collector_scope.languages == ("go",)
    assert "collect_handler.go" in collector_scope.file_hints
    assert collector_scope.confidence >= 0.8


def test_infer_query_scope_recognizes_marker_and_extension_tokens() -> None:
    units = (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), ("package.json",), 0.95),
        ProjectUnit(Path("collector"), "collector", "go", ("go",), ("go.mod",), 0.95),
        ProjectUnit(Path("backend"), "backend", "java", ("java",), ("pom.xml",), 0.95),
    )

    go_scope = infer_query_scope("go.mod collector .go collect_handler.go", ["go", "mod", "collector", "go", "collect", "handler"], units)
    vue_scope = infer_query_scope("package.json .vue auth.store.ts", ["package", "json", "vue", "auth", "store", "ts"], units)
    java_scope = infer_query_scope("pom.xml .java JwtAuthenticationFilter.java", ["pom", "xml", "java", "jwtauthenticationfilter"], units)

    assert go_scope.kinds == ("go",)
    assert go_scope.languages == ("go",)
    assert "collect_handler.go" in go_scope.file_hints
    assert "frontend" in vue_scope.kinds
    assert "vue" in vue_scope.languages
    assert "auth.store.ts" in vue_scope.file_hints
    assert java_scope.kinds == ("java",)
    assert java_scope.languages == ("java",)
    assert "jwtauthenticationfilter.java" in java_scope.file_hints
```

- [ ] **Step 3: Write unit tests for score parts and rerank adjustment**

Append these tests to `tests/test_project_scope.py`:

```python
def test_project_scope_score_parts_are_zero_for_single_project_repo() -> None:
    chunk = DocumentChunk(
        chunk_id="frontend-auth",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=10,
        content="useAuthStore login register",
        chunk_type="generic",
        metadata={
            "language": "typescript",
            "project_root": "frontend",
            "project_name": "frontend",
            "project_kind": "frontend",
            "project_languages": ["typescript", "vue"],
            "project_markers": ["package.json"],
        },
    )
    scope = QueryScope(project_names=("frontend",), kinds=("frontend",), languages=("typescript",), confidence=0.9)

    assert project_scope_score_parts(chunk, scope, project_unit_count=1) == {}


def test_project_scope_score_parts_boost_match_and_penalize_conflict() -> None:
    frontend_chunk = DocumentChunk(
        chunk_id="frontend-auth",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=10,
        content="useAuthStore login register",
        chunk_type="generic",
        metadata={
            "language": "typescript",
            "project_root": "frontend",
            "project_name": "frontend",
            "project_kind": "frontend",
            "project_languages": ["typescript", "vue"],
            "project_markers": ["package.json"],
        },
    )
    backend_chunk = DocumentChunk(
        chunk_id="backend-auth",
        file_path=Path("backend/src/main/java/com/example/UserAppService.java"),
        start_line=1,
        end_line=10,
        content="auth login register",
        chunk_type="generic",
        metadata={
            "language": "java",
            "project_root": "backend",
            "project_name": "backend",
            "project_kind": "java",
            "project_languages": ["java"],
            "project_markers": ["pom.xml"],
        },
    )
    scope = QueryScope(
        project_names=("frontend",),
        kinds=("frontend",),
        languages=("typescript", "vue"),
        path_prefixes=(Path("frontend/src"),),
        file_hints=("auth.store.ts",),
        confidence=0.9,
    )

    frontend_parts = project_scope_score_parts(frontend_chunk, scope, project_unit_count=3)
    backend_parts = project_scope_score_parts(backend_chunk, scope, project_unit_count=3)

    assert frontend_parts["project_scope_boost"] == 0.10
    assert frontend_parts["project_kind_boost"] == 0.06
    assert frontend_parts["project_language_boost"] == 0.04
    assert frontend_parts["project_path_hint_boost"] == 0.08
    assert backend_parts["project_scope_mismatch_penalty"] == -0.06
    assert project_scope_rerank_adjustment(frontend_parts) == 0.28
    assert project_scope_rerank_adjustment(backend_parts) == -0.06


def test_project_scope_mismatch_penalty_skips_evidence_anchor_files() -> None:
    pom_chunk = DocumentChunk(
        chunk_id="backend-pom",
        file_path=Path("backend/pom.xml"),
        start_line=1,
        end_line=10,
        content="<project />",
        chunk_type="generic",
        metadata={
            "language": "xml",
            "project_root": "backend",
            "project_name": "backend",
            "project_kind": "java",
            "project_languages": ["java"],
            "project_markers": ["pom.xml"],
        },
    )
    scope = QueryScope(project_names=("frontend",), kinds=("frontend",), languages=("typescript", "vue"), confidence=0.9)

    assert "project_scope_mismatch_penalty" not in project_scope_score_parts(pom_chunk, scope, project_unit_count=3)


def test_project_units_from_chunk_metadata_dedupes_units() -> None:
    chunks = [
        DocumentChunk(
            chunk_id="a",
            file_path=Path("frontend/src/main.ts"),
            start_line=1,
            end_line=1,
            content="",
            chunk_type="generic",
            metadata={
                "project_root": "frontend",
                "project_name": "frontend",
                "project_kind": "frontend",
                "project_languages": ["typescript", "vue"],
                "project_markers": ["package.json"],
            },
        ),
        DocumentChunk(
            chunk_id="b",
            file_path=Path("frontend/src/App.vue"),
            start_line=1,
            end_line=1,
            content="",
            chunk_type="generic",
            metadata={
                "project_root": "frontend",
                "project_name": "frontend",
                "project_kind": "frontend",
                "project_languages": ["typescript", "vue"],
                "project_markers": ["package.json"],
            },
        ),
    ]

    assert project_units_from_chunk_metadata(chunks) == (
        ProjectUnit(Path("frontend"), "frontend", "frontend", ("typescript", "vue"), ("package.json",), 1.0),
    )
```

- [ ] **Step 4: Run tests and confirm the module is missing**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'context_search_tool.project_scope'`.

- [ ] **Step 5: Implement `project_scope.py`**

Create `src/context_search_tool/project_scope.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context_search_tool.models import DocumentChunk


PROJECT_SCOPE_METADATA_VERSION = 1
PROJECT_SCOPE_METADATA_VERSION_KEY = "project_scope_metadata_version"

_ROOT = Path(".")
_BUSINESS_WORDS = {"auth", "portfolio", "fund", "position", "sse", "calendar"}
_ARCHITECTURE_WORDS = {"service", "controller", "handler", "repository"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst"}
_MARKER_NAMES = {
    "package.json",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "cargo.toml",
    "pyproject.toml",
}
_DISCOVERY_SKIPPED_DIRS = {
    ".git",
    ".context-search",
    "node_modules",
    "vendor",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
}


@dataclass(frozen=True)
class ProjectUnit:
    root: Path
    name: str
    kind: str
    languages: tuple[str, ...]
    markers: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class QueryScope:
    project_names: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    path_prefixes: tuple[Path, ...] = ()
    file_hints: tuple[str, ...] = ()
    confidence: float = 0.0


def detect_project_units(repo: Path, relative_paths: list[Path]) -> tuple[ProjectUnit, ...]:
    paths = sorted(
        {Path(path) for path in relative_paths} | set(_discover_marker_paths(repo)),
        key=lambda item: item.as_posix(),
    )
    path_set = {path.as_posix() for path in paths}
    units_by_root: dict[Path, ProjectUnit] = {}

    for path in paths:
        marker = path.name.lower()
        root = path.parent if path.parent.as_posix() != "" else _ROOT
        if marker == "package.json":
            kind, languages = _package_kind_and_languages(repo / path, root, path_set)
            units_by_root[root] = ProjectUnit(root, _unit_name(root), kind, languages, (path.name,), 0.95)
        elif marker == "go.mod":
            units_by_root[root] = ProjectUnit(root, _unit_name(root), "go", ("go",), (path.name,), 0.95)
        elif marker == "pom.xml":
            units_by_root[root] = ProjectUnit(root, _unit_name(root), "java", ("java",), (path.name,), 0.95)
        elif marker in {"build.gradle", "settings.gradle"}:
            units_by_root[root] = ProjectUnit(root, _unit_name(root), "java", ("java", "kotlin"), (path.name,), 0.90)
        elif marker == "cargo.toml":
            units_by_root[root] = ProjectUnit(root, _unit_name(root), "rust", ("rust",), (path.name,), 0.95)
        elif marker == "pyproject.toml":
            units_by_root[root] = ProjectUnit(root, _unit_name(root), "python", ("python",), (path.name,), 0.95)

    if not units_by_root:
        return (ProjectUnit(_ROOT, ".", "unknown", (), (), 0.0),)

    return tuple(sorted(units_by_root.values(), key=lambda unit: unit.root.as_posix()))


def unit_for_path(path: Path, units: tuple[ProjectUnit, ...]) -> ProjectUnit:
    normalized = Path(path)
    matches = [
        unit
        for unit in units
        if unit.root == _ROOT or normalized == unit.root or unit.root in normalized.parents
    ]
    if not matches:
        return ProjectUnit(_ROOT, ".", "unknown", (), (), 0.0)
    return max(matches, key=lambda unit: len(unit.root.parts) if unit.root != _ROOT else 0)


def project_metadata(unit: ProjectUnit) -> dict[str, object]:
    return {
        "project_root": "" if unit.root == _ROOT else unit.root.as_posix(),
        "project_name": unit.name,
        "project_kind": unit.kind,
        "project_languages": list(unit.languages),
        "project_markers": list(unit.markers),
    }


def project_units_from_chunk_metadata(chunks: list[DocumentChunk] | tuple[DocumentChunk, ...]) -> tuple[ProjectUnit, ...]:
    units: dict[str, ProjectUnit] = {}
    for chunk in chunks:
        root_value = str(chunk.metadata.get("project_root", ""))
        name = str(chunk.metadata.get("project_name", root_value or "."))
        kind = str(chunk.metadata.get("project_kind", "unknown"))
        languages = tuple(str(value) for value in chunk.metadata.get("project_languages", []) if value)
        markers = tuple(str(value) for value in chunk.metadata.get("project_markers", []) if value)
        if not root_value and kind == "unknown" and not languages and not markers:
            continue
        root = _ROOT if root_value in {"", "."} else Path(root_value)
        units[root.as_posix()] = ProjectUnit(root, name, kind, languages, markers, 1.0)
    return tuple(sorted(units.values(), key=lambda unit: unit.root.as_posix()))


def infer_query_scope(query: str, tokens: list[str], project_units: tuple[ProjectUnit, ...]) -> QueryScope:
    lowered_query = query.lower()
    lowered_tokens = {token.lower() for token in tokens}
    project_names: set[str] = set()
    kinds: set[str] = set()
    languages: set[str] = set()
    path_prefixes: set[Path] = set()
    file_hints: set[str] = set()
    confidence = 0.0

    useful_tokens = lowered_tokens - _BUSINESS_WORDS - _ARCHITECTURE_WORDS
    filename_hints = set(_filename_hints(lowered_query))
    file_hints.update(filename_hints)

    for unit in project_units:
        root = "" if unit.root == _ROOT else unit.root.as_posix().lower()
        name = unit.name.lower()
        if root and f"{root}/" in lowered_query:
            project_names.add(unit.name)
            path_prefixes.add(unit.root)
            confidence = max(confidence, 0.90)
        if root and root in useful_tokens:
            project_names.add(unit.name)
            confidence = max(confidence, 0.70)
        if name and name != "." and name in useful_tokens:
            project_names.add(unit.name)
            confidence = max(confidence, 0.70)
        if unit.kind in _kinds_for_tokens(useful_tokens):
            kinds.add(unit.kind)
            languages.update(unit.languages)
            confidence = max(confidence, 0.80)
        if set(unit.languages) & _languages_for_tokens(useful_tokens):
            languages.update(set(unit.languages) & _languages_for_tokens(useful_tokens))
            kinds.add(unit.kind)
            confidence = max(confidence, 0.75)
        if set(unit.languages) & _languages_for_filename_hints(filename_hints):
            languages.update(set(unit.languages) & _languages_for_filename_hints(filename_hints))
            kinds.add(unit.kind)
            confidence = max(confidence, 0.80)
        if set(unit.markers) & filename_hints:
            kinds.add(unit.kind)
            languages.update(unit.languages)
            confidence = max(confidence, 0.80)
        if _layout_hints_match(unit, useful_tokens):
            kinds.add(unit.kind)
            languages.update(unit.languages)
            confidence = max(confidence, 0.65)

    for prefix in _path_like_prefixes(lowered_query):
        path_prefixes.add(Path(prefix))
        first = prefix.split("/", 1)[0]
        for unit in project_units:
            if unit.root.as_posix().lower() == first or unit.name.lower() == first:
                project_names.add(unit.name)
                kinds.add(unit.kind)
                languages.update(unit.languages)
                confidence = max(confidence, 0.90)

    return QueryScope(
        project_names=tuple(sorted(project_names)),
        kinds=tuple(sorted(kind for kind in kinds if kind and kind != "unknown")),
        languages=tuple(sorted(language for language in languages if language)),
        path_prefixes=tuple(sorted(path_prefixes, key=lambda item: item.as_posix())),
        file_hints=tuple(sorted(file_hints)),
        confidence=confidence,
    )


def project_scope_score_parts(
    chunk: DocumentChunk,
    query_scope: QueryScope,
    *,
    project_unit_count: int,
) -> dict[str, float]:
    if project_unit_count <= 1 or query_scope.confidence <= 0:
        return {}

    metadata = chunk.metadata
    root = str(metadata.get("project_root", ""))
    name = str(metadata.get("project_name", root or "."))
    kind = str(metadata.get("project_kind", "unknown"))
    languages = {str(value) for value in metadata.get("project_languages", [])}
    path = chunk.file_path.as_posix()
    path_lower = path.lower()
    parts: dict[str, float] = {}

    if name in query_scope.project_names or (root and root in query_scope.project_names):
        parts["project_scope_boost"] = 0.10
    if kind in query_scope.kinds and kind != "unknown":
        parts["project_kind_boost"] = 0.06
    if languages & set(query_scope.languages):
        parts["project_language_boost"] = 0.04
    if any(path == prefix.as_posix() or path.startswith(f"{prefix.as_posix().rstrip('/')}/") for prefix in query_scope.path_prefixes) or any(
        path_lower.endswith(f"/{hint}") or chunk.file_path.name.lower() == hint
        for hint in query_scope.file_hints
    ):
        parts["project_path_hint_boost"] = 0.08

    mixed_scope = len(query_scope.project_names) > 1 or len(query_scope.kinds) > 1
    has_positive = any(value > 0 for value in parts.values())
    if (
        query_scope.confidence >= 0.60
        and not mixed_scope
        and not has_positive
        and not _is_evidence_anchor_path(chunk.file_path)
    ):
        parts["project_scope_mismatch_penalty"] = -0.06

    return parts


def project_scope_rerank_adjustment(score_parts: dict[str, float]) -> float:
    return (
        score_parts.get("project_scope_boost", 0.0)
        + score_parts.get("project_kind_boost", 0.0)
        + score_parts.get("project_language_boost", 0.0)
        + score_parts.get("project_path_hint_boost", 0.0)
        + score_parts.get("project_scope_mismatch_penalty", 0.0)
    )


def _package_kind_and_languages(package_path: Path, root: Path, path_set: set[str]) -> tuple[str, tuple[str, ...]]:
    content = _read_text(package_path).lower()
    root_prefix = "" if root == _ROOT else f"{root.as_posix()}/"
    has_vue_file = any(path.startswith(root_prefix) and path.endswith(".vue") for path in path_set)
    has_ts_file = any(path.startswith(root_prefix) and path.endswith((".ts", ".tsx")) for path in path_set)
    if has_vue_file or "vue" in content or "vite" in content or "@vitejs/plugin-vue" in content:
        languages = ("typescript", "vue") if has_ts_file else ("vue",)
        return "frontend", languages
    if has_ts_file:
        return "node", ("typescript",)
    return "node", ("javascript",)


def _unit_name(root: Path) -> str:
    return "." if root == _ROOT else root.name


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _discover_marker_paths(repo: Path) -> tuple[Path, ...]:
    markers: list[Path] = []
    for path in repo.rglob("*"):
        try:
            relative = path.relative_to(repo)
        except ValueError:
            continue
        if any(part in _DISCOVERY_SKIPPED_DIRS for part in relative.parts):
            continue
        if path.is_file() and path.name.lower() in _MARKER_NAMES:
            markers.append(relative)
    return tuple(sorted(markers, key=lambda item: item.as_posix()))


def _kinds_for_tokens(tokens: set[str]) -> set[str]:
    kinds: set[str] = set()
    if tokens & {"vue", "pinia", "vite", "eventsource"}:
        kinds.add("frontend")
    if tokens & {"go", "gin", "gomod"}:
        kinds.add("go")
    if tokens & {"java", "spring", "maven", "pom"}:
        kinds.add("java")
    return kinds


def _languages_for_tokens(tokens: set[str]) -> set[str]:
    languages: set[str] = set()
    if tokens & {"vue"}:
        languages.add("vue")
    if tokens & {"ts", "tsx", "typescript", "pinia", "vite"}:
        languages.add("typescript")
    if tokens & {"go", "gin"}:
        languages.add("go")
    if tokens & {"java", "spring", "maven", "pom"}:
        languages.add("java")
    return languages


def _languages_for_filename_hints(hints: set[str]) -> set[str]:
    languages: set[str] = set()
    for hint in hints:
        if hint.endswith((".ts", ".tsx")):
            languages.add("typescript")
        if hint.endswith(".vue") or hint == "package.json":
            languages.add("vue")
        if hint.endswith(".go") or hint == "go.mod":
            languages.add("go")
        if hint.endswith(".java") or hint == "pom.xml":
            languages.add("java")
    return languages


def _layout_hints_match(unit: ProjectUnit, tokens: set[str]) -> bool:
    if unit.kind == "frontend":
        return bool(tokens & {"views", "stores", "composables", "src"})
    if unit.kind == "go":
        return bool(tokens & {"internal", "cmd"})
    if unit.kind == "java":
        return bool(tokens & {"src", "main", "java"})
    return False


def _path_like_prefixes(query: str) -> tuple[str, ...]:
    prefixes: list[str] = []
    for part in query.replace("\\", "/").split():
        if "/" not in part:
            continue
        cleaned = part.strip(".,:;()[]{}'\"")
        if cleaned:
            prefixes.append(cleaned)
    return tuple(dict.fromkeys(prefixes))


def _filename_hints(query: str) -> tuple[str, ...]:
    hints: list[str] = []
    for part in query.replace("\\", "/").split():
        cleaned = part.strip(".,:;()[]{}'\"")
        name = cleaned.rsplit("/", 1)[-1]
        lowered = name.lower()
        if lowered in _MARKER_NAMES or any(
            lowered.endswith(suffix)
            for suffix in (".vue", ".ts", ".tsx", ".go", ".java")
        ):
            hints.append(lowered)
    return tuple(dict.fromkeys(hints))


def _is_evidence_anchor_path(path: Path) -> bool:
    name = path.name.lower()
    stem = path.stem.lower()
    return (
        path.suffix.lower() in _DOC_SUFFIXES
        or (path.suffix.lower() == ".md" and stem.startswith(("readme", "risks")))
        or name == "pom.xml"
    )
```

- [ ] **Step 6: Run project scope tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py -q
```

Expected: PASS for the project-scope module tests written in this task.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add src/context_search_tool/project_scope.py tests/test_project_scope.py
git commit -m "feat: add monorepo project scope helpers"
```

Expected: commit succeeds.

### Task 2: Annotate Indexed Chunks And Version Project Scope Metadata

**Files:**
- Modify: `src/context_search_tool/indexer.py`
- Modify: `tests/test_project_scope.py`

- [ ] **Step 1: Add failing tests for chunk metadata and stale metadata rewrite**

Append these tests to `tests/test_project_scope.py`:

```python
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.paths import index_dir_for
from context_search_tool.sqlite_store import SQLiteStore


def test_indexer_writes_project_metadata_to_chunks(tmp_path: Path) -> None:
    _touch(tmp_path, "frontend/package.json", '{"dependencies":{"vue":"latest","vite":"latest"}}')
    _touch(tmp_path, "frontend/src/main.ts", "createApp(App)")
    _touch(tmp_path, "frontend/src/App.vue", "<template>{{ auth }}</template>")

    summary = index_repository(tmp_path, DEFAULT_CONFIG)

    store = SQLiteStore(index_dir_for(tmp_path) / "index.sqlite")
    source_file = store.source_file_for_path(Path("frontend/src/App.vue"))
    chunks = store.chunks_for_file(Path("frontend/src/App.vue"), limit=10)
    assert summary.files_indexed == 3
    assert source_file is not None
    assert source_file.metadata["project_root"] == "frontend"
    assert source_file.metadata["project_kind"] == "frontend"
    assert chunks
    assert chunks[0].metadata["project_root"] == "frontend"
    assert chunks[0].metadata["project_kind"] == "frontend"
    assert chunks[0].metadata["project_languages"] == ["typescript", "vue"]


def test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_stale(tmp_path: Path) -> None:
    _touch(tmp_path, "collector/go.mod", "module collector")
    _touch(tmp_path, "collector/internal/scheduler/scheduler.go", "package scheduler")
    index_repository(tmp_path, DEFAULT_CONFIG)

    store = SQLiteStore(index_dir_for(tmp_path) / "index.sqlite")
    store.set_metadata("project_scope_metadata_version", "0")

    summary = index_repository(tmp_path, DEFAULT_CONFIG)
    chunks = store.chunks_for_file(Path("collector/internal/scheduler/scheduler.go"), limit=10)

    assert summary.files_skipped == 0
    assert summary.files_indexed == 2
    assert chunks[0].metadata["project_root"] == "collector"
    assert store.get_metadata("project_scope_metadata_version") == "1"


def test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_absent(tmp_path: Path) -> None:
    _touch(tmp_path, "backend/pom.xml", "<project />")
    _touch(tmp_path, "backend/src/main/java/com/example/AuthController.java", "class AuthController {}")
    index_repository(tmp_path, DEFAULT_CONFIG)

    db_path = index_dir_for(tmp_path) / "index.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM index_metadata WHERE key = ?",
            ("project_scope_metadata_version",),
        )

    summary = index_repository(tmp_path, DEFAULT_CONFIG)
    store = SQLiteStore(db_path)
    chunks = store.chunks_for_file(Path("backend/src/main/java/com/example/AuthController.java"), limit=10)

    assert summary.files_skipped == 0
    assert summary.files_indexed == 2
    assert chunks[0].metadata["project_root"] == "backend"
    assert store.get_metadata("project_scope_metadata_version") == "1"
```

- [ ] **Step 2: Run the new indexer tests and confirm they fail**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py::test_indexer_writes_project_metadata_to_chunks tests/test_project_scope.py::test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_stale tests/test_project_scope.py::test_indexer_rewrites_unchanged_chunks_when_project_scope_metadata_version_is_absent -q
```

Expected: FAIL because `indexer.py` has not written project metadata or project metadata version yet.

- [ ] **Step 3: Import project scope helpers in `indexer.py`**

Add these imports near the existing imports:

```python
from context_search_tool.project_scope import (
    PROJECT_SCOPE_METADATA_VERSION,
    PROJECT_SCOPE_METADATA_VERSION_KEY,
    ProjectUnit,
    detect_project_units,
    project_metadata,
    unit_for_path,
)
```

- [ ] **Step 4: Add project scope version helper**

Add this function after `signal_schema_is_current`:

```python
def project_scope_metadata_is_current(store: SQLiteStore) -> bool:
    version = store.get_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY)
    if version is None:
        return False
    try:
        return int(version) >= PROJECT_SCOPE_METADATA_VERSION
    except ValueError:
        return False
```

- [ ] **Step 5: Update `index_repository` to detect units and rewrite stale metadata**

Replace the section from `stale_signal_schema = ...` through the `for scanned_file in scanned_files:` loop with this code:

```python
    stale_signal_schema = not signal_schema_is_current(store)
    stale_project_scope_metadata = not project_scope_metadata_is_current(store)
    if stale_signal_schema:
        store.clear_signal_data()

    scanned_files = scan_workspace(repo, config)
    project_units = detect_project_units(repo, [scanned_file.path for scanned_file in scanned_files])
    scanned_paths = {scanned_file.path for scanned_file in scanned_files}
    indexed_paths = store.source_file_paths()
    deleted_paths = indexed_paths - scanned_paths

    plugins = default_plugins()
    prepared_files: list[_PreparedFile] = []
    changed_chunks: list[DocumentChunk] = []
    files_skipped = 0

    for scanned_file in scanned_files:
        existing = store.source_file_for_path(scanned_file.path)
        if (
            not stale_signal_schema
            and not stale_project_scope_metadata
            and existing is not None
            and existing.sha256 == scanned_file.sha256
        ):
            files_skipped += 1
            continue

        project_unit = unit_for_path(scanned_file.path, project_units)
        prepared_file = _prepare_file(scanned_file, plugins, project_unit)
        prepared_files.append(prepared_file)
        changed_chunks.extend(prepared_file.chunks)
```

Then add this metadata write next to the existing signal schema metadata write:

```python
    store.set_metadata(SIGNAL_SCHEMA_VERSION_KEY, str(CURRENT_SIGNAL_SCHEMA_VERSION))
    store.set_metadata(PROJECT_SCOPE_METADATA_VERSION_KEY, str(PROJECT_SCOPE_METADATA_VERSION))
    store.set_metadata("indexed_at", str(int(time.time())))
```

- [ ] **Step 6: Update `_prepare_file` to accept and write `ProjectUnit` metadata**

Change the function signature:

```python
def _prepare_file(
    scanned_file: ScannedFile,
    plugins: list[LanguagePlugin],
    project_unit: ProjectUnit,
) -> _PreparedFile:
```

After plugin metadata is merged, add shared project fields and write them to `SourceFile.metadata`:

```python
    project_fields = project_metadata(project_unit)

    source_file = SourceFile(
        path=scanned_file.path,
        language=scanned_file.language,
        sha256=scanned_file.sha256,
        size=scanned_file.size,
        mtime_ns=scanned_file.mtime_ns,
        is_generated=scanned_file.is_generated,
        is_test=scanned_file.is_test,
        metadata={**metadata, **project_fields},
    )
```

Then update the chunk `replace(...)` block to reuse the same fields:

```python
            metadata={
                **chunk.metadata,
                **project_fields,
            },
```

The complete `replace(...)` block should be:

```python
        replace(
            chunk,
            lexical_tokens=_dedupe_tokens(
                [*chunk.lexical_tokens, *_localized_plugin_tokens(chunk, extraction)]
            ),
            embedding_id=chunk.chunk_id,
            metadata={
                **chunk.metadata,
                **project_fields,
            },
        )
```

- [ ] **Step 7: Run focused project scope tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py -q
```

Expected: PASS.

- [ ] **Step 8: Run indexer manifest regression tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_indexer_manifest.py -q
```

Expected: PASS. If this fails because `files_skipped` expectations assume unchanged files always skip, update the test expectation only for the project-scope metadata version transition and keep normal unchanged-index behavior covered.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add src/context_search_tool/indexer.py tests/test_project_scope.py
git commit -m "feat: annotate chunks with project scope metadata"
```

Expected: commit succeeds.

### Task 3: Consume Project Scope In Retrieval Rerank

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add failing rerank-score unit test**

Append this test to `tests/test_retrieval_pipeline.py`:

```python
def test_project_scope_score_parts_affect_rerank_score() -> None:
    chunk = DocumentChunk(
        chunk_id="frontend-auth",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=12,
        content="useAuthStore login register fetchCurrentUser",
        chunk_type="generic",
        metadata={"language": "typescript"},
    )

    base_parts = {"lexical": 0.8}
    scoped_parts = {
        "lexical": 0.8,
        "project_scope_boost": 0.10,
        "project_kind_boost": 0.06,
        "project_language_boost": 0.04,
    }

    base_score = retrieval._rerank_score(
        0.5,
        base_parts,
        chunk,
        {"has_endpoint_signal": False, "is_controller": False, "has_relation_support": False},
        retrieval._ChunkRole("generic", 5, 0.0),
        planner_ceiling=None,
    )
    scoped_score = retrieval._rerank_score(
        0.5,
        scoped_parts,
        chunk,
        {"has_endpoint_signal": False, "is_controller": False, "has_relation_support": False},
        retrieval._ChunkRole("generic", 5, 0.0),
        planner_ceiling=None,
    )

    assert scoped_score == base_score + 0.20
```

- [ ] **Step 2: Add failing reason tests**

Append this test to `tests/test_retrieval_pipeline.py`:

```python
def test_reasons_include_project_scope_diagnostics() -> None:
    reasons = retrieval._reasons(
        {
            "project_scope_boost": 0.10,
            "project_kind_boost": 0.06,
            "project_language_boost": 0.04,
            "project_path_hint_boost": 0.08,
            "project_scope_mismatch_penalty": -0.06,
        },
        "frontend useAuthStore",
    )

    assert "project scope match" in reasons
    assert "project kind match" in reasons
    assert "project language match" in reasons
    assert "project path hint match" in reasons
    assert "project scope mismatch penalty" in reasons
```

- [ ] **Step 3: Run the new retrieval tests and confirm they fail**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_project_scope_score_parts_affect_rerank_score tests/test_retrieval_pipeline.py::test_reasons_include_project_scope_diagnostics -q
```

Expected: FAIL because `_rerank_score` and `_reasons` do not consume project scope score parts yet.

- [ ] **Step 4: Import project scope helpers in `retrieval.py`**

Add this import block after existing imports:

```python
from context_search_tool.project_scope import (
    infer_query_scope,
    project_scope_rerank_adjustment,
    project_scope_score_parts,
    project_units_from_chunk_metadata,
)
```

- [ ] **Step 5: Add project scope score parts inside `_rank_chunks`**

After `candidate_chunks = store.chunks_for_ids(list(candidates))`, add:

```python
    project_units = project_units_from_chunk_metadata(tuple(candidate_chunks.values()))
    query_scope = infer_query_scope(query, tokens, project_units)
```

After the Java context score block, add:

```python
        score_parts = _merge_score_parts(
            score_parts,
            project_scope_score_parts(
                chunk,
                query_scope,
                project_unit_count=len(project_units),
            ),
        )
```

The project scope block must run before `score = _combined_score(score_parts)` so diagnostics are included in final result payloads. `_combined_score` remains unchanged in this milestone.

- [ ] **Step 6: Add project scope adjustment to `_rerank_score`**

After the existing Spring path rerank adjustment:

```python
    rerank_score += _route_rerank_adjustment(score_parts)
    rerank_score += score_parts.get("route_tail_context_match", 0.0)
    rerank_score += _spring_path_rerank_adjustment(score_parts)
```

add:

```python
    rerank_score += project_scope_rerank_adjustment(score_parts)
```

- [ ] **Step 7: Add project scope reasons**

In `_reasons`, after the path/symbol or token coverage reasons and before Java/Spring reasons, add:

```python
    if score_parts.get("project_scope_boost", 0.0) > 0:
        reasons.append("project scope match")
    if score_parts.get("project_kind_boost", 0.0) > 0:
        reasons.append("project kind match")
    if score_parts.get("project_language_boost", 0.0) > 0:
        reasons.append("project language match")
    if score_parts.get("project_path_hint_boost", 0.0) > 0:
        reasons.append("project path hint match")
    if score_parts.get("project_scope_mismatch_penalty", 0.0) < 0:
        reasons.append("project scope mismatch penalty")
```

- [ ] **Step 8: Run focused retrieval tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_project_scope_score_parts_affect_rerank_score tests/test_retrieval_pipeline.py::test_reasons_include_project_scope_diagnostics -q
```

Expected: PASS.

- [ ] **Step 9: Run existing rerank regression tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_rerank_soft_sorting.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 3**

Run:

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: rerank by monorepo project scope"
```

Expected: commit succeeds.

### Task 4: Add Synthetic Monorepo Retrieval Tests And Candidate-Pool Diagnostics

**Files:**
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add a synthetic monorepo fixture helper**

Append this helper near other fixture helpers in `tests/test_retrieval_pipeline.py`:

```python
def _write_monorepo_scope_fixture(repo: Path) -> None:
    (repo / "frontend" / "src" / "stores" / "modules").mkdir(parents=True)
    (repo / "frontend" / "src" / "views" / "portfolio").mkdir(parents=True)
    (repo / "frontend" / "package.json").write_text(
        '{"dependencies":{"vue":"latest","pinia":"latest","vite":"latest"}}\n',
        encoding="utf-8",
    )
    (repo / "frontend" / "src" / "stores" / "modules" / "auth.store.ts").write_text(
        """
export const useAuthStore = defineStore('auth', {
  actions: {
    login() { return fetchCurrentUser() },
    register() { return fetchCurrentUser() },
    fetchCurrentUser() { return 'frontend auth portfolio fund position' }
  }
})
""".strip() + "\n",
        encoding="utf-8",
    )
    (repo / "frontend" / "src" / "views" / "portfolio" / "index.vue").write_text(
        """
<script setup lang="ts">
function fetchPortfolios() { return 'frontend portfolio fund position' }
function fetchPositions() { return fetchPortfolios() }
</script>
<template><section>portfolio position fund</section></template>
""".strip() + "\n",
        encoding="utf-8",
    )

    (repo / "collector" / "internal" / "api" / "handler").mkdir(parents=True)
    (repo / "collector" / "internal" / "scheduler").mkdir(parents=True)
    (repo / "collector" / "go.mod").write_text("module collector\n", encoding="utf-8")
    (repo / "collector" / "internal" / "api" / "handler" / "collect_handler.go").write_text(
        """
package handler

type CollectHandler struct {}

func (h *CollectHandler) CollectNav() string {
    return BatchCollectNav("fund portfolio nav")
}

func BatchCollectNav(topic string) string {
    return "collector gin fund portfolio " + topic
}
""".strip() + "\n",
        encoding="utf-8",
    )
    (repo / "collector" / "internal" / "scheduler" / "scheduler.go").write_text(
        """
package scheduler

type Scheduler struct {}

func (s *Scheduler) AddTask(name string) string {
    return "collector cron heartbeat fund portfolio " + name
}
""".strip() + "\n",
        encoding="utf-8",
    )

    (repo / "investment-assistant-backend" / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (repo / "investment-assistant-backend" / "pom.xml").write_text("<project />\n", encoding="utf-8")
    (repo / "investment-assistant-backend" / "src" / "main" / "java" / "com" / "example" / "AuthController.java").write_text(
        """
package com.example;

public class AuthController {
    public String login() {
        return new UserAppService().register();
    }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    (repo / "investment-assistant-backend" / "src" / "main" / "java" / "com" / "example" / "PortfolioAppService.java").write_text(
        """
package com.example;

public class PortfolioAppService {
    public String fetchPortfolios() {
        return "backend portfolio fund position auth";
    }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    (repo / "investment-assistant-backend" / "src" / "main" / "java" / "com" / "example" / "UserAppService.java").write_text(
        """
package com.example;

public class UserAppService {
    public String register() {
        return "backend auth login register fetchCurrentUser";
    }
}
""".strip() + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Add a candidate-pool diagnostic helper**

Append this helper in `tests/test_retrieval_pipeline.py`:

```python
def _candidate_pool_paths_before_rerank(repo: Path, query: str) -> set[str]:
    config = DEFAULT_CONFIG
    index_dir = index_dir_for(repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    original_tokens = retrieval._dedupe(retrieval.tokenize_query(query))
    deleted_ids = store.deleted_chunk_ids()
    initial_candidates = retrieval._initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        config,
        deleted_ids,
    )
    signal_candidates = retrieval._signal_candidates(store, original_tokens, config)
    direct_candidates = retrieval._merge_candidates([*initial_candidates, *signal_candidates])
    anchor_candidates = retrieval._anchor_expansion_candidates(
        store,
        list(direct_candidates.values()),
        config,
        query=query,
        tokens=original_tokens,
    )
    relation_seed_candidates = retrieval._merge_candidates(
        [*direct_candidates.values(), *anchor_candidates]
    )
    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    candidates = retrieval._merge_candidates(
        [*direct_candidates.values(), *anchor_candidates, *relation_candidates]
    )
    chunks = store.chunks_for_ids(list(candidates))
    return {chunk.file_path.as_posix() for chunk in chunks.values()}
```

- [ ] **Step 3: Add synthetic ranking tests**

Append this parametrized test to `tests/test_retrieval_pipeline.py`:

```python
@pytest.mark.parametrize(
    ("query", "expected_path"),
    [
        (
            "frontend useAuthStore login register fetchCurrentUser Pinia",
            "frontend/src/stores/modules/auth.store.ts",
        ),
        (
            "frontend portfolio index.vue fetchPortfolios fetchPositions",
            "frontend/src/views/portfolio/index.vue",
        ),
        (
            "collector CollectHandler CollectNav BatchCollectNav gin",
            "collector/internal/api/handler/collect_handler.go",
        ),
        (
            "collector scheduler.go type Scheduler AddTask heartbeat cron",
            "collector/internal/scheduler/scheduler.go",
        ),
        (
            "AuthController login register UserAppService",
            "investment-assistant-backend/src/main/java/com/example/AuthController.java",
        ),
    ],
)
def test_monorepo_scope_rerank_surfaces_scoped_subproject_files(
    tmp_path: Path,
    query: str,
    expected_path: str,
) -> None:
    _write_monorepo_scope_fixture(tmp_path)
    index_repository(tmp_path, DEFAULT_CONFIG)

    candidate_paths = _candidate_pool_paths_before_rerank(tmp_path, query)
    bundle = query_repository(tmp_path, query, DEFAULT_CONFIG)
    top_paths = [result.file_path.as_posix() for result in bundle.results[:5]]

    assert expected_path in candidate_paths
    assert expected_path in top_paths
    expected_result = next(result for result in bundle.results if result.file_path.as_posix() == expected_path)
    assert any(key.startswith("project_") for key in expected_result.score_parts)
```

- [ ] **Step 4: Add ambiguous query regression**

Append this test to `tests/test_retrieval_pipeline.py`:

```python
def test_monorepo_scope_does_not_overconstrain_unscoped_business_query(tmp_path: Path) -> None:
    _write_monorepo_scope_fixture(tmp_path)
    index_repository(tmp_path, DEFAULT_CONFIG)

    bundle = query_repository(tmp_path, "portfolio service", DEFAULT_CONFIG)
    top_paths = [result.file_path.as_posix() for result in bundle.results[:5]]

    assert any(path.endswith("PortfolioAppService.java") for path in top_paths) or any(
        path.endswith("frontend/src/views/portfolio/index.vue") for path in top_paths
    )
    assert all("project_scope_mismatch_penalty" not in result.score_parts for result in bundle.results[:5])
```

- [ ] **Step 5: Run synthetic monorepo tests and confirm current behavior**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -k "monorepo_scope" -q
```

Expected: PASS after Tasks 1-3. If the candidate-pool assertion fails for a target, stop and follow Step 6 instead of tuning project scope constants.

- [ ] **Step 6: Stop on candidate-pool misses**

If Step 5 fails with `expected_path not in candidate_paths`, stop this task and record the exact failing query, expected path, and candidate path set in the implementation notes. Do not increase project scope constants to hide a recall failure. The next change should be a separate recall-focused plan that adds generic scoped candidate seeding with its own tests and store access strategy.

- [ ] **Step 7: Run broader retrieval pipeline tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Run:

```bash
git add tests/test_retrieval_pipeline.py src/context_search_tool/retrieval.py
git commit -m "test: cover monorepo subproject retrieval"
```

Expected: commit succeeds. If Step 6 was not needed, `src/context_search_tool/retrieval.py` should already be clean from Task 3 and `git add` will stage only tests.

### Task 5: Add Real Monorepo Smoke Fixture And README Note

**Files:**
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
- Modify: `tests/test_generic_baseline_quality.py`
- Modify: `README.md`

- [ ] **Step 1: Update fixture-key validation**

In `tests/test_generic_baseline_quality.py`, update:

```python
assert {spec["repo_key"] for spec in repo_specs} == {"imagebed", "env_change"}
```

to:

```python
assert {spec["repo_key"] for spec in repo_specs} == {
    "imagebed",
    "env_change",
    "investment_assistant",
}
```

- [ ] **Step 2: Add `Investment-Assistant` real smoke fixture**

Append this object to `tests/fixtures/generic_baseline_quality/queries.json` after the `env_change` object:

```json
{
  "repo_key": "investment_assistant",
  "path_env": "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
  "repo_dir_name": "Investment-Assistant",
  "queries": [
    {
      "id": "frontend-auth-store",
      "query": "frontend useAuthStore login register fetchCurrentUser Pinia",
      "expected_top_k": [
        {"path": "frontend/src/stores/modules/auth.store.ts", "top_k": 5}
      ],
      "absent_top_k": [
        {"glob": "investment-assistant-backend/src/main/java/com/investment/application/auth/*.java", "top_k": 3}
      ]
    },
    {
      "id": "collector-handler",
      "query": "collector CollectHandler collect_handler.go CollectNav BatchCollectNav gin",
      "expected_top_k": [
        {"path": "collector/internal/api/handler/collect_handler.go", "top_k": 5}
      ]
    },
    {
      "id": "frontend-sse-composable",
      "query": "frontend useSseConnection EventSource chat composable",
      "expected_top_k": [
        {"path": "frontend/src/views/chat/composables/useSseConnection.ts", "top_k": 5}
      ]
    },
    {
      "id": "collector-fund-service",
      "query": "collector FundService CollectNav BatchCollectNav fund service",
      "expected_top_k": [
        {"path": "collector/internal/service/fund_service.go", "top_k": 5}
      ]
    },
    {
      "id": "collector-nav-fetcher",
      "query": "collector eastmoney nav.go fetch fund nav",
      "expected_top_k": [
        {"path": "collector/internal/source/eastmoney/nav.go", "top_k": 5}
      ]
    },
    {
      "id": "collector-scheduler",
      "query": "collector scheduler.go Scheduler AddTask cron heartbeat",
      "expected_top_k": [
        {"path": "collector/internal/scheduler/scheduler.go", "top_k": 5}
      ]
    },
    {
      "id": "java-ai-sse-controller",
      "query": "java AIController chatWithSse SseServer SseChatRequest userId message",
      "expected_top_k": [
        {"path": "investment-assistant-backend/src/main/java/com/investment/interfaces/rest/AIController.java", "top_k": 5}
      ]
    }
  ]
}
```

Keep the outer JSON as a valid array with commas between objects.

- [ ] **Step 3: Add real smoke candidate-pool diagnostics and run fixture shape tests**

Before running the shape tests, add candidate-pool diagnostics to `tests/test_generic_baseline_quality.py`.

Extend the imports:

```python
from context_search_tool import retrieval
from context_search_tool.paths import index_dir_for
from context_search_tool.sqlite_store import SQLiteStore
```

Add these helpers near the existing assertion helpers:

```python
def _candidate_pool_paths_before_rerank(repo: Path, query: str) -> set[str]:
    index_dir = index_dir_for(repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    original_tokens = retrieval._dedupe(retrieval.tokenize_query(query))
    deleted_ids = store.deleted_chunk_ids()
    initial_candidates = retrieval._initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        DEFAULT_CONFIG,
        deleted_ids,
    )
    signal_candidates = retrieval._signal_candidates(store, original_tokens, DEFAULT_CONFIG)
    direct_candidates = retrieval._merge_candidates([*initial_candidates, *signal_candidates])
    anchor_candidates = retrieval._anchor_expansion_candidates(
        store,
        list(direct_candidates.values()),
        DEFAULT_CONFIG,
        query=query,
        tokens=original_tokens,
    )
    relation_seed_candidates = retrieval._merge_candidates(
        [*direct_candidates.values(), *anchor_candidates]
    )
    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        list(relation_seed_candidates.values()),
        DEFAULT_CONFIG,
    )
    candidates = retrieval._merge_candidates(
        [*direct_candidates.values(), *anchor_candidates, *relation_candidates]
    )
    chunks = store.chunks_for_ids(list(candidates))
    return {chunk.file_path.as_posix() for chunk in chunks.values()}


def _assert_expected_candidates(query_spec: dict, candidate_paths: set[str]) -> None:
    for expected in query_spec.get("expected_top_k", []):
        assert any(_matches(expected, path) for path in candidate_paths), {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "candidate_paths": sorted(candidate_paths),
            "expected": expected,
        }
```

Update the real-project loop so the `investment_assistant` smoke distinguishes candidate-pool misses from rerank misses:

```python
    for query_spec in repo_spec["queries"]:
        if repo_spec["repo_key"] == "investment_assistant":
            candidate_paths = _candidate_pool_paths_before_rerank(repo, query_spec["query"])
            _assert_expected_candidates(query_spec, candidate_paths)

        bundle = query_repository(repo, query_spec["query"], DEFAULT_CONFIG)
        top_paths = [result.file_path.as_posix() for result in bundle.results]
        _assert_expected_top_k(query_spec, top_paths)
        _assert_expected_any_top_k(query_spec, top_paths)
        _assert_absent_top_k(query_spec, top_paths)
        _assert_outranks(query_spec, top_paths)
        _assert_anchor_expected(query_spec, bundle)
```

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 4: Add README note**

Add this short section near existing usage or retrieval-quality documentation in `README.md`:

````markdown
### Monorepo Root Indexing

CST can index a monorepo root and uses generic project markers such as `package.json`, `go.mod`, and `pom.xml` to detect subproject boundaries. Query-time ranking treats matching project scope as a soft rerank signal, so frontend or collector queries can surface their own files even when backend code shares the same business vocabulary.

Indexing a subproject directly is still a valid workaround when you already know the target area:

```bash
cst index /path/to/repo/frontend
cst query /path/to/repo/frontend "useAuthStore login register fetchCurrentUser"
```
````

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add tests/fixtures/generic_baseline_quality/queries.json tests/test_generic_baseline_quality.py README.md
git commit -m "test: add monorepo retrieval smoke fixture"
```

Expected: commit succeeds.

### Task 6: Run Acceptance And Regression Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run project scope and synthetic retrieval tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py tests/test_retrieval_pipeline.py -q
```

Expected: PASS. The result output should report all selected tests passing with no new failures.

- [ ] **Step 2: Run focused existing regressions**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py tests/test_tokenizer_scanner.py tests/test_rerank_soft_sorting.py -q
```

Expected: PASS for non-slow fixture validation, scanner coverage, and rerank sorting.

- [ ] **Step 3: Run Java/Spring acceptance regressions**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_acceptance_java_fixture.py -q
```

Expected: PASS. Java/Spring route and path graph results should not regress.

- [ ] **Step 4: Run full suite**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest -q
```

Expected: PASS with the same skipped-test profile as the current branch.

- [ ] **Step 5: Run optional real monorepo smoke when the repo is available**

Run:

```bash
CST_SMOKE_INVESTMENT_ASSISTANT_REPO=/Users/flobby/vibe_coding/Investment-Assistant /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

Expected: PASS for `Investment-Assistant`, `imagebed`, and `env-change` smoke cases. If the repo is unavailable, record that this check was skipped because `/Users/flobby/vibe_coding/Investment-Assistant` was not present.

- [ ] **Step 6: Inspect result diagnostics manually on the real repo when available**

Run:

```bash
cst index /Users/flobby/vibe_coding/Investment-Assistant
cst query /Users/flobby/vibe_coding/Investment-Assistant "frontend useAuthStore login register fetchCurrentUser Pinia" --format json
```

Expected: the top result window includes `frontend/src/stores/modules/auth.store.ts`, and that result's `score_parts` include at least one of `project_scope_boost`, `project_kind_boost`, `project_language_boost`, or `project_path_hint_boost`.

- [ ] **Step 7: Final whitespace and status checks**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` prints no errors. `git status --short` shows only intentional files if changes remain uncommitted.

## 5. Self-Review Checklist

- [ ] Every design requirement maps to a task:
  - Project detection and marker discovery outside scanner output: Task 1.
  - Chunk metadata and stale index rewrite: Task 2.
  - Rerank consumption and reasons: Task 3.
  - Synthetic ranking and candidate-pool diagnostics: Task 4.
  - Real smoke, real candidate-pool diagnostics, and docs: Task 5.
  - Regression verification: Task 6.
- [ ] The plan does not add framework plugins, hard filters, per-subproject indexes, schema-breaking payload changes, or user-facing config flags.
- [ ] Project scope score parts are not added to `_combined_score`; they affect `rerank_score` through `project_scope_rerank_adjustment`.
- [ ] Candidate-pool failures are treated as recall failures, not score-tuning failures.
- [ ] Existing Java/Spring and generic baseline tests remain in the verification surface.
