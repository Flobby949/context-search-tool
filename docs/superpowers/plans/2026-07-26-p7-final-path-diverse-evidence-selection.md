# P7 Final Path-Diverse Evidence Selection Implementation Plan

Date: 2026-07-26
Status: Implemented and accepted
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `74aae0abe3dff685282fbcc785f7a9b3532cbbe6`
Preserved P7 design:
`docs/superpowers/specs/2026-07-25-p7-retrieval-quality-attribution-evidence-selection-design.md`
Preserved P7 plan:
`docs/superpowers/plans/2026-07-25-p7-retrieval-quality-attribution-evidence-selection.md`
Reviewed P7A design:
`docs/superpowers/specs/2026-07-25-p7a-retrieval-quality-attribution-route-selection-design.md`
Reviewed P7A plan:
`docs/superpowers/plans/2026-07-25-p7a-retrieval-quality-attribution-route-selection.md`

## Outcome

P7 Final makes the smallest product change supported by the P7A diagnosis and
the real-repository probes:

```text
ranked expanded chunks
  -> keep evidence-anchor allocation independent
  -> keep the first, highest-ranked ordinary result for each path
  -> let later distinct paths consume the remaining result slots
  -> expose duplicate-result-path decisions in RetrievalTrace v1
  -> reuse the unchanged QueryBundle in query, context, and explore
```

The intended outcome is path-diverse evidence, not a claim of fast-context
parity. P7 Final fixes result-slot starvation caused by repeated chunks from one
large file. It does not claim to solve Python relation acquisition, weak
semantic ranking, query planning, or all cross-module retrieval misses.

## Why This Replaces Neither Historical Document

The P7 and P7A documents remain preserved as design history:

- P7 contains a broad quality-attribution and evidence-set architecture. Its
  useful product insight is that file-level evidence selection belongs after
  chunk ranking and before ContextPack construction.
- P7A corrects the sequencing problem by requiring attribution before a
  mechanism is chosen. Its useful process insight is that a downstream fix
  must not be used to hide an upstream acquisition miss.
- P7 Final is the evidence-backed implementation slice selected after applying
  that sequencing. It does not edit, delete, or pretend to complete the wider
  proposals.

## Plan-Time Evidence

### Repository Baseline

The implementation entry commit is:

```text
74aae0abe3dff685282fbcc785f7a9b3532cbbe6
```

The four P7/P7A documents are untracked planning inputs at plan time. No source,
test, fixture, or configuration file has changed.

The pinned runtime is:

```text
Python: 3.13.12
SQLite: 3.51.2
Executable: .quality/p5-runtime/bin/python
```

The runtime contains a stale installed copy of `context_search_tool`.
`pyproject.toml` makes the current `src/` tree visible to pytest's main process,
but P6 benchmark child processes do not inherit that pytest-only path
insertion. Therefore every acceptance command must explicitly set:

```bash
PYTHONPATH="$PWD/src"
```

Without that setting, four P6 worker tests fail because the subprocess imports
the stale installed package. With it, those four tests pass. A current full run
reached 2891 passed and 9 skipped with five P6 calibration/resume tests failing;
all five passed immediately as an isolated group. This is recorded as
pre-existing benchmark process-order/calibration instability. P7 Final must
not edit P6 to conceal it, and its final verification must report full-suite
and isolated P6 results separately if the full process remains unstable.

### Public Python Probe

The public repository probe used a clean archive of:

```text
repository: daily_stock_analysis
commit: 487e49e565ffd1b96a7cf4d855f99cee3c981eaa
query: data fetcher prefetch stock names provider fallback pipeline
```

The original working tree was not modified. The clean snapshot contained:

```text
203 files
1596 chunks
```

Observed baseline:

```text
requested results: 12
returned results: 12
unique result paths: 2
candidate_merge outputs: 212 chunks
context_expansion outputs: 212 chunks
context_expansion unique paths: 135
```

Ten or more result slots were consumed by chunks from
`data_provider/efinance_fetcher.py`. `src/core/pipeline.py` was present, while
`data_provider/base.py` first appeared at expanded rank 18 and could not consume
a result slot. The path-symbol recall source also acquired
`tests/test_data_fetcher_prefetch_stock_names.py`, so the case is not purely an
acquisition failure.

A stable first-occurrence projection of the already-ranked expanded list would
produce 12 distinct paths and recover both `src/core/pipeline.py` and
`data_provider/base.py`. This is the direct evidence for the P7 Final change.

The same probe also showed why widening the ContextPack candidate pool is not
the selected mechanism: a wider 48-result input admitted unrelated services
without reliably recovering the remaining intended targets.

### Private Java Probe

A sanitized read-only probe used a clean archive of a pinned Java repository.
The private path, query text, source, and raw result are not persistent P7
artifacts.

Observed aggregate:

```text
requested results: 12
unique result paths: 11
candidate_merge/ranking population: 402 chunks
context_expansion unique paths: 321
```

The main authorization/service chain was already represented. This shows that
the defect is language-neutral but is amplified by weakly structured languages
and large files. It does not justify a Java-only or Python-AST-only solution.

### Current Code Boundary

The relevant call chain is:

```text
candidate recalls
  -> candidate merge
  -> ranking
  -> cohort rerank
  -> context expansion
  -> retrieval_core.selection.split_results_and_anchors
  -> QueryBundle
  -> query / ContextPack / explore
```

`split_results_and_anchors` currently takes the first `final_top_k` ordinary
chunks regardless of path. ContextPack later normalizes candidates by path, but
that happens after the result budget has already been spent. It can remove
duplicates but cannot restore paths that final selection discarded.

## P7 Versus P7A Versus P7 Final

| concern | preserved P7 | reviewed P7A | P7 Final |
| --- | --- | --- | --- |
| primary purpose | diagnose and ship a broad evidence-set architecture | diagnose and select a later route | ship one already-attributed selection fix |
| behavior change | exact injection, projection, pack transport, trace v2, context changes | none | stable path-diverse ordinary-result allocation |
| causal discipline | attribution and implementation are bundled | strong: diagnose, decide, stop | retains attribution evidence, then changes one boundary |
| implementation size | 13 tasks and multiple new schemas | 7 diagnostic/governance tasks | one vertical product slice plus tests/docs |
| risk | too many interacting mechanisms obscure causality | governance cost exceeds the selected defect | narrow compatibility change with a reversible boundary |
| response to Python probe | would likely help, but through several mechanisms | would classify the loss only | directly prevents repeated-file slot starvation |
| response to remaining misses | risks treating every miss in one phase | defers all fixes | explicitly defers structural/ranking misses |

The selected combination is:

1. P7A's causal rule: verify that a target exists before the changed boundary.
2. P7's file-level insight: spend final evidence slots on distinct files.
3. A smaller implementation than either plan: no new audit framework, result
   type, pack segment, retrieval stage, or schema version.

## Product Contract

### Ordinary Result Selection

`split_results_and_anchors` continues to receive an ordered
`list[_ExpandedResult]`. That order is the ranking authority.

For ordinary, non-anchor results:

1. initialize an empty `seen_result_paths` set;
2. iterate the expanded list in its existing order;
3. if an item's `file_path` is already in the set, skip it;
4. otherwise add the path to the set;
5. select the item when fewer than `final_top_k` ordinary results have been
   selected;
6. otherwise classify it as omitted by the result limit;
7. never replace an earlier item with a later chunk from the same path.

Adding a new path to `seen_result_paths` happens before the result-limit
decision. Consequently, every ordinary input has one deterministic terminal
decision: selected, duplicate path, or result limit.

### Path Identity

Path identity is exact `Path` equality on the already-normalized repository
relative path. P7 Final does not:

- call `resolve()`;
- read the filesystem;
- case-fold path strings;
- normalize Unicode;
- compare stems or basenames;
- infer symlink identity.

This preserves the repository's existing path model and adds no I/O.

### Winner And Content Semantics

The first ranked chunk for a path wins unchanged. P7 Final does not merge
content, line ranges, spans, reasons, scores, or chunk IDs across repeated
results. Merging would create a second ranking/materialization policy and could
make line/span claims inconsistent with content.

The selected winner keeps its existing:

- `chunk_ids`;
- `file_path`;
- line range;
- public and private context content;
- score and score parts;
- reasons and follow-up keywords;
- semantic matches and spans.

### Limits

`final_top_k` remains a maximum number of ordinary result paths. The function
may return fewer results only when the expanded population contains fewer
distinct ordinary paths than the limit.

P7 Final does not widen candidate, expansion, result, context, token, probe, or
round limits.

### Evidence Anchors

Evidence anchors retain their independent allocation and existing identity:

```text
(anchor_kind, file_path)
```

Anchor paths do not enter `seen_result_paths`, and ordinary paths do not enter
`seen_anchor_keys`. Anchor order, limits, kinds, and conversion stay unchanged.

### RetrievalTrace v1

The existing `final_selection` stage gains one additive decision-count key:

```text
duplicate_result_path
```

Canonical order becomes:

```text
selected_result
selected_anchor
duplicate_result_path
duplicate_anchor
result_limit
anchor_limit
```

The trace shape and schema version remain unchanged because `decision_counts`
is already a list/map of named integer counts. The invariant remains:

```text
sum(final_selection.decision_counts.values())
  == final_selection.input_count
```

`duplicate_result_path` counts every later ordinary item whose exact path has
already appeared, including duplicates encountered after the result limit is
full. Selected final results remain the only ordinary entries in
`final_selections`.

### Public Surfaces

No command, argument, response field, result type, or context schema is added.
Membership may intentionally change on:

- `cst query`;
- `cst query --trace`;
- `cst context`;
- `cst explore`;
- MCP adapters backed by the same QueryBundle.

For a fixed index, configuration, and query, the new membership remains
deterministic. Every ordinary `QueryBundle.results` path is unique.

## Explicit Non-Goals

P7 Final does not implement:

- Python AST, call-graph, import-graph, or framework extraction;
- an additional language plugin;
- exact-intent candidate injection;
- a new recall source;
- score or rerank changes;
- file score aggregation;
- set-utility optimization, MMR, quotas, or role reservation;
- ContextPack segment/reservation changes;
- a wider query-to-context boundary;
- content/span merging;
- RetrievalTrace v2 or a new trace stage;
- a P7A target-bearing audit framework;
- new benchmark artifact schemas;
- network access or model/provider changes;
- fast-context parity claims.

If the public Python probe still misses
`src/services/name_to_code_resolver.py` or the prefetch test after path-diverse
selection, that is expected residual evidence for a separate structural
acquisition/ranking experiment. It is not a reason to expand this patch.

## Files In Scope

Expected product and focused test files:

```text
src/context_search_tool/retrieval_core/selection.py
src/context_search_tool/formatters.py
tests/test_retrieval_pipeline.py
tests/test_retrieval_trace_pipeline.py
tests/test_exploration_p7.py
tests/test_retrieval_core_boundaries.py
tests/test_retrieval_core_characterization.py
```

The public-surface contract uses `tests/test_exploration_p7.py`. A separate
module is required because the frozen retrieval-facade migration inventory
allows a new P7 reference without rewriting historical line inventories, while
adding the calls to an older test module would make an unrelated frozen
reference group drift.

Expected documentation files after acceptance:

```text
README.md
docs/retrieval-quality.md
roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
docs/superpowers/plans/2026-07-26-p7-final-path-diverse-evidence-selection.md
```

The four preserved P7/P7A input documents must not be rewritten by the product
implementation.

## TDD And Task Sequence

Each behavior slice follows RED, GREEN, REFACTOR. Do not write the product
condition before its focused assertion fails for the intended reason.

### Task 0: Freeze Entry State

Verify:

```bash
git rev-parse HEAD
git status --short
.quality/p5-runtime/bin/python -VV
.quality/p5-runtime/bin/python -c \
  'import sqlite3; print(sqlite3.sqlite_version)'
```

Acceptance:

- HEAD is the recorded baseline unless the user has intentionally changed it;
- only the five planning documents are untracked;
- no product or test delta predates Task 1;
- the runtime is Python 3.13.12 with SQLite 3.51.2.

Record the full-suite baseline and rerun any P6 process-order failures as an
isolated group. Do not modify P6 in this phase.

### Task 1: RED — Lock Stable Unique-Path Allocation

Add focused tests around `split_results_and_anchors` with an ordered population:

```text
A chunk 1
A chunk 2
B chunk 1
C chunk 1
B chunk 2
```

Test at least:

1. `final_top_k=2` returns A chunk 1 then B chunk 1;
2. the highest-ranked A chunk remains byte-for-byte unchanged;
3. a later A chunk cannot replace or merge with the winner;
4. exact path equality, not basename equality, defines duplicates;
5. fewer than `final_top_k` distinct paths returns the available distinct
   population without padding;
6. evidence anchors remain independent and do not consume ordinary slots;
7. ordinary non-traced execution does not allocate trace decision objects.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_retrieval_pipeline.py \
  -k 'split_results_and_anchors or evidence_anchors'
```

RED acceptance:

- the new duplicate-path membership assertion fails against the baseline;
- pre-existing anchor and allocation tests still pass;
- the failure is not an import, fixture, or runtime error.

### Task 2: RED — Lock Trace Accounting

Update focused RetrievalTrace expectations and add a duplicate-path case.

Test:

1. `duplicate_result_path` exists in the canonical position;
2. a selected item, a repeated ordinary path, an anchor duplicate, and a
   distinct path beyond the cap each reach the intended counter;
3. all counters sum to `input_count`;
4. the duplicate result is absent from `final_selections`;
5. serialization and human formatting accept the additive canonical key;
6. trace version remains v1.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_retrieval_trace_pipeline.py \
  -k 'final_selection'
```

RED acceptance:

- the new key/membership assertion fails because baseline selection does not
  classify result-path duplicates;
- the test does not demand a new trace schema or stage.

### Task 3: GREEN — Implement The Selection Rule

Change only `split_results_and_anchors` and the formatter's canonical trace-key
validation:

1. add `duplicate_result_path` to both canonical key tuples;
2. allocate `seen_result_paths` next to `seen_anchor_keys`;
3. classify a repeated ordinary path before result-limit selection;
4. preserve the existing anchor branch;
5. preserve the no-trace fast path: no `_FinalTraceInput`,
   `_FinalTraceDecisions`, or counter allocation when `collect_trace=False`;
6. do not add a helper unless the final function becomes less clear.

Run the Task 1 and Task 2 commands after each minimal code change.

GREEN acceptance:

- focused membership and trace tests pass;
- all existing selection tests pass;
- the diff contains no ranking, expansion, ContextPack, graph, or parser change.

### Task 4: Lock Public-Surface Propagation

Add or adapt a deterministic indexed micro-repository whose ranked expanded
population contains repeated chunks from one file and at least two lower-ranked
paths.

Through public functions or CLI adapters, verify:

1. query returns at most one ordinary result per path;
2. traced query returns the same QueryBundle membership as plain query;
3. ContextPack receives the newly available distinct paths without a new pack
   rule;
4. explore's initial bundle also contains unique ordinary result paths;
5. repeated runs return the same path order and public bytes.

The test may assert the path-uniqueness invariant rather than overfitting every
score. It must still construct the repository through the real index and query
pipeline; a test that only calls the unit seam does not satisfy this task.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_fusion.py
```

### Task 5: Regression And Quality Gates

Run the focused retrieval/trace/context/explore group first:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_retrieval_pipeline.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_context_pack.py \
  tests/test_exploration_runner.py \
  tests/test_exploration_fusion.py \
  tests/test_exploration_p7.py \
  tests/test_formatters.py
```

Run the protected P3.2 contract:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_retrieval_core_boundaries.py \
  tests/test_retrieval_core_characterization.py
```

Do not rewrite the immutable P3.2 baseline. Add a P7 overlay that proves:

- the reviewed production allowlist grows by exactly `selection.py` and
  `formatters.py`;
- all 13 legacy cases have exact, frozen P7 trace hashes;
- the four complete stage ledgers differ only by the zero-valued canonical
  `duplicate_result_path` entry;
- every non-trace public/internal hash remains identical to the immutable
  baseline.

Run the deterministic CI quality profile to a temporary artifact outside the
tracked evidence tree:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p7-final-quality.json \
  --markdown /tmp/cst-p7-final-quality.md
```

Run P6 protection:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q \
  tests/test_p6_paired.py \
  tests/test_p6_benchmark.py \
  tests/test_p6_measurement_worker.py
```

Run the full suite:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/src" \
.quality/p5-runtime/bin/python -m pytest -q -p no:cacheprovider
```

If the same P6 calibration/process-order failures seen at entry recur, rerun
their exact node IDs together in a fresh process. Acceptance requires:

- no new failing node ID;
- every P7-focused and protected retrieval test passes;
- every recurring entry failure passes in isolation;
- no failure may be dismissed without matching entry evidence.

### Task 6: Real-Repository Acceptance

Rebuild clean temporary snapshots from the pinned commits. Do not index or edit
the source working trees.

Public Python acceptance:

```text
query: same frozen probe query
top_k: 12
expected unique result paths: 12
required represented paths:
  src/core/pipeline.py
  data_provider/base.py
```

Also verify:

- `candidate_merge` and `context_expansion` populations remain non-empty;
- `duplicate_result_path` is positive in final-selection trace;
- ContextPack contains more than the baseline two paths;
- repeated query path order is identical.

These are mechanism acceptance checks, not new gold for every desired business
target. The resolver and prefetch test are diagnostic residuals.

Private Java acceptance records aggregates only:

- returned result count;
- unique result-path count;
- whether duplicate-result-path count is non-zero;
- whether the previously represented high-level chain remains represented.

No private path, query, source text, symbol, report, or raw trace enters a
tracked file.

### Task 7: Documentation And Final Audit

After all gates:

1. document the new selection behavior and additive trace counter;
2. record exact test and probe results in this plan's implementation record;
3. update the roadmap with the narrow P7 completion claim;
4. state explicitly that Python structural acquisition/ranking remains a
   follow-up candidate;
5. inspect `git diff --check`;
6. inspect every changed and untracked path;
7. verify preserved P7/P7A document hashes are unchanged from plan entry.

Do not stage, commit, push, or open a pull request unless the user asks.

## Acceptance Checklist

P7 Final is accepted only when:

1. ordinary result paths are unique at the final-selection boundary;
2. the first ranked chunk wins without merge or replacement;
3. exact path equality is the only duplicate rule;
4. anchors retain independent allocation;
5. limits and upstream rankings are unchanged;
6. `duplicate_result_path` accounts for repeated ordinary paths;
7. trace decision counts still sum exactly to stage input count;
8. RetrievalTrace remains v1 with no shape change;
9. query, traced query, context, and explore observe the central rule;
10. deterministic repeated calls preserve membership and order;
11. focused and protected tests pass;
12. the full suite has no new failure relative to entry;
13. the deterministic CI quality profile passes;
14. the public Python probe reaches 12 unique paths and represents both required
    files;
15. the sanitized Java probe retains its high-level chain;
16. P6 product code and benchmark policy are unchanged;
17. no private repository material is persisted;
18. the four historical P7/P7A documents remain present and unchanged;
19. documentation makes no fast-context parity or Python-AST completion claim;
20. the final diff contains only lines traceable to this plan.

## Stop And Follow-Up Rule

Stop P7 Final after the acceptance checklist is satisfied.

Do not add another mechanism merely because the public Python probe still lacks
some semantically desired paths. Use the residual trace to design a separate
phase whose question is:

```text
Are the remaining Python misses caused by missing structural acquisition,
or by ranking acquired structural/path-symbol candidates too low?
```

That follow-up may compare lightweight Python import/call relations, language
server data, query-term routing, or a file-level reranker. It requires its own
evidence and must not be smuggled into P7 Final.

## Implementation Record

Status: Accepted on 2026-07-26

```text
entry identity:
  74aae0abe3dff685282fbcc785f7a9b3532cbbe6
  Python 3.13.12
  SQLite 3.51.2

RED tests:
  ordinary result allocation failed because the second chunk from path A
  consumed slot 2 instead of the first chunk from path B
  trace final-selection keys failed because duplicate_result_path was absent

changed product files:
  src/context_search_tool/retrieval_core/selection.py
  src/context_search_tool/formatters.py

focused tests, post-review working tree:
  retrieval + trace: 266 passed
  ContextPack + formatters: 156 passed
  exploration runner + fusion: 39 passed
  P7 public-surface integration: 1 passed
  combined focused group: 462 passed
  retrieval-core boundary + characterization: 26 passed

quality profile, post-review working tree:
  ci selected/executed/passed: 8/8/8
  failed/errors: 0/0

P6 protection:
  clean acceptance commit: 81 passed
  post-review working tree:
    earlier sequential run: 80 passed, 1 failed
    failing node:
      tests/test_p6_measurement_worker.py::test_final_resident_benchmark_reuses_one_session
    entry-baseline match: none
    exact-node rerun: 1 passed
    final idle full-group rerun: 81 passed, 16 warnings

full suite:
  clean acceptance commit, second complete run:
    2899 passed, 9 skipped, 0 failed in 59.99s
  first complete run:
    2898 passed, 9 skipped, one pre-existing P6 checkpoint calibration
    instability; the exact node passed 1/1 in an immediate clean process
  post-review working-tree revalidation:
    2900 passed, 9 skipped, 0 failed, 16 warnings

public Python probe:
  pinned commit: 487e49e565ffd1b96a7cf4d855f99cee3c981eaa
  results / unique paths: 12 / 12 (baseline: 12 / 2)
  required paths: src/core/pipeline.py and data_provider/base.py present
  final decisions: selected=12, duplicate_result_path=76, result_limit=47
  ContextPack items / unique paths: 12 / 12
  explore: complete, initial_satisfied, 12 initial and 12 fused results
  two repeated path lists were byte-identical

sanitized Java probe:
  results / unique paths: 12 / 12
  final decisions: selected=12, duplicate_result_path=58, result_limit=253
  the first-ranked representative for every previously selected path is
  preserved by construction; no private path, query, or raw report is tracked

historical document hash check:
  preserved P7 spec:
    04bc5c52179cf63e29a7a6145e43416ab6e21d61de5e2bc2528b62ac12ca64e8
  preserved P7 plan:
    06f80aeda5c70afe315d1b30d2bf88b910b28c340f1fc252cc7d889c18b8c4a2
  reviewed P7A spec:
    32377b361272522af7542927c9750f2ed9badd30032b1457c40b1b66d327ba2d
  reviewed P7A plan:
    73365cdac7da2ea0a86cd71c789ba0369bcb2cea07765dba4c72ef0cdb00ab02

final diff audit:
  whitespace checks passed for tracked and untracked P7 files
  changed product scope is exactly selection.py and formatters.py
  private Java path, query, symbols, source, and raw output are absent
  the four historical P7/P7A document hashes remain exact

residual limitations:
  path diversity does not recover candidates that acquisition never found or
  that ranking places below the available distinct-path population
  Python structural acquisition/ranking remains a separate experiment
  no fast-context parity claim is made
```
