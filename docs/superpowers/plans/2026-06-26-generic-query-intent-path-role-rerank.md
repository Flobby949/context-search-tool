# Generic Query Intent And Path Role Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve CST's pure baseline ranking when broad keyword matches compete with the file role that best answers the user's question, without adding language-specific plugins or repo-specific aliases.

**Architecture:** Add a language-neutral query intent helper and extend existing path/file role classification. Feed the resulting score parts into the existing retrieval pipeline through soft boosts and the existing aggregate `penalty` channel; keep detailed penalties diagnostic only and leave scanner coverage, embeddings, Java/Spring scoring, frontend-specific scoring, project-scope scoring, and candidate generation unchanged.

**Tech Stack:** Python 3.11+, pytest, existing CST retrieval pipeline, `SQLiteStore`, `DocumentChunk`, `RetrievalCandidate`, existing `identifier_intent.py`, existing `path_roles.py`, existing generic baseline real-project smoke suite, optional fast-context comparison for qualitative validation.

---

## 1. Problem Statement

The RedInk comparison exposed a baseline-wide ranking weakness:

- CST can find the right files, but high-frequency terms such as `provider`, `active_provider`, `history`, `task_id`, `image`, and `yaml` can lift broad artifacts above logic files.
- Giving the query more exact keywords does not always help, because whole-file lexical/semantic matches can strengthen examples, docker config, generated data, or sibling UI files.
- The issue is not Python or Vue specifically. The same shape can occur in Java, Go, Rust, TypeScript, shell, and config-heavy repositories whenever implementation logic, examples, docs, deployment config, and generated output share vocabulary.

The baseline needs a deterministic question: when several candidates contain the same words, which file role best matches what the user is asking for?

This builds on the existing generic noise path in `retrieval.py`: `_generic_noise_score_parts()` and `_generic_file_role()` already demote generated schemas, indexed lockfiles, templates, docs, config, and tests for English implementation-style queries. This plan does not replace that system. It extends it with a query-intent layer so Chinese and mixed-language operation queries such as "保存配置" or "历史记录打包下载" can use the same aggregate `penalty` channel instead of creating a second scoring model.

## 2. Scope

### In Scope

- Add a small `QueryIntent` model inferred from raw query text and existing query tokens.
- Extend generic path role classification for artifact/config/deployment/output roles.
- Add an intent-by-role score layer that:
  - boosts logic files for save/update/delete/generate/retry/scan/download behavior queries,
  - boosts deployment/config artifacts only when the query asks for those artifacts,
  - demotes examples, deployment config, generated output, docs, tests, and lockfiles when they are not the requested artifact,
  - keeps negative values flowing through the existing aggregate `penalty`.
- Add focused synthetic tests for the RedInk failure shape without hard-coding RedInk into production code.
- Add optional real-project smoke commands for `/Users/flobby/openSource/RedInk-main` and existing generic fixtures.
- Keep all score changes explainable through `score_parts` and `reasons`.

### Out Of Scope

- No Python parser.
- No Vue parser.
- No framework plugin.
- No AST extraction.
- No import graph work in this slice.
- No LLM reranker.
- No embedding model change.
- No new candidate source.
- No hard filtering.
- No repo-specific aliases.
- No production literals for `RedInk`, `HisMax`, `/Users/flobby/openSource/RedInk-main`, `active_provider`, `image_providers`, or `text_providers`.

## 3. File Responsibilities

- Create: `src/context_search_tool/query_intent.py`
  - Infer broad operation intent, target role intent, artifact intent, and query confidence from raw query text plus existing tokens.
- Create: `tests/test_query_intent.py`
  - Unit tests for generic English and Chinese intent detection.
- Modify: `src/context_search_tool/path_roles.py`
  - Extend `classify_path_role()` with generic artifact/config/deployment/output roles.
  - Preserve existing role names and priorities for Java, frontend, storage, command, engine, service, repository, and source-adapter cases.
- Modify: `tests/test_path_roles.py`
  - Add role classification regressions for deployment config, runtime config, config examples, docs, generated output, lockfiles, and source logic files.
- Modify: `src/context_search_tool/retrieval.py`
  - Import `infer_query_intent`.
  - Compute query intent once inside `_rank_chunks()`.
  - Merge intent-role score parts after existing generic noise score parts and before `_combined_score()`.
  - Add rerank adjustments and human-readable reasons for new score parts.
- Modify: `tests/test_retrieval_pipeline.py`
  - Add focused `_rank_chunks()` synthetic tests for config-save, deployment-config, generated-history, download, and scan intent behavior.
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
  - Add a small number of generic `preferred_rank` or `outranks` assertions only where existing real fixtures already express the same failure class.
- Modify: `README.md`
  - Add a short note that baseline ranking includes generic query intent and path-role scoring.

## 4. Success Criteria

- No production code contains RedInk-specific literals or local absolute paths.
- Existing `tests/test_identifier_intent.py` and `tests/test_path_roles.py` continue to pass.
- New `tests/test_query_intent.py` passes.
- New retrieval synthetic tests prove:
  - save/update config logic outranks yaml/docker/example artifacts,
  - deployment config queries can still rank `Dockerfile`, compose files, and deployment yaml,
  - generated output/history data is demoted for logic queries,
  - download/scan queries boost route/service/API logic over stored artifacts,
  - explicit artifact queries are not demoted away from the artifact.
- Existing frontend-specific tests continue to pass, but this plan does not add new frontend-specific production code.
- Existing Java/Spring path-aware and generic baseline smoke tests keep passing.
- Optional RedInk smoke shows the previous Q4 query no longer places deployment/sample yaml above config logic.

## 5. Test Command Convention

Use the repo Python that has the project dependencies:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_query_intent.py tests/test_path_roles.py -q
```

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

Focused generic smoke:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Full real smoke when local repos exist:

```bash
PYTHONPATH=src CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Optional RedInk external smoke after implementation:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m context_search_tool.cli query /Users/flobby/openSource/RedInk-main "配置页面保存文本服务商和图片服务商 YAML active_provider" --json
```

Expected RedInk qualitative result: config logic files such as backend config routes, frontend settings form logic, or API wrapper rank above docker/sample yaml artifacts. This command is validation evidence only; do not encode RedInk paths or query literals into production code.

---

## Task 1: Add Generic Query Intent

**Goal:** Infer broad language-neutral query intent without looking at repository code.

**Files:**
- Create: `src/context_search_tool/query_intent.py`
- Create: `tests/test_query_intent.py`

- [ ] **Step 1: Write failing query-intent tests**

Create `tests/test_query_intent.py`:

```python
from context_search_tool.query_intent import infer_query_intent


def test_query_intent_detects_config_save_logic_without_artifact_request() -> None:
    intent = infer_query_intent(
        "配置页面保存文本服务商和图片服务商 YAML active provider",
        ["配置", "页面", "保存", "文本", "服务商", "图片", "yaml", "active", "provider"],
    )

    assert intent.operations == frozenset({"save"})
    assert "config" in intent.target_roles
    assert "ui" in intent.target_roles
    assert not intent.wants_artifact
    assert intent.confidence >= 2


def test_query_intent_detects_deployment_artifact_request() -> None:
    intent = infer_query_intent(
        "docker compose deployment yaml mount history output",
        ["docker", "compose", "deployment", "yaml", "mount", "history", "output"],
    )

    assert "deploy" in intent.target_roles
    assert "config_artifact" in intent.artifact_roles
    assert intent.wants_artifact


def test_query_intent_detects_download_logic() -> None:
    intent = infer_query_intent(
        "历史记录打包下载 zip 接口",
        ["历史", "记录", "打包", "下载", "zip", "接口"],
    )

    assert "download" in intent.operations
    assert "entrypoint" in intent.target_roles
    assert not intent.wants_artifact


def test_query_intent_keeps_plain_business_query_low_confidence() -> None:
    intent = infer_query_intent(
        "auth portfolio provider history",
        ["auth", "portfolio", "provider", "history"],
    )

    assert intent.operations == frozenset()
    assert intent.target_roles == frozenset()
    assert not intent.wants_artifact
    assert intent.confidence == 0


def test_query_intent_uses_exact_english_terms_not_substrings() -> None:
    intent = infer_query_intent(
        "rapid assets editor gzip docker-compose",
        ["rapid", "assets", "editor", "gzip", "docker", "compose"],
    )

    assert "update" not in intent.operations
    assert "download" not in intent.operations
    assert "doc" not in intent.target_roles
    assert "deploy" in intent.target_roles
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_query_intent.py -q
```

Expected: FAIL because `context_search_tool.query_intent` does not exist.

- [ ] **Step 3: Implement the minimal query intent module**

Create `src/context_search_tool/query_intent.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryIntent:
    operations: frozenset[str] = field(default_factory=frozenset)
    target_roles: frozenset[str] = field(default_factory=frozenset)
    artifact_roles: frozenset[str] = field(default_factory=frozenset)
    wants_artifact: bool = False
    confidence: int = 0


_OPERATION_KEYWORDS = {
    "save": {"save", "saving", "persist", "persistence", "保存", "持久化", "存储"},
    "update": {"update", "modify", "edit", "更新", "修改"},
    "delete": {"delete", "remove", "删除", "移除"},
    "download": {"download", "zip", "export", "下载", "导出", "打包"},
    "scan": {"scan", "sync", "synchronize", "扫描", "同步"},
    "generate": {"generate", "生成", "创建"},
    "retry": {"retry", "regenerate", "重试", "重新生成"},
}

_TARGET_ROLE_KEYWORDS = {
    "entrypoint": {"api", "endpoint", "route", "router", "controller", "接口", "路由"},
    "implementation": {"service", "handler", "logic", "impl", "实现", "逻辑", "服务"},
    "ui": {"page", "view", "component", "form", "store", "页面", "表单", "组件"},
    "config": {"config", "setting", "settings", "yaml", "yml", "配置", "服务商"},
    "deploy": {"docker", "compose", "deployment", "deploy", "部署", "容器"},
    "history": {"record", "records", "历史记录"},
    "test": {"test", "spec", "测试"},
    "doc": {"doc", "docs", "readme", "文档", "说明"},
}

_ARTIFACT_KEYWORDS = {
    "config_artifact": {
        "yaml",
        "yml",
        "json",
        "toml",
        "docker",
        "compose",
        "dockerfile",
        "配置文件",
    },
    "generated_artifact": {"output", "dist", "build", "生成文件", "产物"},
    "doc_artifact": {"readme", "docs", "markdown", "文档"},
    "test_artifact": {"test", "spec", "测试"},
}

_ARTIFACT_REQUEST_HINTS = {
    "file",
    "files",
    "artifact",
    "artifacts",
    "docker",
    "compose",
    "deployment",
    "deploy",
    "readme",
    "docs",
    "文件",
    "配置文件",
    "部署",
    "文档",
    "产物",
}


def infer_query_intent(query: str, tokens: list[str]) -> QueryIntent:
    raw = query.lower()
    terms = {token.lower() for token in tokens if token}
    raw_terms = set(re.findall(r"[a-z0-9_]+", raw))
    operations = _matching_groups(raw, raw_terms, terms, _OPERATION_KEYWORDS)
    target_roles = _matching_groups(raw, raw_terms, terms, _TARGET_ROLE_KEYWORDS)
    artifact_roles = _matching_groups(raw, raw_terms, terms, _ARTIFACT_KEYWORDS)
    wants_artifact = bool(
        artifact_roles
        and (
            _has_any(raw, raw_terms, terms, _ARTIFACT_REQUEST_HINTS)
            or target_roles.intersection({"deploy", "doc", "test"})
        )
    )
    confidence = len(operations) + len(target_roles) + (1 if wants_artifact else 0)
    return QueryIntent(
        operations=frozenset(operations),
        target_roles=frozenset(target_roles),
        artifact_roles=frozenset(artifact_roles),
        wants_artifact=wants_artifact,
        confidence=confidence,
    )


def _matching_groups(
    raw: str,
    raw_terms: set[str],
    terms: set[str],
    groups: dict[str, set[str]],
) -> set[str]:
    matches: set[str] = set()
    for group, keywords in groups.items():
        if _has_any(raw, raw_terms, terms, keywords):
            matches.add(group)
    return matches


def _has_any(
    raw: str,
    raw_terms: set[str],
    terms: set[str],
    keywords: set[str],
) -> bool:
    for keyword in keywords:
        lowered = keyword.lower()
        if _is_cjk_keyword(lowered):
            if lowered in raw:
                return True
            continue
        if lowered in terms or lowered in raw_terms:
            return True
    return False


def _is_cjk_keyword(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
```

- [ ] **Step 4: Run query-intent tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_query_intent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/query_intent.py tests/test_query_intent.py
git commit -m "feat: infer generic query intent"
```

---

## Task 2: Extend Generic Path Roles For Artifacts And Config

**Goal:** Give the rerank layer language-neutral file roles for logic, config, deployment artifacts, docs, tests, and generated output.

**Files:**
- Modify: `src/context_search_tool/path_roles.py`
- Modify: `tests/test_path_roles.py`

- [ ] **Step 1: Add failing path-role tests**

Append to `tests/test_path_roles.py`:

```python
def test_path_roles_classify_deployment_and_config_artifacts() -> None:
    assert classify_path_role(Path("Dockerfile")).name == "deployment_config"
    assert classify_path_role(Path("docker-compose.yml")).name == "deployment_config"
    assert classify_path_role(Path("docker/image_providers.yaml")).name == "deployment_config"
    assert classify_path_role(Path("docker/entrypoint.sh")).name == "source"
    assert classify_path_role(Path("image_providers.yaml.example")).name == "config_example"
    assert classify_path_role(Path("config/text_providers.yaml")).name == "runtime_config"
    assert classify_path_role(Path("tsconfig.json")).name == "config"


def test_path_roles_classify_generated_output_and_docs() -> None:
    assert classify_path_role(Path("history/index.json")).name == "generated_output"
    assert classify_path_role(Path("output/task_1/result.json")).name == "generated_output"
    assert classify_path_role(Path("README.md")).name == "doc"
    assert classify_path_role(Path("docs/setup.md")).name == "doc"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_path_roles.py -q
```

Expected: FAIL for the new artifact/config roles.

- [ ] **Step 3: Add path role rules before broad config/source fallbacks**

In `src/context_search_tool/path_roles.py`, add helper constants near the top. Use `_ARTIFACT_CONFIG_SUFFIXES` so this set is not confused with the different `_CONFIG_SUFFIXES` constant in `retrieval.py`:

```python
_DEPLOYMENT_CONFIG_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

_ARTIFACT_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env"}
```

Then add these branches in `classify_path_role()` after the existing lockfile branch and after the existing known-tool-config branch for `vite.config.*`, `webpack.config.*`, and `tsconfig.json`, but before the existing doc check. This preserves existing `tsconfig.json -> config` behavior while adding broader artifact roles:

```python
    if name in _DEPLOYMENT_CONFIG_NAMES or (
        any(part in {"docker", "deploy", "deployment", "k8s", "helm"} for part in parts)
        and path.suffix.lower() in _ARTIFACT_CONFIG_SUFFIXES
    ):
        return PathRole("deployment_config", 75)
    if name.endswith(".example") or "example" in parts or "examples" in parts or "sample" in parts:
        return PathRole("config_example", 75)
    if any(part in {"history", "output", "outputs", "generated", "gen"} for part in parts):
        return PathRole("generated_output", 85)
    if path.suffix.lower() in _ARTIFACT_CONFIG_SUFFIXES and any(
        part in {"config", "configs", "setting", "settings"} for part in parts
    ):
        return PathRole("runtime_config", 65)
    if path.suffix.lower() in _ARTIFACT_CONFIG_SUFFIXES and (
        "config" in stem or "provider" in stem or "setting" in stem
    ):
        return PathRole("runtime_config", 65)
```

Keep Java, frontend, storage, command, and service classifications below these branches. The new deployment branch deliberately applies only to known deployment file names or config-like files inside deployment/docker directories, so shell scripts such as `docker/entrypoint.sh` remain ordinary source.

- [ ] **Step 4: Preserve existing behavior tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_path_roles.py tests/test_identifier_intent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/path_roles.py tests/test_path_roles.py
git commit -m "feat: classify generic artifact path roles"
```

---

## Task 3: Add Intent-Role Score Parts

**Goal:** Convert query intent plus path role into explainable score parts and aggregate penalties.

**Files:**
- Modify: `src/context_search_tool/retrieval.py`
- Modify: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Add focused failing tests for config-save and deployment intent**

Append to `tests/test_retrieval_pipeline.py` near existing generic rerank tests:

```python
def test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts(
    tmp_path: Path,
) -> None:
    query = "配置页面保存文本服务商和图片服务商 YAML provider"
    route = _generic_noise_chunk(
        "config-route",
        "backend/routes/config_routes.py",
        "def update_config(): save active provider text image yaml config",
        ["update", "config", "save", "active", "provider", "yaml"],
        {"language": "python"},
    )
    form = _generic_noise_chunk(
        "settings-form",
        "frontend/src/composables/useProviderForm.ts",
        "export async function saveTextProvider() { updateConfig(textConfig) }",
        ["save", "text", "provider", "update", "config"],
        {"language": "typescript"},
    )
    docker_yaml = _generic_noise_chunk(
        "docker-yaml",
        "docker/text_providers.yaml",
        "active_provider: openai providers api_key model",
        ["active", "provider", "providers", "yaml"],
        {"language": "yaml"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [route, form, docker_yaml],
        {
            "config-route": {"semantic": 0.45, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.65},
            "settings-form": {"semantic": 0.42, "lexical": 0.42, "path_symbol": 2.0, "direct_text": 0.55},
            "docker-yaml": {"semantic": 0.80, "lexical": 0.80, "path_symbol": 3.0, "direct_text": 0.90},
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id in {"config-route", "settings-form"}
    assert ranked.index(by_id["docker-yaml"]) > ranked.index(by_id["config-route"])
    assert by_id["docker-yaml"].score_parts["config_artifact_penalty"] < 0
    assert by_id["config-route"].score_parts["query_operation_logic_boost"] > 0


def test_generic_intent_rerank_preserves_deployment_config_queries(
    tmp_path: Path,
) -> None:
    query = "docker compose deployment yaml mount output history"
    compose = _generic_noise_chunk(
        "compose",
        "docker-compose.yml",
        "services app volumes history output text_providers yaml",
        ["docker", "compose", "deployment", "yaml", "history", "output"],
        {"language": "yaml"},
    )
    service = _generic_noise_chunk(
        "service",
        "backend/services/history.py",
        "class HistoryService: scan output history records",
        ["history", "service", "scan", "output"],
        {"language": "python"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [compose, service],
        {
            "compose": {"semantic": 0.55, "lexical": 0.55, "path_symbol": 2.5, "direct_text": 0.70},
            "service": {"semantic": 0.60, "lexical": 0.60, "path_symbol": 2.0, "direct_text": 0.70},
        },
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "compose"
    assert ranked[0].score_parts["deployment_config_boost"] > 0
    assert "config_artifact_penalty" not in ranked[0].score_parts
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts tests/test_retrieval_pipeline.py::test_generic_intent_rerank_preserves_deployment_config_queries -q
```

Expected: FAIL because the new score parts are not implemented.

- [ ] **Step 3: Import query intent and compute it once**

In `src/context_search_tool/retrieval.py`, add:

```python
from context_search_tool.query_intent import QueryIntent, infer_query_intent
```

Inside `_rank_chunks()`, after `identifier_intent = infer_identifier_intent(query, tokens)`, add:

```python
    query_intent = infer_query_intent(query, tokens)
```

- [ ] **Step 4: Add scoring helper functions**

Add near `_identifier_intent_score_parts()`:

```python
_LOGIC_OPERATION_NAMES = {"save", "update", "delete", "download", "scan", "generate", "retry"}
_LOGIC_PATH_ROLES = {
    "entrypoint",
    "router",
    "service",
    "service_impl",
    "service_interface",
    "executor",
    "handler",
    "middleware",
    "repository",
    "source_adapter",
    "storage",
    "command",
    "engine",
    "scheduler",
    "state_store",
    "composable",
    "view",
    "component",
}
_CONFIG_ARTIFACT_ROLES = {
    "deployment_config",
    "config_example",
    "runtime_config",
    "lockfile",
}


def _query_intent_score_parts(
    path_role: PathRole,
    intent: QueryIntent,
) -> dict[str, float]:
    if intent.confidence == 0:
        return {}

    parts: dict[str, float] = {}
    operation_query = bool(
        intent.operations.intersection(_LOGIC_OPERATION_NAMES)
        and (intent.target_roles or intent.artifact_roles)
    )
    wants_deployment = "deploy" in intent.target_roles and intent.wants_artifact
    wants_docs = "doc" in intent.target_roles and intent.wants_artifact
    wants_tests = "test" in intent.target_roles and intent.wants_artifact

    if operation_query and path_role.name in _LOGIC_PATH_ROLES:
        parts["query_operation_logic_boost"] = 0.10

    if "config" in intent.target_roles and path_role.name in {
        "entrypoint",
        "router",
        "service",
        "service_impl",
        "handler",
        "state_store",
        "composable",
        "view",
        "component",
    }:
        parts["config_logic_boost"] = 0.12

    if wants_deployment and path_role.name == "deployment_config":
        parts["deployment_config_boost"] = 0.18

    if wants_docs and path_role.name == "doc":
        parts["doc_artifact_boost"] = 0.12

    if wants_tests and path_role.name == "test":
        parts["test_artifact_boost"] = 0.12

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in _CONFIG_ARTIFACT_ROLES
    ):
        parts["penalty"] = -0.35
        parts["config_artifact_penalty"] = -0.35

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name == "generated_output"
    ):
        parts["penalty"] = -0.45
        parts["generated_output_penalty"] = -0.45

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in {"doc", "test"}
    ):
        parts["penalty"] = -0.20
        parts[f"{path_role.name}_artifact_penalty"] = -0.20

    return parts


def _query_intent_rerank_adjustment(score_parts: dict[str, float]) -> float:
    if not _has_query_intent_rerank_evidence(score_parts):
        return 0.0
    return (
        score_parts.get("query_operation_logic_boost", 0.0)
        + score_parts.get("config_logic_boost", 0.0)
        + score_parts.get("deployment_config_boost", 0.0)
        + score_parts.get("doc_artifact_boost", 0.0)
        + score_parts.get("test_artifact_boost", 0.0)
    )


def _has_query_intent_rerank_evidence(score_parts: dict[str, float]) -> bool:
    return (
        score_parts.get("token_coverage", 0.0) >= 0.35
        or score_parts.get("path_symbol", 0.0) >= 1.5
        or score_parts.get("direct_text", 0.0) >= 0.55
        or score_parts.get("lexical", 0.0) >= 0.35
    )
```

Keep `_LOGIC_PATH_ROLES` narrow. Do not add fallback roles such as `source`, broad build/runtime roles such as `config`, or DTO/data-shape roles such as `data_type` to this set. Plain source files should beat artifacts through the opposing artifact penalty, not through a universal operation boost that can also lift templates, command mains, generated wrappers, or build config.

- [ ] **Step 5: Merge score parts in `_rank_chunks()`**

Inside `_rank_chunks()`, after the existing `_generic_noise_score_parts()` merge and before `penalty = abs(min(score_parts.get("penalty", 0.0), 0.0))`, add:

```python
        path_role = classify_path_role(chunk.file_path, chunk.content)
        score_parts = _merge_score_parts(
            score_parts,
            _query_intent_score_parts(path_role, query_intent),
        )
```

This means intent-driven artifact penalties contribute to `penalty` before `_should_apply_java_context_score(...)` is called. That is intentional: a file already classified as a config/generated/doc/test artifact should not receive additional Java context help for an implementation query.

Reuse this `path_role` for identifier intent scoring rather than reclassifying the path. Change `_identifier_intent_score_parts(...)` to accept the precomputed role:

```python
def _identifier_intent_score_parts(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
    path_role: PathRole,
) -> dict[str, float]:
    parts: dict[str, float] = {}
    identifier_score = _identifier_exact_match_score(chunk, intent)
    if identifier_score:
        parts["identifier_exact_match_boost"] = identifier_score

    role_score = _path_role_hint_score(path_role, intent)
    if role_score:
        parts["path_role_hint_boost"] = role_score

    if _strong_role_mismatch(path_role, intent, identifier_score):
        parts["path_role_mismatch_penalty"] = -0.08

    return parts
```

Then replace the call site:

```python
        score_parts = _merge_score_parts(
            score_parts,
            _identifier_intent_score_parts(chunk, identifier_intent, path_role),
        )
```

- [ ] **Step 6: Keep `_combined_score()` single-channel for intent scoring**

Do not add `query_operation_logic_boost`, `config_logic_boost`, `deployment_config_boost`, `doc_artifact_boost`, or `test_artifact_boost` to `_combined_score()`. Those positive values should affect final ordering only through `_query_intent_rerank_adjustment(...)`.

Do not add `config_artifact_penalty`, `generated_output_penalty`, `doc_artifact_penalty`, or `test_artifact_penalty` to `_combined_score()` either. Only aggregate `penalty` should affect negative scoring there. This avoids asymmetric double-counting where boosts are applied in both combined score and rerank while penalties apply only once.

- [ ] **Step 7: Add gated rerank adjustments**

Inside `_rerank_score()`, after frontend support adjustments and before Java-specific implementation boosts, add:

```python
    if not has_project_scope_mismatch:
        rerank_score += _query_intent_rerank_adjustment(score_parts)
```

The helper gates positive rerank boosts behind direct evidence (`token_coverage`, `path_symbol`, `direct_text`, or `lexical`) so broad operation words such as `generate`, `scan`, or `update` do not reorder weak matches by themselves.

- [ ] **Step 8: Add human-readable reasons**

In `_reasons()`, add:

```python
    if score_parts.get("query_operation_logic_boost", 0.0) > 0:
        reasons.append("query operation logic boost")
    if score_parts.get("config_logic_boost", 0.0) > 0:
        reasons.append("config logic boost")
    if score_parts.get("deployment_config_boost", 0.0) > 0:
        reasons.append("deployment config boost")
    if score_parts.get("config_artifact_penalty", 0.0) < 0:
        reasons.append("config artifact penalty")
    if score_parts.get("generated_output_penalty", 0.0) < 0:
        reasons.append("generated output penalty")
    if score_parts.get("doc_artifact_penalty", 0.0) < 0:
        reasons.append("doc artifact penalty")
    if score_parts.get("test_artifact_penalty", 0.0) < 0:
        reasons.append("test artifact penalty")
```

Calibration note: `backend/routes/config_routes.py`-style files can still be classified by existing chunk/content heuristics as `constant_or_config` and receive the current detail penalty. The config-save test should pass with the planned intent boost plus artifact penalty, but its margin is intentionally modest. Do not tune the `constant_or_config` penalty and intent boost values in the same change without rerunning the focused config-save test, generic smoke, and RedInk external query.

- [ ] **Step 9: Run focused tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_generic_intent_rerank_prefers_config_save_logic_over_yaml_artifacts tests/test_retrieval_pipeline.py::test_generic_intent_rerank_preserves_deployment_config_queries -q
```

Expected: PASS.

- [ ] **Step 10: Run full retrieval and generic shape regressions before committing**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py -q
```

Expected: PASS. This catches broad operation-keyword regressions such as `generate` queries accidentally boosting views over implementation utilities.

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/context_search_tool/retrieval.py tests/test_retrieval_pipeline.py
git commit -m "feat: rerank generic query intent roles"
```

---

## Task 4: Add Artifact Noise Regression Coverage

**Goal:** Cover the remaining generic artifact cases without broadening production logic beyond the baseline role model.

**Files:**
- Modify: `tests/test_retrieval_pipeline.py`
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`

- [ ] **Step 1: Add generated-output and scan/download tests**

Append to `tests/test_retrieval_pipeline.py`:

```python
def test_generic_intent_demotes_generated_history_for_scan_logic(
    tmp_path: Path,
) -> None:
    query = "历史记录扫描同步任务图片 scan sync service"
    service = _generic_noise_chunk(
        "history-service",
        "backend/services/history.py",
        "class HistoryService: scan_and_sync_task_images scan_all_tasks",
        ["history", "scan", "sync", "task", "images", "service"],
        {"language": "python"},
    )
    output = _generic_noise_chunk(
        "history-output",
        "history/index.json",
        '{"records": [{"status": "completed", "task_id": "abc"}]}',
        ["history", "task", "status", "completed", "json"],
        {"language": "json"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [service, output],
        {
            "history-service": {"semantic": 0.45, "lexical": 0.45, "path_symbol": 2.0, "direct_text": 0.65},
            "history-output": {"semantic": 0.75, "lexical": 0.75, "path_symbol": 2.5, "direct_text": 0.85},
        },
        retrieval.tokenize_query(query),
        query,
    )
    by_id = {item.chunk.chunk_id: item for item in ranked}

    assert ranked[0].chunk.chunk_id == "history-service"
    assert by_id["history-output"].score_parts["generated_output_penalty"] < 0


def test_generic_intent_download_logic_prefers_route_over_stored_images(
    tmp_path: Path,
) -> None:
    query = "download zip history record route api 打包下载接口"
    route = _generic_noise_chunk(
        "download-route",
        "backend/routes/history_routes.py",
        "def download_history_zip(record_id): create zip send_file download",
        ["download", "history", "zip", "route", "api"],
        {"language": "python"},
    )
    artifact = _generic_noise_chunk(
        "image-artifact",
        "output/task_1/0.json",
        '{"download": "zip", "history": "record"}',
        ["download", "zip", "history", "record"],
        {"language": "json"},
    )

    ranked = _rank_generic_noise_chunks(
        tmp_path,
        [route, artifact],
        {
            "download-route": {"semantic": 0.40, "lexical": 0.40, "path_symbol": 2.0, "direct_text": 0.70},
            "image-artifact": {"semantic": 0.72, "lexical": 0.72, "path_symbol": 2.5, "direct_text": 0.85},
        },
        retrieval.tokenize_query(query),
        query,
    )

    assert ranked[0].chunk.chunk_id == "download-route"
```

- [ ] **Step 2: Run focused tests and verify failure if Task 3 did not cover them**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_retrieval_pipeline.py::test_generic_intent_demotes_generated_history_for_scan_logic tests/test_retrieval_pipeline.py::test_generic_intent_download_logic_prefers_route_over_stored_images -q
```

Expected: PASS after Task 3. If it fails, adjust only `_query_intent_score_parts()` or `classify_path_role()` so the new score parts apply.

- [ ] **Step 3: Confirm existing fixture-level regression guards**

In `tests/fixtures/generic_baseline_quality/queries.json`, make exactly these fixture assertions present. In the current fixture file these assertions already exist, so the expected repository diff for this step is empty. If any assertion is missing in a future branch, restore exactly these fragments.

This step is a regression guard for real fixture behavior. It does not prove the new intent code works by itself; that proof comes from the Task 3 and Task 4 synthetic tests plus the RedInk external smoke.

For `imagebed/go-storage-implementations`, ensure both assertions exist:

```json
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
```

For `env_change/tauri-commands`, ensure generated schemas stay out of the top neighborhood:

```json
"absent_top_k": [
  {"glob": "src-tauri/gen/schemas/*.json", "top_k": 8}
]
```

For `env_change/engine-apply-restore`, ensure generated schemas stay out of the top neighborhood:

```json
"absent_top_k": [
  {"glob": "src-tauri/gen/schemas/*.json", "top_k": 8}
]
```

For `env_change/frontend-invoke`, ensure build-tool config does not outrank the frontend logic target:

```json
"absent_top_k": [
  {"path": "vite.config.ts", "top_k": 3}
]
```

For `env_change/settings-persistence`, ensure settings logic outranks build-tool config:

```json
"outranks": [
  {
    "source": "src-tauri/src/settings.rs",
    "noise": "vite.config.ts",
    "top_k": 8
  }
]
```

Do not add RedInk-specific fixture names or paths. Do not add absent assertions against deployment/config artifacts for queries whose user intent is explicitly deployment or artifact inspection.

- [ ] **Step 4: Run generic fixture shape tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_retrieval_pipeline.py tests/fixtures/generic_baseline_quality/queries.json
git commit -m "test: cover generic artifact intent rerank"
```

---

## Task 5: Validate, Document, And Compare

**Goal:** Verify the baseline-wide change with unit tests, existing smoke, and RedInk as external evidence.

**Files:**
- Modify: `README.md`
- No production code changes in this task.

- [ ] **Step 1: Add README note**

In `README.md`, add a short bullet under the capability overview:

```markdown
- Generic query intent rerank: broad operation words such as save, update, scan, download, generate, and deploy are matched with language-neutral file roles so implementation files are favored over examples or generated artifacts unless the query explicitly asks for those artifacts.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_query_intent.py tests/test_path_roles.py tests/test_retrieval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 3: Run generic baseline non-slow tests**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "not slow" -q
```

Expected: PASS.

- [ ] **Step 4: Run existing targeted regression suites**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_identifier_intent.py tests/test_direct_text_evidence.py tests/test_mcp_tools.py -q
```

Expected: PASS.

- [ ] **Step 5: Run slow real-project smoke when local repos exist**

Run:

```bash
PYTHONPATH=src CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

Expected: PASS or SKIP only for missing local repos. Any assertion failure is a real ranking regression to investigate before commit.

Record which smoke repositories were present and which were skipped. If any generic smoke repository is absent, do not treat this command as complete regression coverage for the fixture assertions above; call out the gap in the implementation summary.

- [ ] **Step 6: Reindex and query RedInk as external validation**

Run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m context_search_tool.cli index /Users/flobby/openSource/RedInk-main
```

Then run:

```bash
PYTHONPATH=src /opt/homebrew/Caskroom/miniforge/base/bin/python -m context_search_tool.cli query /Users/flobby/openSource/RedInk-main "配置页面保存文本服务商和图片服务商 YAML active_provider" --json
```

Expected qualitative result:

- `backend/routes/config_routes.py`, frontend settings form logic, or frontend API wrapper appears above `docker/*.yaml`.
- Any `docker/*.yaml` or sample config result includes a `config_artifact_penalty` reason when the query asks for save/update logic.

- [ ] **Step 7: Run fast-context qualitative comparison**

Run fast-context with the same RedInk query:

```text
project_path=/Users/flobby/openSource/RedInk-main
query=配置页面保存文本服务商和图片服务商 YAML active_provider
exclude_paths=.venv,frontend/node_modules,.git,.context-search,history,images,frontend/dist,frontend/.vite
```

Expected qualitative result: CST and fast-context both surface config logic files near the top. Exact ordering does not need to match.

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: describe generic query intent rerank"
```

---

## 6. Genericity Guardrails

Before final review, run:

```bash
rg -n "RedInk|HisMax|/Users/flobby/openSource/RedInk-main|active_provider|image_providers|text_providers" src tests
```

Expected:

- No matches in `src/`.
- No matches in committed tests unless a test deliberately verifies generic token handling and avoids RedInk paths.

Run:

```bash
rg -n "config_artifact_penalty|generated_output_penalty|doc_artifact_penalty|test_artifact_penalty" src/context_search_tool/retrieval.py
```

Expected:

- Detailed penalty keys appear in score part construction and reasons.
- `_combined_score()` consumes only aggregate `penalty` for negative scoring.

Run:

```bash
rg -n "query_operation_logic_boost|config_logic_boost|deployment_config_boost" src/context_search_tool/retrieval.py
```

Expected:

- Positive intent score parts appear in `_query_intent_score_parts()`, `_query_intent_rerank_adjustment()`, and `_reasons()`, and do not appear in `_combined_score()`.

## 7. Completion Checklist

- [ ] Query intent unit tests pass.
- [ ] Path role unit tests pass.
- [ ] Retrieval synthetic tests pass.
- [ ] Generic baseline shape tests pass.
- [ ] Existing identifier/path-role tests pass.
- [ ] Slow real-project smoke has been run or skipped only because local repos are absent.
- [ ] RedInk external validation has been run and the top results are recorded in the implementation summary.
- [ ] fast-context comparison has been run and summarized qualitatively.
- [ ] No production RedInk-specific literals are present.
- [ ] Aggregate penalty is the only negative score consumed by `_combined_score()`.
