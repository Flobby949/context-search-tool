# P0 Quality Control Loop Closure Design

Date: 2026-07-11
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`
Predecessor design: `docs/superpowers/specs/2026-07-08-retrieval-quality-scoring-system-design.md`

## Summary

Close Phase 0 of the fast-context-like retrieval roadmap by turning the existing
quality framework and scattered legacy fixtures into one repeatable quality
control loop.

The quality package itself already exists. It can load v1 fixtures, copy and
index repositories safely, evaluate retrieval results, write JSON and Markdown
reports, compare reports, and summarize MCP feedback. The remaining gap is not
another framework rewrite. The remaining gap is operational completeness:

- the canonical quality fixture currently contains one frontend query;
- 22 generic/frontend cases, 8 Java/Spring calibration cases, and 3 embedding
  A/B cases still live in three legacy fixture shapes;
- local planner smoke cases created after the quality branch diverged are not in
  the unified runner;
- reports do not record every repository's effective planner and embedding
  configuration;
- comparison output classifies regressions but does not expose the metric deltas
  used to make the decision;
- the repository does not document one standard Phase 0 run-and-compare
  workflow.

This closure milestone creates one canonical case catalog, selects work through
named profiles, preserves the old quality coverage during migration, and makes
the comparison command suitable as a development gate. It does not change
retrieval ranking.

## Decision

Use one canonical v1 quality catalog with optional profile-level configuration
and case-level profile selection.

The alternatives were rejected for these reasons:

- Reading legacy fixtures directly would permanently retain incompatible
  schemas and duplicated assertion logic.
- Creating unrelated CI, smoke, planner, and A/B fixture files would improve
  organization but would not create one source of truth.
- A canonical catalog with a profile configuration matrix keeps case identity,
  query text, expectations, tags, and known gaps in one place while allowing
  the same cases to run under different environments and model configurations.

## Current State

The following parts are implemented and remain the foundation:

- `context_search_tool.quality.cases` defines the v1 fixture schema and legacy
  case adapters.
- `context_search_tool.quality.metrics` emits Hit@K, Recall@K, MRR, expected
  coverage, noise counts, entrypoint rank, cross-language success, and latency.
- `context_search_tool.quality.runner` copies source repositories into temporary
  workspaces before indexing.
- `context_search_tool.quality.reports` writes stable JSON data and readable
  Markdown summaries.
- `context_search_tool.quality.compare` compares two reports and classifies case
  outcomes.
- `context_search_tool.quality.feedback` summarizes MCP feedback without
  exposing query text by default.
- `cst quality run`, `compare`, and `feedback` expose the workflow through the
  CLI.

The legacy case inventory is:

| source | cases | primary coverage |
| --- | ---: | --- |
| `generic_baseline_quality/queries.json` | 22 | Go, Rust/Tauri, TypeScript/Vue, Java, monorepo scope, noise |
| `retrieval_calibration/queries.json` | 8 | Java/Spring and Chinese business queries |
| `ab_comparison/queries.json` | 3 | hash/BGE comparison and Chinese semantic queries |
| total | 33 | existing legacy baseline |

The canonical catalog also needs three `psf/requests` planner smoke cases that
were specified after the first quality implementation. A committed Java/Spring
snapshot case will provide a deterministic CI gate for Java and Chinese query
coverage. These additions make the final catalog larger than the 33-case legacy
inventory without duplicating any legacy case.

## Goals

- Make one catalog the source of truth for all existing retrieval-quality
  queries and expectations.
- Preserve the 33 legacy cases and their intent during migration.
- Keep deterministic CI checks local, hash-based, planner-free, and backed by
  committed snapshots.
- Keep real-repository, BGE, and Ollama runs available through explicit
  non-CI profiles.
- Record the exact effective configuration for every repository run.
- Report useful metric aggregates and baseline/candidate deltas.
- Make regressions produce a non-zero CLI result by default.
- Document one repeatable workflow for CI, real-repository smoke, planner smoke,
  embedding A/B, comparison, and MCP feedback analysis.
- Add an explicit Phase 0 acceptance test and update the roadmap when it passes.

## Non-Goals

- No retrieval score, weight, candidate, relation, or ranking changes.
- No ContextPack, RetrievalTrace, controlled exploration, or retrieval-core
  decomposition.
- No new embedding provider or query planner provider.
- No required network or model dependency in CI.
- No GitHub Actions workflow in a repository that does not currently have CI
  workflow infrastructure.
- No committed generated quality reports containing timestamps or local paths.
- No automatic branch checkout or baseline-branch execution inside the quality
  CLI.
- No automatic tuning based on quality metrics.

## Canonical Catalog

The canonical source remains:

```text
tests/fixtures/retrieval_quality/queries.json
```

It remains schema version 1. New fields are optional, so existing v1 fixtures
continue to load.

### Profile Configuration

Add optional `profile_configs` at the fixture root:

```json
{
  "schema_version": 1,
  "profile_configs": {
    "ci": {
      "embedding": {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384
      },
      "query_planner": {
        "enabled": false
      }
    },
    "smoke": {
      "embedding": {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384
      },
      "query_planner": {
        "enabled": false
      }
    },
    "planner": {
      "embedding": {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384
      },
      "query_planner": {
        "enabled": true,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "timeout_seconds": 30
      }
    },
    "ab_hash": {
      "embedding": {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384
      },
      "query_planner": {
        "enabled": false
      }
    },
    "calibration_bge": {
      "embedding": {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024
      },
      "query_planner": {
        "enabled": false
      }
    },
    "ab_bge": {
      "embedding": {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024
      },
      "query_planner": {
        "enabled": false
      }
    }
  },
  "repos": []
}
```

Configuration precedence is deterministic:

```text
DEFAULT_CONFIG
  -> repository default_config
  -> selected profile config
```

The selected profile owns embedding and planner behavior. Applying it last means
a repository default cannot silently turn `calibration_bge` back into hash,
disable the `planner` profile, or enable a model in `ci`. Repository defaults
remain useful for repository-specific index and retrieval limits.

Every canonical profile has an explicit `profile_configs` entry, including
profiles whose configuration would otherwise be empty. When `profile_configs`
is present, it is the profile registry: repository and case profiles must refer
to its keys, and the selected profile must exist in it. For backward
compatibility, an older v1 fixture without `profile_configs` derives its known
profiles from the union of repository `profiles` and applies an empty profile
configuration.

Validate final invariants for every canonical profile:

- `ci`, `smoke`, and `ab_hash` use hash embeddings and a disabled planner;
- `planner` uses hash embeddings and an enabled Ollama planner;
- `calibration_bge` and `ab_bge` use BGE M3 with a disabled planner.

### Repository And Case Profile Selection

Repository `profiles` continue to state where a repository is available. Add an
optional `profiles` field to each case. If a case omits it, it inherits the
repository profiles.

```json
{
  "id": "workbench-audit-localized-cjk",
  "query": "工作台统计 待我审核",
  "profiles": ["ci"],
  "tags": ["java_spring", "localized_cjk", "entrypoint"],
  "gate": "required",
  "expected_top_k": [
    {
      "path": "src/main/java/com/example/audit/ApplyAuditController.java",
      "top_k": 3
    }
  ],
  "preferred_rank": [
    {
      "path": "src/main/java/com/example/audit/ApplyAuditController.java",
      "top_k": 3,
      "max_rank": 3,
      "role": "entrypoint"
    }
  ]
}
```

The loader rejects:

- an unknown selected profile;
- a case profile not declared by its repository;
- duplicate repository keys;
- duplicate case IDs within a repository;
- an empty profile configuration name;
- malformed configuration section names or values.

This localized-CJK case is intentionally not tagged `cross_language`: its
target contains Chinese comments. Genuine cross-language cases use Chinese
queries whose expected source files contain only English identifiers and
English source text. They run under `planner` or `calibration_bge`, not under
deterministic hash-only CI.

### Source Resolution

Source selection depends on profile purpose:

- `ci` requires `snapshot_path` and never resolves an external repository.
- Other profiles try `path_env`, then
  `CST_SMOKE_REPOS_DIR / repo_dir_name`, then `snapshot_path`. A candidate is
  selected only when it exists and is a directory; a configured but missing
  external path does not block snapshot fallback.
- Every resolved source is copied before indexing.
- An unavailable non-CI source produces explicit skipped case records.
- A CI snapshot that is absent is an error, not a skip.

This order lets one repository definition use a small committed snapshot in CI
and the full real repository during local smoke runs.

## Profiles

### `ci`

Purpose: fast deterministic protection on every local verification run.

- Hash embeddings only.
- Query planner disabled.
- Committed snapshots only.
- Includes the existing `program_tool` frontend snapshot.
- Includes `java-spring-mini` with at least one Java/Spring entrypoint case and
  one localized-CJK lexical case.
- Includes representative noise and exact-identifier gates.
- Must execute at least one case; an all-skipped run is an error.

### `smoke`

Purpose: exercise the complete legacy generic case inventory against real
repositories.

- Resolves the four generic repositories through environment variables or
  `CST_SMOKE_REPOS_DIR`.
- Uses deterministic hash embeddings and keeps the planner disabled unless a
  repository explicitly belongs to another profile.
- Contains all 22 generic cases.
- Missing repositories are reported as skipped, not silently omitted.

### `calibration_bge`

Purpose: preserve the existing Java/Spring BGE calibration semantics.

- Resolves the two Java calibration repositories through
  `CST_CALIBRATION_OPERATION_CLIENT_REPO` and
  `CST_CALIBRATION_CONSOLE_IOT_REPO`. These replace the legacy
  `--calibration-operation-client-repo` and
  `--calibration-console-iot-repo` pytest-only inputs in the canonical CLI
  workflow.
- Uses BGE M3 with 1024 dimensions and keeps the planner disabled.
- Contains all 8 Java/Spring calibration cases, including Chinese business
  queries.
- Is optional outside dedicated evaluation because it requires the configured
  local BGE service.

### `planner`

Purpose: validate repository-aware natural-language planning with a real local
model.

- Uses the real `psf/requests` checkout resolved by
  `CST_PLANNER_REQUESTS_REPO` or `CST_SMOKE_REPOS_DIR / requests`.
- Enables the configured local Ollama planner.
- Includes cookie/session, retry/proxy/pool, and streamed-response cases.
- Includes a committed English-only dashboard snapshot queried with
  `数据看板统计图表功能`; this is the deterministic fixture shape for genuine
  Chinese-to-English-code measurement, although executing the real planner is
  still a non-CI check.
- Records planner configuration and repository identity in the report.
- Records safe per-case planner diagnostics: status, rewritten queries,
  keywords, symbol hints, discarded hints, prompt version/hash, latency, and
  repo-profile hash. It never records prompts or source content.
- Is never required by CI.

The snapshot lives at
`tests/fixtures/real_projects/cross_language_dashboard/` and contains only
English identifiers, strings, and comments. Its canonical repository key is
`cross_language_dashboard`; its case ID is `dashboard-cross-language`; its
required targets include `DashboardController.java` and either
`StatisticsService.java` or `ChartService.java` within Top 5. A fixture test
scans every source file and rejects CJK text, so the case cannot regress into a
localized lexical match.

### `ab_hash` And `ab_bge`

Purpose: run the same informational semantic cases under two embedding
configurations.

- Uses one small committed A/B snapshot containing relevant and noise files for
  the three existing A/B queries. `CST_QUALITY_AB_REPO` may select a suitable
  real repository instead; a missing external path falls back to the snapshot.
- Uses stable case keys in both profiles so the reports compare directly.
- `ab_hash` runs locally without a model.
- `ab_bge` requires the existing BGE provider setup and is optional outside
  dedicated evaluation.
- Profile and embedding differences remain visible as metadata warnings because
  they are intentional inputs to this comparison.

The A/B snapshot lives at `tests/fixtures/real_projects/embedding_ab/` and uses
canonical repository key `embedding_ab`.

## Planner Diagnostic Acceptance

Retrieval-path assertions alone cannot prove that repository-aware planning is
working: ordinary retrieval can find the expected file after the planner falls
back or emits unrelated hints. Keep planner acceptance specialized instead of
adding planner-specific assertions to every generic quality case.

Add a focused planner quality test that loads the canonical `planner` cases,
runs `query_repository()`, and inspects both results and `bundle.planner`. For
the `psf/requests` cases it requires:

- `planner.status == "ok"` rather than `fallback`;
- a non-empty `repo_profile_hash`;
- consumed `rewritten_queries`, `grep_keywords`, and `symbol_hints` do not
  contain `Spring`, `RestTemplate`, `HttpSession`, or `RestController` under
  Unicode case-insensitive comparison;
- unsupported terms may appear in `discarded_hints`, which proves they were
  rejected before retrieval consumed them;
- all three canonical requests cases satisfy their required Top-5 path gates;
- the cookie/session case returns `sessions.py` or `cookies.py` in Top 5.

The earlier planner notes refer to 3/6 and 5/6 ad hoc smoke counts, while the
specified canonical requests fixture contains three cases. This design replaces
that ambiguous denominator with an explicit 3/3 canonical path gate plus the
planner-diagnostic assertions above. The acceptance record reports both the
3/3 path result and planner diagnostic status.

Dependency-free tests use a fake planner and real `QueryBundle` diagnostics to
verify wiring. The real-model smoke uses local Ollama and a real `psf/requests`
checkout when available; if unavailable, its status is reported as
`unverified`, not `passed`.

## A/B Case Semantics

The legacy A/B fixture records path keywords rather than exact files. Preserve
its measurement intent without making those terms hard pass/fail gates.

Add optional informational measurement fields to `QualityCase`:

```json
{
  "metric_k": 12,
  "relevance_matchers": [
    {"contains": "whitelist"},
    {"contains": "blacklist"}
  ],
  "noise_matchers": [
    {"contains": "region"},
    {"contains": "announcement"}
  ]
}
```

These fields affect metrics only. They do not add failures. The migrated A/B
cases use `gate: informational` and emit:

- `precision_at_12`;
- `mrr` using the first relevance match;
- `noise_top12`;
- result count and latency.

Normal required cases continue to derive relevance from `expected_top_k` and
`expected_any_top_k`. Informational measurement fields do not change their gate
behavior.

Metric-only matching preserves the legacy A/B formulas exactly:

- match `contains` values against normalized repository-relative paths using
  Unicode `casefold()` on both values;
- deduplicate result paths before measurement;
- count a result path once even when it matches multiple relevance terms;
- calculate Precision@K as relevant result paths in the first K divided by the
  fixed configured K, even when fewer than K results are returned;
- calculate MRR from the first relevant unique result path;
- calculate noise@K as unique result paths in the first K matching any noise
  matcher.

Gate matchers keep their existing case-sensitive behavior. The case-insensitive
rule applies only to `relevance_matchers` and `noise_matchers`, so migration does
not silently change required path assertions.

## Legacy Migration

Migration uses one source-of-truth transition rather than copying data and
leaving both copies active.

1. Add catalog support and parity helpers while the legacy JSON files remain.
2. Convert all 33 legacy cases to canonical entries with stable IDs, tags,
   profiles, gates, and expectations.
3. Add tests that compare legacy query text and expectation meaning with the
   canonical cases.
4. Change surviving specialized tests to load canonical cases through the
   shared quality loader.
5. Remove the three legacy query JSON files only after parity tests pass.
6. Keep specialized assertions that the shared runner does not replace, such as
   candidate-pool diagnostics, but keep their query definitions in the canonical
   catalog.

Every migrated case stores canonical provenance:

```json
{
  "legacy": {
    "fixture": "generic_baseline_quality",
    "key": "program_tool/qrcode-tool"
  }
}
```

The durable 33-case mapping is:

| legacy fixture | repository | canonical case IDs |
| --- | --- | --- |
| generic baseline | `imagebed` | `go-upload-handler`, `go-auth-middleware`, `go-storage-implementations`, `go-delete-handler`, `go-route-registration` |
| generic baseline | `env_change` | `tauri-commands`, `engine-apply-restore`, `frontend-invoke`, `settings-persistence` |
| generic baseline | `investment_assistant` | `frontend-auth-store`, `collector-handler`, `frontend-sse-composable`, `collector-fund-service`, `collector-nav-fetcher`, `collector-scheduler`, `java-ai-sse-controller` |
| generic baseline | `program_tool` | `watermark-remover`, `mqtt-tool`, `qrcode-tool`, `json-to-entity`, `app-layout-theme`, `ai-chat` |
| retrieval calibration | `operation_client` | `operation-client-auth-login-register`, `operation-client-station-device-list`, `operation-client-feedback-sms` |
| retrieval calibration | `console_iot` | `console-iot-equipment-list`, `console-iot-access-control`, `console-iot-device-status`, `console-iot-alarm`, `console-iot-user-auth` |
| embedding A/B | `embedding_ab` | `embedding-ab-access-validation`, `embedding-ab-whitelist-management`, `embedding-ab-order-cancel` |

The existing canonical `program_tool_snapshot/qrcode-entrypoint` query is the
same query as legacy `program_tool/qrcode-tool`. Migration keeps the canonical
ID `program_tool/qrcode-tool`, enriches it with the `entrypoint` role, and
removes `qrcode-entrypoint`; it does not create a 34th legacy case.

Parity tests read both old and new fixtures during migration. After old JSON is
deleted, inventory tests assert that canonical `legacy.fixture` and
`legacy.key` pairs are unique and that their source counts remain exactly
22/8/3. Git history preserves the removed raw fixtures; the canonical
provenance fields preserve the live mapping without a second case catalog.

Known gaps remain visible without weakening existing gates. A legacy
`known_gap` string becomes `known_gap_reason`; it does not change a required
case into `gate: known_gap`. The report and Markdown renderer list every
non-empty known-gap reason independently of pass/fail status. Only a case that
was already non-gating uses `gate: known_gap` or `gate: informational`.

## Effective Configuration Reporting

Fixture schema remains v1, but quality report schema advances from v1 to v2
because effective config, typed aggregates, planner diagnostics, safe source
locators, and gate-aware comparison change the report contract. The comparison
reader accepts v1 and v2 reports, emits a schema warning for mixed versions, and
uses available v1 fields without inventing missing metadata. New reports and
comparison outputs always write schema v2.

Each repository report records the configuration actually used for indexing and
querying:

```json
{
  "repo_key": "psf_requests",
  "config": {
    "config_hash": "sha256:...",
    "index": {},
    "embedding": {},
    "retrieval": {},
    "query_planner": {}
  },
  "source": {
    "type": "path_env",
    "locator": "CST_PLANNER_REQUESTS_REPO",
    "git_commit": "...",
    "content_hash": "sha256:..."
  },
  "workspace": {
    "copied": true,
    "preserved": false
  }
}
```

The top-level report keeps the selected profile configuration for backward
compatibility. New comparison logic uses repository-level effective
configuration when available.

The config hash covers all four `ToolConfig` sections shown above. Source
metadata records the locator type and safe locator name: a repository-relative
snapshot path, an environment-variable name, or the literal
`CST_SMOKE_REPOS_DIR` plus `repo_dir_name`. It does not record the resolved
absolute source path or any environment-variable value. Temporary workspace
paths are omitted unless `keep_workspace` is explicitly enabled, in which case
the preserved debug path is marked as local-only.

No planner prompt, source snippet, API key, resolved absolute source path, or
environment-variable value is written into a normal report.

## Metrics And Aggregation

Keep existing metrics and add the measurements required by migrated A/B cases.

Per-case metrics include:

- Hit@1, Hit@3, Hit@5, Hit@10;
- Recall@5 and Recall@10;
- MRR;
- expected coverage in Top 5;
- entrypoint rank;
- noise in Top 5 and Top 10;
- cross-language success;
- latency, result count, and top score;
- optional Precision@K and noise@K for informational measurement cases.

Report aggregates include:

- status counts, including a separate informational count;
- selected, attempted, executed, error, and skipped counts;
- typed metric summaries overall and grouped by repository, tag, profile, and
  embedding provider/model.

`executed` means a case produced a `QueryBundle` and an evaluation with status
`pass`, `fail`, `known_gap`, or `informational`. A query exception is `error`,
not executed. Each aggregate metric records its own denominator because cases
may legitimately emit `null`.

Aggregation rules are explicit:

- Boolean Hit@K and `cross_language_success` become
  `{successes, total, rate}`; `null` is excluded from `total`.
- `entrypoint_rank` becomes `entrypoint_top1` and `entrypoint_top3`, each with
  `{successes, total, rate}` over cases that declare an entrypoint.
- Numeric scalars such as Recall@K, MRR, result count, top score, precision, and
  noise count emit `{count, mean}`.
- Latency emits `{count, mean, p50, p95}` using the deterministic nearest-rank
  percentile over sorted integer milliseconds.
- Nested expected coverage contributes its `ratio` under the flattened metric
  name `expected_coverage_top5_ratio`; the nested count is not averaged.
- Python booleans are never accepted by the numeric-scalar aggregator.

Known-gap and informational cases remain in metric summaries but retain their
own status and gate. Reports list every non-empty `known_gap_reason` independently
of status so a passing required case can still document an unresolved quality
gap.

## Comparison Output

Every matched case contains its baseline status, candidate status, and metric
changes:

```json
{
  "case_key": "program_tool/qrcode-tool",
  "classification": "unchanged_pass",
  "metric_deltas": {
    "mrr": {
      "baseline": 0.5,
      "candidate": 1.0,
      "delta": 0.5
    },
    "latency_ms": {
      "baseline": 20,
      "candidate": 24,
      "delta": 4
    }
  }
}
```

The aggregate comparison contains compatible baseline, candidate, and delta
values overall and by repository, tag, profile, and embedding provider/model.
For success-rate metrics, delta means candidate rate minus baseline rate. For
numeric means and latency percentiles, delta means candidate value minus
baseline value. The Markdown comparison shows gating regressions first,
non-gating observed declines second, then metric changes and metadata warnings.

Comparison first separates gating from observation:

- Only `gate: required` can create a gating regression or improvement.
- Required baseline `pass -> fail/error/skipped` is a gating regression.
- Removing a required baseline case is `removed_required` and is a gating
  regression.
- A required case with no comparable candidate result is
  `incomparable_required` and is a gating regression.
- Required `fail/error -> pass` is an improvement.
- For required comparable cases, loss of Hit@5, an MRR drop greater than 0.25,
  or two or more additional noise results in Top 5 is a gating regression.
- Latency above 150% of a non-zero baseline is a warning, not a functional
  regression.
- Known-gap and informational cases can be classified `metric_improvement`,
  `metric_decline`, or `unchanged_observation`, but never increment the gating
  regression count.
- Removing or skipping a non-required case is an observed coverage change, not
  a gating regression.

The compare aggregate exposes `gating_regressions`, `improvements`,
`observed_declines`, `removed_required`, and `incomparable_required` separately.
The compare command exits non-zero only when gating regressions exist by default.
An explicit `--allow-regressions` flag permits exploratory comparison without
changing classifications. There is no strict-informational mode in this
milestone.

## CLI Behavior

The standard commands are:

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output .quality/ci.json \
  --markdown .quality/ci.md

cst quality compare \
  --baseline .quality/main.json \
  --candidate .quality/branch.json \
  --output .quality/comparison.json \
  --markdown .quality/comparison.md

cst quality feedback .context-search/mcp_calls.jsonl \
  --output .quality/feedback.json
```

CLI output paths create missing parent directories. `.quality/` is ignored by
Git.

`quality run` exits non-zero when:

- a required case fails;
- a case errors;
- the selected profile is unknown;
- no cases are selected;
- no cases execute successfully and `--allow-empty` was not provided.

Skipped real repositories remain visible in reports. The CLI cannot print a
green result for a completely skipped smoke run unless the user explicitly asks
for `--allow-empty`.

## Documentation

Add `docs/retrieval-quality.md` as the operational guide and link it from the
README. It documents:

- environment variables for real repositories;
- each profile and its dependencies;
- producing baseline and candidate reports from separate worktrees or commits;
- interpreting regressions, warnings, known gaps, and skips;
- running planner and embedding model profiles;
- MCP feedback privacy defaults;
- the fact that generated `.quality/` artifacts are local and untracked.

The roadmap records Phase 0 as complete only after the acceptance commands pass
and links to this operational guide. The next-stage pointer then moves to a
Phase 1 Query Understanding acceptance review. ContextPack v1 starts after that
review confirms the Phase 1 success signals or identifies and closes its
remaining gaps.

The guide names every external source variable:

- existing generic variables such as `CST_SMOKE_IMAGEBED_REPO`,
  `CST_SMOKE_ENV_CHANGE_REPO`, `CST_SMOKE_INVESTMENT_ASSISTANT_REPO`, and
  `CST_SMOKE_PROGRAM_TOOL_REPO`;
- `CST_CALIBRATION_OPERATION_CLIENT_REPO`;
- `CST_CALIBRATION_CONSOLE_IOT_REPO`;
- `CST_PLANNER_REQUESTS_REPO`;
- `CST_QUALITY_AB_REPO`;
- shared fallback root `CST_SMOKE_REPOS_DIR`.

## Phase 0 Traceability

| roadmap requirement | canonical evidence | verification |
| --- | --- | --- |
| Unify real-project fixtures and calibration | one catalog with 22 generic and 8 calibration provenance records | legacy parity and 22/8 inventory tests; `smoke` and `calibration_bge` selection |
| Unify A/B comparison | three informational cases shared by `ab_hash` and `ab_bge` | exact legacy metric-formula tests and report comparison |
| Include MCP feedback | existing privacy-preserving `quality feedback` command in the operational guide | feedback CLI tests with query terms disabled by default |
| Track Recall, MRR, entrypoint, noise, cross-language, and latency | typed per-case and aggregate metric contracts | metric tests including success rates, Top1/Top3, and p50/p95 |
| Keep Java/Spring coverage | committed Java snapshot plus eight BGE calibration cases | CI Java case and `calibration_bge` profile wiring |
| Keep generic-language coverage | 22 cases over four repositories | smoke inventory and at least one real-repository acceptance run |
| Keep frontend workflows | six `program_tool` cases including entrypoints and noise | committed snapshot CI and full smoke profile |
| Keep genuine Chinese-to-English cases | English-only dashboard target; calibration cases receive the tag only after the same target-text audit | planner/BGE profile cases; status reported as verified or unverified, never inferred from localized comments |
| Standard branch comparison | documented `quality run` and `quality compare` commands | CI self-comparison plus CLI regression-exit tests |
| Judge ranking changes by deltas | per-case and grouped baseline/candidate/delta output | comparison JSON/Markdown tests |
| Preserve known fast-context gaps | `known_gap_reason` independent of gate status | report and Markdown known-gap tests |

Phase 0 requires the measurement case and workflow for genuine cross-language
retrieval. It does not claim the Phase 1 cross-language success signal merely
because the case exists. A real planner/BGE result is marked `verified` only
after that profile actually runs against an English-only target.

## Testing Strategy

### Schema Tests

- Parse optional profile configurations and case profiles.
- Preserve existing v1 fixtures without the new fields.
- Require explicit registry entries for canonical profiles; derive profiles for
  legacy v1 fixtures without a registry.
- Reject unknown profiles, duplicates, invalid inheritance, and profile
  invariant violations.
- Parse informational A/B matchers and metric K.
- Parse and validate canonical legacy provenance.

### Runner Tests

- Apply configuration precedence in the documented order.
- Record each repository's effective config.
- Prefer external repositories for non-CI profiles and snapshots for CI.
- Fall back after a missing `path_env` or missing smoke-root child.
- Filter cases by profile.
- Error on an absent CI snapshot.
- Report non-CI repositories as skipped.
- Reject an empty or completely skipped run unless explicitly allowed.
- Continue to copy repositories without mutating sources.
- Redact resolved source and temporary workspace paths from normal reports.
- Exercise `ci`, `smoke`, `planner`, `calibration_bge`, `ab_hash`, and `ab_bge`
  wiring end to end with fake embedding/planner dependencies and real copied
  fixture directories.

### Metric And Report Tests

- Preserve existing Hit, Recall, MRR, noise, entrypoint, cross-language, and
  latency behavior.
- Add case-insensitive, unique-path, fixed-denominator Precision@12 and
  noise@12 parity tests for informational cases.
- Aggregate boolean success rates, entrypoint Top1/Top3, numeric means, and
  latency p50/p95 overall and by repository, tag, profile, and provider/model.
- Include informational and executed counts.
- Render aggregate metrics and known gaps in Markdown.

### Comparison Tests

- Emit baseline, candidate, and delta for shared numeric metrics.
- Aggregate deltas across every documented grouping.
- Preserve regression thresholds.
- Warn on repository effective-config differences.
- Treat required pass-to-skipped/error, required removal, and incomparable
  required cases as gating regressions.
- Keep informational and known-gap metric declines non-gating.
- Exit non-zero on gating regressions by default and zero with
  `--allow-regressions`.

### Migration Tests

- Account for all 33 legacy cases before deleting legacy JSON.
- Preserve every legacy query exactly.
- Preserve required, absent, rank, noise, and known-gap intent.
- Assert exact 22/8/3 provenance counts after legacy JSON is removed.
- Merge `qrcode-entrypoint` into `program_tool/qrcode-tool` rather than keeping
  a duplicate.
- Run the committed frontend and Java/Spring CI snapshots.
- Validate the three requests planner cases, the dashboard cross-language case,
  and the three A/B cases are selectable by their profiles.

### Planner Diagnostic Tests

- Load planner queries from the canonical catalog instead of duplicating query
  strings.
- Verify fake-planner wiring without a network dependency.
- When running the real `psf/requests` smoke, require planner status `ok`, a
  non-empty repo-profile hash, no unsupported Java/Spring terms in consumed
  hints, and 3/3 Top-5 path gates.
- Allow unsupported model output only in `discarded_hints`.

### CLI And Documentation Tests

- Create nested parent directories for JSON and Markdown output from `run` and
  `compare` and JSON output from `feedback`.
- Reject unknown, empty, and all-skipped profiles unless `--allow-empty` is
  explicit.
- Verify compare exit codes for gating regressions, observed informational
  declines, and `--allow-regressions`.
- Verify the README links to the operational guide and documented commands use
  the canonical catalog.

### Final Verification

The milestone is accepted only when all of these succeed:

```bash
conda run -n base python -m pytest tests/test_quality_*.py -q
conda run -n base python -m pytest -q

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p0-ci.json \
  --markdown /tmp/cst-p0-ci.md

conda run -n base cst quality compare \
  --baseline /tmp/cst-p0-ci.json \
  --candidate /tmp/cst-p0-ci.json \
  --output /tmp/cst-p0-self-compare.json \
  --markdown /tmp/cst-p0-self-compare.md

conda run -n base cst quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ab_hash \
  --output /tmp/cst-p0-ab-hash.json
```

Acceptance checks confirm:

- the CI report contains both frontend and Java/Spring cases;
- the CI Java case that contains Chinese comments is tagged `localized_cjk`,
  not `cross_language`;
- the catalog contains a genuine `cross_language` case whose expected source
  fixture contains no CJK text;
- no required CI case fails or errors;
- self-comparison reports zero gating regressions and zero metric deltas;
- the Markdown report lists profile, status, aggregate metrics, and known gaps;
- the comparison command exits zero;
- the A/B hash snapshot executes all three informational cases;
- at least one `smoke` repository resolves from a real external checkout and
  executes rather than using a snapshot or skip;
- Git contains no generated `.quality/` reports.

Final handoff includes a profile-status table with one of these values for every
profile: `verified`, `failed`, or `unverified_dependency`. `ci`, `ab_hash`, and
at least one external-repository `smoke` run must be `verified` to close Phase 0.
Planner, calibration BGE, and A/B BGE are executed when their local dependencies
are available. Missing dependencies do not turn into a pass; they are recorded
as `unverified_dependency` with the missing checkout, service, or model named.
All profiles still have dependency-free end-to-end wiring tests.

The profile-status record belongs in the implementation handoff, not in a
generated committed report. Phase 1 cannot be declared complete while its real
cross-language profile remains unverified.

## Risks And Mitigations

### Migration Changes Existing Gates

Risk: translating a legacy fixture changes what pass and fail mean.

Mitigation: keep legacy files during conversion, add parity tests, and delete
them only after all 33 cases are accounted for.

### Canonical Catalog Becomes Large

Risk: one catalog becomes difficult to review.

Mitigation: keep stable ordering by repository and case ID, use tags and
profiles instead of nested custom formats, and keep all parsing logic in the
shared loader.

### Optional Profiles Look Green When Nothing Ran

Risk: unavailable repositories produce only skips while the command exits zero.

Mitigation: track executed count and reject empty runs by default.

### Model Comparisons Are Not Deterministic

Risk: BGE or Ollama availability and latency vary by machine.

Mitigation: keep model profiles outside CI, record effective configuration and
repository identity, treat latency changes as warnings, and distinguish
`unverified_dependency` from a passing result.

### Comparison Deltas Mix Incompatible Runs

Risk: reports from different repositories or configurations look comparable.

Mitigation: compare repository content hashes and effective configurations,
emit metadata warnings, and keep warnings prominent in Markdown.

### Informational Metrics Become Accidental Gates

Risk: an embedding A/B observation changes exit status even though it was never
a required product gate.

Mitigation: only required cases contribute gating regressions. Known-gap and
informational declines are reported separately.

### Localized Text Is Mistaken For Cross-Language Retrieval

Risk: a Chinese query matches Chinese comments and is reported as
Chinese-to-English success.

Mitigation: tag localized lexical cases separately and require an English-only
target for `cross_language` cases.

## Completion Criteria

Phase 0 is complete when:

- one canonical catalog owns all 33 legacy cases;
- deterministic CI covers frontend, Java/Spring, exact identifiers, noise, and
  localized-CJK lexical behavior without claiming translation;
- the catalog and model profiles preserve genuine Chinese-to-English cases with
  English-only targets, and their real execution status is explicit;
- smoke, planner, calibration BGE, A/B hash, and A/B BGE profiles select their
  intended cases;
- report metadata identifies the effective per-repository configuration;
- report aggregation exposes every roadmap metric with an explicit denominator;
- report comparison exposes metric deltas and fails on required gating
  regressions by default without gating informational observations;
- MCP feedback remains available through the documented privacy-preserving
  command;
- legacy fixture JSON is removed only after parity is proven;
- required case removal, skip, or error cannot disappear from comparison without
  a non-zero result;
- the focused and full test suites pass;
- the standard CI, A/B hash, real smoke, and self-comparison commands pass;
- the README, operational guide, and roadmap agree on the workflow and Phase 0
  status.
