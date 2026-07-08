# Retrieval Quality Scoring System Design

Date: 2026-07-08
Status: Draft for review
Repository: `/Users/flobby/Documents/context-seatch-tool`
Roadmap: `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md`

## Summary

Build a unified retrieval quality scoring system for Context Search Tool.

This milestone does not change retrieval behavior. It creates the evaluation layer needed before later fast-context-like work such as ContextPack, RetrievalTrace, controlled multi-round exploration, query planner tuning, language plugins, and retrieval-core decomposition.

The goal is to answer a practical development question after every retrieval change:

```text
Did this change improve code-context retrieval quality, and where did it regress?
```

The scoring system should consolidate the project's current scattered quality assets:

- `src/context_search_tool/metrics.py`
- `tests/test_ab_comparison.py`
- `tests/test_retrieval_calibration.py`
- `tests/test_generic_baseline_quality.py`
- `tests/fixtures/**/queries.json`
- MCP feedback logs written to `.context-search/mcp_calls.jsonl`

The first version should provide shared fixture parsing, shared path assertions, shared metrics, and a report format that can compare a baseline run with a candidate run.

## Motivation

CST is past the stage where manual inspection of a few top results is enough.

The project already has several retrieval-quality efforts:

- Java/Spring and calibration fixtures protect backend retrieval behavior.
- Generic baseline fixtures protect language-neutral ranking and noise handling.
- Frontend quality designs introduce entrypoint and feature-cohort expectations.
- A/B comparison tests compare hash and BGE embeddings.
- MCP query feedback records real usage signals.

These pieces are useful, but they are not yet one quality loop. Each uses slightly different fixture shapes, metrics, output conventions, and skip behavior. That makes it hard to judge whether a new ranking or planner change is a net improvement.

The fast-context-like roadmap makes this more important. The next major features will change query expansion, result grouping, relation expansion, and possibly ranking. Without a shared scoring system, those changes can improve one scenario while silently damaging exact-match, Java/Spring, frontend, or generic baseline behavior.

## Goals

- Define a unified retrieval quality case schema that can represent current fixture expectations and future fast-context-like scenarios.
- Provide shared metric functions for Recall@K, Hit@K, MRR, expected coverage, noise count, entrypoint rank, cross-language success, and latency.
- Provide shared assertion helpers for path/glob expectations currently duplicated across tests.
- Add a quality runner that indexes a repo, runs query cases, records results, computes metrics, and emits a stable JSON report.
- Add a human-readable Markdown summary for before/after review.
- Support baseline-vs-candidate comparison without requiring two separate code checkouts in the first version.
- Keep CI fast by separating committed fixture checks from slow real-repository and model-backed runs.
- Treat MCP feedback as offline analysis input, not as a required CI fixture.
- Preserve existing quality tests while gradually moving them onto the shared evaluator.

## Non-Goals

- No retrieval ranking changes in this milestone.
- No new embedding provider or reranker.
- No ContextPack implementation.
- No RetrievalTrace implementation, though the report shape should leave room for it.
- No required remote model dependency.
- No requirement that CI has access to private real repositories.
- No deletion of existing fixture suites in the first implementation.
- No claim of fast-context parity.
- No automatic tuning of weights based on scores.

## Design Principles

### Measure Before Tuning

The quality system should make retrieval changes measurable before the project adds more exploration, reranking, or plugin logic.

### Shared Core, Multiple Surfaces

Metrics and assertions should live in reusable code. Pytest, CLI commands, local smoke scripts, and future dashboards should call the same evaluator rather than reimplementing path matching and scoring.

### Portable Fixtures

Fixtures must not require hard-coded absolute paths. Real repositories should be resolved through environment variables, `CST_SMOKE_REPOS_DIR`, or reduced committed snapshots.

### CI Is A Floor, Not The Whole Truth

CI should run schema checks, synthetic fixtures, reduced committed snapshots, and fast hash-based tests. Slow BGE, Ollama, large real-repository, and baseline-comparison runs should be available locally but not required for every commit.

### Regressions Should Be Visible, Not Hidden

Known gaps are allowed, but they should be explicitly marked as `known_gap` and reported. A known gap should not silently disappear from the fixture set.

### Reports Should Be Stable Artifacts

The JSON report should be machine-readable and stable enough for future comparison tools. The Markdown report should be concise enough to paste into a PR or development note.

## Target User Experience

### Fast Local Check

```text
cst quality run tests/fixtures/retrieval_quality/queries.json --profile ci --output .quality/latest.json
```

Expected behavior:

- Loads committed fixture cases.
- Uses hash embedding and reduced/synthetic repos.
- Runs quickly enough for local pre-commit or CI.
- Produces JSON and optional Markdown summary.

### Real Project Smoke

```text
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke \
  --output .quality/smoke.json \
  --markdown .quality/smoke.md
```

Expected behavior:

- Resolves real repositories through env vars or `CST_SMOKE_REPOS_DIR`.
- Skips unavailable real repos with explicit skip records.
- Produces metrics for each query and aggregate category.

### Baseline Comparison

```text
cst quality compare \
  --baseline .quality/main.json \
  --candidate .quality/branch.json \
  --markdown .quality/comparison.md
```

Expected behavior:

- Compares query-by-query and aggregate metrics.
- Flags improvements, regressions, unchanged cases, skips, and known gaps.
- Does not require re-running indexing if both reports already exist.

## Architecture

The quality system should sit outside the retrieval algorithm and call the same public core APIs as the CLI and MCP server.

```text
Quality Fixture
  -> Fixture Loader
       -> schema validation
       -> repo resolution
       -> profile filtering
  -> Quality Runner
       -> copy repo when needed
       -> index repository
       -> run query_repository
       -> measure latency
  -> Case Evaluator
       -> path/glob matching
       -> expectation assertions
       -> metric calculation
       -> known-gap handling
  -> Report Writer
       -> JSON report
       -> Markdown summary
  -> Comparison Tool
       -> baseline vs candidate metric delta
       -> regression classification
```

The first implementation should prefer a small new module group over expanding test files further:

```text
src/context_search_tool/quality/
  __init__.py
  cases.py
  metrics.py
  runner.py
  reports.py
  compare.py
```

If a package feels too heavy during implementation, a smaller module layout is acceptable, but the boundaries should remain:

- schema and path matching;
- metric calculation;
- execution;
- report serialization;
- report comparison.

## Quality Fixture Schema

Add a v1 fixture format for retrieval quality cases.

Suggested location:

```text
tests/fixtures/retrieval_quality/queries.json
```

The fixture can contain multiple repositories:

```json
{
  "schema_version": 1,
  "repos": [
    {
      "repo_key": "program_tool",
      "path_env": "CST_SMOKE_PROGRAM_TOOL_REPO",
      "repo_dir_name": "program-tool",
      "snapshot_path": "tests/fixtures/real_projects/program_tool",
      "profiles": ["ci", "smoke"],
      "queries": []
    }
  ]
}
```

Each query case should have this shape:

```json
{
  "id": "dashboard-cross-language",
  "query": "数据看板统计图表功能",
  "tags": ["cross_language", "feature_lookup", "java_spring"],
  "mode": "results",
  "expected_top_k": [
    {"path": "src/main/java/com/example/DashboardController.java", "top_k": 5}
  ],
  "expected_any_top_k": [
    {
      "matchers": [
        {"path": "src/main/java/com/example/DashboardService.java"},
        {"path": "src/main/java/com/example/StatisticsService.java"}
      ],
      "top_k": 5
    }
  ],
  "preferred_rank": [
    {
      "path": "src/main/java/com/example/DashboardController.java",
      "top_k": 5,
      "max_rank": 1,
      "role": "entrypoint"
    }
  ],
  "absent_top_k": [
    {"glob": "**/package-lock.json", "top_k": 5}
  ],
  "outranks": [
    {
      "source": {"path": "src/main/java/com/example/DashboardController.java"},
      "noise": {"glob": "**/*Config.java"},
      "top_k": 10
    }
  ],
  "known_gap": false
}
```

### Required Fields

- `id`: stable case identifier unique within a repo.
- `query`: the user query.

### Optional Repo Fields

- `repo_key`: stable repository identifier.
- `path_env`: repo-specific environment variable.
- `repo_dir_name`: directory name under `CST_SMOKE_REPOS_DIR`.
- `snapshot_path`: committed reduced snapshot path.
- `profiles`: list of profiles that may run this repo.
- `default_config`: optional retrieval or embedding overrides.

### Optional Query Fields

- `tags`: categories such as `java_spring`, `frontend`, `generic`, `cross_language`, `exact`, `noise`, `entrypoint`, `planner`.
- `mode`: initially `results`; future values may include `context_pack` when ContextPack exists.
- `expected_top_k`: every matcher must appear within its own top K.
- `expected_any_top_k`: at least one matcher in each group's `matchers` list must appear within top K.
- `preferred_rank`: a matcher should be at or above `max_rank` within top K.
- `absent_top_k`: matcher must not appear within top K.
- `forbidden_above`: noise matcher must not rank above a target matcher.
- `outranks`: source matcher must outrank noise matcher inside top K when both are present.
- `anchor_expected`: docs or config evidence should appear in evidence anchors when that output exists.
- `known_gap`: case is measured and reported but does not fail gates.
- `notes`: short explanation for humans.

### Matchers

Matchers should support:

```json
{"path": "src/App.java"}
{"glob": "src/**/*.java"}
{"contains": "Dashboard"}
```

The first implementation should strongly prefer `path` and `glob`. `contains` is useful for legacy fixtures but should not become the main style because it can hide ambiguous expectations.

Line-range expectations are out of scope for v1 unless an existing fixture already needs them. File-level quality is enough for this milestone.

## Metrics

The system should compute both case-level and aggregate metrics.

### Case Metrics

Each query case should emit:

- `hit_at_1`, `hit_at_3`, `hit_at_5`, `hit_at_10`: whether any expected target appears within K.
- `recall_at_5`, `recall_at_10`: fraction of expected targets found within K.
- `mrr`: reciprocal rank of the first expected target.
- `expected_coverage_top5`: count and ratio of expected targets in top 5.
- `preferred_rank_pass`: whether all preferred-rank assertions pass.
- `noise_top5`, `noise_top10`: count of absent/noise matchers that appeared within K.
- `entrypoint_rank`: rank of the first preferred entrypoint target, if present.
- `cross_language_success`: boolean for cases tagged `cross_language`, based on expected target hit.
- `latency_ms`: wall-clock query time.
- `result_count`: number of returned primary results.
- `top_score`: top result score when available.
- `status`: `pass`, `fail`, `known_gap`, `skipped`, or `error`.

### Aggregate Metrics

Aggregate by:

- all cases;
- repo key;
- tag;
- profile;
- embedding provider/model when available.

Aggregate output should include:

- total, passed, failed, skipped, known gaps, errors;
- average MRR;
- average Recall@5 and Recall@10;
- Hit@1, Hit@3, Hit@5 rates;
- average noise count in top 5;
- p50 and p95 latency;
- regressions and improvements when comparing two reports.

### Metric Implementation Notes

The current `src/context_search_tool/metrics.py` is keyword-based. The new evaluator should move toward matcher-based metrics over result paths. Existing functions can be kept for compatibility, but new metrics should operate on normalized result paths and matcher objects.

## Existing Asset Mapping

The first implementation should avoid a disruptive rewrite. Existing suites should map into the new quality system gradually:

- `tests/test_generic_baseline_quality.py`: primary source for reusable path/glob assertions and real-project smoke behavior.
- `tests/test_retrieval_calibration.py`: model profile fixture source for BGE-backed calibration cases.
- `tests/test_ab_comparison.py`: historical A/B runner; future embedding comparisons should be expressible as two quality reports plus `quality compare`.
- `src/context_search_tool/metrics.py`: compatibility layer for old keyword metrics; new matcher metrics can live under the quality package and later replace old helpers where appropriate.
- `src/context_search_tool/mcp_tools.py` feedback logging: source for optional feedback analysis, not direct pass/fail gating.

The migration should prove the shared evaluator on one suite before changing all existing quality tests.

## Report Format

### JSON Report

The JSON report should be stable and versioned:

```json
{
  "schema_version": 1,
  "generated_at": 1783526400,
  "tool": {
    "name": "context-search-tool",
    "git_commit": "abc1234"
  },
  "profile": "ci",
  "config": {
    "embedding": {
      "provider": "hash",
      "model": "hash-v1",
      "dimensions": 384
    }
  },
  "aggregate": {},
  "repos": [],
  "cases": []
}
```

Each case record should include:

```json
{
  "repo_key": "program_tool",
  "case_id": "qrcode-tool",
  "query": "QRCode generate scan camera decode paste image qrcode-reader",
  "tags": ["frontend", "entrypoint"],
  "status": "pass",
  "metrics": {
    "mrr": 1.0,
    "hit_at_5": true,
    "recall_at_5": 1.0,
    "noise_top5": 0,
    "latency_ms": 42
  },
  "top_results": [
    {
      "rank": 1,
      "path": "src/views/qrcode/QRCodeTool.vue",
      "score": 12.3,
      "reasons": ["frontend entrypoint match"]
    }
  ],
  "failures": []
}
```

Top results should be capped, for example top 10, so reports remain readable.

### Markdown Summary

The Markdown report should include:

- command/config summary;
- aggregate table;
- failures and regressions first;
- known gaps;
- slowest cases;
- per-tag summary;
- optional top results for failed cases.

The Markdown report is for humans. The JSON report is the source of truth.

## Baseline Comparison

The first comparison tool should compare two JSON reports, not two live repositories.

Comparison categories:

- `improved`: candidate passes where baseline failed, or improves MRR/Recall beyond threshold.
- `regressed`: candidate fails where baseline passed, increases noise, or lowers key metrics beyond threshold.
- `unchanged_pass`
- `unchanged_fail`
- `new_case`
- `removed_case`
- `skipped`

Default regression checks:

- pass to fail is a regression;
- Hit@5 true to false is a regression;
- MRR drop greater than `0.25` is a regression;
- `noise_top5` increase by 2 or more is a regression;
- p95 latency increase by more than 50% is a warning, not a hard regression in v1.

Thresholds should be constants in v1, not user-tuned config. If they prove too noisy, a later spec can add comparison profiles.

## Profiles

### `ci`

Purpose: fast, portable regression floor.

Behavior:

- Use committed snapshots and synthetic fixtures.
- Use hash embedding by default.
- Do not require Ollama, BGE, private repos, or network.
- Fail on schema errors and required case failures.

### `smoke`

Purpose: local real-project confidence.

Behavior:

- Resolve real repos through `path_env`, `CST_SMOKE_REPOS_DIR`, or `snapshot_path`.
- Skip unavailable repos with explicit records.
- Can take longer than CI.
- Fail only when the invoked repo exists and the case is not marked `known_gap`.

### `model`

Purpose: optional model-backed checks.

Behavior:

- Allows BGE or planner-enabled configs.
- Must be opt-in.
- Should record provider, model, dimensions, planner status, and latency.

### `feedback`

Purpose: offline analysis of real MCP use.

Behavior:

- Reads one or more `.context-search/mcp_calls.jsonl` files.
- Reports query counts, success/failure rates, result counts, planner status, top score distribution, and common query terms.
- Does not run retrieval.
- Does not fail CI.

## MCP Feedback Analysis

The current MCP query tool appends events to:

```text
<repo>/.context-search/mcp_calls.jsonl
```

This milestone should not turn feedback logs into test fixtures. The logs are user-local and may include private query text.

Instead, add a separate analysis path that can summarize:

- total calls;
- ok/error counts;
- empty-result rate;
- top score distribution;
- planner enabled/status/latency when present;
- common query terms after local tokenization;
- embedding provider/model distribution.

The feedback analyzer should redact or omit raw queries by default in aggregate output, with an explicit local flag if the developer wants to include query examples.

## CLI And Test Integration

### CLI

Add a developer-facing command under the existing CLI:

```text
cst quality run <fixture> --profile ci --output report.json [--markdown report.md]
cst quality compare --baseline base.json --candidate head.json [--markdown comparison.md]
cst quality feedback <mcp_calls.jsonl> --output feedback-summary.json
```

If adding a CLI subcommand is too much for the first implementation, a module entry point is acceptable:

```text
python -m context_search_tool.quality run ...
```

The core evaluator should not depend on terminal formatting.

### Tests

Add focused tests for:

- fixture schema validation;
- path/glob/contains matcher behavior;
- metric calculations;
- known-gap behavior;
- report JSON shape;
- comparison classification;
- feedback-log summary with synthetic events.

Then gradually update existing quality tests to use shared helpers:

- `tests/test_generic_baseline_quality.py`
- `tests/test_retrieval_calibration.py`
- `tests/test_ab_comparison.py`

Do not rewrite all existing tests in one pass. The first implementation can add shared helpers and migrate one suite enough to prove the design.

## Migration Plan

### Step 1: Add Core Quality Types And Metrics

Create the schema, matcher, and metrics code. Add unit tests with synthetic result paths.

Verification:

```text
python -m pytest tests/test_quality_metrics.py -q
```

### Step 2: Add Fixture Loader And Schema Tests

Create `tests/fixtures/retrieval_quality/queries.json` with a small subset adapted from existing generic/frontend fixtures.

Verification:

```text
python -m pytest tests/test_quality_cases.py -q
```

### Step 3: Add Runner And JSON Report

Run reduced snapshot cases through `index_repository` and `query_repository`.

Verification:

```text
python -m pytest tests/test_quality_runner.py -q
```

### Step 4: Add Compare Command

Compare two synthetic reports and classify improvements/regressions.

Verification:

```text
python -m pytest tests/test_quality_compare.py -q
```

### Step 5: Add CLI Surface

Expose `quality run`, `quality compare`, and optionally `quality feedback`.

Verification:

```text
cst quality run tests/fixtures/retrieval_quality/queries.json --profile ci --output /tmp/cst-quality.json
cst quality compare --baseline /tmp/cst-quality.json --candidate /tmp/cst-quality.json
```

### Step 6: Migrate One Existing Suite

Use shared matcher/assertion helpers in the generic baseline quality suite or create an equivalent reduced quality fixture. Avoid deleting the original suite until the new runner proves stable.

Verification:

```text
python -m pytest tests/test_generic_baseline_quality.py tests/test_quality_runner.py -q
```

## Acceptance Criteria

- A unified quality fixture schema is documented and validated by tests.
- Matcher-based metrics cover path and glob expectations.
- The quality runner emits a versioned JSON report.
- The Markdown summary highlights failures, known gaps, aggregate metrics, and slow cases.
- The comparison tool can classify pass-to-fail and metric regressions from two reports.
- CI-friendly tests run without private repositories, Ollama, BGE, or network.
- Existing default test suite still passes.
- Existing quality fixtures remain usable during migration.
- MCP feedback analysis is opt-in and does not expose raw query text by default.

## Open Questions

### Should The First Runner Reindex Every Time?

Recommendation: yes for v1 CI and smoke correctness. Caching can come later after report semantics are stable.

### Should Quality Reports Store Full Results?

Recommendation: cap at top 10 primary results and include file paths, scores, score parts, and reasons. Full snippets should be omitted to keep reports small and avoid leaking too much source content.

### Should Comparison Require Same Fixture Version?

Recommendation: warn when fixture hashes differ, but still compare overlapping `repo_key + case_id` records. Mark new and removed cases explicitly.

### Should Known Gaps Affect Aggregate Metrics?

Recommendation: include known gaps in measured aggregate metrics but exclude them from pass/fail gate counts. This keeps visibility without blocking progress.

## Future Extensions

- Add ContextPack completeness metrics after ContextPack exists.
- Add RetrievalTrace coverage metrics after trace exists.
- Add line-range relevance when file-level ranking is no longer enough.
- Add branch-to-branch live comparison runner if JSON-only comparison becomes inconvenient.
- Add a local dashboard only after JSON and Markdown reports prove useful.
- Add automatic benchmark trend storage outside git if repeated local runs become common.
