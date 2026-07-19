# Lightweight Graph Retrieval Optimization Implementation Plan

Date: 2026-07-19
Status: Implemented and verified — changes intentionally left uncommitted for review
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Reference project: [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph)
Related plan: `docs/superpowers/plans/2026-07-18-p6-freshness-performance-large-repositories.md`

> **Execution record:** The user explicitly authorized implementation on
> 2026-07-19. Tasks 1 and 2 were completed without changing retrieval output,
> schemas, ranking policy, dependencies, or the P6 plan. P6 remains the source
> of truth for health/status and broad SQLite optimization.

## Decision Summary

CST already has a mature graph-retrieval core: typed relations, direction and
weight policies, bounded multi-hop expansion, confidence/resolution states,
snapshot-consistent reads, stale/legacy fallback, test-intent gating, and a
bounded one-hop graph projection in `context_search_explain`.

The recommended change is therefore **not** a graph redesign. The first delivery
contains only two small, independently reversible changes:

1. batch anchor-seed chunk reads and deduplicate repeated file/directory
   expansion work;
2. document the graph projection already returned by `explain`, so callers can
   discover and use it without adding another MCP tool.

Two other worthwhile improvements are already owned by P6 and must not be
reimplemented here:

- P6 Task 4 owns truthful read-only index/graph health in CLI and MCP
  `status`/`stats`;
- P6 Task 9 owns measured exact SQLite pushdown for signal, path/symbol, and
  other candidate sources.

If P6 Task 9 starts first, fold this plan's Task 1 into that task and keep one
benchmark/acceptance path. If this plan lands first, P6 must take the resulting
code and measurements as its new entry baseline.

## Goal

Reduce avoidable query latency and make existing graph evidence easier to use,
without changing retrieval semantics, public response schemas, graph schema,
ranking policy, or dependencies.

## Definition Of Done

This plan is complete only when:

- `anchor_candidates()` performs one batch seed lookup, never one lookup per
  seed;
- each encountered seed file is expanded at most once per query;
- each document/config directory is expanded at most once per query;
- missing seed chunks retain the current silent-skip behavior;
- the ordered anchor candidates, scores, score parts, sources, final results,
  reasons, follow-up keywords, traces, and ContextPacks remain exact;
- README and MCP descriptions state that `explain` returns bounded signals plus
  incoming/outgoing relations and omission counts;
- no new tool, database table, schema version, configuration field, relation
  kind, dependency, or background service is introduced;
- focused, protected, graph-quality, and fast-CI gates pass;
- paired measurements show the expected work reduction and no end-to-end
  latency regression.

## Current State And Gap Analysis

| Area | Current capability | Decision |
| --- | --- | --- |
| Graph model | Typed relations including calls, implementations, imports, routes, mappings, tests, and type usage | Keep unchanged |
| Traversal | Direction-aware, weighted, confidence-aware, bounded expansion with truncation protection | Keep unchanged |
| Consistency | `GraphReadSession` holds one SQLite read snapshot and detects stale/legacy/fault states | Keep unchanged |
| Explainability | `context_search_explain(file:line)` already returns bounded signals, outgoing relations, incoming relations, and omitted counts | Improve description only |
| Anchor expansion | Loads every direct-text seed separately and can rescan the same file/directory repeatedly | Optimize in Task 1 |
| Graph health | Stats reads graph capability but does not expose it; legacy `status` is artifact-oriented | P6 Task 4 |
| SQL candidate scans | Signal and path/symbol sources still have Python-side/full-scan opportunities | P6 Task 9 |
| Compact output | ContextPack already supports `max_items` and `max_context_bytes` | Do not add a second compact schema |

## Plan-Time Evidence

On 2026-07-19, an in-memory prototype changed only anchor-expansion plumbing:

- replaced per-seed `chunk_for_id()` calls with one `chunks_for_ids()` call;
- processed each file once, using the strongest seed encountered first;
- processed each document/config directory once;
- returned an equal `QueryBundle` for all three sampled queries.

Median of three warm runs on the repository's existing local index:

| Query | Before | Prototype | Reduction |
| --- | ---: | ---: | ---: |
| `ApplyAuditController` | 813.5 ms | 559.7 ms | 31% |
| `/apply/audit/pageEs INVOLVED_BY_ME` | 812.5 ms | 623.0 ms | 23% |
| `how graph relation expansion ranks candidates` | 879.4 ms | 660.6 ms | 25% |

The same traces placed about 599–659 ms in anchor expansion, while relation
expansion used about 0–15 ms. This makes anchor work the first optimization
target; deeper graph redesign is not justified by the observed profile.

These numbers are directional, not release evidence. The local self-index had
57 files, 285 chunks, and legacy signal schema v3. It proves the plumbing
opportunity and result equivalence, but it does not prove fresh-v5 or
large-repository performance. Final acceptance must use the protocol below.

## Implementation Results

The production change is limited to `anchor_candidates()` and the MCP explain
description. Direct seeds are still filtered and sorted by the same keys, then
loaded in one batch. Each seed file and each eligible document/config directory
is expanded only on its strongest encounter. Missing chunks still skip silently.

Characterization coverage keeps every non-operation projection exact and
permits only the reviewed operation-ledger rewrite from per-ID reads to one
ordered batch plus first-occurrence file/directory deduplication. The immutable
baseline fixture remains unchanged (SHA-256
`4235ec5539c548005d75b98be4a0c347364d40ec28a79fc45b10d351bcf8bed7`).

Verification in the frozen characterization runtime (Python 3.13.12,
SQLite 3.51.2):

| Gate | Result |
| --- | ---: |
| Full pytest suite | 2,629 passed, 9 established conditional skips |
| Focused retrieval/explain/MCP suite | 275 passed |
| Protected trace/ContextPack/exploration/MCP suite | 237 passed |
| `p5_language_graphs` quality profile | 12/12 passed |
| Raw `ci` quality profile | 8/8 passed |

The release benchmark used a fresh graph-schema-v5 index with ready status,
1,003 source files, and 1,008 active chunks. Twenty warm paired runs alternated
the baseline and optimized implementations for
`anchorbatchtoken graph retrieval evidence`; result projections matched exactly.

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| End-to-end p50 | 89.27 ms | 72.84 ms | 18.4% faster |
| End-to-end p95 | 90.64 ms | 74.04 ms | 18.3% faster |
| Anchor expansion p50 | 21.56 ms | 4.96 ms | 77.0% faster |
| Anchor expansion p95 | 22.58 ms | 5.72 ms | 74.7% faster |

Twenty-pair smoke measurements on the existing 285-chunk legacy-v3 self-index
also preserved exact bundles for all three plan-time queries. End-to-end p50
fell from 874.84 to 607.29 ms, 890.75 to 686.55 ms, and 947.84 to 698.64 ms.

The related P6 plan file was not modified. P6 Task 4 still owns canonical
health/status exposure, and P6 Task 9 still owns broader measured SQL pushdown;
P6 should take this implementation and benchmark as its entry baseline.

## Scope Boundaries

### In scope

- surgical changes inside `retrieval_core/expansion.py`;
- work-count and exact-output tests for anchor expansion;
- README and MCP tool-description corrections for existing explain behavior;
- paired local performance evidence;
- a clear handoff to P6 Tasks 4 and 9.

### Out of scope

- new graph database, vector database, FTS artifact, or runtime dependency;
- graph schema/version changes or new relation/node kinds;
- community detection, workflow/flow models, risk scoring, ownership models, or
  repository-wide graph analytics;
- a second fusion/ranking system such as global RRF;
- ANN, extra node embeddings, or graph embeddings;
- a new `context_search_related`/`callers_of` family of MCP tools;
- a new compact/minimal response schema;
- changes to graph depth, caps, confidence thresholds, relation weights, test
  gates, or direct-result protection;
- P6 freshness, refresh, lifecycle, or large-repository infrastructure.

The useful ideas borrowed from `code-review-graph` are bounded graph access,
explicit omission/truncation, visible health, and progressive disclosure. CST
already implements most of these internally, so this plan exposes or optimizes
existing capability instead of copying that project's larger surface area.

## File Responsibility Map

| File | Planned responsibility |
| --- | --- |
| `src/context_search_tool/retrieval_core/expansion.py` | Batch and deduplicate anchor-expansion reads without semantic change |
| `tests/test_retrieval_pipeline.py` | Exact-order/score and work-count coverage for duplicate seeds/files/directories |
| `tests/test_direct_text_evidence.py` | Existing end-to-end anchor-to-code behavior remains protected |
| `tests/test_retrieval_core_characterization.py` | Preserve immutable projections while narrowly validating the expected operation-ledger rewrite |
| `tests/test_retrieval_core_boundaries.py` | Register the two reviewed production paths without widening protected ownership boundaries |
| `src/context_search_tool/mcp_server.py` | Describe existing bounded graph projection accurately |
| `README.md` | Explain CLI/MCP graph output and progressive usage |
| `tests/test_p5_explain.py` | Existing ready/legacy/stale/cap projection contracts remain exact |
| `scripts/profile_retrieval.py` | Reuse existing stage/store timing and call-count visibility; no redesign required |

## Task And Commit Order

The checklist below is retained as the original execution procedure. The
authoritative completion evidence is recorded in **Implementation Results**;
commit-only steps remain intentionally deferred so the current diff can be
reviewed first.

| Task | Change | Required focused commit |
| ---: | --- | --- |
| 0 | Preflight and baseline | none |
| 1 | Batch and deduplicate anchor expansion | `perf: deduplicate anchor expansion reads` |
| 2 | Expose existing explain graph projection | `docs: describe graph projection in explain` |
| 3 | Final acceptance and P6 handoff | none |

## Task 0: Freeze The Baseline

- [ ] Record `HEAD`, Python, SQLite, dependency versions, and worktree status.
- [ ] Use the project's supported Python environment; an import/collection
  failure from a missing parser runtime is not valid baseline evidence.
- [ ] Point `CST_RUNTIME` at that environment and verify it before running any
  gate. The local editable environment is the default example:

  ```bash
  CST_RUNTIME="${CST_RUNTIME:-$PWD/.venv/bin/python}"
  test -x "$CST_RUNTIME"
  "$CST_RUNTIME" --version
  ```

- [ ] Do not reindex or rewrite the repository's existing `.context-search/`.
  Create fresh-v5 correctness indexes under pytest temporary directories or an
  untracked benchmark workspace.
- [ ] Record before-projections for the three plan-time queries and at least one
  query whose direct-text seeds share a file and one whose document/config
  seeds share a directory.
- [ ] Record stage timings and store-call counts with
  `scripts/profile_retrieval.py` before editing production code.
- [ ] Run the focused baseline:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$CST_RUNTIME" -m pytest -q \
    tests/test_retrieval_pipeline.py \
    tests/test_direct_text_evidence.py \
    tests/test_retrieval_core_characterization.py \
    tests/test_p5_explain.py \
    tests/test_profile_retrieval.py
  ```

Stop if the baseline is not green for a code-related reason. Do not update
protected fixtures to manufacture a clean starting point.

## Task 1: Batch And Deduplicate Anchor Expansion

### Step 1: Add protective tests first

- [ ] Add one case with multiple direct-text seeds in the same file at different
  scores. Assert the exact ordered candidate list, score, source, and
  `score_parts` before and after optimization.
- [ ] Add one case with multiple Markdown/YAML/JSON/properties seeds in the same
  directory. Assert exact directory-anchor output and strongest-score wins.
- [ ] Include duplicate seed IDs, a missing/deleted seed chunk, generated-schema
  filtering, template filtering, and a limit boundary.
- [ ] Instrument store calls and require for non-empty direct seeds:

  - `chunks_for_ids`: exactly one call;
  - `chunk_for_id`: zero calls from `anchor_candidates()`;
  - `chunks_for_file`: at most one call per encountered file;
  - `chunks_in_directory`: at most one call per encountered document/config
    directory.

Timing is not a normal-CI assertion. Work counts and exact results are.

### Step 2: Make the minimum production change

- [ ] Keep the existing direct-seed filter, score bounds, sort key, limit,
  filtering helpers, and returned insertion order unchanged.
- [ ] Sort direct seeds exactly as today, then fetch their chunks once through
  `store.chunks_for_ids()`.
- [ ] Look up each sorted seed in the returned mapping; continue when missing,
  preserving today's `KeyError` skip semantics.
- [ ] Track processed file paths locally. Because seeds are sorted by descending
  direct-text score, the first seed for a file is the strongest; weaker repeats
  cannot improve any same-file candidate and may be skipped.
- [ ] Track processed parent directories locally for document/config anchors.
  The same strongest-first argument preserves directory-anchor scores.
- [ ] Keep `_add_same_file_anchor_candidates()`,
  `_add_directory_anchor_candidates()`, `_put_anchor_candidate()`, and all
  constants unchanged unless a test proves a mechanical signature adjustment
  is required.
- [ ] Do not introduce a cache class, query-session abstraction, new store API,
  or generic expansion framework.

### Step 3: Verify exactness and work reduction

- [ ] Run the Task-0 focused suite.
- [ ] Run trace, ContextPack, and graph gates:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$CST_RUNTIME" -m pytest -q \
    tests/test_retrieval_trace_pipeline.py \
    tests/test_context_pack.py \
    tests/test_exploration_contracts.py \
    tests/test_p5_explain.py
  ```

- [ ] Compare the before/after query projections exactly. Normalize only
  explicitly timing-bearing fields; never normalize paths, ranks, scores,
  reasons, follow-ups, counts, stop reasons, or content bytes.
- [ ] Commit only the production file and its focused tests.

## Task 2: Describe Existing Explain Graph Capability

- [ ] Update the `context_search_explain` MCP description to say it returns the
  indexed chunk plus a bounded graph projection for `file:line`.
- [ ] Update the README CLI `explain` section to list graph status/schema,
  signals, incoming/outgoing relations, and omitted counts.
- [ ] Update the README MCP tool list with the same behavior and recommend this
  progressive flow:

  1. run `query` or `context` to find relevant locations;
  2. run `explain` only for selected `file:line` locations;
  3. inspect omission counts before deciding whether another query is needed.

- [ ] Do not change the explain payload, caps, CLI rendering, graph traversal,
  or registration. Add a description assertion only if FastMCP exposes stable
  local metadata; do not couple tests to private framework internals.
- [ ] Run:

  ```bash
  PYTHONPATH="$PWD/src:$PWD/tests" "$CST_RUNTIME" -m pytest -q \
    tests/test_mcp_server.py \
    tests/test_mcp_tools.py \
    tests/test_p5_explain.py
  git diff --check
  ```

## Task 3: Final Acceptance And P6 Handoff

### Correctness gates

- [ ] Run the unrestricted suite in the supported project environment and keep
  the established optional skip/xfail set unchanged.
- [ ] Run the deterministic graph profile and raw CI profile:

  ```bash
  PYTHONPATH="$PWD/src" "$CST_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/p5_language_graphs.json \
    --profile p5_language_graphs \
    --output .quality/light-graph-p5.json

  PYTHONPATH="$PWD/src" "$CST_RUNTIME" -m context_search_tool.quality run \
    tests/fixtures/retrieval_quality/queries.json \
    --profile ci \
    --output .quality/light-graph-ci.json
  ```

- [ ] Require all existing cases to pass. This change has no legal relevance
  delta, so a changed expected winner, rank, graph score part, result count, or
  pack byte is a failure, not a baseline-refresh opportunity.

### Performance protocol

- [ ] Measure before and after from clean, immutable trees against the same
  copied index and configuration.
- [ ] Alternate before/after execution order, warm each tree, and collect at
  least 20 measured runs per query.
- [ ] Report per query: end-to-end p50/p95, anchor-expansion p50/p95, store-call
  counts, result projection hash, Python/SQLite versions, commit/tree ID, active
  files/chunks, and signal schema/status.
- [ ] Include one fresh-v5 repository. Prefer a representative repository with
  at least 1,000 active chunks or the P6 generated workload when available.
  The 285-chunk legacy self-index remains smoke evidence only.
- [ ] Acceptance thresholds:

  - exact result projection hashes match;
  - required anchor store-call counts match the Task-1 work contract;
  - anchor-expansion p50 improves by at least 15% on a query that exercises
    duplicate file/directory work;
  - end-to-end p50 does not regress by more than 5% on any case;
  - end-to-end p95 does not regress by more than 10% on any case.

If measurements are too noisy to validate those thresholds, retain the
deterministic work-count evidence but make no release latency claim. Do not add
a host-sensitive timing assertion to pytest.

### P6 ownership handoff

- [ ] Record that P6 Task 4 remains responsible for adding one canonical
  read-only health contract to CLI/MCP `status` and `stats`. Do not add a
  graph-only sibling contract in this plan.
- [ ] Record that P6 Task 9 remains responsible for SQL prefilter/pushdown in
  `GraphReadSession.signal_search()` and `SQLiteStore.path_symbol_search()`.
  It must preserve exact CJK, substring, case, score, and tie behavior.
- [ ] Do not add signal FTS, trigram indexes, or another persistent search
  surface unless P6 measurements and portability gates explicitly authorize a
  design amendment.
- [ ] If real usage later shows that `file:line` explain cannot answer callers,
  callees, tests, or impact questions, collect at least three concrete failed
  workflows and write a separate small design for one unified related-code
  query. Do not pre-create a family of graph tools.

## Rollback

Task 1 changes no schema or stored data. Rollback is the revert of its focused
production/test commit; no reindex or cleanup is required. Task 2 is a separate
documentation-only revert. If P6 is already in progress, rebase its benchmark
baseline after rollback rather than keeping two anchor implementations.

## Stop Conditions

Stop implementation and request review if any of the following occurs:

- exact candidate insertion order or strongest-score behavior cannot be
  preserved with per-file/per-directory deduplication;
- a protected query, graph profile, trace, or ContextPack changes;
- the change requires a new schema, dependency, tool, background process, or
  cache lifecycle;
- performance improvement requires changing ranking weights, graph depth, caps,
  or direct-result protection;
- P6 has already changed the same anchor path or established a query-wide read
  session, making this implementation shape obsolete;
- the benchmark cannot distinguish improvement from noise after one controlled
  rerun.

## Expected Change Size

The intended implementation is small:

- production: one function, approximately 15–30 changed lines;
- tests: two or three focused cases plus call-count instrumentation;
- documentation: MCP description and two README paragraphs;
- commits: two focused commits;
- persistent migrations and new dependencies: zero.

Anything materially larger requires a new review of scope before coding.
