# Frontend Function Retrieval Quality Design

Date: 2026-06-23
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`
Evidence repo: `/Users/flobby/vueProject/program-tool`

## Summary

Improve CST retrieval for frontend-focused repositories where one user-facing feature spans a route/view component, shared components, state stores, services, utilities, and type declarations.

The previous baseline work made explicit identifiers and many backend-style module queries reliable. Validation on `program-tool` shows a different failure mode: CST often finds relevant files, but ranks low-level utilities, stores, lockfiles, scratch files, or type declarations above the user-facing feature entrypoint. Fast-context is stronger here because it behaves like controlled exploration: it groups the feature page with its imported support files and suppresses context-pollution files.

This design should stay generic. It must not hard-code `program-tool`, and it should not tune against the earlier backend/monorepo projects as the optimization target.

## Motivation

`program-tool` is a Vue 3 + TypeScript + Vite developer-tool application. It is small enough to inspect directly, but it exercises a common frontend retrieval shape:

- `src/router/index.ts` maps route names to lazy-loaded views.
- `src/views/**` contains the user-facing tools.
- `src/components/**` contains layout and shared UI.
- `src/stores/**` contains Pinia state.
- `src/services/**` contains feature services.
- `src/utils/**` contains reusable implementation functions.
- `src/types/**` contains support types and declarations.
- `package-lock.json` and `temp/**` can contain strong lexical matches but are usually not useful code answers.

Current CST result examples from a fresh `program-tool` index, using branch `codex/storage-role-scanner-noise` at commit `7192fc4`:

| Query | CST top results | Fast-context top results | Gap |
| --- | --- | --- | --- |
| `watermark remover remove image watermark detection mask canvas inpaint` | `src/utils/imageUtils.ts` #1, `src/views/image/WatermarkRemover.vue` #2, `src/services/watermarkDetection.ts` #8 | `WatermarkRemover.vue` #1, `watermarkDetection.ts` #2 | Feature page and feature service should form the core result cluster. |
| `MQTT connect subscribe publish topic qos websocket logs` | `MqttTool.vue` #1, `src/stores/tool.ts` #2, `mqttUtils.ts` #3 | `mqttUtils.ts` #1, `MqttTool.vue` #2, `types/index.ts` #3 | Both page and utility are relevant; query intent determines order. Store should not crowd the cluster. |
| `QRCode generate scan camera decode paste image qrcode-reader` | `qrcodeUtils.ts` #1, `qrcode-reader.d.ts` #2, `QRCodeTool.vue` #3, `package-lock.json` #5 | `QRCodeTool.vue` #1, `qrcodeUtils.ts` #2, `qrcode-reader.d.ts` #3 | Type declarations and lockfiles can outrank the page. |
| `JSON to entity generate Java TypeScript CSharp Python class interface` | `jsonToEntity.ts` #1, `temp/entityToMock.js` #2, `entityToMock.ts` #3, `package-lock.json` #4, `JsonToEntity.vue` #5 | `jsonToEntity.ts` #1, `JsonToEntity.vue` #2, `stores/tool.ts` #3 | Scratch files and lockfiles pollute the feature cluster. |
| `AppLayout theme sidebar tool categories dark light Pinia` | `stores/app.ts` #1, `AppLayout.vue` #2 | `AppLayout.vue` #1, `stores/app.ts` #2 | Store evidence is strong, but layout component is the feature entrypoint. |

The common pattern is not missing recall. Most target files are present in the candidate set. The gap is role-aware ordering and feature-cohort coherence.

## Goals

- Add `program-tool` as a new real-project fixture for frontend function retrieval quality.
- Make frontend feature queries return a coherent cluster: page/layout component first when the query describes UI workflow, then imported services, utilities, stores, and types.
- Keep utility-first behavior when the query clearly asks for a concrete utility, function, class, or algorithm implementation.
- Demote dependency lockfiles, scratch/temp files, and type declarations for feature workflow queries unless the query explicitly asks for those artifacts.
- Use soft reranking and explainable `score_parts`; no hard filters for source files.
- Preserve existing backend, monorepo, and explicit identifier Top1 behavior.
- Create enough measurement to decide whether the next bottleneck is deterministic rerank or a model/LLM reranker.

## Non-Goals

- No hard-coded paths, aliases, or query shortcuts for `program-tool`.
- No Vue-specific plugin as the primary solution.
- No framework parser dependency in the first implementation.
- No schema-breaking change to `RetrievalResult`, MCP payloads, formatters, or SQLite tables.
- No broad exclusion of `temp/`, `*.d.ts`, stores, services, or utilities from the index.
- No attempt to exactly match fast-context result order.
- No LLM reranker in the first deterministic baseline pass.

## Design Principles

### Feature Entrypoints Matter

For frontend application repositories, a view/page or layout component is often the best first file for a user-facing feature query. Utilities and stores explain implementation details, but they should not automatically outrank the page when the query describes a tool workflow or UI behavior.

### Utilities Still Win Utility Queries

When the query names concrete utility symbols such as `jsonToJava`, `MqttTester`, `generateQRCode`, or `FrontendDetector`, implementation files should be allowed to win. The system should not blindly boost views above exact implementation evidence.

### Cohort Before Isolated Hits

Top results should look like one feature cluster. A good cluster may contain a route/view, service, utility, store, type file, and one shared component. It should not contain lockfiles, scratch files, unrelated tools, or broad app state unless those are explicitly requested.

### Soft Rerank, Not Hard Filter

The frontend role layer should be a ranking signal. It must not hide support files that contain strong direct evidence.

### Evidence Before Model Claims

Before declaring the model to be the bottleneck, measure whether deterministic role/noise/cohort reranking fixes the `program-tool` gaps. If it does not, run a fixed-candidate LLM rerank experiment against the same fixture.

## Target User Experience

The user runs normal commands:

```text
cst index /Users/flobby/vueProject/program-tool
cst query /Users/flobby/vueProject/program-tool "QRCode generate scan camera decode paste image qrcode-reader"
cst query /Users/flobby/vueProject/program-tool "watermark remover remove image watermark detection mask canvas inpaint"
```

Expected result shape:

- `QRCodeTool.vue`, `qrcodeUtils.ts`, and `qrcode-reader.d.ts` appear together, with the page first for workflow-style QR queries.
- `WatermarkRemover.vue` and `services/watermarkDetection.ts` appear near the top together.
- `JsonToEntity.vue` stays near `jsonToEntity.ts`; `temp/entityToMock.js` and `package-lock.json` do not crowd the top.
- `AppLayout.vue` can outrank `stores/app.ts` when the query asks about layout, sidebar, categories, and theme.
- Reasons explain frontend role and noise adjustments, for example: `frontend entrypoint match`, `feature support import`, `scratch temp penalty`, `lockfile penalty`.

## Quality Fixture

Add a new real-project fixture entry:

```json
{
  "repo_key": "program_tool",
  "path_env": "CST_SMOKE_PROGRAM_TOOL_REPO",
  "repo_dir_name": "program-tool",
  "queries": []
}
```

The existing path resolution contract should apply:

1. `CST_SMOKE_PROGRAM_TOOL_REPO`.
2. `CST_SMOKE_REPOS_DIR / program-tool`.
3. `tests/fixtures/real_projects/program_tool/` as a reduced CI snapshot.
4. Skip only when none of the above exists.

The CI snapshot should be a minimal, committed subset derived from `program-tool`, not a full vendored application. It must include only the files needed by the gates and their import edges, plus representative noise files such as `package-lock.json` and `temp/entityToMock.js`. Local development should prefer the env-var or `CST_SMOKE_REPOS_DIR` copy so the fixture can still be checked against the full real project.

Initial query gates:

```json
[
  {
    "id": "watermark-remover",
    "query": "watermark remover remove image watermark detection mask canvas inpaint",
    "expected_top_k": [
      {"path": "src/views/image/WatermarkRemover.vue", "top_k": 5},
      {"path": "src/services/watermarkDetection.ts", "top_k": 5}
    ],
    "preferred_rank": [
      {"path": "src/views/image/WatermarkRemover.vue", "top_k": 5, "max_rank": 1}
    ],
    "forbidden_above": [
      {"path": "src/utils/imageUtils.ts", "top_k": 5, "max_rank": 1}
    ]
  },
  {
    "id": "mqtt-tool",
    "query": "MQTT connect subscribe publish topic qos websocket logs",
    "expected_top_k": [
      {"path": "src/views/communication/MqttTool.vue", "top_k": 3},
      {"path": "src/utils/mqttUtils.ts", "top_k": 3},
      {"path": "src/types/index.ts", "top_k": 5}
    ]
  },
  {
    "id": "qrcode-tool",
    "query": "QRCode generate scan camera decode paste image qrcode-reader",
    "expected_top_k": [
      {"path": "src/views/qrcode/QRCodeTool.vue", "top_k": 3},
      {"path": "src/utils/qrcodeUtils.ts", "top_k": 3},
      {"path": "src/types/qrcode-reader.d.ts", "top_k": 5}
    ],
    "preferred_rank": [
      {"path": "src/views/qrcode/QRCodeTool.vue", "top_k": 5, "max_rank": 1}
    ],
    "absent_top_k": [
      {"path": "package-lock.json", "top_k": 5}
    ]
  },
  {
    "id": "json-to-entity",
    "query": "JSON to entity generate Java TypeScript CSharp Python class interface",
    "expected_top_k": [
      {"path": "src/utils/jsonToEntity.ts", "top_k": 3},
      {"path": "src/views/json/JsonToEntity.vue", "top_k": 3}
    ],
    "preferred_rank": [
      {"path": "src/utils/jsonToEntity.ts", "top_k": 5, "max_rank": 1}
    ],
    "absent_top_k": [
      {"glob": "temp/*", "top_k": 5},
      {"path": "package-lock.json", "top_k": 5}
    ]
  },
  {
    "id": "app-layout-theme",
    "query": "AppLayout theme sidebar tool categories dark light Pinia",
    "expected_top_k": [
      {"path": "src/components/AppLayout.vue", "top_k": 3},
      {"path": "src/stores/app.ts", "top_k": 3}
    ],
    "preferred_rank": [
      {"path": "src/components/AppLayout.vue", "top_k": 5, "max_rank": 1}
    ]
  },
  {
    "id": "ai-chat",
    "query": "AI chat markdown history export highlight code conversation",
    "expected_top_k": [
      {"path": "src/views/ai/AiChat.vue", "top_k": 3},
      {"path": "src/utils/markdownUtils.ts", "top_k": 5}
    ],
    "preferred_rank": [
      {"path": "src/views/ai/AiChat.vue", "top_k": 5, "max_rank": 1}
    ]
  }
]
```

Some gates intentionally fail on the current branch. They are not regressions; they define the next quality target.

## Architecture

The first implementation should stay in the existing deterministic retrieval pipeline:

```text
Index
  -> scan files
  -> existing chunk/signals/metadata
  -> optional lightweight import/path metadata

Query
  -> tokenize query
  -> infer generic frontend feature intent
  -> collect existing semantic/lexical/path/signal candidates
  -> existing merge/dedupe
  -> generic noise score parts
  -> frontend role score parts
  -> feature cohort score parts
  -> existing rerank sort and evidence anchor split
```

The design can be implemented without a schema migration by storing additional fields in `DocumentChunk.metadata` or computing role evidence at ranking time from path and content.

## Components

### 1. Frontend Role Classification

Extend the generic path-role vocabulary. This can live in `path_roles.py` or a small adjacent module if that keeps the existing roles clear.

Suggested roles:

| Role | Examples | Ranking meaning |
| --- | --- | --- |
| `route_config` | `src/router/index.ts` | Support file; strong for route-registration queries, not usually feature Top1. |
| `view_page` | `src/views/**.vue` | User-facing feature entrypoint. |
| `layout_component` | `src/components/AppLayout.vue` | Entrypoint for layout/sidebar/theme queries. |
| `shared_component` | `src/components/ImageUploader.vue`, `ToolPanel.vue` | Support file for feature pages. |
| `store` | `src/stores/*.ts` | State support; can win store-specific queries. |
| `service` | `src/services/*.ts` | Feature service; should stay near importing page. |
| `utility` | `src/utils/*.ts` | Implementation support; can win utility-symbol queries. |
| `type_decl` | `src/types/*.d.ts`, `*.d.ts` | Support evidence; should rarely outrank page/utility. |
| `scratch_temp` | `temp/**` | High-noise source-like file; demote unless query asks temp/scratch. |
| `lockfile` | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, `Gemfile.lock` | High-noise dependency evidence. |

Role detection should be path/layout based first, then use symbol/content hints as secondary evidence. Avoid hard-coded feature names such as `qrcode`, `watermark`, or `jsonToEntity`.

### 2. Query Intent Classification

Add a small frontend intent classifier that emits score parts instead of a hard decision.

Suggested intents:

- `frontend_feature_entrypoint`: query contains UI/workflow/tool/page terms, route names, component names, or user actions such as upload, paste, scan, download, sidebar, theme, chat, generate, parse, preview.
- `frontend_utility_implementation`: query contains exact utility symbols, class names, algorithm terms, conversion functions, or path/file hints for `utils/**` or `services/**`.
- `frontend_state`: query contains store/Pinia/state/current tool/theme persistence terms.
- `unknown`: no frontend-specific confidence.

The classifier should be conservative. A single broad token such as `tool` must not force page-first ranking by itself. Confidence should increase when multiple pieces line up, for example:

- A component-like token matches a `.vue` filename.
- Query terms match route path/name/title tokens.
- Query terms match UI actions present in a view template.
- A candidate view imports a service or utility whose path also matches the query.

The classifier may emit more than one intent. Intent scores should be additive evidence, not mutually exclusive labels. Suggested first-pass score ranges:

```text
frontend_feature_entrypoint: 0.00 to 1.00
frontend_utility_implementation: 0.00 to 1.00
frontend_state: 0.00 to 1.00
```

Worked example: `JSON to entity generate Java TypeScript CSharp Python class interface`

- `frontend_feature_entrypoint ~= 0.45`: `generate` and `JSON to entity` describe a user-facing tool workflow, and `JsonToEntity.vue` is a route/view page.
- `frontend_utility_implementation ~= 0.80`: `Java`, `TypeScript`, `CSharp`, `Python`, `class`, and `interface` map directly to implementation functions in `src/utils/jsonToEntity.ts`.
- `frontend_state ~= 0.15`: `stores/tool.ts` has related persisted input/output state, but the query does not ask for Pinia/state behavior.

The expected ordering for this mixed query is utility-first: `src/utils/jsonToEntity.ts` should remain Top1 because the implementation-symbol evidence is stronger than the page-entrypoint evidence. `src/views/json/JsonToEntity.vue` should still appear near it because it is the feature entrypoint that calls the utility. This is different from `QRCode generate scan camera decode paste image qrcode-reader`, where the query describes the full page workflow and the page should be allowed to outrank the utility.

### 3. Feature Cohort Rerank

Add soft score parts that keep a frontend feature cluster together.

Suggested score parts:

- `frontend_entrypoint_boost`: view/layout gets a small boost for feature-entrypoint queries.
- `frontend_support_boost`: service/utility/type/store imported by a top feature entrypoint gets a smaller boost.
- `frontend_type_decl_penalty`: `.d.ts` files lose priority unless query asks declaration/types.
- `scratch_temp_penalty`: `temp/**` files are demoted unless query asks temp/scratch.

The feature cohort signal should be bounded. It should not overcome exact symbol evidence by itself.

Do not implement a broad `frontend_role_mismatch_penalty` in the first pass. "Same feature" is ambiguous without a relation. V1 should infer feature cohesion only from explicit evidence:

- A view/layout imports the support file.
- A route entry points at the view.
- A support file path or symbol matches the same query terms as the view.

If later evidence shows broad stores/utilities still crowd top results, add a narrower `frontend_import_peer_penalty` that applies only when an explicit import edge links the page/layout and support file.

### 4. Lightweight Import/Relation Evidence

Current `program-tool` evidence shows useful edges:

- `WatermarkRemover.vue` imports `@/services/watermarkDetection` and `@/utils/imageUtils`.
- `MqttTool.vue` imports `@/utils/mqttUtils`.
- `QRCodeTool.vue` imports `@/utils/qrcodeUtils`.
- `JsonToEntity.vue` imports `@/utils/jsonToEntity`.
- `AppLayout.vue` imports `@/stores/app`.

The first implementation can use a bounded local readback or lightweight import extraction:

1. Inspect at most 3 view/layout/shared-component files from the current top 10 ranked candidates.
2. Read at most 50KB per inspected file; skip import readback for larger files and emit no penalty for the skip.
3. Extract static imports from `.vue`, `.ts`, `.tsx`, `.js`, and `.jsx`.
4. Resolve `@/` to `src/` and relative paths within the repo.
5. Boost imported files that are already in the candidate pool.
6. Do not recursively chase imports in the first pass.
7. Do not add second-pass candidates in v1; import extraction is a rerank-only signal.

This keeps the behavior deterministic and local while approximating fast-context's controlled exploration.

### 5. Noise Policy Tightening

The existing lockfile demotion is not enough for frontend workflow queries: `package-lock.json` still entered top5 for QR code and JSON/entity queries.

Adjust policy:

- For source-like feature queries, lockfiles should be absent from top5 unless query contains dependency/version/package/lock terms.
- `temp/**` should be a high-noise source role, not equivalent to normal source.
- `.d.ts` files should be support evidence. They can appear in top5 when highly relevant, but should not outrank the page or implementation utility for feature workflow queries.
- Detailed diagnostic penalties should remain separate from the aggregate `penalty`; only the aggregate negative value should feed `_combined_score`.

This follows the existing generic noise design: `retrieval.py::_combined_score` consumes the aggregate `penalty`, while detailed fields such as `lockfile_penalty`, `test_penalty`, and `generated_schema_penalty` stay diagnostic. See `docs/superpowers/specs/2026-06-19-generic-baseline-retrieval-quality-design.md` for the earlier baseline rule.

### 6. Model Bottleneck Experiment

After deterministic role/cohort/noise changes, run a fixed-candidate comparison:

1. Use CST to generate top50 candidates for each `program-tool` query.
2. Ask a configured reranker, local or remote, to order only those top50 paths with short snippets/path metadata.
3. Compare against deterministic CST and fast-context on:
   - Top1 target accuracy.
   - Feature-cohort purity in top5.
   - Noise count in top5.
   - Whether target files were missing from top50.

Interpretation:

- If model rerank fixes ordering while targets were present in top50, the bottleneck is rerank intelligence.
- If target files are absent from top50, the bottleneck is candidate recall or second-pass readback.
- If deterministic role/cohort fixes most cases, the model is not yet the primary bottleneck.

Reranker experiment setup:

- Add an experiment-only runner, not a production query dependency.
- Configure provider/model through a small experiment config or environment variables, and record `provider`, `model`, prompt version, and latency in the output artifact.
- Default local option: reuse the existing query-planner provider shape with Ollama-compatible configuration, for example `provider=ollama`, `model=qwen3.5:4b-mlx`, when available.
- Optional stronger option: use an OpenAI-compatible or Anthropic-compatible HTTP adapter when credentials are available. The spec should not require a paid external model for CI.
- Rate/cost guard: maximum 6 `program-tool` queries, 50 candidates per query, one rerank call per query, no retries by default, and a hard timeout per call.
- Input per candidate: relative path, detected role, project metadata, best chunk line range, first 200 characters of the best chunk, and the best chunk's current score parts.
- Prompt contract:

```text
You are reranking code-search results.
Query: {query}
Return a JSON array of relative file paths ordered by relevance.
Prefer the user-facing feature entrypoint for workflow queries, but prefer utility implementation files when the query asks for concrete conversion functions, algorithms, classes, or APIs.
Demote lockfiles, scratch/temp files, and unrelated feature files unless explicitly requested.
Candidates:
{candidate_json}
```

- Output validation: accept only a JSON array of known candidate paths. If parsing fails, mark the run invalid and do not silently use the model order.

## Success Criteria

- `program_tool` fixture runs under the same real-project smoke framework as existing generic baseline fixtures.
- The six initial `program-tool` queries pass their `expected_top_k`, `preferred_rank`, and noise gates.
- Existing real-project fixtures keep their current preferred-rank distribution.
- No lockfile appears in top5 for the `qrcode-tool` and `json-to-entity` queries.
- `temp/entityToMock.js` does not appear in top5 for `json-to-entity`.
- `watermarkDetection.ts` appears top5 for the watermark query.
- `WatermarkRemover.vue`, `QRCodeTool.vue`, and `AppLayout.vue` can be Top1 for their feature-entrypoint queries.
- `jsonToEntity.ts` remains Top1 for the JSON-to-entity utility-heavy query.
- Score parts explain at least one positive frontend role/cohort reason or one negative noise reason for changed rankings.

## Risks

- Over-boosting pages can hurt utility implementation queries.
- Over-penalizing stores can hurt state-management questions.
- Import readback can become expensive or recursive if not bounded.
- `.d.ts` files are sometimes the right answer for type-definition queries.
- `temp/**` can contain legitimate scripts in some repositories; demote by default, do not hard-skip.
- Fast-context comparisons are useful evidence, but the CST fixture should define product behavior instead of copying fast-context order.
- Frontend role scoring can regress backend or generic fixtures if it applies outside frontend-focused repositories.

## Rollback Strategy

Frontend role scoring should be guarded by frontend repo detection. Enable it only when the repository has strong frontend structure, such as `package.json` plus at least one of `src/views/`, `src/pages/`, `src/components/`, or framework dependencies like Vue/React/Svelte.

If existing backend/generic fixtures regress:

1. Disable frontend score parts for repos that do not pass the frontend-structure guard.
2. If the guard is insufficient, add a temporary config flag such as `retrieval.frontend_role_rerank_enabled` and default it to false until the regression is understood.
3. Keep the `program_tool` fixture in place so rollback is visible as a targeted frontend-quality failure, not a silent deletion of the requirement.

## Design Decisions

- Route metadata extraction: defer to post-v1. V1 should use path-role, query intent, and bounded import-cohort rerank first.
- Frontend role location: create a new `frontend_roles.py` helper for v1 frontend-specific roles, query intent, and import-cohort helpers. Keep `path_roles.py` generic and only use it for broad language-neutral path roles.
- Import readback budget: inspect at most 3 view/component files in top 10, read at most 50KB per file, no recursion, rerank-only.
- Model reranker input: use path, role, project metadata, best line range, first 200 characters of the best chunk, and current score parts.

## Recommended Implementation Order

1. Add `program_tool` fixture and verify it exposes the current failures.
2. Add frontend path-role classification and scratch/temp/type declaration noise policy.
3. Add conservative frontend query intent score parts.
4. Add bounded import-cohort support for already retrieved candidates.
5. Re-run `program-tool` plus existing real-project fixtures.
6. Only then run the fixed-candidate model/reranker experiment.
