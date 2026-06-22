# Explicit Identifier And Path Role Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve CST's language-neutral Top1/Top3 ranking quality when queries explicitly name symbols, filenames, or common code roles, without adding framework-specific plugins or repo-specific aliases.

**Architecture:** Add small generic query-intent and path-role helpers that feed conservative score parts into the existing retrieval rerank path. Keep scanner coverage, project scope, Java/Spring relation scoring, planner behavior, and combined-score calculation stable; use the new signals only as explainable rerank adjustments for high-confidence explicit code intent.

**Tech Stack:** Python 3.11+, pytest, existing scanner/indexer/retrieval pipeline, SQLite-backed chunks/signals/relations, existing real-project generic baseline fixture suite, optional `fast_context_search` comparison as a qualitative check.

---

## 1. Problem Statement

The current baseline has crossed the "usable" line:

- Common source files are indexed across Go, Rust, TypeScript, Java, and related ecosystems.
- Generated schemas, lockfiles, templates, docs, config, and test noise are demoted.
- Root-indexed monorepos use generic subproject metadata and soft project-scope reranking.
- Current real smoke checks place all known targets in Top5 across `imagebed`, `env-change`, and `Investment-Assistant`.

The remaining generic gap is Top1/Top3 precision. Cross-project diagnostics show the pattern is not specific to one repository:

- Explicit identifiers such as `useAuthStore`, `useSseConnection`, `FundService`, `UploadHandler`, `apply_dev`, and `NewS3Storage` should dominate broad business-term matches.
- Common path roles such as `stores/`, `composables/`, `handler/`, `service/`, `repository/`, `source/`, `views/`, `types/`, `commands`, and `engine` should help break ties when the query names the same role.
- Top5-only assertions now hide useful ranking-quality regressions.

This plan focuses on generic code intent and path-role ranking. It must not optimize for `Investment-Assistant` alone.

## 2. Scope

### In Scope

- Add a reusable quality-target assertion for real smoke fixtures, separate from the existing hard Top5 target.
- Extract explicit identifier intent from query text and tokenized query terms.
- Classify generic path roles across languages without depending on Vue, Go/Gin, Rust/Tauri, Java/Spring, or repo-specific plugins.
- Add conservative rerank score parts for:
  - exact identifier hits,
  - explicit filename hints,
  - query role hints matching file path role,
  - weak role mismatch only when the query contains a strong explicit role hint.
- Add synthetic cross-language tests for TypeScript, Go, Rust/Tauri-style, and Java-safe regressions.
- Upgrade real-project smoke expectations across `imagebed`, `env-change`, and `Investment-Assistant` using Top1/Top3 quality targets where the target is unambiguous.
- Preserve existing project-scope behavior, Java/Spring path graph behavior, planner fallback behavior, JSON/MCP payload shape, and CLI arguments.

### Out Of Scope

- No Vue plugin.
- No Go or Gin plugin.
- No Rust or Tauri plugin.
- No repo-specific aliases.
- No Chinese business alias map.
- No LLM planner changes.
- No embedding model changes.
- No hard filtering by role or project.
- No physical sub-indexes.
- No SQLite schema migration.

## 3. Files And Responsibilities

- Create: `src/context_search_tool/identifier_intent.py`
  - Extract query identifiers, filenames, suffix hints, and role hints from raw query text and existing tokenized terms.
- Create: `src/context_search_tool/path_roles.py`
  - Classify language-neutral query-intent path roles from relative path, suffix, and chunk content.
  - This must not become a second business-role ontology competing with `retrieval._chunk_role`; Task 3 documents the boundary and Task 5 adds overlap regressions.
- Modify: `src/context_search_tool/retrieval.py`
  - Compute query intent once per ranked candidate set.
  - Merge identifier and path-role score parts before `_rerank_score`.
  - Use one shared role-compatibility helper for path-role boosts and mismatch penalties.
  - Add explainable reasons for the new score parts.
  - Keep `_combined_score` unchanged.
- Modify: `tests/test_generic_baseline_quality.py`
  - Add strict fixture-shape validation for `preferred_rank` assertions.
  - Add assertion helper for Top1/Top3 quality targets.
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
  - Add cross-project `preferred_rank` targets to selected unambiguous queries.
- Create: `tests/test_identifier_intent.py`
  - Unit tests for query intent extraction.
- Create: `tests/test_path_roles.py`
  - Unit tests for generic path-role classification.
- Modify: `tests/test_retrieval_pipeline.py`
  - Add synthetic ranking tests that prove generic identifier and role signals work before real smoke runs.
- Modify: `README.md`
  - Add a short note that generic baseline quality now includes explicit code-intent and path-role reranking.

## 4. Success Criteria

- Existing unit, retrieval, and generic smoke tests pass.
- New synthetic tests pass for TypeScript store/composable, Go handler/service/source, Rust/Tauri command/engine, and Java executor/service regression shapes.
- Real smoke keeps every existing `expected_top_k` passing.
- New `preferred_rank` targets pass across all three current real fixture repos:
  - `imagebed`
  - `env-change`
  - `Investment-Assistant`
- A reproducible rank-distribution diagnostic shows current real-smoke Top1 count improves from the observed `11/16` without weakening any existing absent/noise assertions.
- `fast_context_search` remains a qualitative comparator only; CST tests do not depend on fast-context output.

## 5. Implementation Tasks

### Task 1: Add Preferred-Rank Fixture Assertions

**Files:**
- Modify: `tests/test_generic_baseline_quality.py`
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`

- [ ] **Step 1: Add fixture-shape tests for `preferred_rank`**

In `tests/test_generic_baseline_quality.py`, extend `_assert_query_spec` with this validation:

```python
def _assert_preferred_rank_item(item: object) -> None:
    assert isinstance(item, dict)
    _assert_matcher_item(item)
    _assert_positive_integer(item.get("max_rank"))
    assert item["max_rank"] <= item["top_k"]


def _assert_query_spec(query_spec: object) -> None:
    assert isinstance(query_spec, dict)
    for key in ("id", "query"):
        assert key in query_spec
        _assert_non_empty_string(query_spec[key])

    for key in ("expected_top_k", "absent_top_k", "expected_any_top_k"):
        if key in query_spec:
            _assert_matcher_list(query_spec[key])

    if "preferred_rank" in query_spec:
        assert isinstance(query_spec["preferred_rank"], list)
        assert query_spec["preferred_rank"]
        for item in query_spec["preferred_rank"]:
            _assert_preferred_rank_item(item)

    if "outranks" in query_spec:
        assert isinstance(query_spec["outranks"], list)
        assert query_spec["outranks"]
        for item in query_spec["outranks"]:
            _assert_outrank_item(item)

    if "anchor_expected" in query_spec:
        _assert_string_list(query_spec["anchor_expected"])
        for expected_anchor in query_spec["anchor_expected"]:
            _assert_relative_string(expected_anchor)

    if "known_gap" in query_spec:
        _assert_non_empty_string(query_spec["known_gap"])
```

- [ ] **Step 2: Add negative fixture-shape coverage**

Add these invalid specs inside `test_generic_baseline_quality_rejects_invalid_fixture_shapes`:

```python
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "preferred_rank": [
                        {"path": "handler/upload.go", "top_k": 5, "max_rank": 0}
                    ],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "preferred_rank": [
                        {"path": "handler/upload.go", "top_k": 3, "max_rank": 4}
                    ],
                }
            ],
        },
```

- [ ] **Step 3: Add preferred-rank assertion helper**

Add this helper near `_assert_expected_top_k`:

```python
def _preferred_rank_position(preferred: dict, top_paths: list[str]) -> int | None:
    scoped_paths = top_paths[: preferred["top_k"]]
    for index, path in enumerate(scoped_paths, start=1):
        if _matches(preferred, path):
            return index
    return None


def _assert_preferred_rank(query_spec: dict, top_paths: list[str]) -> None:
    for preferred in query_spec.get("preferred_rank", []):
        rank = _preferred_rank_position(preferred, top_paths)
        if rank is None:
            assert False, {
                "query_id": query_spec["id"],
                "query": query_spec["query"],
                "top_paths": top_paths,
                "preferred": preferred,
            }
        assert rank <= preferred["max_rank"], {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "top_paths": top_paths,
            "preferred": preferred,
            "actual_rank": rank,
        }
```

Call it in `test_generic_baseline_real_project_quality` immediately after `_assert_expected_top_k(query_spec, top_paths)`:

```python
        _assert_expected_top_k(query_spec, top_paths)
        _assert_preferred_rank(query_spec, top_paths)
```

- [ ] **Step 4: Run shape tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS before fixture rank targets are added.

- [ ] **Step 5: Add cross-project preferred ranks to fixture**

Update `tests/fixtures/generic_baseline_quality/queries.json` with these initial quality targets:

```json
"preferred_rank": [
  {"path": "handler/upload.go", "top_k": 5, "max_rank": 1}
]
```

Apply that pattern to unambiguous already-Top1 targets:

- `imagebed/go-upload-handler`: `handler/upload.go`, `max_rank: 1`
- `imagebed/go-auth-middleware`: `middleware/auth.go`, `max_rank: 1`
- `imagebed/go-delete-handler`: `handler/delete.go`, `max_rank: 1`
- `imagebed/go-route-registration`: `main.go`, `max_rank: 1`
- `env_change/tauri-commands`: `src-tauri/src/commands.rs`, `max_rank: 1`
- `env_change/engine-apply-restore`: `src-tauri/src/engine.rs`, `max_rank: 1`
- `env_change/settings-persistence`: `src-tauri/src/settings.rs`, `max_rank: 1`
- `investment_assistant/collector-handler`: `collector/internal/api/handler/collect_handler.go`, `max_rank: 1`
- `investment_assistant/collector-nav-fetcher`: `collector/internal/source/eastmoney/nav.go`, `max_rank: 1`
- `investment_assistant/collector-scheduler`: `collector/internal/scheduler/scheduler.go`, `max_rank: 1`
- `investment_assistant/java-ai-sse-controller`: `investment-assistant-backend/src/main/java/com/investment/interfaces/rest/AIController.java`, `max_rank: 1`

Add failing or near-failing quality targets that this milestone should improve:

- `env_change/frontend-invoke`: `src/main.ts`, `top_k: 5`, `max_rank: 1`
- `investment_assistant/frontend-auth-store`: `frontend/src/stores/modules/auth.store.ts`, `top_k: 5`, `max_rank: 3`
- `investment_assistant/frontend-sse-composable`: `frontend/src/views/chat/composables/useSseConnection.ts`, `top_k: 5`, `max_rank: 3`
- `investment_assistant/collector-fund-service`: `collector/internal/service/fund_service.go`, `top_k: 5`, `max_rank: 2`

Keep `go-storage-implementations` as Top5 plus `outranks`; `main.go` is a useful initialization result and should not be forced below all storage implementations in this milestone.

- [ ] **Step 6: Run real smoke and capture expected failures**

Run all available real fixture repos:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected before implementation: failures only from the new `preferred_rank` assertions listed as milestone targets. Existing `expected_top_k`, `absent_top_k`, and `outranks` assertions must remain passing.

- [ ] **Step 7: Commit Task 1 as a local red-phase checkpoint**

This commit is expected to contain failing slow/integration `preferred_rank` assertions until the rerank implementation lands. Do not push it alone or declare CI green from this checkpoint.

```bash
git add tests/test_generic_baseline_quality.py tests/fixtures/generic_baseline_quality/queries.json
git commit -m "test: add generic baseline preferred-rank gates"
```

### Task 2: Add Query Identifier Intent Extraction

**Files:**
- Create: `src/context_search_tool/identifier_intent.py`
- Create: `tests/test_identifier_intent.py`

- [ ] **Step 1: Write unit tests for identifier extraction**

Create `tests/test_identifier_intent.py`:

```python
from context_search_tool.identifier_intent import infer_identifier_intent


def test_identifier_intent_extracts_symbols_and_filenames() -> None:
    intent = infer_identifier_intent(
        "frontend useAuthStore auth.store.ts fetchCurrentUser Pinia",
        ["frontend", "use", "auth", "store", "auth", "store", "ts", "fetch", "current", "user", "pinia"],
    )

    assert intent.identifiers == ("fetchCurrentUser", "useAuthStore")
    assert intent.file_hints == ("auth.store.ts",)
    assert intent.role_hints == ("state_store",)


def test_identifier_intent_extracts_snake_case_and_rust_commands() -> None:
    intent = infer_identifier_intent(
        "tauri command apply_dev restore_clean command handler",
        ["tauri", "command", "apply", "dev", "restore", "clean", "command", "handler"],
    )

    assert intent.identifiers == ("apply_dev", "restore_clean")
    assert intent.file_hints == ()
    assert intent.role_hints == ("command", "handler")


def test_identifier_intent_extracts_go_service_and_handler_roles() -> None:
    intent = infer_identifier_intent(
        "collector FundService CollectNav BatchCollectNav fund service",
        ["collector", "fund", "service", "collect", "nav", "batch", "collect", "nav", "fund", "service"],
    )

    assert intent.identifiers == ("BatchCollectNav", "CollectNav", "FundService")
    assert intent.role_hints == ("service",)


def test_identifier_intent_ignores_plain_business_words() -> None:
    intent = infer_identifier_intent(
        "auth portfolio fund service",
        ["auth", "portfolio", "fund", "service"],
    )

    assert intent.identifiers == ()
    assert intent.file_hints == ()
    assert intent.role_hints == ("service",)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_identifier_intent.py -q
```

Expected: FAIL because `context_search_tool.identifier_intent` does not exist.

- [ ] **Step 3: Create identifier intent module**

Create `src/context_search_tool/identifier_intent.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


_CAMEL_OR_PASCAL_RE = re.compile(r"\b[A-Z]?[a-z]+(?:[A-Z][A-Za-z0-9]*)+\b")
_SNAKE_IDENTIFIER_RE = re.compile(r"\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b")
_FILE_HINT_RE = re.compile(r"(?i)(?<![\w.-])[\w-]+(?:\.[\w-]+)+(?![\w.-])")

_ROLE_HINTS = {
    "store": "state_store",
    "stores": "state_store",
    "pinia": "state_store",
    "redux": "state_store",
    "zustand": "state_store",
    "composable": "composable",
    "composables": "composable",
    "hook": "composable",
    "hooks": "composable",
    "service": "service",
    "services": "service",
    "handler": "handler",
    "handlers": "handler",
    "middleware": "middleware",
    "middlewares": "middleware",
    "router": "router",
    "route": "router",
    "routes": "router",
    "controller": "entrypoint",
    "controllers": "entrypoint",
    "repository": "repository",
    "repositories": "repository",
    "repo": "repository",
    "source": "source_adapter",
    "adapter": "source_adapter",
    "client": "source_adapter",
    "view": "view",
    "views": "view",
    "page": "view",
    "pages": "view",
    "component": "component",
    "components": "component",
    "type": "data_type",
    "types": "data_type",
    "dto": "data_type",
    "entity": "data_type",
    "model": "data_type",
    "command": "command",
    "commands": "command",
    "engine": "engine",
}


@dataclass(frozen=True)
class IdentifierIntent:
    identifiers: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    suffix_hints: tuple[str, ...] = ()
    role_hints: tuple[str, ...] = ()


def infer_identifier_intent(query: str, tokens: list[str]) -> IdentifierIntent:
    identifiers: list[str] = []
    file_hints: list[str] = []
    suffix_hints: list[str] = []
    role_hints: list[str] = []

    for match in _CAMEL_OR_PASCAL_RE.findall(query):
        _append_unique(identifiers, match)
    for match in _SNAKE_IDENTIFIER_RE.findall(query):
        _append_unique(identifiers, match)
    for match in _FILE_HINT_RE.findall(query):
        normalized = match.lower()
        _append_unique(file_hints, normalized)
        suffix = "." + normalized.rsplit(".", 1)[-1]
        _append_unique(suffix_hints, suffix)

    for token in [*tokens, *re.findall(r"[A-Za-z0-9_+-]+", query)]:
        role = _ROLE_HINTS.get(token.lower())
        if role:
            _append_unique(role_hints, role)

    return IdentifierIntent(
        identifiers=tuple(sorted(identifiers)),
        file_hints=tuple(file_hints),
        suffix_hints=tuple(suffix_hints),
        role_hints=tuple(role_hints),
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
```

- [ ] **Step 4: Run identifier intent tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_identifier_intent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/context_search_tool/identifier_intent.py tests/test_identifier_intent.py
git commit -m "feat: infer explicit query identifier intent"
```

### Task 3: Add Generic Path Role Classification

**Files:**
- Create: `src/context_search_tool/path_roles.py`
- Create: `tests/test_path_roles.py`

- [ ] **Step 1: Write path-role tests**

Create `tests/test_path_roles.py`:

```python
from pathlib import Path

from context_search_tool.path_roles import classify_path_role


def test_path_roles_classify_frontend_state_and_composable_files() -> None:
    assert classify_path_role(Path("src/stores/modules/auth.store.ts")).name == "state_store"
    assert classify_path_role(Path("src/views/chat/composables/useSseConnection.ts")).name == "composable"
    assert classify_path_role(Path("src/views/chat/types.ts")).name == "data_type"
    assert classify_path_role(Path("src/views/auth/register.vue")).name == "view"


def test_path_roles_classify_backend_and_collector_files() -> None:
    assert classify_path_role(Path("handler/upload.go")).name == "handler"
    assert classify_path_role(Path("middleware/auth.go")).name == "middleware"
    assert classify_path_role(Path("collector/internal/service/fund_service.go")).name == "service"
    assert classify_path_role(Path("collector/internal/repository/nav_repo.go")).name == "repository"
    assert classify_path_role(Path("collector/internal/source/eastmoney/nav.go")).name == "source_adapter"
    assert classify_path_role(Path("collector/internal/scheduler/scheduler.go")).name == "scheduler"


def test_path_roles_preserve_java_specific_semantics() -> None:
    assert classify_path_role(Path("src/main/java/com/example/service/impl/AuthServiceImpl.java")).name == "service_impl"
    assert classify_path_role(Path("src/main/java/com/example/service/AuthService.java"), "interface AuthService {}").name == "service_interface"
    assert classify_path_role(Path("src/main/java/com/example/service/PageAppCatalogQueryExe.java")).name == "executor"
    assert classify_path_role(Path("src/main/java/com/example/dto/AuthDto.java")).name == "data_type"


def test_path_roles_classify_rust_tauri_files() -> None:
    assert classify_path_role(Path("src-tauri/src/commands.rs")).name == "command"
    assert classify_path_role(Path("src-tauri/src/engine.rs")).name == "engine"
    assert classify_path_role(Path("src-tauri/src/settings.rs")).name == "config"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_path_roles.py -q
```

Expected: FAIL because `context_search_tool.path_roles` does not exist.

- [ ] **Step 3: Create path role module**

Create `src/context_search_tool/path_roles.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRole:
    name: str
    priority: int


def classify_path_role(path: Path, content: str = "") -> PathRole:
    normalized = path.as_posix().lower()
    parts = tuple(part for part in normalized.split("/") if part)
    name = path.name.lower()
    stem = path.stem.lower()
    content_lower = content.lower()

    if _is_test_path(normalized, name, parts):
        return PathRole("test", 90)
    if name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "cargo.lock", "go.sum"}:
        return PathRole("lockfile", 90)
    if name in {"vite.config.ts", "vite.config.js", "webpack.config.js", "tsconfig.json"}:
        return PathRole("config", 70)
    if path.suffix.lower() in {".md", ".mdx", ".rst"}:
        return PathRole("doc", 80)

    if "/service/impl/" in normalized or "serviceimpl" in stem:
        return PathRole("service_impl", 10)
    if "/service/" in normalized and "interface " in content_lower:
        return PathRole("service_interface", 35)
    if stem.endswith(("queryexe", "qryexe", "executor", "queryexecutor", "exe")):
        return PathRole("executor", 20)
    if (
        any(part in {"dto", "vo", "entity", "model", "models", "types", "type"} for part in parts)
        or stem in {"type", "types"}
        or name.endswith((".types.ts", ".types.tsx"))
    ):
        return PathRole("data_type", 45)
    if any(part in {"store", "stores", "state"} for part in parts) or name.endswith(".store.ts"):
        return PathRole("state_store", 20)
    if any(part in {"composable", "composables", "hook", "hooks"} for part in parts) or stem.startswith("use"):
        return PathRole("composable", 20)
    if any(part in {"controller", "controllers"} for part in parts) or "controller" in stem:
        return PathRole("entrypoint", 10)
    if any(part in {"router", "routers", "routes"} for part in parts) or name == "router.go":
        return PathRole("router", 15)
    if any(part in {"command", "commands"} for part in parts) or stem == "commands":
        return PathRole("command", 15)
    if stem == "engine":
        return PathRole("engine", 20)
    if any(part in {"handler", "handlers"} for part in parts) or "handler" in stem:
        return PathRole("handler", 25)
    if any(part in {"middleware", "middlewares"} for part in parts) or "middleware" in stem:
        return PathRole("middleware", 25)
    if any(part in {"service", "services"} for part in parts):
        return PathRole("service", 30)
    if any(part in {"repository", "repositories", "repo", "repos"} for part in parts) or stem.endswith("_repo"):
        return PathRole("repository", 40)
    if any(part in {"source", "sources", "adapter", "adapters", "client", "clients"} for part in parts):
        return PathRole("source_adapter", 40)
    if any(part in {"view", "views", "page", "pages"} for part in parts) or path.suffix.lower() in {".vue", ".svelte"}:
        return PathRole("view", 50)
    if any(part in {"component", "components"} for part in parts):
        return PathRole("component", 50)
    if "scheduler" in parts or "scheduler" in stem:
        return PathRole("scheduler", 25)
    if stem in {"settings", "config"}:
        return PathRole("config", 70)

    return PathRole("source", 60)


def _is_test_path(path: str, name: str, parts: tuple[str, ...]) -> bool:
    return (
        "test" in parts
        or "tests" in parts
        or name.endswith(("_test.go", ".test.ts", ".spec.ts", "test.java"))
        or "/src/test/" in path
    )
```

`path_roles.py` is only for query-intent path-role hints. It does not replace the existing `_chunk_role()` business-role classifier in `retrieval.py`; any overlapping role semantics must be covered by Task 5 regressions before tuning scores.

- [ ] **Step 4: Run path-role tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_path_roles.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/context_search_tool/path_roles.py tests/test_path_roles.py
git commit -m "feat: classify generic path roles"
```

### Task 4: Add Identifier And Role Score Parts

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add synthetic ranking tests**

Add these tests near the existing role-rerank tests in `tests/test_retrieval_pipeline.py`:

```python
def test_identifier_intent_ranks_state_store_above_related_frontend_files(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    auth_store = DocumentChunk(
        chunk_id="auth-store",
        file_path=Path("frontend/src/stores/modules/auth.store.ts"),
        start_line=1,
        end_line=80,
        content="export const useAuthStore = defineStore('auth', { actions: { login() {}, register() {}, fetchCurrentUser() {} } })",
        chunk_type="symbol",
        lexical_tokens=["use", "auth", "store", "login", "register", "fetch", "current", "user"],
        metadata={"language": "typescript"},
    )
    auth_service = DocumentChunk(
        chunk_id="auth-service",
        file_path=Path("frontend/src/api/services/auth.service.ts"),
        start_line=1,
        end_line=60,
        content="export function login() {} export function register() {} export function fetchCurrentUser() {}",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "login", "register", "fetch", "current", "user"],
        metadata={"language": "typescript"},
    )
    register_view = DocumentChunk(
        chunk_id="register-view",
        file_path=Path("frontend/src/views/auth/register.vue"),
        start_line=1,
        end_line=60,
        content="<script setup>useAuthStore().register()</script>",
        chunk_type="symbol",
        lexical_tokens=["auth", "register", "use", "store"],
        metadata={"language": "vue"},
    )
    for chunk in (auth_store, auth_service, register_view):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "auth-store": RetrievalCandidate(
                chunk_id="auth-store",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 4.25, "direct_text": 1.0},
            ),
            "auth-service": RetrievalCandidate(
                chunk_id="auth-service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.65, "path_symbol": 3.5, "direct_text": 1.0},
            ),
            "register-view": RetrievalCandidate(
                chunk_id="register-view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 2.5, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("frontend useAuthStore login register fetchCurrentUser Pinia"),
        "frontend useAuthStore login register fetchCurrentUser Pinia",
    )

    assert ranked[0].chunk.chunk_id == "auth-store"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert (
        score_parts_by_chunk["auth-store"]["identifier_exact_match_boost"]
        > score_parts_by_chunk["auth-service"].get("identifier_exact_match_boost", 0.0)
    )
    assert ranked[0].score_parts["path_role_hint_boost"] > 0
```

```python
def test_identifier_intent_ranks_composable_above_chat_types_and_views(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    composable = DocumentChunk(
        chunk_id="sse-composable",
        file_path=Path("frontend/src/views/chat/composables/useSseConnection.ts"),
        start_line=1,
        end_line=120,
        content="export function useSseConnection() { return new EventSource('/chat') }",
        chunk_type="symbol",
        lexical_tokens=["use", "sse", "connection", "eventsource", "chat", "composable"],
        metadata={"language": "typescript"},
    )
    types = DocumentChunk(
        chunk_id="chat-types",
        file_path=Path("frontend/src/views/chat/types.ts"),
        start_line=1,
        end_line=60,
        content="export interface ChatMessage { id: string; content: string }",
        chunk_type="symbol",
        lexical_tokens=["chat", "types", "message"],
        metadata={"language": "typescript"},
    )
    view = DocumentChunk(
        chunk_id="chat-view",
        file_path=Path("frontend/src/views/chat/index.vue"),
        start_line=1,
        end_line=100,
        content="<script setup>useSseConnection()</script>",
        chunk_type="symbol",
        lexical_tokens=["chat", "use", "sse", "connection"],
        metadata={"language": "vue"},
    )
    for chunk in (composable, types, view):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "sse-composable": RetrievalCandidate(
                chunk_id="sse-composable",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 4.5, "direct_text": 1.0},
            ),
            "chat-types": RetrievalCandidate(
                chunk_id="chat-types",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.62, "path_symbol": 3.0, "direct_text": 0.6},
            ),
            "chat-view": RetrievalCandidate(
                chunk_id="chat-view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 3.0, "direct_text": 0.8},
            ),
        },
        retrieval.tokenize_query("frontend useSseConnection EventSource chat composable"),
        "frontend useSseConnection EventSource chat composable",
    )

    assert ranked[0].chunk.chunk_id == "sse-composable"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert (
        score_parts_by_chunk["sse-composable"]["identifier_exact_match_boost"]
        > score_parts_by_chunk["chat-view"].get("identifier_exact_match_boost", 0.0)
    )
    assert ranked[0].score_parts["path_role_hint_boost"] > 0
```

```python
def test_identifier_intent_ranks_rust_frontend_entry_when_query_names_frontend(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    frontend = DocumentChunk(
        chunk_id="frontend-main",
        file_path=Path("src/main.ts"),
        start_line=1,
        end_line=120,
        content="function ProjectSwitcher() { invoke('apply_dev'); invoke('restore_clean'); }",
        chunk_type="symbol",
        lexical_tokens=["frontend", "project", "switcher", "invoke", "apply", "dev", "restore", "clean"],
        metadata={"language": "typescript"},
    )
    commands = DocumentChunk(
        chunk_id="commands",
        file_path=Path("src-tauri/src/commands.rs"),
        start_line=1,
        end_line=120,
        content="pub fn apply_dev() {} pub fn restore_clean() {}",
        chunk_type="symbol",
        lexical_tokens=["tauri", "command", "apply", "dev", "restore", "clean"],
        metadata={"language": "rust"},
    )
    for chunk in (frontend, commands):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "frontend-main": RetrievalCandidate(
                chunk_id="frontend-main",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.45, "path_symbol": 3.5, "direct_text": 0.8},
            ),
            "commands": RetrievalCandidate(
                chunk_id="commands",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 3.75, "direct_text": 1.0},
            ),
        },
        retrieval.tokenize_query("invoke apply_dev restore_clean frontend ProjectSwitcher"),
        "invoke apply_dev restore_clean frontend ProjectSwitcher",
    )

    assert ranked[0].chunk.chunk_id == "frontend-main"
    score_parts_by_chunk = {item.chunk.chunk_id: item.score_parts for item in ranked}
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert (
        score_parts_by_chunk["frontend-main"]["identifier_exact_match_boost"]
        > score_parts_by_chunk["commands"].get("identifier_exact_match_boost", 0.0)
    )
```

- [ ] **Step 2: Run synthetic tests and verify failure**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -k "identifier_intent_ranks" -q
```

Expected: at least one ranking assertion fails because retrieval does not yet use query identifier intent and generic path roles.

- [ ] **Step 3: Wire identifier intent into `_rank_chunks`**

In `src/context_search_tool/retrieval.py`, add imports:

```python
from context_search_tool.identifier_intent import IdentifierIntent, infer_identifier_intent
from context_search_tool.path_roles import PathRole, classify_path_role
```

Inside `_rank_chunks`, compute the intent after `project_units` and `query_scope`:

```python
    identifier_intent = infer_identifier_intent(query, tokens)
```

When building each candidate item, merge score parts:

```python
            score_parts = _merge_score_parts(
                score_parts,
                _identifier_intent_score_parts(chunk, identifier_intent),
            )
```

- [ ] **Step 4: Add score-part helpers**

Add these helpers near `_role_exact_match_boost`:

```python
def _identifier_intent_score_parts(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> dict[str, float]:
    parts: dict[str, float] = {}
    path_role = classify_path_role(chunk.file_path, chunk.content)
    identifier_score = _identifier_exact_match_score(chunk, intent)
    if identifier_score:
        parts["identifier_exact_match_boost"] = identifier_score

    role_score = _path_role_hint_score(path_role, intent)
    if role_score:
        parts["path_role_hint_boost"] = role_score

    if _strong_role_mismatch(path_role, intent, identifier_score):
        parts["path_role_mismatch_penalty"] = -0.08

    return parts


def _identifier_exact_match_score(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> float:
    if not intent.identifiers and not intent.file_hints:
        return 0.0

    path_text = chunk.file_path.as_posix().lower()
    stem_text = chunk.file_path.stem.lower()
    content_text = chunk.content.lower()
    symbol_names = {symbol.name.lower() for symbol in chunk.symbols}
    score = 0.0

    for file_hint in intent.file_hints:
        normalized = file_hint.lower()
        if normalized in path_text:
            score = max(score, 0.40)
        elif normalized in content_text:
            score = max(score, 0.30)

    matched_identifiers = 0
    for identifier in intent.identifiers:
        normalized = identifier.lower()
        if normalized in symbol_names or normalized == stem_text or normalized in path_text:
            matched_identifiers += 1
            score = max(score, 0.30)
        elif normalized in content_text:
            matched_identifiers += 1
            score = max(score, 0.20)

    if matched_identifiers > 1:
        score += min(0.10, 0.05 * (matched_identifiers - 1))

    return min(score, 0.40)


def _path_role_hint_score(path_role: PathRole, intent: IdentifierIntent) -> float:
    if _path_role_matches_intent(path_role, intent.role_hints):
        if path_role.name == "service_interface":
            return 0.08
        return 0.14
    return 0.0


def _path_role_matches_intent(path_role: PathRole, role_hints: tuple[str, ...]) -> bool:
    if path_role.name in role_hints:
        return True
    compatible_hints = {
        "service_impl": {"service"},
        "service_interface": {"service"},
    }
    return bool(compatible_hints.get(path_role.name, set()).intersection(role_hints))


def _strong_role_mismatch(
    path_role: PathRole,
    intent: IdentifierIntent,
    identifier_score: float,
) -> bool:
    if identifier_score > 0:
        return False
    if not intent.role_hints:
        return False
    high_confidence_roles = {
        "state_store",
        "composable",
        "command",
        "engine",
        "handler",
        "middleware",
        "service",
        "repository",
        "source_adapter",
    }
    return (
        bool(set(intent.role_hints).intersection(high_confidence_roles))
        and not _path_role_matches_intent(path_role, intent.role_hints)
    )
```

- [ ] **Step 5: Add rerank score application**

In `_rerank_score`, after existing `file_hint_match_boost` handling and before route/project adjustments, add:

```python
    if not has_project_scope_mismatch:
        if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
            rerank_score += score_parts["identifier_exact_match_boost"]
        if score_parts.get("path_role_hint_boost", 0.0) > 0:
            rerank_score += score_parts["path_role_hint_boost"]
        if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
            rerank_score += score_parts["path_role_mismatch_penalty"]
```

Do not add these new keys to `_combined_score`.

- [ ] **Step 6: Add public reasons**

In `_reasons`, add:

```python
    if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
        reasons.append("explicit identifier match")
    if score_parts.get("path_role_hint_boost", 0.0) > 0:
        reasons.append("path role hint match")
    if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
        reasons.append("path role mismatch penalty")
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_identifier_intent.py tests/test_path_roles.py tests/test_retrieval_pipeline.py -k "identifier_intent_ranks or path_role or chunk_role" -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: rerank explicit identifier and path-role matches"
```

### Task 5: Harden Regressions Around Existing Ranking Behavior

**Files:**
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `src/context_search_tool/retrieval.py` only if a regression appears

- [ ] **Step 1: Add Java preservation tests**

Add this test near existing Java role/path tests:

```python
def test_identifier_role_boosts_preserve_java_executor_over_service_directory_label(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    executor = DocumentChunk(
        chunk_id="executor",
        file_path=Path("src/main/java/com/example/service/PageAppCatalogQueryExe.java"),
        start_line=1,
        end_line=60,
        content="class PageAppCatalogQueryExe { String fillCanApplyFilter() { return \"\"; } }",
        chunk_type="symbol",
        lexical_tokens=["page", "app", "catalog", "query", "exe", "can", "apply"],
        metadata={"language": "java"},
    )
    service = DocumentChunk(
        chunk_id="service",
        file_path=Path("src/main/java/com/example/service/AppCatalogService.java"),
        start_line=1,
        end_line=60,
        content="interface AppCatalogService { String page(); }",
        chunk_type="symbol",
        lexical_tokens=["app", "catalog", "service", "page"],
        metadata={"language": "java"},
    )
    for chunk in (executor, service):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "executor": RetrievalCandidate(
                chunk_id="executor",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.50, "path_symbol": 4.0, "direct_text": 1.0},
            ),
            "service": RetrievalCandidate(
                chunk_id="service",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 2.0, "direct_text": 0.6},
            ),
        },
        retrieval.tokenize_query("PageAppCatalogQueryExe fillCanApplyFilter"),
        "PageAppCatalogQueryExe fillCanApplyFilter",
    )

    assert ranked[0].chunk.chunk_id == "executor"
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
```

- [ ] **Step 2: Add Java service role compatibility regression**

Add:

```python
def test_path_role_service_hint_treats_java_impl_as_service_without_mismatch(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service_impl = DocumentChunk(
        chunk_id="service-impl",
        file_path=Path("src/main/java/com/example/service/impl/AuthServiceImpl.java"),
        start_line=1,
        end_line=80,
        content="class AuthServiceImpl implements AuthService { User currentUser() { return null; } }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "impl", "current", "user"],
        metadata={"language": "java"},
    )
    service_interface = DocumentChunk(
        chunk_id="service-interface",
        file_path=Path("src/main/java/com/example/service/AuthService.java"),
        start_line=1,
        end_line=40,
        content="interface AuthService { User currentUser(); }",
        chunk_type="symbol",
        lexical_tokens=["auth", "service", "current", "user"],
        metadata={"language": "java"},
    )
    for chunk in (service_impl, service_interface):
        store.replace_chunks(chunk.file_path, [chunk])

    ranked = retrieval._rank_chunks(
        store,
        {
            "service-impl": RetrievalCandidate(
                chunk_id="service-impl",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.55, "path_symbol": 3.0, "direct_text": 0.8},
            ),
            "service-interface": RetrievalCandidate(
                chunk_id="service-interface",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.60, "path_symbol": 2.0, "direct_text": 0.6},
            ),
        },
        retrieval.tokenize_query("auth service current user"),
        "auth service current user",
    )

    assert ranked[0].chunk.chunk_id == "service-impl"
    assert ranked[0].score_parts["path_role_hint_boost"] > 0
    assert "path_role_mismatch_penalty" not in ranked[0].score_parts
```

- [ ] **Step 3: Add no-hard-filter cross-role test**

Add:

```python
def test_path_role_mismatch_penalty_does_not_hide_strong_identifier_match(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    view = DocumentChunk(
        chunk_id="view",
        file_path=Path("frontend/src/views/auth/register.vue"),
        start_line=1,
        end_line=80,
        content="<script setup>function useAuthStore() { return null }</script>",
        chunk_type="symbol",
        lexical_tokens=["use", "auth", "store", "register"],
        metadata={"language": "vue"},
    )
    store.replace_chunks(view.file_path, [view])

    ranked = retrieval._rank_chunks(
        store,
        {
            "view": RetrievalCandidate(
                chunk_id="view",
                score=1.0,
                source="direct",
                score_parts={"semantic": 0.55, "path_symbol": 2.5, "direct_text": 1.0},
            )
        },
        retrieval.tokenize_query("useAuthStore register"),
        "useAuthStore register",
    )

    assert ranked[0].chunk.chunk_id == "view"
    assert ranked[0].score_parts["identifier_exact_match_boost"] > 0
    assert "path_role_mismatch_penalty" not in ranked[0].score_parts
```

- [ ] **Step 4: Run full retrieval pipeline tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add tests/test_retrieval_pipeline.py src/context_search_tool/retrieval.py
git commit -m "test: guard identifier rerank regressions"
```

### Task 6: Validate Real Projects And Tune Conservatively

**Files:**
- Modify: `src/context_search_tool/retrieval.py` if real smoke exposes a generic scoring issue
- Modify: `tests/fixtures/generic_baseline_quality/queries.json` only to correct an invalid rank target

- [ ] **Step 1: Run non-slow fixture tests**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 2: Run all available real fixture repos**

Run:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected after implementation:

- Existing `expected_top_k` assertions pass.
- Existing `absent_top_k` assertions pass.
- Existing `outranks` assertions pass.
- New `preferred_rank` assertions pass.

- [ ] **Step 3: Capture preferred-rank distribution**

Run this read-only diagnostic to make the Top1/Top3/Top5 improvement reproducible:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python - <<'PY'
import tempfile
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository
from tests.test_generic_baseline_quality import (
    _copy_repo_for_smoke,
    _load_repo_specs,
    _preferred_rank_position,
    _repo_for_spec,
)

combined = {"total": 0, "top1": 0, "top3": 0, "top5": 0}

for repo_spec in _load_repo_specs():
    source_repo = _repo_for_spec(repo_spec)
    if source_repo is None or not source_repo.exists():
        print(f"{repo_spec['repo_key']}: skipped")
        continue

    workspace = Path(tempfile.mkdtemp(prefix=f"cst-rank-dist-{repo_spec['repo_key']}-"))
    repo = _copy_repo_for_smoke(source_repo, workspace)
    index_repository(repo, DEFAULT_CONFIG)

    repo_counts = {"total": 0, "top1": 0, "top3": 0, "top5": 0}
    for query_spec in repo_spec["queries"]:
        bundle = query_repository(repo, query_spec["query"], DEFAULT_CONFIG)
        top_paths = [result.file_path.as_posix() for result in bundle.results]
        for preferred in query_spec.get("preferred_rank", []):
            repo_counts["total"] += 1
            combined["total"] += 1
            rank = _preferred_rank_position(preferred, top_paths)
            if rank == 1:
                repo_counts["top1"] += 1
                combined["top1"] += 1
            if rank is not None and rank <= 3:
                repo_counts["top3"] += 1
                combined["top3"] += 1
            if rank is not None and rank <= 5:
                repo_counts["top5"] += 1
                combined["top5"] += 1

    print(f"{repo_spec['repo_key']}: {repo_counts}")

print(f"combined: {combined}")
PY
```

Expected: combined Top1 count is higher than the captured pre-implementation baseline (`11/16` if the preferred-rank target count is unchanged). Copy the per-repo and combined counts into the final task summary.

- [ ] **Step 4: If preferred-rank failures remain, inspect score parts before tuning**

For each failing query, run this diagnostic script after replacing `REPO_DIR_NAME` and `QUERY_TEXT`:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python - <<'PY'
import shutil
import tempfile
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository

source = Path("/Users/flobby/vibe_coding/REPO_DIR_NAME")
workspace = Path(tempfile.mkdtemp(prefix="cst-rank-debug-"))
repo = workspace / source.name
shutil.copytree(source, repo, ignore=shutil.ignore_patterns(".git", ".context-search"))
index_repository(repo, DEFAULT_CONFIG)
bundle = query_repository(repo, "QUERY_TEXT", DEFAULT_CONFIG)
for index, result in enumerate(bundle.results[:8], start=1):
    interesting = {
        key: result.score_parts[key]
        for key in sorted(result.score_parts)
        if key in {
            "semantic",
            "lexical",
            "path_symbol",
            "direct_text",
            "token_coverage",
            "identifier_exact_match_boost",
            "path_role_hint_boost",
            "path_role_mismatch_penalty",
            "file_hint_match_boost",
            "project_scope_boost",
            "project_scope_mismatch_penalty",
            "rerank_score",
        }
    }
    print(index, result.file_path.as_posix(), interesting, result.reasons)
PY
```

Only tune if the failure is a generic pattern visible in at least one synthetic test or more than one real fixture shape.

- [ ] **Step 5: Run fast-context comparison as qualitative evidence**

Use fast-context on the same queries that gained `preferred_rank` targets. Use lightweight mode:

- `project_path=/Users/flobby/vibe_coding/imagebed`
- `project_path=/Users/flobby/vibe_coding/env-change`
- `project_path=/Users/flobby/vibe_coding/Investment-Assistant`
- `tree_depth=2`
- `max_turns=1`
- `max_results=5`
- `exclude_paths=[".git", ".context-search", "node_modules", "dist", "target", "build"]`

Record the comparison in the final task summary. Do not add fast-context output to tests.

- [ ] **Step 6: Commit Task 6 if tuning was required**

If production or fixture corrections were needed:

```bash
git add src/context_search_tool/retrieval.py tests/fixtures/generic_baseline_quality/queries.json
git commit -m "fix: tune generic identifier rank targets"
```

If no tuning was needed, skip this commit.

### Task 7: Documentation And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README generic baseline section**

Add this paragraph under the existing Generic Language Baseline section:

```markdown
CST also treats explicit code intent as a generic ranking signal. Queries that name identifiers such as `UploadHandler`, `useAuthStore`, `apply_dev`, filenames such as `nav.go`, or broad path roles such as `handler`, `service`, `store`, `composable`, `command`, and `engine` receive explainable rerank support. These are language-neutral baseline signals, not framework plugins.
```

- [ ] **Step 2: Run complete focused verification**

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest \
  tests/test_identifier_intent.py \
  tests/test_path_roles.py \
  tests/test_generic_baseline_quality.py \
  tests/test_tokenizer_scanner.py \
  tests/test_rerank_soft_sorting.py \
  tests/test_retrieval_pipeline.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run real-project slow verification**

Run:

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected: PASS.

- [ ] **Step 4: Run whitespace checks**

Run:

```bash
git diff --check
git diff --cached --check
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Commit docs**

```bash
git add README.md
git commit -m "docs: describe explicit code-intent baseline"
```

## 6. Review Checklist

Before merging:

- [ ] No production code mentions real repository names such as `Investment-Assistant`, `imagebed`, or `env-change`.
- [ ] New rank improvements are driven by generic identifier, filename, path-role, or project-scope evidence.
- [ ] Query-intent path roles do not diverge silently from existing `_chunk_role()` behavior on overlapping Java/service/view/source cases.
- [ ] `expected_top_k` continues to protect recall.
- [ ] `preferred_rank` protects precision without replacing recall assertions.
- [ ] Rank-distribution diagnostic output is captured in the final summary, including Top1/Top3/Top5 counts.
- [ ] Planner-disabled behavior remains deterministic.
- [ ] Java/Spring executor/service/controller behavior is preserved.
- [ ] Single-project repos and root-indexed monorepos both pass real smoke.

## 7. Completion Commands

Run these commands before declaring the milestone complete:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest \
  tests/test_identifier_intent.py \
  tests/test_path_roles.py \
  tests/test_generic_baseline_quality.py \
  tests/test_tokenizer_scanner.py \
  tests/test_rerank_soft_sorting.py \
  tests/test_retrieval_pipeline.py \
  -q

CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv

git diff --check
git diff --cached --check
```

Expected outcome:

- Unit and retrieval tests pass.
- Real smoke passes for every available fixture repo.
- Cross-project preferred-rank targets pass.
- Final summary includes CST rank distribution and fast-context qualitative comparison.
