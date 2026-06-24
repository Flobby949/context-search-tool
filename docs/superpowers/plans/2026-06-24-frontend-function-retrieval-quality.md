# Frontend Function Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each task below has explicit red/green verification and commit points.

**Goal:** Improve generic retrieval quality for frontend-heavy repositories where one user-facing function spans route/view files, components, stores, services, utilities, and type declarations. The first real target is `program-tool`, but the implementation must stay baseline-wide and guarded so non-frontend repositories are not retuned around this project.

**Architecture:** Add a frontend-specific, guarded rerank layer on top of the existing lexical/path/identifier scoring pipeline. The layer classifies frontend file roles, infers broad query intent, applies soft score parts for entrypoints/support/noise, and optionally boosts already-retrieved files that are directly imported by the top frontend entrypoint. It must not hard-filter candidates or introduce new second-pass candidates.

**Tech Stack:** Python retrieval pipeline, pytest, existing generic baseline quality fixtures, optional Ollama experiment runner only after deterministic gates are green.

**Prerequisite:** Execute this plan on top of the branch or mainline that already contains the storage-role and scanner-noise followups. In the current workspace, the frontend spec evidence was collected after `codex/storage-role-scanner-noise` commit `7192fc4`; plain older main may lack the `.d.ts`, lockfile, test-path, and storage-role fixes that this plan assumes.

**Genericity Guardrail:** Production code must not contain `program_tool`, `program-tool`, `/Users/flobby/vueProject/program-tool`, `watermark-remover`, `mqtt-tool`, `qrcode-tool`, `json-to-entity`, `app-layout-theme`, or `ai-chat`. Those literals are allowed only in tests, fixtures, documentation, and diagnostic commands. The implementation must rely on generic frontend repository structure, path roles, import relationships, query-intent signals, and noise classes.

---

## Success Criteria

- `program_tool` is added to the generic baseline quality fixture with committed reduced-project coverage and real-repo override support.
- No production module contains `program_tool`, `program-tool`, the local absolute `program-tool` path, or the fixture query ids.
- The six initial frontend queries pass on `/Users/flobby/vueProject/program-tool`:
  - `watermark-remover`
  - `mqtt-tool`
  - `qrcode-tool`
  - `json-to-entity`
  - `app-layout-theme`
  - `ai-chat`
- Existing generic baseline repositories keep their previous preferred-rank behavior.
- Non-frontend repositories do not receive frontend boosts or frontend noise penalties.
- Top1 for mixed implementation queries, especially JSON-to-entity, remains the implementation utility when the query intent clearly asks for generated code/entity conversion behavior.
- Lockfiles and scratch `temp/**` files cannot occupy top feature-query ranks merely through broad dependency or generated-code lexical overlap.
- Any optional model reranker remains experiment-only and is not wired into production retrieval.

---

## Test Command Convention

Use these commands unless a task gives a narrower command:

```bash
PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py tests/test_retrieval_pipeline.py -q
```

```bash
PYTHONPATH=src conda run -n base python -m pytest tests/test_generic_baseline_quality.py::test_generic_baseline_quality_queries_load tests/test_generic_baseline_quality.py::test_generic_baseline_quality_rejects_invalid_fixture_shapes -q
```

```bash
PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv
```

Run broader existing smoke after deterministic work is green:

```bash
PYTHONPATH=src CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
```

If a local real repository is absent, the test may skip. The committed reduced fixture must still exercise fixture loading and shape validation in normal CI.

---

## Task 1: Add Program-Tool Quality Fixture And Fallback Repo Resolution

**Goal:** Make the frontend weakness measurable before tuning.

**Files:**

- `tests/fixtures/generic_baseline_quality/queries.json`
- `tests/test_generic_baseline_quality.py`
- `tests/fixtures/real_projects/program_tool/package.json`
- `tests/fixtures/real_projects/program_tool/package-lock.json`
- `tests/fixtures/real_projects/program_tool/src/router/index.ts`
- `tests/fixtures/real_projects/program_tool/src/views/image/WatermarkRemover.vue`
- `tests/fixtures/real_projects/program_tool/src/services/watermarkDetection.ts`
- `tests/fixtures/real_projects/program_tool/src/utils/imageUtils.ts`
- `tests/fixtures/real_projects/program_tool/src/views/communication/MqttTool.vue`
- `tests/fixtures/real_projects/program_tool/src/utils/mqttUtils.ts`
- `tests/fixtures/real_projects/program_tool/src/views/qrcode/QRCodeTool.vue`
- `tests/fixtures/real_projects/program_tool/src/utils/qrcodeUtils.ts`
- `tests/fixtures/real_projects/program_tool/src/types/index.ts`
- `tests/fixtures/real_projects/program_tool/src/types/qrcode-reader.d.ts`
- `tests/fixtures/real_projects/program_tool/src/views/json/JsonToEntity.vue`
- `tests/fixtures/real_projects/program_tool/src/utils/jsonToEntity.ts`
- `tests/fixtures/real_projects/program_tool/src/components/AppLayout.vue`
- `tests/fixtures/real_projects/program_tool/src/stores/app.ts`
- `tests/fixtures/real_projects/program_tool/src/views/ai/AiChat.vue`
- `tests/fixtures/real_projects/program_tool/src/utils/markdownUtils.ts`
- `tests/fixtures/real_projects/program_tool/temp/entityToMock.js`

**Steps:**

- [ ] Extend the quality fixture schema to accept a fourth repo key, `program_tool`.

  Add this entry to `tests/fixtures/generic_baseline_quality/queries.json`:

  ```json
  {
    "repo_key": "program_tool",
    "repo_dir_name": "program-tool",
    "queries": [
      {
        "id": "watermark-remover",
        "query": "watermark remover remove image watermark detection mask canvas inpaint",
        "expected_paths": [
          "src/views/image/WatermarkRemover.vue",
          "src/services/watermarkDetection.ts"
        ],
        "preferred": [
          {
            "path": "src/views/image/WatermarkRemover.vue",
            "max_rank": 1
          }
        ],
        "forbidden_above": [
          {
            "path": "src/utils/imageUtils.ts",
            "max_rank": 1
          }
        ],
        "top_k": 5
      },
      {
        "id": "mqtt-tool",
        "query": "MQTT connect subscribe publish topic qos websocket logs",
        "expected_paths": [
          "src/views/communication/MqttTool.vue",
          "src/utils/mqttUtils.ts",
          "src/types/index.ts"
        ],
        "preferred": [
          {
            "path": "src/views/communication/MqttTool.vue",
            "max_rank": 3
          },
          {
            "path": "src/utils/mqttUtils.ts",
            "max_rank": 3
          },
          {
            "path": "src/types/index.ts",
            "max_rank": 5
          }
        ],
        "top_k": 5
      },
      {
        "id": "qrcode-tool",
        "query": "QRCode generate scan camera decode paste image qrcode-reader",
        "expected_paths": [
          "src/views/qrcode/QRCodeTool.vue",
          "src/utils/qrcodeUtils.ts",
          "src/types/qrcode-reader.d.ts"
        ],
        "preferred": [
          {
            "path": "src/views/qrcode/QRCodeTool.vue",
            "max_rank": 1
          },
          {
            "path": "src/utils/qrcodeUtils.ts",
            "max_rank": 3
          },
          {
            "path": "src/types/qrcode-reader.d.ts",
            "max_rank": 5
          }
        ],
        "absent_top_k": [
          {
            "path": "package-lock.json",
            "top_k": 5
          }
        ],
        "top_k": 5
      },
      {
        "id": "json-to-entity",
        "query": "JSON to entity generate Java TypeScript CSharp Python class interface",
        "expected_paths": [
          "src/utils/jsonToEntity.ts",
          "src/views/json/JsonToEntity.vue"
        ],
        "preferred": [
          {
            "path": "src/utils/jsonToEntity.ts",
            "max_rank": 1
          },
          {
            "path": "src/views/json/JsonToEntity.vue",
            "max_rank": 3
          }
        ],
        "absent_top_k": [
          {
            "path": "package-lock.json",
            "top_k": 5
          },
          {
            "path": "temp/entityToMock.js",
            "top_k": 5
          }
        ],
        "top_k": 5
      },
      {
        "id": "app-layout-theme",
        "query": "AppLayout theme sidebar tool categories dark light Pinia",
        "expected_paths": [
          "src/components/AppLayout.vue",
          "src/stores/app.ts"
        ],
        "preferred": [
          {
            "path": "src/components/AppLayout.vue",
            "max_rank": 1
          },
          {
            "path": "src/stores/app.ts",
            "max_rank": 3
          }
        ],
        "top_k": 5
      },
      {
        "id": "ai-chat",
        "query": "AI chat markdown history export highlight code conversation",
        "expected_paths": [
          "src/views/ai/AiChat.vue",
          "src/utils/markdownUtils.ts"
        ],
        "preferred": [
          {
            "path": "src/views/ai/AiChat.vue",
            "max_rank": 1
          },
          {
            "path": "src/utils/markdownUtils.ts",
            "max_rank": 5
          }
        ],
        "top_k": 5
      }
    ]
  }
  ```

- [ ] Update `test_generic_baseline_quality_queries_load` so the accepted repo set includes `program_tool`.

  The assertion should become:

  ```python
  assert {repo["repo_key"] for repo in data} == {
      "imagebed",
      "env_change",
      "investment_assistant",
      "program_tool",
  }
  ```

- [ ] Extend `_repo_for_spec` to resolve the committed reduced fixture when no real repo is configured.

  Keep the resolution order:

  1. `CST_SMOKE_<REPO_KEY>_REPO`
  2. `CST_SMOKE_REPOS_DIR / repo_dir_name`
  3. `tests/fixtures/real_projects/<repo_key>`
  4. skip

  Implementation shape:

  ```python
  fixture_repo = Path(__file__).parent / "fixtures" / "real_projects" / str(repo_spec["repo_key"])
  if fixture_repo.exists():
      return fixture_repo
  ```

- [ ] Add a focused test that proves `_repo_for_spec` can resolve the committed reduced fixture for `program_tool` without environment variables.

  Keep it narrow and restore environment state with `monkeypatch`.

- [ ] Build the reduced fixture by copying only the source files listed above from `/Users/flobby/vueProject/program-tool`.

  Do not copy `node_modules`, `dist`, `.git`, generated caches, screenshots, or unrelated source directories.

- [ ] Run fixture shape tests.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_generic_baseline_quality.py::test_generic_baseline_quality_queries_load tests/test_generic_baseline_quality.py::test_generic_baseline_quality_rejects_invalid_fixture_shapes -q
  ```

- [ ] Run the real-project `program_tool` smoke and record the failing ranks. This is expected to fail before deterministic rerank work.

  ```bash
  PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv
  ```

**Commit:** `test: add frontend program_tool quality gates`

---

## Task 2: Add Guarded Frontend Role And Query Intent Classification

**Goal:** Introduce a small, testable frontend classification module without wiring it into ranking yet.

**Files:**

- `src/context_search_tool/frontend_roles.py`
- `tests/test_frontend_roles.py`

**Steps:**

- [ ] Create `tests/test_frontend_roles.py` first.

  Cover these role classifications:

  ```python
  @pytest.mark.parametrize(
      ("path", "expected"),
      [
          ("src/router/index.ts", "route_config"),
          ("src/views/qrcode/QRCodeTool.vue", "view_page"),
          ("src/pages/qrcode/QRCodeTool.vue", "view_page"),
          ("src/components/AppLayout.vue", "layout_component"),
          ("src/components/ImageUploader.vue", "shared_component"),
          ("src/stores/app.ts", "store"),
          ("src/services/watermarkDetection.ts", "service"),
          ("src/api/toolApi.ts", "service"),
          ("src/utils/qrcodeUtils.ts", "utility"),
          ("src/types/qrcode-reader.d.ts", "type_decl"),
          ("temp/entityToMock.js", "scratch_temp"),
          ("package-lock.json", "lockfile"),
      ],
  )
  def test_classify_frontend_role(path, expected):
      assert classify_frontend_role(path).name == expected
  ```

- [ ] Add intent tests that lock the risky mixed-query behavior.

  Required assertions:

  ```python
  intent = infer_frontend_intent("QRCode generate scan camera decode paste image qrcode-reader")
  assert intent.feature_entrypoint >= 0.65
  assert intent.utility_implementation >= 0.35
  assert intent.feature_entrypoint > intent.state
  ```

  ```python
  intent = infer_frontend_intent("JSON to entity generate Java TypeScript CSharp Python class interface")
  assert intent.utility_implementation >= 0.75
  assert intent.utility_implementation > intent.feature_entrypoint
  assert intent.state <= intent.feature_entrypoint
  ```

  ```python
  intent = infer_frontend_intent("AppLayout theme sidebar tool categories dark light Pinia")
  assert intent.feature_entrypoint >= 0.55
  assert intent.state >= 0.35
  ```

- [ ] Add frontend guard tests.

  The guard must enable only when repository evidence looks frontend-specific. It should not enable merely because a random path contains `src/`.

  Required cases:

  ```python
  assert frontend_repo_enabled([
      "package.json",
      "src/views/qrcode/QRCodeTool.vue",
      "src/components/AppLayout.vue",
  ])
  assert not frontend_repo_enabled([
      "pom.xml",
      "src/main/java/com/example/App.java",
      "src/test/java/com/example/AppTest.java",
  ])
  ```

- [ ] Implement `src/context_search_tool/frontend_roles.py` with immutable result types.

  Implementation shape:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from pathlib import PurePosixPath
  from typing import Iterable

  @dataclass(frozen=True)
  class FrontendRole:
      name: str

  @dataclass(frozen=True)
  class FrontendIntent:
      feature_entrypoint: float
      utility_implementation: float
      state: float
  ```

- [ ] Keep role rules path-first and deterministic.

  Minimum role mapping:

  - `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `pnpm-lock.yml`, `bun.lockb` -> `lockfile`
  - `temp/**`, `tmp/**`, `.cache/**` -> `scratch_temp`
  - `src/router/**`, `src/routes/**` -> `route_config`
  - `src/views/**`, `src/pages/**` -> `view_page`
  - `src/components/AppLayout.vue`, `src/components/layout/**`, `src/layouts/**` -> `layout_component`
  - other `src/components/**` -> `shared_component`
  - `src/stores/**`, `src/store/**` -> `store`
  - `src/services/**`, `src/api/**` -> `service`
  - `src/utils/**`, `src/lib/**`, `src/helpers/**` -> `utility`
  - `src/types/**`, `src/**/*.d.ts` -> `type_decl`
  - otherwise `other`

- [ ] Keep query intent small and transparent.

  Use additive token groups and clamp each score to `0.0..1.0`.

  Initial token groups:

  - Feature entrypoint: `tool`, `page`, `view`, `component`, `layout`, `chat`, `qrcode`, `mqtt`, `watermark`, `sidebar`, `theme`
  - Utility implementation: `generate`, `decode`, `encode`, `parse`, `format`, `convert`, `entity`, `class`, `interface`, `typescript`, `java`, `csharp`, `python`, `mask`, `inpaint`, `detection`, `markdown`
  - State: `pinia`, `store`, `state`, `theme`, `sidebar`, `dark`, `light`, `history`

  Preserve the spec's mixed-intent target:

  - JSON-to-entity: utility implementation clearly wins.
  - QRCode/MQTT/watermark: entrypoint is strong, support files still have measurable utility intent.

- [ ] Run role tests.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py -q
  ```

**Commit:** `feat: classify frontend roles and query intent`

---

## Task 3: Wire Frontend Score Parts Into Ranking Without Import Readback

**Goal:** Improve obvious frontend feature/support/noise ordering using only candidate metadata and content already indexed.

**Files:**

- `src/context_search_tool/frontend_roles.py`
- `src/context_search_tool/retrieval.py`
- `tests/test_retrieval_pipeline.py`
- `tests/test_frontend_roles.py`

**Steps:**

- [ ] Add failing synthetic ranking tests before implementation.

  Add tests to `tests/test_retrieval_pipeline.py` using the existing temporary-store helpers. The tests must prove:

  1. A feature entrypoint view can outrank a broad utility for a feature query.
  2. JSON-to-entity keeps the utility implementation above the view.
  3. `temp/**` and lockfiles are demoted for feature queries.
  4. The frontend score parts are absent in a Java-only repo.

  Example expected assertions:

  ```python
  results = query_repository(repo, "QRCode generate scan camera decode paste image qrcode-reader", max_results=5)
  assert results[0].path == "src/views/qrcode/QRCodeTool.vue"
  assert "package-lock.json" not in [result.path for result in results]
  ```

  ```python
  results = query_repository(repo, "JSON to entity generate Java TypeScript CSharp Python class interface", max_results=5)
  assert results[0].path == "src/utils/jsonToEntity.ts"
  assert "temp/entityToMock.js" not in [result.path for result in results]
  ```

- [ ] Add `frontend_score_parts(path, query, enabled)` in `frontend_roles.py`.

  Suggested signature:

  ```python
  def frontend_score_parts(path: str, query: str, *, enabled: bool) -> dict[str, float]:
      ...
  ```

  The function returns an empty dict when `enabled` is false.

- [ ] Use soft, explainable score parts only.

  Initial values:

  - `frontend_entrypoint_boost`: up to `+0.35`
  - `frontend_support_boost`: up to `+0.18`
  - `penalty`: aggregate negative score for lockfile/scratch/type noise, combined by taking the most negative existing/new penalty
  - `frontend_lockfile_penalty`: diagnostic detail, `-0.50` when lockfile is not explicitly requested
  - `frontend_scratch_temp_penalty`: diagnostic detail, `-0.60`
  - `frontend_type_decl_penalty`: diagnostic detail, `-0.12` for feature-entrypoint-heavy queries unless the query includes `type`, `types`, `declaration`, `d.ts`, or a concrete type package token such as `qrcode-reader`

  Role-specific boost rules:

  - `view_page`, `layout_component`, `route_config`: receive entrypoint boost when `feature_entrypoint >= 0.45`.
  - `shared_component`: receive a smaller entrypoint boost when `feature_entrypoint >= 0.55`.
  - `utility`, `service`: receive support boost when `utility_implementation >= 0.45`.
  - `store`: receive support boost when `state >= 0.35`.
  - `type_decl`: receive support boost only when type-related terms are present.

- [ ] Do not implement a broad `frontend_role_mismatch_penalty`.

  The v1 risk is misclassifying mixed intent. Use positive boosts and targeted noise penalties only.

- [ ] Wire frontend score parts in `retrieval._rank_chunks`.

  Implementation location:

  - after existing generic noise and identifier/path role score parts are collected
  - before `_combined_score(score_parts)`

  Implementation shape:

  ```python
  frontend_enabled = frontend_repo_enabled(chunk.document.path for chunk in candidate_chunks)
  ...
  score_parts.update(frontend_score_parts(chunk.document.path, query, enabled=frontend_enabled))
  ```

  If `penalty` already exists, merge penalties by keeping the most negative value:

  ```python
  if key == "penalty" and key in score_parts:
      score_parts[key] = min(score_parts[key], value)
  else:
      score_parts[key] = value
  ```

- [ ] Extend `_combined_score` to consume positive frontend boosts.

  Add:

  ```python
  + score_parts.get("frontend_entrypoint_boost", 0.0)
  + score_parts.get("frontend_support_boost", 0.0)
  ```

  Keep detailed diagnostic penalties out of `_combined_score`; only aggregate `penalty` should be consumed as the negative adjustment.

- [ ] Extend `_reasons` for explainability.

  Add concise reasons:

  - `frontend entrypoint boost`
  - `frontend support boost`
  - `frontend lockfile penalty`
  - `frontend scratch temp penalty`
  - `frontend type declaration penalty`

- [ ] Run focused tests.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py tests/test_retrieval_pipeline.py -q
  ```

- [ ] Run the `program_tool` real-project smoke and inspect remaining misses.

  ```bash
  PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv
  ```

**Commit:** `feat: rerank frontend roles and noise`

---

## Task 4: Add Bounded Import-Cohort Rerank For Already Retrieved Candidates

**Goal:** Pull direct support files near their feature entrypoint without running a second search pass or recursively expanding context.

**Files:**

- `src/context_search_tool/frontend_roles.py`
- `src/context_search_tool/retrieval.py`
- `tests/test_frontend_roles.py`
- `tests/test_retrieval_pipeline.py`

**Steps:**

- [ ] Add import parsing tests first.

  Cover Vue and TypeScript static imports:

  ```python
  content = '''
  <script setup lang="ts">
  import { detectWatermark } from "@/services/watermarkDetection";
  import { resizeImage } from "@/utils/imageUtils";
  import type { QrcodeReader } from "@/types/qrcode-reader";
  </script>
  '''
  assert extract_static_imports(content) == (
      "@/services/watermarkDetection",
      "@/utils/imageUtils",
      "@/types/qrcode-reader",
  )
  ```

- [ ] Add path resolution tests.

  Required behavior:

  - `@/services/watermarkDetection` resolves to `src/services/watermarkDetection.ts` when that file exists.
  - `@/types/qrcode-reader` resolves to `src/types/qrcode-reader.d.ts` when that file exists.
  - relative imports resolve from the importer directory.
  - unsupported package imports like `vue`, `pinia`, and `mqtt` return no local path.

- [ ] Add a synthetic retrieval test proving import-cohort support boost.

  Create a temporary frontend repo with:

  - `src/views/image/WatermarkRemover.vue` importing `@/services/watermarkDetection`
  - `src/services/watermarkDetection.ts`
  - `src/utils/imageUtils.ts`

  Force all three into candidates with enough lexical evidence. Assert:

  ```python
  results = query_repository(repo, "watermark remover detection mask canvas inpaint", max_results=5)
  paths = [result.path for result in results]
  assert paths.index("src/services/watermarkDetection.ts") < paths.index("src/utils/imageUtils.ts")
  assert any("frontend import support boost" in reason for reason in results_by_path["src/services/watermarkDetection.ts"].reasons)
  ```

- [ ] Implement `extract_static_imports(content: str) -> tuple[str, ...]`.

  Support only static frontend imports:

  - `import ... from "specifier"`
  - `import type ... from "specifier"`
  - `import "specifier"`

  Do not execute code, parse dynamic imports, or interpret comments beyond normal regex avoidance.

- [ ] Implement `resolve_frontend_import(repo: Path, importer: str, specifier: str) -> str | None`.

  Resolution rules:

  - `@/x` maps to `src/x`
  - `~/x` maps to `src/x` only if the repo follows that alias in fixture evidence
  - `./x` and `../x` resolve relative to the importer directory
  - Try extensions in this order: exact path, `.ts`, `.tsx`, `.js`, `.jsx`, `.vue`, `.d.ts`, `/index.ts`, `/index.tsx`, `/index.js`, `/index.vue`
  - Reject paths that escape the repo

- [ ] Add `_apply_frontend_import_cohort_rerank(repo, ranked_chunks, query)` in `retrieval.py`.

  Apply it in `query_repository` after `_rank_chunks(...)` and before `_expand_ranked_chunks(...)`, because that stage has the repository path and the ranked candidate list.

  Budget:

  - Inspect at most top 10 ranked chunks.
  - Read at most 3 files classified as `view_page`, `layout_component`, or `shared_component`.
  - Read at most 50KB per inspected file.
  - Do not recurse through imports.
  - Do not add second-pass candidates. Only boost paths already present in `ranked_chunks`.

  Implementation sketch:

  ```python
  ranked_chunks = _rank_chunks(store, candidates, tokens, query)
  ranked_chunks = _apply_frontend_import_cohort_rerank(repo, ranked_chunks, query)
  expanded_chunks = _expand_ranked_chunks(store, ranked_chunks, max_results=max_results)
  ```

- [ ] Keep the boost soft and narrow.

  Initial import support boost:

  - Add `frontend_import_support_boost = +0.16` to already-ranked imported service/utility/store/type candidates.
  - Add it to rerank score only for this post-rank stage.
  - Preserve the anchor entrypoint rank unless another candidate already clearly outranks it.

  If `_RankedChunk` is immutable enough to make direct score-part mutation awkward, create a helper that returns copied ranked entries with adjusted `score`, `rerank_score`, and `score_parts`.

- [ ] Add reason text.

  Add `frontend import support boost` when the boost is applied.

- [ ] Run focused tests.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py tests/test_retrieval_pipeline.py -q
  ```

- [ ] Run the `program_tool` real-project smoke again and compare ranks with Task 3 output.

  ```bash
  PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv
  ```

**Commit:** `feat: boost frontend direct import cohorts`

---

## Task 5: Green Program-Tool And Existing Baseline Repositories

**Goal:** Confirm the deterministic frontend work improves the real project without regressing earlier baseline gates.

**Files:**

- No new implementation files expected. Only adjust tests or scores if evidence shows the initial thresholds were too strict or too loose.

**Steps:**

- [ ] Run the full focused suite.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py tests/test_retrieval_pipeline.py tests/test_generic_baseline_quality.py::test_generic_baseline_quality_queries_load tests/test_generic_baseline_quality.py::test_generic_baseline_quality_rejects_invalid_fixture_shapes -q
  ```

- [ ] Run the real `program_tool` smoke.

  ```bash
  PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv
  ```

- [ ] Run all available generic real-project smoke tests.

  ```bash
  PYTHONPATH=src CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv
  ```

- [ ] Run the broader retrieval tests that are cheap enough for local confidence.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_retrieval_pipeline.py tests/test_path_roles.py tests/test_scanner.py -q
  ```

- [ ] If a `program_tool` gate fails, diagnose from score parts before tuning.

  Use a small ad hoc diagnostic with `PYTHONPATH=src` and inspect:

  - final rank
  - `_combined_score`
  - `_rerank_score`
  - frontend score parts
  - generic noise penalties
  - cohort/import boost reason

  Do not change numeric weights without writing or updating a test that captures the observed failure shape.

- [ ] If an old baseline repo regresses, first confirm whether frontend guard incorrectly enabled.

  Expected fix order:

  1. Tighten `frontend_repo_enabled`.
  2. Narrow the relevant frontend token group.
  3. Reduce a boost value.
  4. Only then soften a quality gate.

- [ ] Run whitespace hygiene after final edits.

  Use the repository's existing whitespace check if present. If there is no dedicated script, run:

  ```bash
  git diff --check
  git diff --cached --check
  ```

**Commit:** `test: validate frontend function baseline quality`

---

## Task 6: Add Experiment-Only Model Rerank Runner If Deterministic Gaps Remain

**Goal:** Measure whether a small local model can improve surrounding-result coherence after deterministic ranking is already green or the remaining failures are clearly semantic.

**Start Condition:** Do not start this task until Task 5 has produced concrete remaining misses that are not explainable by path role, import cohort, lockfile, temp, or scanner coverage.

**Files:**

- `scripts/frontend_rerank_experiment.py`
- `tests/test_frontend_rerank_experiment.py`

**Steps:**

- [ ] Add tests for prompt payload construction without calling a model.

  The payload must include only:

  - query
  - path
  - frontend role
  - current rank
  - current score parts
  - best line range or snippet metadata already available from retrieval
  - first 200 characters of candidate text

  It must not include full files.

- [ ] Add tests for robust JSON response parsing.

  Required accepted shape:

  ```json
  ["src/views/qrcode/QRCodeTool.vue", "src/utils/qrcodeUtils.ts"]
  ```

  Reject unknown paths and duplicate paths.

- [ ] Implement `scripts/frontend_rerank_experiment.py`.

  Requirements:

  - Default model provider: local Ollama.
  - Default model: `qwen3.5:4b-mlx`.
  - One model call per query.
  - Candidate input: top 50 deterministic candidates.
  - Output: JSONL rows with query id, deterministic ranks, model order, changed ranks, and unknown/invalid response diagnostics.
  - Never import this script from production retrieval.
  - Never change production ranking based on experiment output in this task.

- [ ] Run the parser tests.

  ```bash
  PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_rerank_experiment.py -q
  ```

- [ ] Run the experiment only if Ollama and the model are available.

  ```bash
  PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python scripts/frontend_rerank_experiment.py --repo /Users/flobby/vueProject/program-tool --fixture tests/fixtures/generic_baseline_quality/queries.json --repo-key program_tool --model qwen3.5:4b-mlx
  ```

**Commit:** `test: add frontend model rerank experiment harness`

---

## Rollback Plan

- Frontend scoring must be guarded by `frontend_repo_enabled`. If regressions appear outside frontend repositories, disable the guard path first rather than tuning general ranking weights.
- If frontend scoring causes a broad regression inside frontend repositories, temporarily set the new score-part function to return `{}` and keep tests/fixtures for diagnosis.
- If import readback is too expensive or noisy, remove only `_apply_frontend_import_cohort_rerank`; keep role and noise scoring intact.
- Do not remove `program_tool` fixture gates unless the real evidence changes and a replacement frontend repo gate is added in the same commit.

---

## Final Verification Checklist

- [ ] `PYTHONPATH=src conda run -n base python -m pytest tests/test_frontend_roles.py tests/test_retrieval_pipeline.py -q`
- [ ] `PYTHONPATH=src conda run -n base python -m pytest tests/test_generic_baseline_quality.py::test_generic_baseline_quality_queries_load tests/test_generic_baseline_quality.py::test_generic_baseline_quality_rejects_invalid_fixture_shapes -q`
- [ ] `PYTHONPATH=src CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest 'tests/test_generic_baseline_quality.py::test_generic_baseline_real_project_quality[program_tool]' -q -vv`
- [ ] `PYTHONPATH=src CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding CST_SMOKE_PROGRAM_TOOL_REPO=/Users/flobby/vueProject/program-tool conda run -n base python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q -vv`
- [ ] `git diff --check`
- [ ] `git diff --cached --check`
