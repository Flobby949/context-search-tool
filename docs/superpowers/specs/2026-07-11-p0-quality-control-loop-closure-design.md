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
    "planner": {
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
      }
    }
  },
  "repos": []
}
```

Configuration precedence is deterministic:

```text
DEFAULT_CONFIG
  -> selected profile config
  -> repository default_config
```

The final effective configuration must pass the existing CI compatibility
validation. A repository override cannot enable a planner or remote embedding in
the `ci` profile.

### Repository And Case Profile Selection

Repository `profiles` continue to state where a repository is available. Add an
optional `profiles` field to each case. If a case omits it, it inherits the
repository profiles.

```json
{
  "id": "workbench-audit-cross-language",
  "query": "工作台统计 待我审核",
  "profiles": ["ci"],
  "tags": ["java_spring", "cross_language", "entrypoint"],
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

### Source Resolution

Source selection depends on profile purpose:

- `ci` requires `snapshot_path` and never resolves an external repository.
- Other profiles prefer `path_env`, then
  `CST_SMOKE_REPOS_DIR / repo_dir_name`, then fall back to `snapshot_path` when
  one exists.
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
  one Chinese-to-English-code case.
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

- Resolves the two Java calibration repositories through their existing
  environment variables.
- Uses BGE M3 with 1024 dimensions and keeps the planner disabled.
- Contains all 8 Java/Spring calibration cases, including Chinese business
  queries.
- Is optional outside dedicated evaluation because it requires the configured
  local BGE service.

### `planner`

Purpose: validate repository-aware natural-language planning with a real local
model.

- Uses the real `psf/requests` checkout.
- Enables the configured local Ollama planner.
- Includes cookie/session, retry/proxy/pool, and streamed-response cases.
- Records planner configuration and repository identity in the report.
- Is never required by CI.

### `ab_hash` And `ab_bge`

Purpose: run the same informational semantic cases under two embedding
configurations.

- Uses one small committed A/B snapshot containing relevant and noise files for
  the three existing A/B queries.
- Uses stable case keys in both profiles so the reports compare directly.
- `ab_hash` runs locally without a model.
- `ab_bge` requires the existing BGE provider setup and is optional outside
  dedicated evaluation.
- Profile and embedding differences remain visible as metadata warnings because
  they are intentional inputs to this comparison.

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

Known gaps remain visible without weakening existing gates. A legacy
`known_gap` string becomes `known_gap_reason`; it does not change a required
case into `gate: known_gap`. The report and Markdown renderer list every
non-empty known-gap reason independently of pass/fail status. Only a case that
was already non-gating uses `gate: known_gap` or `gate: informational`.

## Effective Configuration Reporting

Each repository report records the configuration actually used for indexing and
querying:

```json
{
  "repo_key": "psf_requests",
  "config": {
    "config_hash": "sha256:...",
    "embedding": {},
    "retrieval": {},
    "query_planner": {}
  }
}
```

The top-level report keeps the selected profile configuration for backward
compatibility. New comparison logic uses repository-level effective
configuration when available.

No planner prompt, source snippet, API key, or environment variable value is
written into a report.

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
- executed and skipped counts;
- mean numeric metrics across compatible executed cases;
- the same metric summary grouped by case tag.

`null` metrics are excluded from means. Boolean values are not treated as
numbers. Known-gap and informational cases appear in their own status counts and
remain available in metric summaries.

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

The aggregate comparison contains mean baseline, candidate, and delta values
overall and by tag. The Markdown comparison shows regressions first, then metric
changes and metadata warnings.

Regression classification remains conservative:

- required `pass -> fail/error` is a regression;
- `fail/error -> pass` is an improvement;
- loss of Hit@5 is a regression;
- an MRR drop greater than 0.25 is a regression;
- two or more additional noise results in Top 5 is a regression;
- latency above 150% of a non-zero baseline is a warning, not a functional
  regression.

The compare command exits non-zero when regressions exist by default. An
explicit `--allow-regressions` flag is available for exploratory analysis.

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

## Testing Strategy

### Schema Tests

- Parse optional profile configurations and case profiles.
- Preserve existing v1 fixtures without the new fields.
- Reject unknown profiles, duplicates, invalid inheritance, and unsafe CI
  configurations.
- Parse informational A/B matchers and metric K.

### Runner Tests

- Apply configuration precedence in the documented order.
- Record each repository's effective config.
- Prefer external repositories for non-CI profiles and snapshots for CI.
- Filter cases by profile.
- Error on an absent CI snapshot.
- Report non-CI repositories as skipped.
- Reject an empty or completely skipped run unless explicitly allowed.
- Continue to copy repositories without mutating sources.

### Metric And Report Tests

- Preserve existing Hit, Recall, MRR, noise, entrypoint, cross-language, and
  latency behavior.
- Add Precision@12 and noise@12 for informational cases.
- Aggregate compatible metrics overall and by tag.
- Include informational and executed counts.
- Render aggregate metrics and known gaps in Markdown.

### Comparison Tests

- Emit baseline, candidate, and delta for shared numeric metrics.
- Aggregate deltas overall and by tag.
- Preserve regression thresholds.
- Warn on repository effective-config differences.
- Exit non-zero on regressions by default and zero with
  `--allow-regressions`.

### Migration Tests

- Account for all 33 legacy cases before deleting legacy JSON.
- Preserve every legacy query exactly.
- Preserve required, absent, rank, noise, and known-gap intent.
- Run the committed frontend and Java/Spring CI snapshots.
- Validate the three planner cases and three A/B cases are selectable by their
  profiles.

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
```

Acceptance checks confirm:

- the CI report contains both frontend and Java/Spring cases;
- the CI report contains at least one `cross_language` case;
- no required CI case fails or errors;
- self-comparison reports zero regressions and zero metric deltas;
- the Markdown report lists profile, status, aggregate metrics, and known gaps;
- the comparison command exits zero;
- Git contains no generated `.quality/` reports.

Real-repository, planner, and BGE profiles are executed when their local
dependencies are available. Their absence does not block deterministic CI, but
the documented commands and fixture selection tests must remain valid.

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
repository identity, and treat latency changes as warnings.

### Comparison Deltas Mix Incompatible Runs

Risk: reports from different repositories or configurations look comparable.

Mitigation: compare repository content hashes and effective configurations,
emit metadata warnings, and keep warnings prominent in Markdown.

## Completion Criteria

Phase 0 is complete when:

- one canonical catalog owns all 33 legacy cases;
- deterministic CI covers frontend, Java/Spring, exact identifiers, noise, and
  Chinese-to-English retrieval;
- smoke, planner, calibration BGE, A/B hash, and A/B BGE profiles select their
  intended cases;
- report metadata identifies the effective per-repository configuration;
- report comparison exposes metric deltas and fails on regressions by default;
- MCP feedback remains available through the documented privacy-preserving
  command;
- legacy fixture JSON is removed only after parity is proven;
- the focused and full test suites pass;
- the standard CI run and self-comparison commands pass;
- the README, operational guide, and roadmap agree on the workflow and Phase 0
  status.
