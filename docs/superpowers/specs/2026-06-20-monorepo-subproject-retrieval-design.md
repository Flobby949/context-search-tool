# Monorepo Subproject Retrieval Design

Date: 2026-06-20
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`

## Summary

Improve CST retrieval for repositories that contain several independent subprojects under one root, such as a Vue frontend, a Go collector, and a Java backend sharing the same business vocabulary.

The previous generic baseline work reduced template, generated schema, lockfile, docs, and config noise. That does not solve a different failure mode: when a monorepo is indexed from its root, strong Java backend files can outrank Vue or Go files for frontend or collector queries because terms such as `auth`, `fund`, `portfolio`, `position`, and `sse` appear across all subprojects.

This design adds a generic subproject-boundary and scope-aware reranking layer. It should remain deterministic, local, explainable, and language-neutral. It should not add Vue, Go, Gin, Java, Spring, or repo-specific plugins.

## Motivation

Real validation on `/Users/flobby/vibe_coding/Investment-Assistant` showed two different behaviors.

When each subproject is indexed separately, retrieval is already acceptable:

- `frontend`: `src/views/portfolio/index.vue` Top1, `src/api/core/request.ts` Top1, `src/stores/modules/auth.store.ts` Top2, `src/views/chat/composables/useSseConnection.ts` Top4.
- `collector`: `internal/api/handler/collect_handler.go`, `internal/service/fund_service.go`, `internal/source/eastmoney/nav.go`, and `internal/scheduler/scheduler.go` all Top1 with focused queries.
- `investment-assistant-backend`: Java controller/service/MCP/SSE queries mostly Top1, with `JwtAuthenticationFilter` Top3.

When the monorepo root is indexed as one repository, cross-subproject competition dominates:

| Query | Baseline rank | Current rank | Current Top1 | Target |
| --- | ---: | ---: | --- | --- |
| `vue-auth-store` | MISS | MISS | `investment-assistant-backend/.../UserAppService.java` | `frontend/src/stores/modules/auth.store.ts` |
| `vue-portfolio-page` | 9 | MISS | `investment-assistant-backend/.../PortfolioAppService.java` | `frontend/src/views/portfolio/index.vue` |
| `vue-sse-composable` | 7 | 7 | `investment-assistant-backend/.../SseServer.java` | `frontend/src/views/chat/composables/useSseConnection.ts` |
| `go-collect-handler` | MISS | MISS | `investment-assistant-backend/.../FundDataClient.java` | `collector/internal/api/handler/collect_handler.go` |
| `go-fund-service` | 3 | 3 | `investment-assistant-backend/.../FundAppService.java` | `collector/internal/service/fund_service.go` |
| `go-nav-fetcher` | 2 | 2 | `investment-assistant-backend/.../FundController.java` | `collector/internal/source/eastmoney/nav.go` |
| `go-scheduler` | 2 | 2 | `investment-assistant-backend/.../PositionProfitController.java` | `collector/internal/scheduler/scheduler.go` |

Adding project words to the query, such as `frontend` or `collector`, did not consistently fix this. The query pipeline needs to understand subproject boundaries as first-class ranking context, not just as ordinary lexical tokens.

## Goals

- Detect likely subproject units during indexing using generic project markers.
- Attach subproject metadata to files/chunks without requiring an index schema migration.
- Infer a query's likely subproject and language scope from path hints, project names, framework/tool terms, and exact file-like tokens.
- Use scope fit as a soft reranking signal, not as a hard filter.
- Improve root-indexed monorepo results while preserving the current good behavior for separately indexed subprojects.
- Keep Java/Spring plugin boosts and existing generic noise demotion intact.
- Make ranking decisions explainable through `score_parts` and `reasons`.
- Add synthetic and real-project smoke tests so future tuning is measurable.

## Non-Goals

- No Vue plugin.
- No Go or Gin plugin.
- No Java or Spring behavior changes beyond regression protection.
- No LLM query planner dependency.
- No hard-coded `Investment-Assistant` paths, aliases, or query shortcuts.
- No separate physical index per subproject in this milestone.
- No mandatory user configuration for common monorepos.
- No strict filtering that hides cross-subproject architecture results.
- No schema-breaking change to `RetrievalResult`, MCP payloads, formatter payloads, or the SQLite schema.

## Design Principles

### Scope Is A Tie-Breaker, Not A Gate

Subproject scope should help choose between similarly relevant candidates. It should not suppress strong direct evidence from another subproject when the query is intentionally cross-cutting.

### Prefer Generic Markers

Detect project boundaries from standard files and directories such as `package.json`, `go.mod`, `pom.xml`, `build.gradle`, `Cargo.toml`, `pyproject.toml`, `src/main/java`, and frontend `src/` layouts. Do not bake in business names such as `Investment-Assistant`.

### Preserve Single-Project Behavior

If a repository has only one detected project unit, or if the query has no confident scope, the new score parts should be near zero. Single-project results should not churn.

### Explain Every Adjustment

Rerank adjustments should emit score parts such as `project_scope_boost`, `project_language_boost`, `project_path_hint_boost`, and `project_scope_mismatch_penalty`. Output reasons should describe the adjustment in human-readable terms.

## Approaches Considered

### Option A: Tell Users To Index Each Subproject Separately

This works today and is the safest workaround. It avoids ranking ambiguity and keeps implementation trivial.

The downside is poor default behavior. Users often point tools at the repo root, and CST should not require them to know which subdirectory contains the answer before searching.

### Option B: Hard Filter By Explicit Scope Terms

If a query says `frontend`, only return `frontend/**`; if it says `collector`, only return `collector/**`.

This is too brittle. It would hurt cross-project questions such as "frontend portfolio call backend API" or "collector data used by Java service", and it would fail when project names are not obvious.

### Option C: Soft Subproject Scope Reranking

Detect subprojects at index time and infer likely scope at query time. Boost candidates whose project unit and language fit the query, and lightly penalize conflicting project units only when confidence is high.

This is the recommended approach. It fixes root-indexed monorepo confusion without turning CST into a framework-specific plugin system.

## User Experience

The user keeps the same commands:

```text
cst index /Users/flobby/vibe_coding/Investment-Assistant
cst query /Users/flobby/vibe_coding/Investment-Assistant "frontend useAuthStore login register fetchCurrentUser"
cst query /Users/flobby/vibe_coding/Investment-Assistant "collector CollectHandler CollectNav BatchCollectNav gin"
```

Expected behavior after this design:

- Frontend queries can surface Vue/TypeScript files even when Java backend files contain the same business terms.
- Go collector queries can surface `collector/internal/**` files even when Java backend files mention collector APIs.
- Java backend queries keep their current strong results.
- Cross-project queries can still return multiple subprojects when the query has mixed scope.

Markdown output does not need a new section. JSON/MCP payloads should expose the score parts already attached to each result.

Example reasons:

```text
path/symbol match; project scope match; language scope match
```

Example score parts:

```json
{
  "lexical": 0.74,
  "path_symbol": 4.0,
  "project_scope_boost": 0.08,
  "project_language_boost": 0.04
}
```

## Architecture

The retrieval flow remains local and deterministic:

```text
Index
  -> scan files
  -> detect repo project units
  -> annotate source/chunk metadata with nearest project unit
  -> write normal chunks/signals/manifest

Query
  -> tokenize query
  -> infer query project/language scope
  -> collect normal semantic/lexical/path/signal candidates
  -> existing merge/dedupe
  -> existing generic noise score parts
  -> existing Java/Spring rerank adjustments
  -> new project scope score parts consumed by rerank_score
  -> evidence anchor split and formatting
```

The first implementation should avoid a SQLite table migration by storing subproject fields in existing chunk metadata. A later implementation can add typed SQLite tables only if profiling shows metadata lookup is too expensive or if CLI stats need richer project reporting.

Because unchanged files are skipped during incremental indexing, this milestone must add a small project-scope metadata version in index metadata, for example `project_scope_metadata_version = "1"`. If the version is missing or stale, indexing should prepare and rewrite chunks for all active scanned files even when their source SHA is unchanged. This prevents old indexes from silently lacking `project_root`, `project_kind`, and related fields after users upgrade CST.

## Core Data Model

Add a small internal model in a new module, for example `src/context_search_tool/project_scope.py`.

```python
@dataclass(frozen=True)
class ProjectUnit:
    root: Path
    name: str
    kind: str
    languages: tuple[str, ...]
    markers: tuple[str, ...]
    confidence: float
```

Suggested `kind` values:

- `frontend`
- `go`
- `java`
- `rust`
- `python`
- `node`
- `mixed`
- `unknown`

```python
@dataclass(frozen=True)
class QueryScope:
    project_names: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    path_prefixes: tuple[Path, ...] = ()
    confidence: float = 0.0
```

Chunk metadata should use plain JSON-compatible values:

```json
{
  "project_root": "frontend",
  "project_name": "frontend",
  "project_kind": "frontend",
  "project_languages": ["typescript", "vue"],
  "project_markers": ["package.json", "src/main.ts"]
}
```

For a single-project repository, `project_root` can be `""` or `"."`, and scope scoring should have no meaningful effect.

The project metadata must be written onto each `DocumentChunk.metadata`, not only onto `SourceFile.metadata`, because query-time ranking loads chunks directly. In `indexer.py`, the expected shape is to compute project units once, choose the unit for each scanned path, then `replace(...)` each prepared chunk with merged metadata such as `{"language": "...", "project_root": "...", ...}` before storing chunks.

## Project Unit Detection

Detection should run once per index operation after scanning, before chunk preparation.

Marker examples:

| Marker | Suggested kind | Languages |
| --- | --- | --- |
| `package.json` with `vite`, `vue`, `@vitejs/plugin-vue`, or `.vue` files nearby | `frontend` | `typescript`, `vue` |
| `go.mod` | `go` | `go` |
| `pom.xml` | `java` | `java` |
| `build.gradle` or `settings.gradle` | `java` | `java`, `kotlin` |
| `Cargo.toml` | `rust` | `rust` |
| `pyproject.toml` | `python` | `python` |

Boundary rules:

- Prefer the nearest marker ancestor for each file.
- If nested markers exist, choose the deepest marker path.
- Ignore dependency/build directories already skipped by scanner.
- If the repo root has a marker and there are also child markers, keep both but assign files to the deepest matching unit.
- If no marker is found, assign files to the root unit with `kind="unknown"`.

For `Investment-Assistant`, expected units are:

| Root | Kind | Markers |
| --- | --- | --- |
| `frontend` | `frontend` | `package.json`, Vue/Vite files |
| `collector` | `go` | `go.mod` |
| `investment-assistant-backend` | `java` | `pom.xml`, `src/main/java` |
| `searxng` | `unknown` or `config` | config-only directory |
| `document` | `unknown` or `docs` | docs-only directory |

The first implementation can ignore docs/config-only units for positive boosts, while still allowing their files to be retrieved normally when they have direct evidence.

## Query Scope Inference

`infer_query_scope(query, tokens, project_units)` should combine weak signals into a confidence score.

High-confidence signals:

- Exact path prefix token or path-like phrase: `frontend/src`, `collector/internal`, `investment-assistant-backend`.
- Exact filename token: `auth.store.ts`, `collect_handler.go`, `scheduler.go`, `JwtAuthenticationFilter.java`.
- Language or framework term paired with a matching project unit: `vue`, `pinia`, `vite`, `EventSource`, `gin`, `go`, `go.mod`, `maven`, `pom`, `spring`, `java`.

Medium-confidence signals:

- Project directory name token: `frontend`, `collector`, `backend`.
- File extension hints: `.vue`, `.ts`, `.go`, `.java`.
- Common layout hints: `views`, `stores`, `composables`, `internal`, `cmd`, `src/main/java`.

Low-confidence signals:

- Business words such as `auth`, `portfolio`, `fund`, `position`, `sse`, `calendar`.
- Generic architecture words such as `service`, `controller`, `handler`, `repository`.

Business words must not determine project scope by themselves because they appear in several subprojects.

## Scoring Policy

Add project scope score parts inside `_rank_chunks` after candidate merge and after normal candidate score parts are available. The score parts must affect the actual sorted value, not only diagnostics.

For the first implementation, consume project scope parts as a rerank-only adjustment in `_rerank_score`, after the normalized combined score and before final sorting. Do not also add the same values to `_combined_score` in the same milestone; otherwise the adjustment is easy to double-count. If a later implementation moves these fields into `_combined_score`, it should remove the rerank-only addition in the same change.

Suggested initial values:

| Condition | Score part | Value |
| --- | --- | ---: |
| Candidate project root matches high-confidence query prefix | `project_scope_boost` | `+0.10` |
| Candidate kind matches inferred query kind | `project_kind_boost` | `+0.06` |
| Candidate language matches inferred query language | `project_language_boost` | `+0.04` |
| Candidate path stem or filename matches explicit file-like query token | `project_path_hint_boost` | `+0.08` |
| Candidate project conflicts with high-confidence query scope | `project_scope_mismatch_penalty` | `-0.06` |

Guardrails:

- Do not apply mismatch penalties when query confidence is below `0.60`.
- Do not apply mismatch penalties for docs/evidence anchors.
- Do not let project scope boosts exceed strong direct evidence from lexical/path/symbol matches.
- Do not reduce Java/Spring path graph boosts.
- Do not apply scope boosts when only one project unit exists.
- If a query has mixed scope, for example `frontend portfolio backend API`, allow both matching units to receive boosts and avoid mismatch penalties.

This is deliberately conservative. The target is to lift scoped subproject files into the top window, not to rewrite the whole ranking system.

Candidate-pool guardrail: reranking can only help files that are already candidates. For every synthetic and real smoke failure converted into a passing assertion, record whether the expected target was present before project-scope rerank. If the target is missing from the pre-rerank candidate pool, fix recall with generic scoped candidate seeding, such as path-symbol/direct-text probes derived from high-confidence path, filename, extension, or project-root hints. Do not inflate project scope score constants to compensate for a missing candidate.

## Fixture And Test Design

### Synthetic Monorepo Fixture

Create a small fixture under `tests/fixtures/monorepo_scope/` with three subprojects:

```text
frontend/
  package.json
  src/stores/modules/auth.store.ts
  src/views/portfolio/index.vue
collector/
  go.mod
  internal/api/handler/collect_handler.go
  internal/scheduler/scheduler.go
investment-assistant-backend/
  pom.xml
  src/main/java/com/example/AuthController.java
  src/main/java/com/example/PortfolioAppService.java
```

The fixture should intentionally repeat business words across projects so tests prove subproject scope is the differentiator.

Required synthetic assertions:

- `frontend useAuthStore login register fetchCurrentUser Pinia` puts `frontend/src/stores/modules/auth.store.ts` in Top5.
- `frontend portfolio index.vue fetchPortfolios fetchPositions` puts `frontend/src/views/portfolio/index.vue` in Top5.
- `collector CollectHandler CollectNav BatchCollectNav gin` puts `collector/internal/api/handler/collect_handler.go` in Top5.
- `collector scheduler.go type Scheduler AddTask heartbeat cron` puts `collector/internal/scheduler/scheduler.go` in Top5.
- `AuthController login register UserAppService` keeps the Java controller/service in Top5.
- Unscoped `portfolio service` can return backend or frontend results; the test should not overconstrain ambiguous queries.

### Real Project Smoke

Extend the generic smoke fixture mechanism with an optional monorepo case:

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

The smoke should copy the repo to a temp directory before indexing, as the existing real-project quality harness does.

When adding this fixture, also update the fixture-shape test in `tests/test_generic_baseline_quality.py` so the allowed `repo_key` set includes `investment_assistant`.

### Unit Tests

Add focused tests for:

- Marker detection chooses deepest project unit.
- Files without a marker fall back to root unit.
- Chunk metadata receives project fields; source-file metadata alone is not sufficient.
- Existing unchanged indexes are rewritten when `project_scope_metadata_version` is missing or stale.
- Query scope inference ignores business words when no project/language/path hints exist.
- Query scope inference recognizes `frontend`, `collector`, `.go`, `.vue`, `.java`, `package.json`, `go.mod`, and `pom.xml`.
- Scope score parts are zero for single-project repositories.
- Mismatch penalty is disabled for low-confidence scopes.
- Project scope score parts change `rerank_score`; they are not diagnostics-only fields.
- Expected synthetic and smoke targets are present in the candidate pool before project-scope rerank, or generic scoped candidate seeding is covered by tests.
- Existing generic noise tests still pass.
- Existing Java/Spring rerank tests still pass.

## Implementation Boundaries

Likely files:

- Create: `src/context_search_tool/project_scope.py`
  - `ProjectUnit`, `QueryScope`, marker detection, query inference, score-part helper.
- Modify: `src/context_search_tool/indexer.py`
  - Detect project units once, attach metadata to chunks during file/chunk preparation, and force a chunk rewrite when project-scope metadata version is stale.
- Modify: `src/context_search_tool/retrieval.py`
  - Add project scope score parts to the existing rerank path and consume them in `rerank_score`.
- Modify: `src/context_search_tool/models.py`
  - Only if a typed helper is needed. Prefer keeping new dataclasses in `project_scope.py`.
- Modify: `tests/test_retrieval_pipeline.py`
  - Synthetic monorepo ranking tests.
- Create: `tests/test_project_scope.py`
  - Unit tests for marker detection and query scope inference.
- Modify: `tests/fixtures/generic_baseline_quality/queries.json`
  - Optional real-project `Investment-Assistant` smoke case.
- Modify: `tests/test_generic_baseline_quality.py`
  - Allow the new `investment_assistant` repo key and keep fixture-shape validation green.
- Modify: `README.md`
  - Short note that monorepo root indexing uses subproject-aware reranking and that indexing subprojects separately remains a valid workaround.

Do not touch CLI argument shape, MCP tool schema, or formatter output shape unless a test proves score parts are being dropped.

## Acceptance Criteria

Run:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_project_scope.py tests/test_retrieval_pipeline.py -q
```

Expected:

- All new unit and synthetic retrieval tests pass.
- New project scope score parts are visible in `score_parts`, represented in `reasons`, and reflected in `rerank_score`.
- Tests prove stale indexes without project-scope metadata are rewritten or invalidated before querying.
- Tests distinguish "target was in candidate pool but ranked too low" from "target was absent from candidate pool".

Run existing focused regressions:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py tests/test_tokenizer_scanner.py tests/test_rerank_soft_sorting.py -q
```

Expected:

- Existing generic baseline, scanner, and rerank tests pass.

Run full suite:

```bash
/opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest -q
```

Expected:

- Full suite passes with the same skipped-test profile as the current branch unless unrelated environment-dependent tests are skipped.

Run real monorepo smoke when the repo is available:

```bash
CST_SMOKE_INVESTMENT_ASSISTANT_REPO=/Users/flobby/vibe_coding/Investment-Assistant /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
```

Expected:

- `Investment-Assistant` root-indexed smoke queries pass.
- `imagebed` and `env-change` smoke queries still pass.

## Risks And Mitigations

### Risk: Scope Boost Overfits To Directory Names

Mitigation: require multiple weak signals or one strong path/file signal before applying mismatch penalties. Keep boosts small.

### Risk: Cross-Project Questions Get Worse

Mitigation: allow mixed scopes and avoid hard filters. Add one synthetic ambiguous query that is intentionally not overconstrained.

### Risk: Java Results Regress

Mitigation: run existing Java/Spring regression tests and keep Spring path graph score parts stronger than project scope boosts.

### Risk: Metadata-Only Storage Becomes Hard To Inspect

Mitigation: start with chunk metadata for no migration. Add stats/profile display later only if needed.

### Risk: Old Indexes Keep Missing Project Metadata

Mitigation: version the project-scope metadata in index metadata and force chunk rewrites when that version is absent or stale.

### Risk: Score Parts Are Diagnostic But Do Not Affect Sorting

Mitigation: make project scope score parts an explicit rerank-score input and test that `rerank_score` changes when the scope fit changes.

### Risk: Rerank Cannot Rescue Missing Candidates

Mitigation: add candidate-pool diagnostics for the failing smoke queries. If expected files are absent before rerank, add generic scoped candidate seeding instead of increasing scope boost constants.

### Risk: Detection Mistakes In Nonstandard Repos

Mitigation: root fallback and low/no scoring when confidence is low. Users can still index subprojects separately.

## Open Questions

- Should `document/` and config-only directories become explicit project units or remain root/unknown in the first implementation?
- Should project scope score parts be configurable in `config.toml`, or stay internal until the first real-project regression set stabilizes?
- Should `cst stats` show detected project units in this milestone, or should that wait until after ranking behavior is proven?

Recommended first implementation choices:

- Treat docs/config-only directories as `unknown` with no positive boost.
- Keep score constants internal for the first milestone.
- Defer `cst stats` project-unit reporting until ranking acceptance tests pass.
