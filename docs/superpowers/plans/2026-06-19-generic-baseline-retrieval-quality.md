# Generic Baseline Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-round generic baseline retrieval quality gate and conservative noise/rerank cleanup, without adding Go, Rust/Tauri, or other framework plugins and without implementing two-pass retrieval.

**Architecture:** Keep retrieval local and deterministic. Add a reusable real-project smoke suite for generic baseline regressions, add scanner-level default skips for dependency/build directories, and consolidate generic file-role/noise demotion into the existing retrieval ranking path that already owns `_generated_or_test_penalty(chunk)`. Existing plugin signals and Java path reranking stay as higher-value signals and must keep passing.

**Tech Stack:** Python 3.11+, pytest, SQLite FTS, existing scanner/indexer/retrieval pipeline, existing `DEFAULT_CONFIG` hash embedding for deterministic tests, optional explicit real-repo smoke paths via environment variables.

---

## 1. Problem Statement

The generic language baseline can now index common source suffixes, so projects such as `imagebed` and `env-change` are no longer blocked at scan time. The next failure mode is ranking cleanliness:

- Source files are present, but templates, generated schemas, broad config files, and indexed lockfiles can compete with implementation files.
- The scanner still relies on `.gitignore` or configured excludes for dependency/build directories such as `node_modules/`, `vendor/`, `.venv/`, `dist/`, `build/`, and `target/`.
- `retrieval.py` already has `_generated_or_test_penalty(chunk)`, so new generated/test/file-noise behavior must extend that path instead of creating a second unrelated penalty system.
- Existing README/RISKS/pom evidence anchor behavior is already implemented and should be treated as regression protection, not as a new deliverable.
- Java/Spring plugin ranking is an important regression gate; generic demotion must not flatten Java service/executor/endpoint boosts.

This plan implements the first round only: quality suite, scanner default skips, and conservative retrieval-time demotion. Two-pass retrieval remains future work.

## 2. Scope

### In Scope

- Add a fixture-driven generic baseline quality suite for `imagebed` and `env-change`.
- Resolve real smoke repo paths through environment variables or `CST_SMOKE_REPOS_DIR`, never hard-coded absolute paths.
- Copy real repos to a pytest temp workspace before indexing so `.context-search/` and `.gitignore` side effects do not touch the source repo.
- Add scanner-level default skips for dependency/build output directories.
- Add a generic file role/noise classifier that uses path, suffix, metadata, and existing chunk fields only.
- Extend/consolidate `_generated_or_test_penalty(chunk)` into the new generic noise penalty path.
- Expose numeric `score_parts` for noise/file-role decisions.
- Preserve existing evidence anchor behavior for README/RISKS/pom.
- Preserve existing Java regression gates.

### Out Of Scope

- No Go/Gin plugin.
- No Rust/Tauri plugin.
- No framework-specific route or command graph extraction.
- No two-pass retrieval.
- No LLM reranker.
- No embedding default change.
- No schema-breaking change to `RetrievalResult`, MCP payloads, formatter payloads, or index storage.
- No scanner support for `.lock` files in this first round. `Cargo.lock` and `yarn.lock` remain unindexed unless a later scanner change adds `.lock`.
- No repo-specific alias maps or hard-coded query shortcuts.

## 3. Target Semantics

After implementation:

- `node_modules/`, `vendor/`, `.venv/`, `dist/`, `build/`, `target/`, and similar dependency/build directories are skipped even when a repo forgot to ignore them.
- Include patterns do not override hidden/internal paths, `.gitignore`, configured excludes, default dependency/build skips, binary checks, or oversized-file checks.
- Indexed JSON/YAML lockfiles such as `package-lock.json` and `pnpm-lock.yaml` receive a high retrieval-time penalty unless directly requested with unusually strong evidence.
- Generated schemas such as `src-tauri/gen/schemas/*.json` receive a high retrieval-time penalty.
- Templates such as `templates/index.html` receive a medium penalty for implementation-oriented queries.
- Broad config files receive a small-to-medium penalty for implementation-oriented queries, but remain retrievable for config-specific queries.
- Source files can receive a very small generic source boost, but this boost must be lower than established Java route/service/executor signals.
- README/RISKS/pom continue to appear as `evidence_anchors` when applicable and should not consume primary code result slots when code results exist.

Initial penalty ladder:

| Kind | Score part | Initial value | Notes |
| --- | --- | ---: | --- |
| generated/test aggregate | `penalty` | negative aggregate | Existing combined score already adds this field. |
| generated schema | `generated_schema_penalty` | `-0.20` | Same scale as current generated penalty. |
| indexed lockfile | `lockfile_penalty` | `-0.20` | Only for indexed JSON/YAML lockfiles in this round. |
| test | `test_penalty` | `-0.10` | Preserve existing test penalty scale unless regression tests show it is too strong. |
| template | `template_penalty` | `-0.08` | Apply mainly to implementation-oriented queries. |
| broad config/doc | `config_penalty` / `doc_penalty` | `-0.03` to `-0.08` | Keep conservative; README anchor behavior is separate. |
| source | `file_role_source_boost` | `+0.03` | Optional small nudge, lower than Java role boosts. |

## 4. Files And Responsibilities

- Create: `tests/fixtures/generic_baseline_quality/queries.json`
  - Fixture contract and initial real-project query expectations.
- Create: `tests/test_generic_baseline_quality.py`
  - Fixture validation, repo path resolution, safe temp copy, assertion helpers, and explicit real-project smoke tests.
- Modify: `src/context_search_tool/scanner.py`
  - Default dependency/build directory skip list.
- Modify: `tests/test_tokenizer_scanner.py`
  - Scanner default skip tests and include-precedence regression tests.
- Modify: `src/context_search_tool/retrieval.py`
  - Generic file-role/noise classification, `_generated_or_test_penalty` consolidation, score parts, reasons, and rank integration.
- Modify: `tests/test_retrieval_pipeline.py`
  - Focused synthetic tests for generated schema, indexed lockfile, template/config demotion, source preference, and README/RISKS/pom anchor regression if needed.
- Modify: `README.md`
  - Short documentation for generic baseline behavior and explicit real-project smoke command.
- Keep: `tests/test_acceptance_java_fixture.py`
  - Existing Java gates run unchanged.
- Keep: `tests/test_rerank_soft_sorting.py`
  - Existing rerank tests run unchanged.

## 5. Fixture Contract

Create `tests/fixtures/generic_baseline_quality/queries.json`:

```json
[
  {
    "repo_key": "imagebed",
    "path_env": "CST_SMOKE_IMAGEBED_REPO",
    "repo_dir_name": "imagebed",
    "queries": [
      {
        "id": "go-upload-handler",
        "query": "UploadHandler MultiUpload multipart file storage Save",
        "expected_top_k": [
          {"path": "handler/upload.go", "top_k": 5}
        ],
        "absent_top_k": [
          {"glob": "templates/*", "top_k": 5}
        ]
      },
      {
        "id": "go-auth-middleware",
        "query": "AuthMiddleware Authorization Bearer token AdminMiddleware",
        "expected_top_k": [
          {"path": "middleware/auth.go", "top_k": 5}
        ]
      },
      {
        "id": "go-storage-implementations",
        "query": "NewS3Storage NewOSSStorage NewLocalStorage initStorage",
        "expected_top_k": [
          {"glob": "storage/*.go", "top_k": 8}
        ],
        "expected_any_top_k": [
          {"path": "main.go", "top_k": 8},
          {"glob": "storage/*.go", "top_k": 8}
        ],
        "absent_top_k": [
          {"path": "templates/index.html", "top_k": 5}
        ],
        "outranks": [
          {
            "source": "storage/*.go",
            "noise": "templates/index.html",
            "top_k": 8
          }
        ]
      },
      {
        "id": "go-delete-handler",
        "query": "DeleteHandler delete object storage remove image",
        "expected_top_k": [
          {"path": "handler/delete.go", "top_k": 5}
        ]
      },
      {
        "id": "go-route-registration",
        "query": "router upload delete middleware route group main",
        "expected_top_k": [
          {"path": "main.go", "top_k": 5}
        ],
        "absent_top_k": [
          {"glob": "*.md", "top_k": 5}
        ]
      }
    ]
  },
  {
    "repo_key": "env_change",
    "path_env": "CST_SMOKE_ENV_CHANGE_REPO",
    "repo_dir_name": "env-change",
    "queries": [
      {
        "id": "tauri-commands",
        "query": "tauri command apply_dev restore_clean command handler",
        "expected_top_k": [
          {"path": "src-tauri/src/commands.rs", "top_k": 5}
        ],
        "absent_top_k": [
          {"glob": "src-tauri/gen/schemas/*.json", "top_k": 8}
        ]
      },
      {
        "id": "engine-apply-restore",
        "query": "apply_dev restore_clean file_swap session conflict engine",
        "expected_top_k": [
          {"path": "src-tauri/src/engine.rs", "top_k": 5}
        ],
        "absent_top_k": [
          {"glob": "src-tauri/gen/schemas/*.json", "top_k": 8}
        ]
      },
      {
        "id": "frontend-invoke",
        "query": "invoke apply_dev restore_clean frontend ProjectSwitcher",
        "expected_top_k": [
          {"path": "src/main.ts", "top_k": 5}
        ],
        "absent_top_k": [
          {"path": "vite.config.ts", "top_k": 3}
        ]
      },
      {
        "id": "settings-persistence",
        "query": "settings persistence save load project config app settings",
        "expected_top_k": [
          {"path": "src-tauri/src/settings.rs", "top_k": 5}
        ],
        "outranks": [
          {
            "source": "src-tauri/src/settings.rs",
            "noise": "vite.config.ts",
            "top_k": 8
          }
        ]
      }
    ]
  }
]
```

Rules:

- `repo_key`, `path_env`, and `repo_dir_name` are required for each repo spec.
- `queries[].id` and `queries[].query` are required.
- `expected_top_k`: every listed path/glob must appear within its own `top_k`.
- `expected_any_top_k`: at least one listed path/glob must appear within its own `top_k`.
- `absent_top_k`: listed path/glob must not appear within its own `top_k`.
- `outranks`: within the declared top-K window, `source` must rank ahead of `noise` if `noise` appears. If `noise` is absent from that top-K window, the assertion passes. Source presence must be covered by `expected_top_k` or `expected_any_top_k`.
- `anchor_expected`: optional list of README/RISKS/pom paths that should appear in `bundle.evidence_anchors` and not in `bundle.results` when code results exist.
- `known_gap`: optional string explaining a non-failing gap; the test runner validates shape but does not assert it.

## 6. Implementation Tasks

### Task 1: Add The Generic Quality Fixture And Test Harness

**Files:**

- Create: `tests/fixtures/generic_baseline_quality/queries.json`
- Create: `tests/test_generic_baseline_quality.py`

- [ ] **Step 1: Add the fixture JSON**

Create the fixture exactly from section 5.

- [ ] **Step 2: Add fixture validation helpers**

Create `tests/test_generic_baseline_quality.py` with helpers shaped like:

```python
import fnmatch
import json
import os
import shutil
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "generic_baseline_quality"
    / "queries.json"
)


def _load_repo_specs() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
```

Validation should assert:

- repo spec keys are present and non-empty strings.
- every query has `id` and `query`.
- every matcher item has exactly one of `path` or `glob`.
- every matcher item has a positive integer `top_k`.
- `outranks` entries have `source`, `noise`, and positive integer `top_k`.
- `anchor_expected`, when present, is a list of non-empty strings.

- [ ] **Step 3: Add path resolution without absolute fixture paths**

Implement:

```python
def _repo_for_spec(repo_spec: dict) -> Path | None:
    direct = os.environ.get(repo_spec["path_env"])
    if direct:
        return Path(direct)

    base = os.environ.get("CST_SMOKE_REPOS_DIR")
    if base:
        return Path(base) / repo_spec["repo_dir_name"]

    return None
```

- [ ] **Step 4: Add safe temp repo copy**

Reuse the existing calibration approach:

```python
def _copy_repo_for_smoke(source_repo: Path, workspace: Path) -> Path:
    target = workspace / source_repo.name
    if target.exists():
        return target
    return Path(
        shutil.copytree(
            source_repo,
            target,
            ignore=shutil.ignore_patterns(".git", ".context-search"),
        )
    )
```

Add a unit test proving `.git` and `.context-search` are not copied and the source repo is not mutated.

- [ ] **Step 5: Add result assertion helpers**

Implement path/glob matching against `result.file_path.as_posix()`:

```python
def _matches(pattern: dict, path: str) -> bool:
    if "path" in pattern:
        return path == pattern["path"]
    return fnmatch.fnmatch(path, pattern["glob"])
```

Helpers:

- `_assert_expected_top_k(query_spec, top_paths)`
- `_assert_expected_any_top_k(query_spec, top_paths)`
- `_assert_absent_top_k(query_spec, top_paths)`
- `_assert_outranks(query_spec, top_paths)`
- `_assert_anchor_expected(query_spec, bundle)`

Keep assertion failure payloads verbose: include query id, query text, top paths, and expected/noise pattern.

- [ ] **Step 6: Add load and shape tests**

Add:

```python
def test_generic_baseline_quality_queries_load() -> None:
    repo_specs = _load_repo_specs()
    assert {spec["repo_key"] for spec in repo_specs} == {"imagebed", "env_change"}
    for repo_spec in repo_specs:
        _assert_repo_spec(repo_spec)
```

Also add invalid shape tests for:

- missing `repo_key`
- matcher containing both `path` and `glob`
- zero `top_k`
- invalid `expected_any_top_k`
- invalid `outranks`

- [ ] **Step 7: Add explicit real-project smoke test**

Add:

```python
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("repo_spec", _load_repo_specs(), ids=lambda item: item["repo_key"])
def test_generic_baseline_real_project_quality(
    repo_spec: dict,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    source_repo = _repo_for_spec(repo_spec)
    if source_repo is None:
        pytest.skip(f"{repo_spec['repo_key']} repo path not configured")
    if not source_repo.exists():
        pytest.skip(f"repo not found: {source_repo}")

    workspace = tmp_path_factory.mktemp(f"generic-baseline-{repo_spec['repo_key']}")
    repo = _copy_repo_for_smoke(source_repo, workspace)
    index_repository(repo, DEFAULT_CONFIG)

    for query_spec in repo_spec["queries"]:
        bundle = query_repository(repo, query_spec["query"], DEFAULT_CONFIG)
        top_paths = [result.file_path.as_posix() for result in bundle.results]
        _assert_expected_top_k(query_spec, top_paths)
        _assert_expected_any_top_k(query_spec, top_paths)
        _assert_absent_top_k(query_spec, top_paths)
        _assert_outranks(query_spec, top_paths)
        _assert_anchor_expected(query_spec, bundle)
```

- [ ] **Step 8: Verify the harness before ranking changes**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py::test_generic_baseline_quality_queries_load -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Then run the explicit real-project smoke to record baseline failures:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

Expected before implementation: the harness loads, but some real-project smoke assertions may fail due to template/config/generated noise.

### Task 2: Add Scanner Default Dependency/Build Skips

**Files:**

- Modify: `src/context_search_tool/scanner.py`
- Modify: `tests/test_tokenizer_scanner.py`

- [ ] **Step 1: Write failing scanner tests**

Add tests near the existing scanner skip tests:

```python
def test_scanner_skips_default_dependency_and_build_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "App.ts").write_text("export const app = true\n", encoding="utf-8")

    for dirname in ("node_modules", "vendor", ".venv", "dist", "build", "target"):
        directory = repo / dirname
        directory.mkdir()
        (directory / "Noise.ts").write_text("export const noise = true\n", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("src/App.ts")]
```

Add a second test proving include patterns do not override default skips:

```python
def test_scanner_include_patterns_do_not_override_default_skips(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "App.ts").write_text("export const app = true\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "Noise.ts").write_text(
        "export const noise = true\n",
        encoding="utf-8",
    )
    config = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, include=["src/**/*.ts", "node_modules/**/*.ts"]),
    )

    files = scan_workspace(repo, config)

    assert [item.path for item in files] == [Path("src/App.ts")]
```

- [ ] **Step 2: Implement the default skip list**

Add near `_LANGUAGES_BY_SUFFIX`:

```python
_DEFAULT_SKIPPED_DIRS = {
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    "target",
    "out",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
}
```

Add:

```python
def _is_default_skipped_path(relative_path: Path) -> bool:
    return any(part in _DEFAULT_SKIPPED_DIRS for part in relative_path.parts)
```

Update `_is_skipped_path(...)` so the returned expression includes `_is_default_skipped_path(relative_path)`.

- [ ] **Step 3: Verify scanner behavior**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
```

### Task 3: Add Generic File Role And Unified Noise Penalties

**Files:**

- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add focused failing tests**

Add synthetic tests in `tests/test_retrieval_pipeline.py` near other `_rank_chunks` and evidence-anchor tests.

Test generated schema demotion:

- Create a `SQLiteStore`.
- Add `src-tauri/src/engine.rs` and `src-tauri/gen/schemas/apply_dev.json` chunks.
- Give both candidates comparable `direct_text`/`lexical` score parts.
- Call `retrieval._rank_chunks(...)`.
- Assert `engine.rs` ranks ahead.
- Assert schema result has `generated_schema_penalty < 0` and `penalty < 0`.

Test indexed lockfile demotion:

- Compare `src/main.ts` with `package-lock.json` or `pnpm-lock.yaml`.
- Assert source ranks ahead for implementation-oriented query.
- Assert `lockfile_penalty < 0`.
- Do not add `.lock` files to this test; `.lock` is not indexed in this milestone.

Test template demotion:

- Compare `storage/local.go` or `main.go` with `templates/index.html`.
- Assert source ranks ahead for storage implementation query.
- Assert `template_penalty < 0`.

Test README/RISKS/pom regression:

- Keep the existing anchor tests passing.
- Add only a small fixture-shape assertion if `anchor_expected` support is added to the new real-project harness.

- [ ] **Step 2: Add generic file role metadata**

Near `_ChunkRole`, add:

```python
@dataclass(frozen=True)
class _GenericFileRole:
    name: str
    noise_level: str
    source_boost: float = 0.0
    penalty: float = 0.0
    penalty_key: str = ""
```

Use this independently from `_ChunkRole`. `_ChunkRole` keeps business/code role behavior for Java and similar code-role ranking.

- [ ] **Step 3: Add classifier helpers**

Add helpers in `retrieval.py`:

```python
_SOURCE_SUFFIXES = {
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".py", ".pyw",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".c", ".h",
    ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".cs", ".swift",
    ".php", ".rb", ".lua", ".dart", ".sh", ".bash", ".zsh", ".fish",
}

_TEMPLATE_SUFFIXES = {".html", ".vue", ".svelte"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst"}
_CONFIG_SUFFIXES = {".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env", ".xml"}
_INDEXED_LOCKFILE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "pnpm-lock.yml"}
```

Classifier rules:

- if `_is_test_path(path)` or `chunk.metadata.get("is_test")`: test role, `test_penalty = -0.10`.
- if `chunk.metadata.get("is_generated")`, `"/generated/" in path`, or `"/gen/" in path` plus JSON/schema-like suffix/name: generated schema role, `generated_schema_penalty = -0.20`.
- if `path.name.lower()` is in `_INDEXED_LOCKFILE_NAMES`: lockfile role, `lockfile_penalty = -0.20`.
- if suffix in `_TEMPLATE_SUFFIXES`: template role, `template_penalty = -0.08` for implementation-oriented queries.
- if suffix in `_DOC_SUFFIXES`: doc role, `doc_penalty = -0.03` to `-0.08` only when it is not handled as README/RISKS anchor.
- if suffix in `_CONFIG_SUFFIXES`: config role, `config_penalty = -0.03` to `-0.08` for implementation-oriented queries.
- if suffix in `_SOURCE_SUFFIXES`: source role, `file_role_source_boost = 0.03`.
- otherwise unknown role with no boost.

Add a small helper such as:

```python
def _looks_implementation_query(query: str, tokens: list[str]) -> bool:
    if "/" in query:
        return True
    implementation_terms = {
        "handler", "middleware", "command", "engine", "service", "controller",
        "storage", "upload", "delete", "apply", "restore", "invoke", "route",
        "function", "class", "method",
    }
    return bool(set(tokens).intersection(implementation_terms))
```

Keep this helper conservative. Do not add business alias dictionaries.

- [ ] **Step 4: Consolidate `_generated_or_test_penalty(chunk)`**

Keep the public helper name in place, but make new generic penalty code build on it rather than bypass it.

One acceptable shape:

```python
def _generated_or_test_penalty(chunk: DocumentChunk) -> float:
    path = chunk.file_path.as_posix().lower()
    penalty = 0.0
    if chunk.metadata.get("is_generated") or "generated" in path:
        penalty += 0.20
    if chunk.metadata.get("is_test") or _is_test_path(path):
        penalty += 0.10
    return penalty


def _generic_noise_score_parts(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> dict[str, float]:
    parts: dict[str, float] = {}
    legacy_penalty = _generated_or_test_penalty(chunk)
    if legacy_penalty:
        parts["penalty"] = -legacy_penalty
        if chunk.metadata.get("is_generated") or "generated" in chunk.file_path.as_posix().lower():
            parts["generated_schema_penalty"] = -0.20
        if chunk.metadata.get("is_test") or _is_test_path(chunk.file_path.as_posix().lower()):
            parts["test_penalty"] = -0.10

    role = _generic_file_role(chunk, query, tokens)
    if role.source_boost:
        parts["file_role_source_boost"] = role.source_boost
    if role.penalty:
        parts[role.penalty_key] = -role.penalty
        parts["penalty"] = min(parts.get("penalty", 0.0), -role.penalty)
    return parts
```

The exact implementation can differ, but it must satisfy:

- one aggregate `penalty` remains negative.
- detailed penalty parts remain numeric and negative.
- generated/test metadata feeds the same path as generated schema and lockfile penalties.
- no index schema migration is required.

- [ ] **Step 5: Integrate score parts in `_rank_chunks`**

Replace the direct penalty block:

```python
penalty = _generated_or_test_penalty(chunk)
if penalty:
    score_parts["penalty"] = -penalty
```

with:

```python
score_parts = _merge_score_parts(
    score_parts,
    _generic_noise_score_parts(chunk, query, tokens),
)
penalty = abs(min(score_parts.get("penalty", 0.0), 0.0))
```

Keep the `penalty` variable as a positive magnitude because `_should_apply_java_context_score(...)` currently receives it that way.

- [ ] **Step 6: Include new numeric parts in scoring and reasons**

Update `_combined_score(score_parts)` to include:

```python
+ score_parts.get("file_role_source_boost", 0.0)
```

Do not add detailed negative parts directly if they are already folded into aggregate `penalty`; otherwise penalties will double-apply.

Update `_reasons(...)`:

```python
if score_parts.get("file_role_source_boost", 0.0) > 0:
    reasons.append("source file role boost")
if score_parts.get("generated_schema_penalty", 0.0) < 0:
    reasons.append("generated schema penalty")
if score_parts.get("lockfile_penalty", 0.0) < 0:
    reasons.append("lockfile penalty")
if score_parts.get("template_penalty", 0.0) < 0:
    reasons.append("template penalty")
if score_parts.get("config_penalty", 0.0) < 0:
    reasons.append("config penalty")
if score_parts.get("doc_penalty", 0.0) < 0:
    reasons.append("doc penalty")
if score_parts.get("test_penalty", 0.0) < 0:
    reasons.append("test penalty")
```

Keep the existing `"generated/test penalty"` reason or replace it with more specific reasons after tests are updated. Do not remove existing reason coverage without a test.

- [ ] **Step 7: Verify focused retrieval tests**

Run the specific new tests first, then the broader retrieval file:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -k "generic_noise or evidence_anchor" -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

### Task 4: Run Real-Project Smoke And Tune Conservatively

**Files:**

- Modify only `src/context_search_tool/retrieval.py` and tests if assertions reveal a precise issue.

- [ ] **Step 1: Run generic smoke**

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

If a query fails:

- inspect the failing top paths and score parts.
- prefer adjusting fixture top-K only when the result is genuinely acceptable.
- prefer reducing penalties if strong direct evidence is being suppressed.
- prefer increasing only the specific noise penalty if a known noise class still crowds out source.
- do not add repo-specific aliases or path shortcuts.

- [ ] **Step 2: Run Java regression gates**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_es_audit_business_chain -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_rerank_soft_sorting.py -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -k "java_context or spring_path or evidence_anchor" -q
```

If a Java gate fails:

- first inspect whether `file_role_source_boost` or aggregate `penalty` changed ordering.
- keep Java route/service/executor boosts stronger than generic source/template/config adjustments.
- do not tune Java tests around a generic demotion regression.

- [ ] **Step 3: Run scanner and generic baseline tests**

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_indexer_manifest.py tests/test_retrieval_pipeline.py -q
```

### Task 5: Document The User-Facing Behavior

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Add a concise generic baseline note**

Document:

- common source suffixes are indexed generically even without framework plugins.
- default scanner skips dependency/build directories.
- generated schemas, indexed lockfiles, templates, docs, and config may be demoted in code-oriented queries.
- README/RISKS/pom can appear as evidence anchors rather than primary results.
- framework plugins remain optional enhancement layers.

- [ ] **Step 2: Add explicit real smoke command**

Add:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

Avoid claiming fast-context parity.

## 7. Full Verification

Run this focused suite before considering the task complete:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_tokenizer_scanner.py -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -k "generic_noise or evidence_anchor or java_context or spring_path" -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_acceptance_java_fixture.py::test_java_spring_path_rerank_prefers_es_audit_business_chain -q
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_rerank_soft_sorting.py -q
```

Run this explicit real-project smoke when the local repos are available:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

Run diff hygiene:

```bash
git diff --check
git status --short --branch --untracked-files=normal
```

Optional broader pass if time allows:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest -q
```

## 8. Acceptance Criteria

- Generic quality fixture contains no absolute repo paths.
- Generic real-project smoke skips cleanly when repos are not configured.
- Generic real-project smoke copies repos without `.git` or `.context-search`.
- `imagebed` upload/auth/delete/route/storage cases meet their top-K expectations.
- `imagebed` template noise does not appear in the declared top-K windows.
- `env-change` command/engine/frontend/settings cases meet their top-K expectations.
- `env-change` generated schema files do not appear in the declared top-K windows.
- Indexed JSON/YAML lockfiles receive lockfile penalties; `.lock` files are not treated as covered by this milestone.
- Scanner skips default dependency/build directories even when `.gitignore` is missing.
- Include patterns do not override default dependency/build skips.
- New retrieval score parts are numeric and explainable.
- `_generated_or_test_penalty(chunk)` remains the generated/test compatibility path and feeds the unified noise behavior.
- README/RISKS/pom evidence anchor tests keep passing.
- Java path rerank acceptance tests keep passing.

## 9. Risk Controls

- Keep all generic boosts smaller than Java route/service/executor boosts.
- Apply high penalties only to clearly noisy classes: generated schemas and indexed lockfiles.
- Apply template/config/doc penalties mainly for implementation-oriented queries.
- Do not double-apply detailed penalties and aggregate `penalty`.
- Do not use real-project smoke in default CI unless explicitly requested; missing repos should skip.
- Do not let `known_gap` hide a failing assertion. It is documentation only.
- Do not add `.lock` suffix scanning in this plan; that would change index coverage and needs a separate decision.

## 10. Self-Review Checklist

- [ ] The plan acknowledges existing `_generated_or_test_penalty(chunk)`.
- [ ] The plan does not describe hard skips as existing scanner behavior.
- [ ] The plan handles the `.lock` split explicitly.
- [ ] README/RISKS/pom anchors are treated as regression protection.
- [ ] Fixtures are portable through env vars and `CST_SMOKE_REPOS_DIR`.
- [ ] `outranks` semantics are non-vacuous for source presence because source presence is asserted separately.
- [ ] Java regression gates are named explicitly.
- [ ] Penalty magnitudes are lower than or comparable to existing boosts and are documented.
- [ ] No two-pass retrieval task is included in the implementation steps.
